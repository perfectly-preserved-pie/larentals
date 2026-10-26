"""Protect parcel identity, coverage, and independent official-source failures."""

import json
from pathlib import Path
import sqlite3

from flask import Flask
import pytest
import requests

from api.property_context import register_property_context_routes
from functions import property_context as pc


LISTING = {"full_street_address": "361 N La Brea Avenue #2", "zip_code": "90036", "city": "Los Angeles",
           "latitude": 34.077, "longitude": -118.344}
PIN = "138B181   112"


@pytest.fixture(autouse=True)
def isolated_sources(monkeypatch, tmp_path):
    """Keep tests offline and prevent one test's cached home affecting another.

    Every network-capable test must explicitly supply the official response it
    exercises; unintended live requests fail immediately.
    """
    pc._CACHE.clear()
    monkeypatch.setattr(pc, "PROPERTY_CONTEXT_CACHE_PATH", tmp_path / "property_context.sqlite")
    monkeypatch.setattr(pc.requests, "get", lambda *args, **kwargs: pytest.fail("Unexpected live property request"))
    yield
    pc._CACHE.clear()


def source_profile():
    """Load an observed public ZIMAS response with its nested row structure.

    The fixture excludes assessor ownership fields and preserves full zone
    strings and official links used by the drawer.
    """
    return json.loads((Path(__file__).parent / "fixtures/zimas_property_context.json").read_text())


@pytest.mark.parametrize("addresses, expected", [
    ([(PIN, "361 N LA BREA AVE", 90036)], PIN),
    ([(PIN, "361 N LA BREA AVE", 90037)], None),
    ([(PIN, "363 N LA BREA AVE", 90036)], None),
    ([(PIN, "361 S LA BREA AVE", 90036)], None),
    ([(PIN, "361 N OTHER AVE", 90036)], None),
    ([(PIN, "361 N LA BREA AVE", 90036), ("another PIN", "361 N LA BREA AVE", 90036)], None),
])
def test_address_match_requires_street_number_direction_zip_and_unique_pin(monkeypatch, addresses, expected):
    """Never attach plausible neighboring or ambiguous parcel records.

    Removing a unit is allowed because city records describe the property;
    changing its street, direction, ZIP, or parcel identity is not.
    """
    monkeypatch.setattr(pc, "_source_json", lambda *args: {"features": [{"attributes": {"PIN": pin, "ADDRESS": address, "ZIP": zipcode}} for pin, address, zipcode in addresses]})
    match = pc._match_zimas_address(LISTING)
    assert (match or {}).get("PIN") == expected


def test_directionless_address_is_not_resolved_between_two_parcels(monkeypatch):
    """A missing MLS direction cannot select one of two opposite street parcels.

    Accepting the first row would depend on the city's current sort order.
    """
    rows = [{"attributes": {"PIN": direction, "ADDRESS": f"361 {direction} LA BREA AVE", "ZIP": 90036}} for direction in ("N", "S")]
    monkeypatch.setattr(pc, "_source_json", lambda *args: {"features": rows})
    assert pc._match_zimas_address({**LISTING, "full_street_address": "361 La Brea Ave"}) is None


def test_full_pin_profile_preserves_flags_zoning_and_housing_without_private_fields(monkeypatch):
    """Use the full PIN profile rather than the assessor-only APN response.

    The observed response has current JCO information and multiple zoning
    notices; neither should be replaced by an inferred legal conclusion.
    """
    calls = []
    monkeypatch.setattr(pc, "_match_zimas_address", lambda listing: {"PIN": PIN, "ADDRESS": "361 N LA BREA AVE"})
    def fetch(url, params):
        calls.append((url, params))
        return source_profile()
    monkeypatch.setattr(pc, "_source_json", fetch)
    result = pc.fetch_zimas_context(LISTING)
    assert calls[0][1] == {"PIN": PIN, "APN": "", "project": ""}
    assert result["status"] == "available"
    assert result["apns"] == ["5525033001"]
    assert any(row["label"] == "Zoning" and row["value"] == "C2-1VL" for row in result["planning"])
    assert any(row["label"] == "Methane Hazard Site" and row["value"] == "Methane Zone" for row in result["hazards"])
    assert any(row["label"] == "Just Cause For Eviction Ordinance (JCO)" for row in result["housing"])
    assert "Ownership" not in json.dumps(result)


