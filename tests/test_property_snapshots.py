"""Keep web requests offline and preserve facts through refresh failures."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import sqlite3
from threading import Event

from flask import Flask
import pytest
import requests

from api.listings import LEASE_LISTING_DETAIL_SQL, register_listing_routes
from api.property_context import register_property_context_routes
from functions import property_snapshots as snapshots
from functions import property_context as sources
from scripts.refresh_property_snapshots import load_snapshot_listings

LISTING = {"mls_number": "26991311", "full_street_address": "345 S Alexandria Ave #304, Los Angeles 90020",
           "city": "Los Angeles", "zip_code": "90020", "latitude": 34.06767, "longitude": -118.29834}


@pytest.fixture(autouse=True)
def isolate_snapshots(monkeypatch, tmp_path):
    """Use an isolated snapshot database and reject accidental network calls.

    Neither cache-reader tests nor refresh fixtures should depend on agencies.
    """
    path = tmp_path / "snapshots.sqlite"
    monkeypatch.setattr(snapshots, "PROPERTY_CONTEXT_CACHE_PATH", path)
    monkeypatch.setattr(sources, "PROPERTY_CONTEXT_CACHE_PATH", path)
    monkeypatch.setattr(sources.requests, "get", lambda *args, **kwargs: pytest.fail("Web path contacted an agency"))
    sources._CACHE.clear()
    yield
    sources._CACHE.clear()


def install_sources(monkeypatch):
    """Provide explicit successful source rows without external requests.

    Empty permit records still represent a complete source query in this fixture.
    """
    result = snapshots.empty_property_snapshot(LISTING)
    for name in ("fire", "flood", "zimas", "permits"):
        result[name]["status"] = "available"
        monkeypatch.setattr(sources, f"fetch_{'permit' if name == 'permits' else name}_context", lambda argument, section=result[name]: deepcopy(section))
    result["fire"]["zones"] = [{"designation": "High", "responsibility": "LRA"}]
    result["zimas"]["pin"] = "135B197 1256"
    return result


def listing_server(tmp_path, monkeypatch):
    """Build the real listing and snapshot routes against one fixture home.

    Optional rental amenities remain absent, as in a legacy production table.
    """
    selection = LEASE_LISTING_DETAIL_SQL.split("SELECT")[1].split("FROM")[0]
    selection = selection.replace("COALESCE(laundry_category, 'Unknown') AS laundry", "laundry_category")
    columns = [field.strip() for field in selection.split(",")]
    db = tmp_path / "listings.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE lease (" + ", ".join(f"{column} TEXT" for column in columns) + ")")
        conn.execute("ALTER TABLE lease ADD COLUMN zip_code TEXT")
        conn.execute("INSERT INTO lease (mls_number,full_street_address,city,latitude,longitude,list_price) VALUES (?,?,?,?,?,?)",
                     (LISTING["mls_number"], LISTING["full_street_address"], LISTING["city"], LISTING["latitude"], LISTING["longitude"], "2900"))
        conn.execute("UPDATE lease SET zip_code = ?", (LISTING["zip_code"],))
    monkeypatch.setattr("api.listings.build_lahd_listing_summary", lambda listing: pytest.fail("Basic popup waited for live housing records"))
    monkeypatch.setattr("api.listings.build_rso_listing_summary", lambda listing: {})
    server = Flask(__name__)
    server.add_url_rule("/health", view_func=lambda: "OK")
    register_listing_routes(server, str(db))
    register_property_context_routes(server, str(db))
    return server


def test_missing_snapshot_and_basic_popup_never_fetch_sources(tmp_path, monkeypatch):
    """A first visit must work before a maintenance job has warmed the home.

    Cache misses are explicit data states, never synchronous agency requests.
    """
    client = listing_server(tmp_path, monkeypatch).test_client()
    detail = client.get("/api/lease/listing-details/26991311")
    assert detail.status_code == 200
    assert detail.json["list_price"] == "2900"
    assert "lahd_property_summary" not in detail.json
    context = client.get("/api/lease/property-context/26991311")
    assert context.status_code == 200
    assert context.json["zimas"]["status"] == "not_cached"
    housing = client.get("/api/lease/housing-summary/26991311")
    assert housing.status_code == 200
    assert housing.json["snapshot_status"] == "not_cached"


def test_slow_refresh_cannot_hold_up_other_popups(tmp_path, monkeypatch):
    """Keep serving listing requests while the city lookup is still blocked.

    The old implementation held the only request worker until this source
    finished. Here real HTTP route handlers complete before the source releases.
    """
    install_sources(monkeypatch)
    started, release = Event(), Event()
    def slow_city(listing):
        started.set()
        assert release.wait(5), "Refresh was not released after checking the web routes"
        return {**snapshots.empty_property_snapshot(listing)["zimas"], "status": "available", "pin": "verified"}
    monkeypatch.setattr(sources, "fetch_zimas_context", slow_city)
    client = listing_server(tmp_path, monkeypatch).test_client()
    with ThreadPoolExecutor(max_workers=1) as pool:
        refresh = pool.submit(snapshots.refresh_property_snapshot, LISTING)
        try:
            assert started.wait(1)
            assert client.get("/health").data == b"OK"
            assert client.get("/api/lease/listing-details/26991311").status_code == 200
            assert client.get("/api/lease/property-context/26991311").json["zimas"]["status"] == "not_cached"
            assert not refresh.done()
        finally:
            release.set()
        assert refresh.result()["zimas"]["status"] == "available"


def test_expired_saved_sections_remain_readable_without_live_requests(monkeypatch):
    """Refresh age must not control whether existing property facts disappear.

    Outages and missed maintenance runs retain dated facts until a successful
    replacement is published.
    """
    saved = snapshots.empty_property_snapshot(LISTING)
    saved["zimas"].update(status="available", planning=[{"label": "Zoning", "value": "R5-2"}], checked_at="2020-01-01T00:00:00Z")
    snapshots._write_saved(snapshots.property_identity_key(LISTING), saved)
    result = snapshots.read_property_snapshot(LISTING)
    assert result["zimas"]["planning"][0]["value"] == "R5-2"
    assert result["zimas"]["stale"] is True
    assert result["zimas"]["checked_at"] == "2020-01-01T00:00:00Z"


def test_failed_refresh_preserves_successful_records_and_timestamp(monkeypatch):
    """A source timeout cannot overwrite a useful saved designation.

    Preserve its old check date while exposing the failed refresh separately.
    """
    install_sources(monkeypatch)
    first = snapshots.refresh_property_snapshot(LISTING)
    monkeypatch.setattr(sources, "fetch_fire_context", lambda listing: (_ for _ in ()).throw(requests.Timeout()))
    second = snapshots.refresh_property_snapshot(LISTING, force=True)
    assert second["fire"]["status"] == "available"
    assert second["fire"]["zones"] == first["fire"]["zones"]
    assert second["fire"]["checked_at"] == first["fire"]["checked_at"]
    assert second["fire"]["refresh_failed"] is True


def test_refresh_intervals_skip_unchanged_sections(monkeypatch):
    """A daily maintenance invocation need not re-fetch weekly fire maps.

    All new sections are fetched once; subsequent same-day runs reuse them.
    """
    install_sources(monkeypatch)
    snapshots.refresh_property_snapshot(LISTING)
    for name in ("fire", "flood", "zimas", "permit"):
        monkeypatch.setattr(sources, f"fetch_{name}_context", lambda listing: pytest.fail("Fresh section was downloaded again"))
    snapshots.refresh_property_snapshot(LISTING)


def test_housing_snapshot_is_published_only_by_refresh_job():
    """Reading a housing summary cannot invoke the supplied live builder.

    An available summary is saved with its check time for later popup requests.
    """
    assert snapshots.read_housing_snapshot(LISTING)["data_available"] is False
    saved = snapshots.refresh_housing_snapshot(LISTING, lambda listing: {"data_available": True, "matched": True, "documented_issue_count": 3})
    assert saved["checked_at"]
    assert snapshots.read_housing_snapshot(LISTING)["documented_issue_count"] == 3


def test_housing_route_uses_same_zip_and_coordinate_identity_as_backfill(tmp_path, monkeypatch):
    """Read the summary saved for exactly the stored listing identity.

    The original listing-detail query omitted ZIP, which would make a separate
    housing lookup miss a snapshot written by the maintenance job.
    """
    client = listing_server(tmp_path, monkeypatch).test_client()
    # This fixture uses TEXT coordinate columns, like a legacy listing table.
    identity = {**LISTING, "latitude": str(LISTING["latitude"]), "longitude": str(LISTING["longitude"])}
    snapshots.refresh_housing_snapshot(identity, lambda listing: {"data_available": True, "matched": True, "documented_issue_count": 7})
    assert client.get("/api/lease/housing-summary/26991311").json["documented_issue_count"] == 7


def test_backfill_prefers_uncached_properties_and_deduplicates_markets(tmp_path):
    """Limited jobs must progress beyond homes they already warmed.

    A shared property in Buy and Rent has one source identity and one refresh.
    """
    db = tmp_path / "listings.sqlite"
    with sqlite3.connect(db) as conn:
        for market in ("buy", "lease"):
            conn.execute(f"CREATE TABLE {market} (mls_number TEXT,full_street_address TEXT,listed_date TEXT)")
            conn.execute(f"INSERT INTO {market} VALUES ('known','Known address','2026-10-25')")
            conn.execute(f"INSERT INTO {market} VALUES ('new','New address','2026-10-24')")
    snapshots._write_saved(snapshots.property_identity_key({"full_street_address": "Known address"}), {})
    rows = load_snapshot_listings(db, ("buy", "lease"))
    assert [row["mls_number"] for row in rows] == ["new", "known"]
