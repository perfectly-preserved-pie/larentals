"""Tests for guarded ImageKit-to-listing reconciliation."""

from pathlib import Path
import sqlite3

from scripts.reconcile_imagekit_assets import (
    _reconcile_database,
    load_database_photo_state,
)


def _create_listing_database(path: Path) -> None:
    """Create minimal buy and lease tables used by reconciliation tests.

    The fixture includes only the listing fields needed to decide whether ImageKit URLs are still referenced.

    Args:
        path: Temporary SQLite database destination.

    Returns:
        None.
    """
    with sqlite3.connect(path) as connection:
        for table_name in ("buy", "lease"):
            connection.execute(
                f"""
                CREATE TABLE {table_name} (
                    mls_number TEXT PRIMARY KEY,
                    mls_photo TEXT,
                    image_status TEXT,
                    reported_as_inactive INTEGER
                )
                """
            )
        connection.executemany(
            "INSERT INTO buy VALUES (?, ?, ?, ?)",
            (
                (
                    "A",
                    "https://ik.imagekit.io/account/listings/buy/A?tr=w-400",
                    "success",
                    0,
                ),
                ("B", "None", "not_found", 0),
                ("C", "https://ik.imagekit.io/account/C", "success", 1),
            ),
        )
        connection.executemany(
            "INSERT INTO lease VALUES (?, ?, ?, ?)",
            (
                ("D", "https://ik.imagekit.io/account/D", "success", 0),
                ("E", "https://ik.imagekit.io/account/E", "success", 0),
            ),
        )


def test_load_database_photo_state_excludes_inactive_and_placeholders(
    tmp_path: Path,
) -> None:
    """Build an exact allowlist from usable photo URLs on unflagged rows.

    Only active rows with usable photos may keep an asset in the allowlist.

    Args:
        tmp_path: Pytest-managed temporary directory.

    Returns:
        None.
    """
    database = tmp_path / "listings.db"
    _create_listing_database(database)

    state = load_database_photo_state(database, endpoint_prefix="/account")

    assert state.active_rows == 4
    assert state.inactive_rows == 1
    assert state.active_paths == frozenset({"/listings/buy/A", "/D", "/E"})


def test_reconcile_database_clears_inactive_missing_and_placeholder_urls(
    tmp_path: Path,
) -> None:
    """Repair database references after the ImageKit deletion is verified.

    Stale database URLs are cleared only after the corresponding remote deletion has succeeded.

    Args:
        tmp_path: Pytest-managed temporary directory.

    Returns:
        None.
    """
    database = tmp_path / "listings.db"
    _create_listing_database(database)

    result = _reconcile_database(
        database,
        live_paths={"/listings/buy/A", "/D"},
        endpoint_prefix="/account",
    )

    assert result["buy"] == {
        "inactive_rows_cleared": 1,
        "placeholder_urls_cleared": 1,
        "missing_active_urls_cleared": 0,
    }
    assert result["lease"]["missing_active_urls_cleared"] == 1
    with sqlite3.connect(database) as connection:
        rows = dict(
            connection.execute(
                "SELECT mls_number, image_status FROM lease ORDER BY mls_number"
            )
        )
        missing_photo = connection.execute(
            "SELECT mls_photo FROM lease WHERE mls_number = 'E'"
        ).fetchone()
    assert rows == {"D": "success", "E": "failed"}
    assert missing_photo == (None,)
