"""Exercise subtype recovery using recorded API shapes and request counts."""

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

from functions import dataframe_utils as frames
from functions import webscraping_utils as scraping
from functions.listing_pipeline_checkpoint import ListingCheckpointStore
from scripts import backfill_listing_subtypes as backfill


SAMPLES = json.loads((Path(__file__).parent / "fixtures/agency_subtypes_sample.json").read_text())


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda sample: sample["mls_number"])
def test_recorded_agency_subtypes(monkeypatch, sample):
    """Replay the live sample through the pipeline's actual detail reader.

    A missing provider record must stay unknown instead of becoming a URL guess.
    """
    response = Mock()
    response.json.return_value = sample["payload"]
    if sample["http_status"] == 404:
        response.raise_for_status.side_effect = requests.HTTPError(response=SimpleNamespace(status_code=404))
    monkeypatch.setattr(scraping, "get_with_backoff", Mock(return_value=response))
    assert scraping.fetch_the_agency_data(sample["mls_number"], 0, 1)[3] == sample["expected_subtype"]


@pytest.mark.parametrize("market", ["buy", "lease"])
@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("provider_type", ["Condominium", "Residential"])
def test_expiration_backfills_without_another_request(tmp_path, monkeypatch, market, encoded, provider_type):
    """Expiration, subtype recovery, and resume share one HTTP response.

    Successful responses with no home type are also checkpointed, so the
    subtype-only pass cannot repeat a completed expiration request.
    """
    payload = {"Status": "Active", "PropertyType": provider_type}
    response = SimpleNamespace(
        status_code=200, raise_for_status=lambda: None,
        json=lambda: json.dumps(payload) if encoded else payload,
    )
    get = Mock(return_value=response)
    monkeypatch.setattr(scraping, "get_with_backoff", get)
    store = ListingCheckpointStore(tmp_path / "checkpoint.sqlite", listing_type=market)
    source = pd.DataFrame([{
        "mls_number": "OLD-1", "subtype": "Unknown", "list_price": 100,
        "listing_url": "https://www.theagencyre.com/condominium/crmls/OLD-1/address",
    }])
    expected = "Condominium" if provider_type == "Condominium" else "Unknown"
    for _ in range(2):
        kept = frames.remove_inactive_listings(source.copy(), market, checkpoint_store=store)
        enriched = frames.update_missing_listing_subtypes(kept, checkpoint_store=store)
        assert enriched.at[0, "subtype"] == expected
        assert enriched.at[0, "list_price"] == 100
    assert get.call_count == 1
    assert "/detail/crmls/OLD-1" in get.call_args.args[0]


def test_remaining_unknowns_retry_failures_and_reuse_outcomes(tmp_path, monkeypatch):
    """A legacy cached expiration check still permits a missing subtype lookup.

    Only failed attempts are retried; absent types and unavailable records stay
    cached, and known source subtypes are never requested or overwritten.
    """
    store = ListingCheckpointStore(tmp_path / "checkpoint.sqlite", listing_type="buy")
    source = pd.DataFrame([
        {"mls_number": mls, "subtype": subtype, "listing_url": ""}
        for mls, subtype in [("KNOWN", "Loft"), ("FOUND", "Unknown"), ("MISSING", None), ("GONE", "Unknown"), ("RETRY", "Unknown")]
    ])
    fetch = Mock(side_effect=[
        {"PropertyType": "Single Family"}, {},
        requests.HTTPError(response=SimpleNamespace(status_code=404)),
        requests.ConnectionError("offline"),
        {"PropertyType": "Townhouse"},
    ])
    monkeypatch.setattr(frames, "fetch_agency_detail", fetch)
    first = frames.update_missing_listing_subtypes(source.copy(), checkpoint_store=store)
    second = frames.update_missing_listing_subtypes(source.copy(), checkpoint_store=store)
    third = frames.update_missing_listing_subtypes(source.copy(), checkpoint_store=store)
    assert fetch.call_count == 5
    assert first.at[4, "subtype"] == "Unknown"
    assert second.at[0, "subtype"] == "Loft"
    assert second.at[1, "subtype"] == "Single Family Residence"
    assert second.at[4, "subtype"] == third.at[4, "subtype"] == "Townhouse"
    assert store.get("MISSING")["subtype_lookup_status"] == "not_found"
    assert store.get("GONE")["subtype_lookup_status"] == "unavailable"


def test_missing_expiration_records_do_not_repeat_detail_lookup(tmp_path, monkeypatch):
    """Two HTTP 404 status checks also complete the subtype lookup.

    Missing provider records do not prove expiration, so keep the listing while
    avoiding a third request to the same active detail endpoint.
    """
    monkeypatch.delenv("RENTCAST_API_KEY", raising=False)
    get = Mock(return_value=SimpleNamespace(status_code=404))
    monkeypatch.setattr(scraping, "get_with_backoff", get)
    store = ListingCheckpointStore(tmp_path / "checkpoint.sqlite", listing_type="buy")
    source = pd.DataFrame([{"mls_number": "GONE", "subtype": "Unknown", "listing_url": ""}])
    kept = frames.remove_inactive_listings(source, "buy", checkpoint_store=store)
    enriched = frames.update_missing_listing_subtypes(kept, checkpoint_store=store)
    assert enriched.at[0, "subtype"] == "Unknown"
    assert get.call_count == 2
    assert store.get("GONE")["subtype_lookup_status"] == "unavailable"


