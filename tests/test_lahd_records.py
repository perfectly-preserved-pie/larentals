import gzip

import orjson
import requests

from api import listings
from functions import lahd
from functions import lahd_records_ui


def test_fetch_lahd_property_record_details_normalizes_rows(monkeypatch) -> None:
    def fake_request(url, params):
        assert params["apn"] == "5046034015"
        assert params["$limit"] == 2
        if url == lahd.LAHD_INVESTIGATION_DATASET_URL:
            return [
                {
                    "officialaddress": "4616 W RODEO ROAD, Los Angeles, CA 90016",
                    "case_filed_date": "2025-01-02T00:00:00.000",
                    "casetype": "Reduction of Services",
                },
                {
                    "officialaddress": "4616 W RODEO ROAD, Los Angeles, CA 90016",
                    "case_filed_date": "2024-06-01T00:00:00.000",
                    "closed_date": "2024-07-01T00:00:00.000",
                    "casetype": "Illegal Rent Increase",
                },
            ]
        if url == lahd.LAHD_VIOLATION_DATASET_URL:
            return [
                {
                    "address": "4616 W RODEO ROAD, Los Angeles, CA 90016",
                    "violationtype": "CAULKING",
                    "violations_cited": "5",
                    "violations_cleared": "2",
                },
                {
                    "address": "4616 W RODEO ROAD, Los Angeles, CA 90016",
                    "violationtype": "EXPOSED WIRING",
                    "violations_cited": "3",
                    "violations_cleared": "3",
                },
            ]
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(lahd, "_request_socrata_rows", fake_request)
    lahd.fetch_lahd_property_record_details.cache_clear()

    try:
        payload = lahd.fetch_lahd_property_record_details("5046-034-015", row_limit=1)
    finally:
        lahd.fetch_lahd_property_record_details.cache_clear()

    assert payload["apn"] == "5046034015"
    assert payload["cases"] == [
        {
            "filed_date": "2025-01-02",
            "closed_date": "",
            "status": "No close date",
            "case_type": "Reduction of Services",
            "address": "4616 W RODEO ROAD, Los Angeles, CA 90016",
        }
    ]
    assert payload["violations"][0]["uncleared_estimate"] == 3
    assert payload["summary"]["documented_issue_count"] == 6
    assert payload["summary"]["unresolved_issue_count"] == 4
    assert payload["truncated"]["cases"] is True
    assert payload["truncated"]["violations"] is True


def test_fetch_lahd_property_record_details_falls_back_to_snapshot(monkeypatch) -> None:
    response = requests.Response()
    response.status_code = 403
    response.url = lahd.LAHD_INVESTIGATION_DATASET_URL
    error = requests.HTTPError("403 Client Error: Forbidden", response=response)

    def fake_investigation_records(apn, limit):
        raise error

    def fake_violation_records(apn, limit):
        return []

    monkeypatch.setattr(lahd, "_fetch_property_investigation_records", fake_investigation_records)
    monkeypatch.setattr(lahd, "_fetch_property_violation_records", fake_violation_records)
    monkeypatch.setattr(
        lahd,
        "lookup_lahd_property_record_by_apn",
        lambda apn: {
            "address": "4633 W AUGUST ST, Los Angeles, CA 90008",
            "apn": apn,
            "documented_issue_count": 509,
            "unresolved_issue_count": 35,
            "investigation_case_count": 23,
            "open_case_count": 3,
            "violation_row_count": 32,
            "violations_cited": 486,
            "violations_cleared": 454,
            "unresolved_violation_count": 32,
            "first_case_date": "2015-07-07",
            "latest_case_date": "2025-09-10",
        },
    )
    monkeypatch.setattr(lahd, "get_lahd_property_lookup_metadata", lambda: {"generated_at": "2026-05-27T17:09:54Z"})
    lahd.fetch_lahd_property_record_details.cache_clear()

    try:
        payload = lahd.fetch_lahd_property_record_details("5030-011-006")
    finally:
        lahd.fetch_lahd_property_record_details.cache_clear()

    assert payload["apn"] == "5030011006"
    assert payload["cases"] == []
    assert payload["violations"] == []
    assert payload["summary"]["documented_issue_count"] == 509
    assert payload["summary"]["unresolved_issue_count"] == 35
    assert payload["detail_status"]["live_records_available"] is False
    assert "logged-in access" in payload["detail_status"]["message"]


