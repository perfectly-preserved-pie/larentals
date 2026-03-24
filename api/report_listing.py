import sqlite3
from typing import Any

import bleach
from flask import Response, abort, jsonify, request
from loguru import logger

ALLOWED_OPTIONS = {
    "Wrong Location",
    "Unavailable/Sold/Rented",
    "Wrong Details",
    "Incorrect Price",
    "Other",
}


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

    @server.route("/report_listing", methods=["POST"])
    def report_listing() -> tuple[Response, int]:
        data = request.get_json()
        mls_number: str = data.get("mls_number")
        option: str = data.get("option")
        text_report: str = data.get("text")
        page_path: str = (data.get("page_path") or "").lower()

        if option not in ALLOWED_OPTIONS:
            abort(400, "Invalid option provided.")

        sanitized_text = bleach.clean(text_report, tags=[], attributes={}, strip=True)
        logger.info(
            f"Received report for MLS {mls_number}: "
            f"Option='{option}', Details='{sanitized_text}'"
        )

        try:
            if page_path.startswith("/buy"):
                table_name = "buy"
            elif page_path == "" or page_path == "/":
                table_name = "lease"
            else:
                abort(400, f"Invalid page context: {page_path}")

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()

            cur.execute(f"PRAGMA table_info({table_name});")
            cols = [r[1] for r in cur.fetchall()]
            if "report_option" not in cols:
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN report_option TEXT;")
            if "report_text" not in cols:
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN report_text TEXT;")

            if option == "Unavailable/Sold/Rented":
                cur.execute(
                    f"UPDATE {table_name} SET reported_as_inactive = 1 WHERE mls_number = ?",
                    (mls_number,),
                )
                logger.success(
                    f"Marked MLS {mls_number} as inactive in '{table_name}' table."
                )
            else:
                cur.execute(
                    f"""UPDATE {table_name}
                      SET report_option = ?, report_text = ?
                      WHERE mls_number = ?""",
                    (option, sanitized_text, mls_number),
                )
                logger.success(
                    f"Saved user-submitted report for MLS {mls_number}: "
                    f"option={option}, text='{sanitized_text}'"
                )

            conn.commit()
            conn.close()
            return jsonify(status="success"), 200

        except Exception as exc:
            logger.error(f"Error handling report for MLS {mls_number}: {exc}")
            return (
                jsonify(
                    status="error",
                    message="Internal error, please try again later.",
                ),
                500,
            )
