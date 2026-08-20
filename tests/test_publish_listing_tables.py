import sqlite3
from pathlib import Path

import pytest

from scripts.publish_listing_tables import publish_listing_tables


def _create_table(db_path: Path, table_name: str, rows: list[tuple[str, int]]) -> None:
    """Handle create table.

    Args:
        db_path: Filesystem path to the SQLite database.
        table_name: SQLite table to inspect or modify.
        rows: Records to write, summarize, or display.

    Returns:
        None.
    """
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f'CREATE TABLE "{table_name}" (mls_number TEXT, list_price INTEGER)'
        )
        connection.executemany(
            f'INSERT INTO "{table_name}" VALUES (?, ?)',
            rows,
        )


def test_publish_replaces_both_listing_tables_and_preserves_other_tables(
    tmp_path: Path,
) -> None:
    """Verify that publish replaces both listing tables and preserves other tables.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    destination = tmp_path / "larentals.db"
    buy_stage = tmp_path / "buy-stage.db"
    lease_stage = tmp_path / "lease-stage.db"
    _create_table(destination, "buy", [("old-buy", 1)])
    _create_table(destination, "lease", [("old-lease", 2)])
    with sqlite3.connect(destination) as connection:
        connection.execute("CREATE TABLE listing_reports (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO listing_reports VALUES (1)")
    _create_table(buy_stage, "buy", [("new-buy", 100)])
    _create_table(lease_stage, "lease", [("new-lease", 200)])

    publish_listing_tables(
        db_path=destination,
        buy_stage_path=buy_stage,
        lease_stage_path=lease_stage,
    )

    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT * FROM buy").fetchall() == [("new-buy", 100)]
        assert connection.execute("SELECT * FROM lease").fetchall() == [("new-lease", 200)]
        assert connection.execute("SELECT * FROM listing_reports").fetchall() == [(1,)]


def test_publish_does_not_change_destination_when_a_stage_is_invalid(
    tmp_path: Path,
) -> None:
    """Verify that publish does not change destination when a stage is invalid.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    destination = tmp_path / "larentals.db"
    buy_stage = tmp_path / "buy-stage.db"
    missing_lease_stage = tmp_path / "missing-lease-stage.db"
    _create_table(destination, "buy", [("old-buy", 1)])
    _create_table(destination, "lease", [("old-lease", 2)])
    _create_table(buy_stage, "buy", [("new-buy", 100)])

    with pytest.raises(FileNotFoundError):
        publish_listing_tables(
            db_path=destination,
            buy_stage_path=buy_stage,
            lease_stage_path=missing_lease_stage,
        )

    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT * FROM buy").fetchall() == [("old-buy", 1)]
        assert connection.execute("SELECT * FROM lease").fetchall() == [("old-lease", 2)]