def test_live_lahd_dataset_status_reports_non_200(monkeypatch) -> None:
    def fake_get(url, **kwargs):
        response = requests.Response()
        response.status_code = 403 if url == lahd.LAHD_INVESTIGATION_DATASET_URL else 200
        return response

    monkeypatch.setattr(lahd.requests, "get", fake_get)
    lahd._get_lahd_live_dataset_status.cache_clear()

    try:
        status = lahd.get_lahd_live_dataset_status()
    finally:
        lahd._get_lahd_live_dataset_status.cache_clear()

    assert status["available"] is False
    assert status["status_codes"] == {
        "investigation": 403,
        "violation": 200,
    }


def test_listing_lahd_summary_hidden_when_live_datasets_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        listings,
        "is_listing_in_los_angeles_city",
        lambda *, city, latitude, longitude: True,
    )
    monkeypatch.setattr(listings, "live_lahd_datasets_available", lambda: False)

    def fail_lookup(**_kwargs):
        raise AssertionError("Local LAHD snapshot should not be used when live datasets are unavailable.")

    monkeypatch.setattr(listings, "lookup_lahd_property_for_listing", fail_lookup)

    summary = listings.build_lahd_listing_summary(
        {
            "city": "Los Angeles",
            "latitude": 34.0522,
            "longitude": -118.2437,
            "full_street_address": "200 N Spring St",
        }
    )

    assert summary["data_available"] is False
    assert summary["jurisdiction_in_scope"] is True


def test_lahd_listing_lookup_uses_spatial_candidates(tmp_path) -> None:
    artifact_path = tmp_path / "lookup.json.gz"
    payload = {
        "records": [
            [
                34.017488,
                -118.350133,
                544,
                509,
                35,
                23,
                3,
                486,
                32,
                32,
                20,
                454,
                "4633 W AUGUST ST, Los Angeles, CA 90008",
                "5030011006",
                "2015-07-07",
                "2025-09-10",
            ]
        ],
        "metadata": {"generated_at": "2026-05-27T17:09:54Z"},
    }
    with gzip.open(artifact_path, "wb") as artifact_file:
        artifact_file.write(orjson.dumps(payload))

    lahd._load_lahd_listing_lookup.cache_clear()
    try:
        result = lahd.lookup_lahd_property_for_listing(
            address="4631 W AUGUST ST",
            latitude=34.01749,
            longitude=-118.35013,
            artifact_path=artifact_path,
        )
    finally:
        lahd._load_lahd_listing_lookup.cache_clear()

    assert result["matched"] is True
    assert result["match_type"] == "nearby_parcel"
    assert result["apn"] == "5030011006"


def test_lahd_records_grids_do_not_repeat_property_address() -> None:
    assert "address" not in {column["field"] for column in lahd_records_ui.CASE_COLUMN_DEFS}
    assert "address" not in {column["field"] for column in lahd_records_ui.VIOLATION_COLUMN_DEFS}


def test_lahd_scope_uses_official_la_city_boundary() -> None:
    assert (
        lahd.is_listing_in_los_angeles_city(
            city="North Hollywood",
            latitude=34.1706,
            longitude=-118.3772,
        )
        is True
    )
    assert (
        lahd.is_listing_in_los_angeles_city(
            city="Santa Monica",
            latitude=34.0195,
            longitude=-118.4912,
        )
        is False
    )
    assert (
        lahd.is_listing_in_los_angeles_city(
            city="Diamond Bar",
            latitude=33.9994022,
            longitude=-117.5924017,
        )
        is False
    )
