"""Tests for guarded ImageKit-to-listing reconciliation."""

from pathlib import Path
import json
import sqlite3

import pytest

from scripts.reconcile_imagekit_assets import (
    DeletionGuardExceeded,
    _reconcile_database,
    reconcile,
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


def test_guard_writes_audit_without_deleting_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep an over-limit cleanup reviewable without changing remote assets.

    The guarded exit leaves a manifest that bootstrap can preserve after publishing the database.

    Args:
        tmp_path: Pytest-managed temporary directory.
        monkeypatch: Replaces the remote ImageKit client with a fixed asset list.

    Returns:
        None.
    """
    database = tmp_path / "listings.db"
    _create_listing_database(database)
    assets = [
        {"fileId": str(index), "filePath": path, "size": 10}
        for index, path in enumerate(("/listings/buy/A", "/D", "/E", "/orphan"))
    ]

    class FakeClient:
        """Expose current files and fail if guarded cleanup attempts deletion."""

        def __init__(self, private_key: str) -> None:
            self.private_key = private_key

        def list_assets(self, asset_type: str) -> list[dict]:
            assert asset_type == "file"
            return assets

        def delete_files(self, file_ids: object) -> int:
            raise AssertionError("guarded cleanup must not delete files")

    monkeypatch.setattr("scripts.reconcile_imagekit_assets.ImageKitMediaClient", FakeClient)
    audit_dir = tmp_path / "audit"
    options = dict(
        db_path=database,
        audit_dir=audit_dir,
        private_key="test",
        url_endpoint="https://ik.imagekit.io/account",
        force=False,
        max_delete_fraction=0.10,
        min_active_references=1,
    )

    with pytest.raises(DeletionGuardExceeded, match="25.0%"):
        reconcile(**options, apply=True)

    summary = json.loads((audit_dir / "summary.json").read_text())
    assert summary["status"] == "review_required"
    assert summary["current_assets_to_delete"] == 1
    assert "/orphan" in (audit_dir / "delete_current.csv").read_text()
    assert reconcile(**options, apply=False)["status"] == "review_required"
