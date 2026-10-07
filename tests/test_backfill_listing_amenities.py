"""Verify amenity-only backfills preserve listings and resume provider outcomes."""

from pathlib import Path
import sqlite3
import json
from types import SimpleNamespace

import pytest
import requests

from scripts.backfill_listing_amenities import backfill_amenities, fetch_amenities


def test_backfill_preserves_other_fields_and_resumes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only amenity fields change while cached outcomes avoid repeat requests.

    Omitted dishwasher data must remain NULL across both market tables.

    Args:
        tmp_path: Directory containing isolated listing and checkpoint databases.
        monkeypatch: Fixture replacing network lookups.

    Returns:
        None.
    """
    db = tmp_path / 'listings.db'
    checkpoint = tmp_path / 'amenities.db'
    with sqlite3.connect(db) as conn:
        for market in ('buy', 'lease'):
            conn.execute(f'CREATE TABLE {market} (mls_number TEXT, listing_url TEXT, list_price INTEGER, mls_photo TEXT)')
            conn.execute(f"INSERT INTO {market} VALUES ('MLS-1', 'https://example.test', 1234, 'original-photo')")
    calls = []
    monkeypatch.setattr('scripts.backfill_listing_amenities.fetch_amenities', lambda *args: calls.append(args) or {'has_ac': 'Yes', 'has_dishwasher': None})
    summary = backfill_amenities(db, checkpoint)
    assert summary['processed'] == 2
    assert summary['failed'] == 0
    assert backfill_amenities(db, checkpoint)['cached'] == 2
    assert len(calls) == 2
    with sqlite3.connect(db) as conn:
        for market in ('buy', 'lease'):
            assert conn.execute(f'SELECT list_price, mls_photo, has_ac, has_dishwasher FROM {market}').fetchone() == (1234, 'original-photo', 'Yes', None)


def test_failed_requests_are_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Network failures remain pending instead of becoming cached unknowns.

    A later successful run fills the same rows without replacing listing data.

    Args:
        tmp_path: Directory containing isolated listing and checkpoint databases.
        monkeypatch: Fixture replacing network lookups.

    Returns:
        None.
    """
    db = tmp_path / 'listings.db'
    checkpoint = tmp_path / 'amenities.db'
    with sqlite3.connect(db) as conn:
        for market in ('buy', 'lease'):
            conn.execute(f'CREATE TABLE {market} (mls_number TEXT, listing_url TEXT)')
            conn.execute(f"INSERT INTO {market} VALUES ('MLS-1', '')")

    def fail(*args: object) -> dict[str, str | None]:
        """Simulate an unavailable transport without successful provider data.

        Args:
            args: Listing identifiers passed by the backfill.

        Returns:
            No statuses because the transport raises first.
        """
        raise requests.ConnectionError('offline')

    monkeypatch.setattr('scripts.backfill_listing_amenities.fetch_amenities', fail)
    assert backfill_amenities(db, checkpoint)['failed'] == 2
    monkeypatch.setattr('scripts.backfill_listing_amenities.fetch_amenities', lambda *args: {'has_ac': 'No', 'has_dishwasher': 'Yes'})
    summary = backfill_amenities(db, checkpoint)
    assert summary['processed'] == 2
    assert summary['cached'] == 0
    assert summary['failed'] == 0


@pytest.mark.parametrize("encoded", [False, True])
def test_fetch_decodes_provider_content_negotiation(monkeypatch: pytest.MonkeyPatch, encoded: bool) -> None:
    """Accept ordinary and double-encoded provider detail objects.

    Some Accept headers cause this API to wrap a JSON object in a JSON string.

    Args:
        monkeypatch: Fixture replacing the provider GET.
        encoded: Whether the fake response wraps its object in a JSON string.

    Returns:
        None.
    """
    payload = {"AddtionalPropertyInfo": {"Item": [{"Label": "Cooling", "Value": "Central"}]}}
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: json.dumps(payload) if encoded else payload)
    monkeypatch.setattr("scripts.backfill_listing_amenities.get_with_backoff", lambda *args, **kwargs: response)
    assert fetch_amenities("MLS-1", None) == {"has_ac": "Yes", "has_dishwasher": None}