@pytest.mark.parametrize("changed", ["address", "pin"])
def test_mismatched_profile_is_rejected(monkeypatch, changed):
    """Reject a profile even if the preceding address search succeeded.

    The service may change its parameter handling or return an unrelated PIN.
    """
    profile = source_profile()
    for row in profile[0]["Value"]:
        if row["Description"] == ("Site Address" if changed == "address" else "PIN Number"):
            row["Value"] = "wrong property"
    monkeypatch.setattr(pc, "_match_zimas_address", lambda listing: {"PIN": PIN, "ADDRESS": "361 N LA BREA AVE"})
    monkeypatch.setattr(pc, "_source_json", lambda *args: profile)
    with pytest.raises(ValueError, match="does not match"):
        pc.fetch_zimas_context(LISTING)


def test_outside_city_skips_zimas_and_permits(monkeypatch):
    """City coverage is a status rather than an empty permit history.

    State and federal hazard adapters remain usable for these listings.
    """
    monkeypatch.setattr(pc, "is_listing_in_los_angeles_city", lambda **kwargs: False)
    context = pc.fetch_zimas_context({**LISTING, "city": "Pasadena"})
    assert context["status"] == "outside_coverage"
    assert pc.fetch_permit_context(context)["status"] == "outside_coverage"


def test_fire_queries_both_responsibility_areas_and_does_not_invent_low_rating(monkeypatch):
    """A point missing from LRA may still intersect a high SRA designation.

    No intersections in either layer produce a separate coverage status.
    """
    queried = []
    def query(layer, *point):
        queried.append(layer)
        return [{"FHSZ_Description": "High"}] if layer == pc.FIRE_SRA else []
    monkeypatch.setattr(pc, "_point_query", query)
    result = pc.fetch_fire_context(LISTING)
    assert queried == [pc.FIRE_LRA, pc.FIRE_SRA]
    assert result["zones"][0]["designation"] == "High"
    monkeypatch.setattr(pc, "_point_query", lambda *args: [])
    assert pc.fetch_fire_context(LISTING)["status"] == "no_intersection"


def test_flood_keeps_zone_x_subtype_and_missing_geometry(monkeypatch):
    """Zone X subtypes must survive both the API and summary data boundary.

    Missing or invalid coordinates cannot trigger unrelated hazard lookups.
    """
    monkeypatch.setattr(pc, "_point_query", lambda *args: [{"FLD_ZONE": "X", "ZONE_SUBTY": "0.2 PCT ANNUAL CHANCE FLOOD HAZARD", "SFHA_TF": "F"}])
    result = pc.fetch_flood_context(LISTING)
    assert result["zones"][0]["subtype"].startswith("0.2 PCT")
    for location in (None, "nan", "inf", 0):
        assert pc.fetch_flood_context({**LISTING, "latitude": location})["status"] == "missing_location"


