from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
from typing import Optional
import sqlite3

def get_earliest_listed_date(
    db_path: str | Path,
    *,
    table_name: str = "lease",
    date_column: str = "listed_date",
) -> Optional[str]:
    """
    Fetch the earliest non-null listed date from a SQLite table.

    This is intended for seeding Dash date pickers. It returns a string in
    "YYYY-MM-DD" format, or None if no valid dates exist.

    Args:
        db_path: Path to the SQLite database file.
        table_name: Table to query (e.g., "lease" or "buy").
        date_column: Column containing the listed date.

    Returns:
        The earliest date as "YYYY-MM-DD", or None if not found.

    Raises:
        sqlite3.OperationalError: If the table/column does not exist.
    """
    sql = f"""
    SELECT MIN(DATE({date_column}))
    FROM {table_name}
    WHERE {date_column} IS NOT NULL
      AND TRIM(CAST({date_column} AS TEXT)) != ''
    """

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(sql).fetchone()

    if not row or row[0] is None:
        return None

    # SQLite DATE(...) returns "YYYY-MM-DD" (text) when it can parse the input.
    value = row[0]

    if isinstance(value, str):
        return value

    # Defensive fallback if something odd comes back
    if isinstance(value, (date, datetime)):
        return value.date().isoformat()

    return str(value)

def get_latest_date_processed(
    db_path: str | Path,
    *,
    table_name: str = "lease",
    date_column: str = "date_processed",
) -> Optional[str]:
    """
    Fetch the latest non-null date_processed from a SQLite table.

    This is intended for display purposes. It returns a string in
    "MM/DD/YYYY" format, or None if no valid dates exist.

    Args:
        db_path: Path to the SQLite database file.
        table_name: Table to query (e.g., "lease" or "buy").
        date_column: Column containing the date_processed.

    Returns:
        The latest date as "MM/DD/YYYY", or None if not found.

    Raises:
        sqlite3.OperationalError: If the table/column does not exist.
    """
    sql = f"""
    SELECT MAX(DATE({date_column}))
    FROM {table_name}
    WHERE {date_column} IS NOT NULL
      AND TRIM(CAST({date_column} AS TEXT)) != ''
    """

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(sql).fetchone()

    if not row or row[0] is None:
        return None

    value = row[0]

    if isinstance(value, str):
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
            return dt.strftime("%m/%d/%Y")
        except ValueError:
            return value  # Return as-is if format is unexpected

    if isinstance(value, (date, datetime)):
        return value.strftime("%m/%d/%Y")

    return str(value)
