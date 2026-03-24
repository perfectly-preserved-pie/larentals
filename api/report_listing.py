import sqlite3
from typing import Any

import bleach
from flask import Response, abort, jsonify, request
from functions.listing_report_utils import (
    ensure_listing_reports_schema,
    infer_listing_type_from_page_path,
    insert_listing_report,
    normalize_mls_number,
)
from loguru import logger
from werkzeug.exceptions import HTTPException

ALLOWED_OPTIONS = {
    "Wrong Location",
    "Unavailable/Sold/Rented",
    "Wrong Details",
    "Incorrect Price",
    "Other",
}
MAX_MLS_NUMBER_LENGTH = 64
MAX_REPORT_TEXT_LENGTH = 2000


def register_report_listing_routes(
    server: Any,
    db_path: str = "assets/datasets/larentals.db",
) -> None:
    """
    Register the user-facing listing report endpoint.

    Args:
        server: The Flask server instance (typically `app.server` in Dash).
        db_path: Path to the SQLite database file.
    """
    with sqlite3.connect(db_path) as conn:
        ensure_listing_reports_schema(conn)
        conn.commit()

    @server.route("/report_listing", methods=["POST"])
    def report_listing() -> tuple[Response, int]:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400, "Expected a JSON object body.")

        mls_number = normalize_mls_number(data.get("mls_number") or "")
        option = data.get("option")
        text_report = data.get("text")
        page_path = str(data.get("page_path") or "").strip().lower()

        if option not in ALLOWED_OPTIONS:
            abort(400, "Invalid option provided.")
        if not mls_number or len(mls_number) > MAX_MLS_NUMBER_LENGTH:
            abort(400, "Invalid MLS number provided.")

        listing_type = infer_listing_type_from_page_path(page_path)

        sanitized_text = bleach.clean(
            str(text_report or ""),
            tags=[],
            attributes={},
            strip=True,
        ).strip()
        if len(sanitized_text) > MAX_REPORT_TEXT_LENGTH:
            abort(400, "Report text is too long.")

        normalized_page_path = page_path or "/"
        logger.info(
            f"Received report for MLS {mls_number}: "
            f"Option='{option}', Details='{sanitized_text}'"
        )

        try:
            with sqlite3.connect(db_path) as conn:
                insert_listing_report(
                    conn,
                    listing_type=listing_type,
                    mls_number=mls_number,
                    option=option,
                    text_report=sanitized_text or None,
                    page_path=normalized_page_path,
                )
                conn.commit()

            logger.success(
                f"Saved append-only report for MLS {mls_number}: "
                f"listing_type={listing_type}, option={option}"
            )
            return jsonify(status="success"), 200

        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Error handling report for MLS {mls_number}: {exc}")
            return (
                jsonify(
                    status="error",
                    message="Internal error, please try again later.",
                ),
                500,
            )
