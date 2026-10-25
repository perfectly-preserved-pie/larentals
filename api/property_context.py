"""Listing-scoped access to official property records and mapped hazards."""

import sqlite3
from typing import Any

from flask import Blueprint, Response, abort, jsonify

from functions.data_paths import LARENTALS_DB_PATH
from functions.property_context import get_property_context


def register_property_context_routes(server: Any, db_path: str = str(LARENTALS_DB_PATH)) -> None:
    """Register property lookups separately from the fast listing detail routes.

    Resolve address and coordinates from the stored listing, never client input.
    Only known listing tables may be queried; missing homes retain the same 404
    behavior as the listing detail API.
    """
    bp = Blueprint("property_context_api", __name__)

    @bp.get("/api/<market>/property-context/<listing_id>")
    def property_context(market: str, listing_id: str) -> Response:
        """Fetch agency records for a stored buy or rental listing.

        Legacy tables may lack ZIP codes, so the address matcher can still
        require a unique city parcel while hazard queries use the stored point.
        """
        if market not in {"buy", "lease"}:
            abort(404)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({market})")}
            if not columns:
                abort(404)
            selected = [field for field in ("full_street_address", "zip_code", "city", "latitude", "longitude") if field in columns]
            if not selected:
                abort(404)
            row = conn.execute(f"SELECT {', '.join(selected)} FROM {market} WHERE mls_number = ? LIMIT 1", (listing_id,)).fetchone()
        if row is None:
            abort(404)
        response = jsonify(get_property_context(dict(row)))
        # Browser caching is owned by the records UI; failed agency sections can
        # be retried without a CDN retaining an incomplete snapshot.
        response.headers["Cache-Control"] = "no-store"
        return response

    server.register_blueprint(bp)
