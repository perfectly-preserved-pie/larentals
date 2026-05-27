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


def test_lahd_records_grids_do_not_repeat_property_address() -> None:
    assert "address" not in {column["field"] for column in lahd_records_ui.CASE_COLUMN_DEFS}
    assert "address" not in {column["field"] for column in lahd_records_ui.VIOLATION_COLUMN_DEFS}
