from __future__ import annotations

from typing import Optional
import sqlite3

INACTIVE_REPORT_OPTION = "Unavailable/Sold/Rented"
REPORT_TABLE_NAME = "listing_reports"
VALID_LISTING_TYPES = {"lease", "buy"}

_CREATE_LISTING_REPORTS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {REPORT_TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_type TEXT NOT NULL CHECK (listing_type IN ('lease', 'buy')),
    mls_number TEXT NOT NULL,
    report_option TEXT NOT NULL,
    report_text TEXT,
    page_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_LISTING_REPORTS_LOOKUP_INDEX_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_{REPORT_TABLE_NAME}_lookup
ON {REPORT_TABLE_NAME} (listing_type, report_option, mls_number)
"""


def infer_listing_type_from_page_path(page_path: str) -> str:
    """
    Infer the listing type from the current browser path.

    Args:
        page_path: Browser pathname submitted by the popup UI.

    Returns:
        "lease" or "buy".

    Raises:
        ValueError: If the path does not map to a supported listing type.
    """
    normalized = (page_path or "").strip().lower()
    if normalized.startswith("/buy"):
        return "buy"
    if normalized in {"", "/"}:
        return "lease"
    raise ValueError(f"Invalid page context: {page_path}")


def normalize_mls_number(value: object) -> str:
    """
    Normalize an MLS number into a trimmed string without a trailing `.0`.
    """
    normalized = str(value).strip()
    if normalized.endswith(".0"):
        normalized = normalized[:-2]
    return normalized


def ensure_listing_reports_schema(conn: sqlite3.Connection) -> None:
    """
    Create the append-only listing reports table and lookup index if needed.
    """
    conn.execute(_CREATE_LISTING_REPORTS_TABLE_SQL)
    conn.execute(_CREATE_LISTING_REPORTS_LOOKUP_INDEX_SQL)


def insert_listing_report(
    conn: sqlite3.Connection,
    *,
    listing_type: str,
    mls_number: str,
    option: str,
    text_report: Optional[str],
    page_path: str,
) -> None:
    """
    Insert a single user-submitted listing report.

    Args:
        conn: Open SQLite connection.
        listing_type: "lease" or "buy".
        mls_number: Listing identifier.
        option: User-selected report category.
        text_report: Optional free-form explanation.
        page_path: Browser pathname supplied by the client.
    """
    if listing_type not in VALID_LISTING_TYPES:
        raise ValueError(f"Invalid listing_type: {listing_type}")

    normalized_mls_number = normalize_mls_number(mls_number)
    ensure_listing_reports_schema(conn)
    conn.execute(
        f"""
        INSERT INTO {REPORT_TABLE_NAME} (
            listing_type,
            mls_number,
            report_option,
            report_text,
            page_path
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (listing_type, normalized_mls_number, option, text_report, page_path),
    )


def get_reported_inactive_mls_numbers(
    conn: sqlite3.Connection,
    *,
    listing_type: str,
) -> set[str]:
    """
    Return MLS numbers that users have reported as inactive for a listing type.

    Args:
        conn: Open SQLite connection.
        listing_type: "lease" or "buy".

    Returns:
        Set of MLS numbers flagged with the inactive report option.
    """
    if listing_type not in VALID_LISTING_TYPES:
        raise ValueError(f"Invalid listing_type: {listing_type}")

    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (REPORT_TABLE_NAME,),
    ).fetchone()
    if row is None:
        return set()

    rows = conn.execute(
        f"""
        SELECT DISTINCT mls_number
        FROM {REPORT_TABLE_NAME}
        WHERE listing_type = ?
          AND report_option = ?
          AND TRIM(COALESCE(mls_number, '')) != ''
        """,
        (listing_type, INACTIVE_REPORT_OPTION),
    ).fetchall()
    return {normalize_mls_number(row[0]) for row in rows if row[0] is not None}