def test_host_circuit_stops_remaining_subtype_requests(tmp_path, monkeypatch):
    """An open provider circuit leaves remaining listings pending for resume.

    It must not create terminal missing-type checkpoints for unattempted rows.
    """
    store = ListingCheckpointStore(tmp_path / "checkpoint.sqlite", listing_type="lease")
    fetch = Mock(side_effect=scraping.HostCircuitOpen("paused"))
    monkeypatch.setattr(frames, "fetch_agency_detail", fetch)
    source = pd.DataFrame([{"mls_number": mls, "subtype": "Unknown"} for mls in ("A", "B")])
    pd.testing.assert_frame_equal(
        frames.update_missing_listing_subtypes(source.copy(), checkpoint_store=store),
        source, check_dtype=False,
    )
    assert fetch.call_count == 1
    assert store.get("A") is None
    assert store.get("B") is None


@pytest.mark.parametrize("incoming, stored, expected", [
    ("Unknown", "Condominium", "Condominium"),
    (None, "Loft", "Loft"),
    ("Apartment", "Condominium", "Apartment"),
    ("Unknown", "Unknown", "Unknown"),
])
def test_refresh_preserves_backfilled_subtypes(incoming, stored, expected):
    """An incomplete source refresh cannot undo a recovered stored home type.

    Explicit incoming types still take priority over previously saved types.
    """
    merged = frames.merge_listing_dataframes(
        pd.DataFrame([{"mls_number": "MLS-1", "subtype": incoming}]),
        pd.DataFrame([{"mls_number": "MLS-1", "subtype": stored}]),
    )
    assert merged.at[0, "subtype"] == expected


def test_standalone_backfill_limits_resumes_and_preserves_fields(tmp_path, monkeypatch):
    """Subtype-only runs skip known types and preserve unrelated listing data.

    Resetting a filled row simulates a crash before the database update, which
    must replay the saved lookup without another HTTP request.
    """
    db_path, checkpoint_path = tmp_path / "listings.sqlite", tmp_path / "lookups.sqlite"
    with sqlite3.connect(db_path) as db:
        for market in ("buy", "lease"):
            db.execute(f"CREATE TABLE {market} (mls_number TEXT, listing_url TEXT, subtype TEXT, price INTEGER)")
            db.executemany(f"INSERT INTO {market} VALUES (?, '', ?, 123)", [("KNOWN", "Loft"), ("FOUND", "Unknown"), ("MISSING", None)])
    fetch = Mock(side_effect=lambda mls, url: {"PropertyType": "Condominium"} if mls == "FOUND" else {})
    monkeypatch.setattr(backfill, "fetch_agency_detail", fetch)
    assert backfill.backfill_subtypes(db_path, checkpoint_path, limit=1)["updated"] == 1
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE buy SET subtype = 'Unknown' WHERE mls_number = 'FOUND'")
    summary = backfill.backfill_subtypes(db_path, checkpoint_path)
    assert summary["cached"] == 1
    assert summary["updated"] == 2
    assert summary["not_found"] == 2
    assert fetch.call_count == 4
    assert backfill.backfill_subtypes(db_path, checkpoint_path)["requested"] == 0
    with sqlite3.connect(db_path) as db:
        for market in ("buy", "lease"):
            assert db.execute(f"SELECT subtype, price FROM {market} WHERE mls_number = 'KNOWN'").fetchone() == ("Loft", 123)
            assert db.execute(f"SELECT subtype, price FROM {market} WHERE mls_number = 'FOUND'").fetchone() == ("Condominium", 123)


def test_standalone_backfill_retries_transport_errors(tmp_path, monkeypatch):
    """A transport failure remains retryable while HTTP 404 is cached.

    Neither outcome should change an existing Unknown subtype on the first pass.
    """
    db_path, checkpoint_path = tmp_path / "listings.sqlite", tmp_path / "lookups.sqlite"
    with sqlite3.connect(db_path) as db:
        for market in ("buy", "lease"):
            db.execute(f"CREATE TABLE {market} (mls_number TEXT, listing_url TEXT, subtype TEXT)")
            db.execute(f"INSERT INTO {market} VALUES (?, '', 'Unknown')", (market,))
    fetch = Mock(side_effect=[
        requests.ConnectionError("offline"),
        requests.HTTPError(response=SimpleNamespace(status_code=404)),
        {"PropertyType": "Townhouse"},
    ])
    monkeypatch.setattr(backfill, "fetch_agency_detail", fetch)
    first = backfill.backfill_subtypes(db_path, checkpoint_path)
    second = backfill.backfill_subtypes(db_path, checkpoint_path)
    assert first["failed"] == first["unavailable"] == 1
    assert second["cached"] == second["updated"] == 1
    assert second["failed"] == 0
    assert fetch.call_count == 3
