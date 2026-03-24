import sqlite3
from typing import Any

from flask import Blueprint, Response, abort, jsonify

LEASE_LISTING_DETAIL_SQL = """
  SELECT
    mls_number,
    subtype,
    list_price,
    bedrooms,
    total_bathrooms,
    sqft,
    ppsqft,
    year_built,
    parking_spaces,
    pet_policy,
    terms,
    furnished,
    phone_number,
    security_deposit,
    pet_deposit,
    key_deposit,
    other_deposit,
    full_street_address,
    listed_date,
    listing_url,
    mls_photo,
    COALESCE(laundry_category, 'Unknown') AS laundry
  FROM lease
  WHERE mls_number = ?
  LIMIT 1
"""

BUY_LISTING_DETAIL_SQL = """
  SELECT
    mls_number,
    subtype,
    list_price,
    bedrooms,
    total_bathrooms,
    sqft,
    ppsqft,
    year_built,
    lot_size,
    garage_spaces,
    hoa_fee,
    hoa_fee_frequency,
    full_street_address,
    listed_date,
    listing_url,
    mls_photo
  FROM buy
  WHERE mls_number = ?
  LIMIT 1
"""


def build_listing_detail_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """
    Convert a single SQLite row into the popup-detail JSON payload.

    Args:
        row: SQLite row returned from a page-specific listing detail query.

    Returns:
        Serializable detail payload, or `None` when the listing was not found.
    """
    if row is None:
        return None

    return {key: row[key] for key in row.keys()}


def register_listing_routes(server: Any, db_path: str = "assets/datasets/larentals.db") -> None:
    """
    Register on-demand listing-detail routes used by lazy-loaded popups.

    Args:
        server: The Flask server instance (typically `app.server` in Dash).
        db_path: Path to the SQLite database file.
    """
    bp = Blueprint("listing_api", __name__)

    @bp.get("/api/lease/listing-details/<listing_id>")
    def get_lease_listing_details(listing_id: str) -> Response:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(LEASE_LISTING_DETAIL_SQL, (listing_id,)).fetchone()

        payload = build_listing_detail_payload(row)
        if payload is None:
            abort(404, f"Lease listing not found: {listing_id}")
        return jsonify(payload)

    @bp.get("/api/buy/listing-details/<listing_id>")
    def get_buy_listing_details(listing_id: str) -> Response:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(BUY_LISTING_DETAIL_SQL, (listing_id,)).fetchone()

        payload = build_listing_detail_payload(row)
        if payload is None:
            abort(404, f"Buy listing not found: {listing_id}")
        return jsonify(payload)

    server.register_blueprint(bp)