@pytest.mark.parametrize("body", [{"error": {"message": "failure"}}, {"features": [], "exceededTransferLimit": True}])
def test_http_200_errors_and_truncated_results_are_unavailable(monkeypatch, body):
    """ArcGIS errors must not become successful negative hazard findings.

    HTTP status alone does not establish a complete query response.
    """
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return body
    monkeypatch.setattr(pc.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(ValueError):
        pc._source_json(pc.FLOOD_LAYER, {})


def test_permits_use_verified_pin_and_report_limited_history(monkeypatch):
    """Keep expired permits visible and disclose a longer parcel history.

    APN lists on condo sites must not lead to guessing a unit-specific parcel.
    """
    calls = []
    def fetch(url, params):
        calls.append(params)
        return [{"permit_nbr": str(i), "status_desc": "Permit Expired"} for i in range(pc.PERMIT_LIMIT + 1)]
    monkeypatch.setattr(pc, "_source_json", fetch)
    result = pc.fetch_permit_context({"status": "available", "pin": PIN, "apns": ["1", "2"]})
    assert calls[0]["$where"] == f"pin_nbr = '{PIN}'"
    assert result["has_more"] is True
    assert len(result["records"]) == 25
    assert result["records"][0]["status_desc"] == "Permit Expired"


def test_failed_source_does_not_hide_other_sources_and_cache_tracks_location(monkeypatch):
    """Partial outages retain working sections and corrected locations refetch.

    Reopening a home's popup should share the same snapshot within its TTL.
    """
    calls = []
    def fire(listing):
        calls.append(listing)
        raise requests.Timeout()
    monkeypatch.setattr(pc, "fetch_fire_context", fire)
    monkeypatch.setattr(pc, "fetch_flood_context", lambda listing: {"status": "available", "zones": [{"zone": "AE"}]})
    monkeypatch.setattr(pc, "fetch_zimas_context", lambda listing: {"status": "outside_coverage"})
    first = pc.get_property_context(LISTING)
    assert first["fire"]["status"] == "unavailable"
    assert first["flood"]["zones"][0]["zone"] == "AE"
    first["flood"]["zones"].clear()
    assert pc.get_property_context(LISTING)["flood"]["zones"]
    assert len(calls) == 1
    pc.get_property_context({**LISTING, "latitude": 34.09})
    assert len(calls) == 2


@pytest.mark.parametrize("market", ["buy", "lease"])
def test_property_api_uses_stored_identity_and_handles_missing_listings(monkeypatch, tmp_path, market):
    """Ignore URL attempts to override the stored home's location or address.

    The route is usable with legacy tables and rejects unknown market names.
    """
    db = tmp_path / "listings.db"
    with sqlite3.connect(db) as conn:
        conn.execute(f"CREATE TABLE {market} (mls_number TEXT, full_street_address TEXT, city TEXT, latitude REAL, longitude REAL)")
        conn.execute(f"INSERT INTO {market} VALUES (?, ?, ?, ?, ?)", ("MLS-1", LISTING["full_street_address"], "Los Angeles", 34.077, -118.344))
    seen = []
    monkeypatch.setattr("api.property_context.read_property_snapshot", lambda listing: seen.append(listing) or {"address": listing["full_street_address"]})
    server = Flask(__name__)
    register_property_context_routes(server, str(db))
    client = server.test_client()
    response = client.get(f"/api/{market}/property-context/MLS-1?latitude=0&address=wrong")
    assert response.status_code == 200
    assert seen[0]["latitude"] == 34.077
    assert response.json["address"] == LISTING["full_street_address"]
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get(f"/api/{market}/property-context/missing").status_code == 404
    assert client.get("/api/other/property-context/MLS-1").status_code == 404


def test_source_html_and_unsafe_drillthrough_links_remain_inert():
    """Keep malformed official markup out of the app's HTML and links.

    A useful source label is still displayed when its URL is unusable.
    """
    row = pc._zimas_row({"Description": "Test", "Value": "<b>Check notes</b>", "Link": "javascript:alert(1)"})
    assert row == {"label": "Test", "value": "Check notes", "url": ""}


def test_disk_cache_survives_worker_memory_and_expires(monkeypatch):
    """Share slow source lookups across workers without reusing stale facts.

    A location correction changes the caller's identity key independently of
    the source snapshot's expiry.
    """
    monkeypatch.setattr(pc.time, "time", lambda: 1000)
    pc._cache_context("key", {"checked_at": "source time"}, 60)
    pc._CACHE.clear()
    assert pc._read_cached_context("key", 1059) == {"checked_at": "source time"}
    assert pc._read_cached_context("key", 1060) is None


def test_unreadable_disk_cache_does_not_block_records(monkeypatch):
    """An unusable optional cache must not break a source response.

    Container volumes can be read-only even while the app serves listing data.
    """
    pc.PROPERTY_CONTEXT_CACHE_PATH.mkdir()
    pc._cache_context("key", {"address": "123 Example Ave"}, 60)
    assert pc._read_cached_context("key", pc.time.time()) == {"address": "123 Example Ave"}
