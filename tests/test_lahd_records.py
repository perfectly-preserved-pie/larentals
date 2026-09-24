import gzip
from pathlib import Path

import orjson
import pytest
import requests

from api import listings
from functions import lahd
from functions import lahd_records_ui


def test_fetch_lahd_property_record_details_normalizes_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that fetch lahd property record details normalizes rows.

    Both investigation and violation sources must be reduced to the common drawer row shape.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.

    Returns:
        None.
    """
    def fake_request(
        url: str,
        params: dict[str, object],
    ) -> list[dict[str, object]]:
        """Handle fake request.

        The fake captures Socrata query parameters so filters and limits can be asserted.

        Args:
            url: URL requested, validated, or downloaded by the function.
            params: Query parameters included with the HTTP request.

        Returns:
            A list containing the fake request.

        Raises:
            AssertionError: If the operation cannot be completed.
        """
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
                    "violations_cited": "2025-01-02T00:00:00.000",
                    "violations_cleared": "2",
                    "countviolationtypespercase": "5",
                },
                {
                    "address": "4616 W RODEO ROAD, Los Angeles, CA 90016",
                    "violationtype": "EXPOSED WIRING",
                    "violations_cited": "2024-06-01T00:00:00.000",
                    "violations_cleared": "3",
                    "countviolationtypespercase": "3",
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
    assert payload["violations"][0]["cited_date"] == "2025-01-02"
    assert payload["violations"][0]["violations_cleared"] == 2
    assert payload["violations"][0]["violation_types_per_case"] == 5
    assert payload["summary"]["documented_issue_count"] == 2
    assert payload["summary"]["unresolved_issue_count"] == 1
    assert payload["truncated"]["cases"] is True
    assert payload["truncated"]["violations"] is True


def test_fetch_lahd_property_record_details_falls_back_to_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that fetch lahd property record details falls back to snapshot.

    A failed live request should still show the locally prepared property snapshot.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.

    Returns:
        None.
    """
    response = requests.Response()
    response.status_code = 403
    response.url = lahd.LAHD_INVESTIGATION_DATASET_URL
    error = requests.HTTPError("403 Client Error: Forbidden", response=response)

    def fake_investigation_records(
        apn: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Handle fake investigation records.

        The fixture supplies stable case rows for aggregation and drawer rendering.

        Args:
            apn: Assessor Parcel Number identifying the property.
            limit: Maximum number of records to return.

        Returns:
            A list containing the fake investigation records.

        Raises:
            error: If the operation cannot be completed.
        """
        raise error

    def fake_violation_records(
        apn: str,
        limit: int,
    ) -> list[dict[str, object]]:
        """Handle fake violation records.

        The fixture isolates violation normalization from live source schemas.

        Args:
            apn: Assessor Parcel Number identifying the property.
            limit: Maximum number of records to return.

        Returns:
            A list containing the fake violation records.
        """
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


def test_live_lahd_dataset_status_reports_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that live lahd dataset status reports non 200.

    Non-200 responses make the corresponding live dataset unavailable.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.

    Returns:
        None.
    """
    def fake_get(url: str, **kwargs: object) -> requests.Response:
        """Handle fake get.

        The HTTP stub exercises status and fallback branches without contacting Socrata.

        Args:
            url: URL requested, validated, or downloaded by the function.
            **kwargs: Additional keyword arguments forwarded to the dependency.

        Returns:
            An HTTP response containing the fake get.
        """
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


def test_listing_lahd_summary_hidden_when_live_datasets_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that listing lahd summary hidden when live datasets unavailable.

    The popup should not imply zero records when source data could not be checked.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.

    Returns:
        None.
    """
    monkeypatch.setattr(
        listings,
        "is_listing_in_los_angeles_city",
        lambda *, city, latitude, longitude: True,
    )
    monkeypatch.setattr(listings, "live_lahd_datasets_available", lambda: False)

    def fail_lookup(**_kwargs: object) -> None:
        """Handle fail lookup.

        A deterministic failure drives the snapshot fallback path.

        Args:
            **_kwargs: Ignored keyword arguments accepted by the test double.

        Returns:
            None.

        Raises:
            AssertionError: If the operation cannot be completed.
        """
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


def test_lahd_listing_rejects_neighboring_street_number(tmp_path: Path) -> None:
    """Do not assign a nearby parcel with a different street number.

    MLS coordinates can sit directly on the neighboring building, so distance
    does not establish that its LAHD records belong to the listing.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
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

    assert result["matched"] is False
    assert result["apn"] is None



def test_lahd_listing_prefers_unique_address_with_missing_direction_over_wrong_coordinates(tmp_path: Path) -> None:
    """Use the Marathon street address when a listing pin falls on Mariposa.

    LAHD includes a west direction that the MLS listing omits, while the MLS
    coordinates point about a kilometer away to another LAHD property.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    artifact_path = tmp_path / "lookup.json.gz"
    payload = {
        "metadata": {"generated_at": "2026-05-27T17:09:54Z"},
        "records": [
            [34.084319, -118.285263, 70, 70, 0, 3, 0, 67, 0, 16, 3, 67,
             "3920 W MARATHON ST, Los Angeles, CA 90029", "5539019017", "2019-02-26", "2025-05-15"],
            [34.08431, -118.298563, 64, 64, 0, 11, 0, 53, 0, 21, 11, 53,
             "724 N MARIPOSA AVE, Los Angeles, CA 90029", "5538007029", "2021-03-25", "2025-03-07"],
        ],
    }
    with gzip.open(artifact_path, "wb") as artifact_file:
        artifact_file.write(orjson.dumps(payload))

    lahd._load_lahd_listing_lookup.cache_clear()
    try:
        matched = lahd.lookup_lahd_property_for_listing(
            address="3920 Marathon St #7a, Los Angeles 90029",
            latitude=34.08431,
            longitude=-118.298563,
            artifact_path=artifact_path,
        )
        unmatched = lahd.lookup_lahd_property_for_listing(
            address="3922 Marathon St #7a",
            latitude=34.08431,
            longitude=-118.298563,
            artifact_path=artifact_path,
        )
    finally:
        lahd._load_lahd_listing_lookup.cache_clear()

    assert matched["matched"] is True
    assert matched["match_type"] == "address"
    assert matched["apn"] == "5539019017"
    assert matched["documented_issue_count"] == 0  # The local index supplies identity only.
    assert unmatched["matched"] is False
    assert unmatched["apn"] is None


def test_lahd_listing_does_not_guess_missing_direction_when_ambiguous(tmp_path: Path) -> None:
    """Leave a directionless address unmatched if LAHD has two distinct parcels.

    The same street number can exist on both sides of a directional street, so
    an omitted direction alone cannot identify either property.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    artifact_path = tmp_path / "lookup.json.gz"
    payload = {"records": [
        [34.084319, -118.285263, 1, 1, 0, 1, 0, 0, 0, 0, 1, 0,
         "3920 W MARATHON ST, Los Angeles, CA 90029", "5539019017", "", ""],
        [34.08431, -118.298563, 1, 1, 0, 1, 0, 0, 0, 0, 1, 0,
         "3920 E MARATHON ST, Los Angeles, CA 90029", "5538007029", "", ""],
    ]}
    with gzip.open(artifact_path, "wb") as artifact_file:
        artifact_file.write(orjson.dumps(payload))

    lahd._load_lahd_listing_lookup.cache_clear()
    try:
        result = lahd.lookup_lahd_property_for_listing(
            address="3920 Marathon St, Los Angeles 90029",
            latitude=None,
            longitude=None,
            artifact_path=artifact_path,
        )
    finally:
        lahd._load_lahd_listing_lookup.cache_clear()

    assert result["matched"] is False




def test_lahd_listing_rejects_shared_address_with_multiple_apns(tmp_path: Path) -> None:
    """Leave an exact street address unmatched when LAHD lists two parcels.

    A higher issue count on one parcel is not evidence that a listing belongs
    to it, even when both LAHD records use the same address and ZIP.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    artifact_path = tmp_path / "lookup.json.gz"
    payload = {"records": [
        [34.05, -118.24, 100, 100, 0, 1, 0, 0, 0, 0, 1, 0,
         "123 S FIGUEROA ST, Los Angeles, CA 90012", "5151001027", "", ""],
        [34.05, -118.24, 1, 1, 0, 1, 0, 0, 0, 0, 1, 0,
         "123 S FIGUEROA ST, Los Angeles, CA 90012", "5151001033", "", ""],
    ]}
    with gzip.open(artifact_path, "wb") as artifact_file:
        artifact_file.write(orjson.dumps(payload))

    lahd._load_lahd_listing_lookup.cache_clear()
    try:
        result = lahd.lookup_lahd_property_for_listing(
            address="123 S Figueroa Street, Los Angeles 90012",
            latitude=34.05,
            longitude=-118.24,
            artifact_path=artifact_path,
        )
    finally:
        lahd._load_lahd_listing_lookup.cache_clear()

    assert result["matched"] is False



def test_lahd_listing_uses_zip_to_separate_identical_street_addresses(tmp_path: Path) -> None:
    """Select the parcel in the listing ZIP when two areas share an address.

    Venice and San Pedro both have a 704 S Pacific Ave in the stored LAHD data.
    The ZIP is part of the listing address and identifies the intended area.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    artifact_path = tmp_path / "lookup.json.gz"
    payload = {"records": [
        [33.73, -118.29, 5, 5, 0, 1, 0, 0, 0, 0, 1, 0,
         "704 S PACIFIC AVE, SAN PEDRO, CA 90731", "7455006001", "", ""],
        [33.99, -118.46, 6, 6, 0, 1, 0, 0, 0, 0, 1, 0,
         "704 S PACIFIC AVE, VENICE, CA 90291", "4286015003", "", ""],
    ]}
    with gzip.open(artifact_path, "wb") as artifact_file:
        artifact_file.write(orjson.dumps(payload))

    lahd._load_lahd_listing_lookup.cache_clear()
    try:
        matched = lahd.lookup_lahd_property_for_listing(
            address="704 S Pacific Avenue, Venice 90291",
            latitude=33.73,
            longitude=-118.29,
            artifact_path=artifact_path,
        )
        missing_zip = lahd.lookup_lahd_property_for_listing(
            address="704 S Pacific Avenue",
            latitude=33.99,
            longitude=-118.46,
            artifact_path=artifact_path,
        )
    finally:
        lahd._load_lahd_listing_lookup.cache_clear()

    assert matched["apn"] == "4286015003"
    assert missing_zip["matched"] is False


def test_lahd_street_name_prefix_is_not_removed_as_unit() -> None:
    """Keep street names beginning with a unit abbreviation intact.

    STEVELY once became an empty route because the unit regex treated its
    first three letters as a suite marker.

    Returns:
        None.
    """
    assert lahd._normalize_property_address_for_lookup("3923 S Stevely Ave #2") == "3923 S STEVELY AVE"
    assert lahd._normalize_property_address_for_lookup("3920 Marathon St Ste 2") == "3920 MARATHON ST"


def test_lahd_listing_summary_uses_live_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Show the drawer's live totals instead of stale artifact counts.

    Both popup and drawer must use the same APN and row summary when the live
    source succeeds.

    Args:
        monkeypatch: Pytest fixture used to replace lookup and live fetch.

    Returns:
        None.
    """
    monkeypatch.setattr(listings, "is_listing_in_los_angeles_city", lambda **kwargs: True)
    monkeypatch.setattr(listings, "live_lahd_datasets_available", lambda: True)
    monkeypatch.setattr(listings, "lookup_lahd_property_for_listing", lambda **kwargs: {
        "matched": True, "data_available": True, "apn": "5539019017",
        "address": "3920 W MARATHON ST, Los Angeles, CA 90029",
        "documented_issue_count": 70, "snapshot_generated_at": "2026-05-27T17:09:54Z",
    })
    requested_apns = []

    def fake_fetch(apn):
        """Supply a live count for the requested APN.

        Args:
            apn: Parcel identifier requested by the popup.

        Returns:
            Minimal current LAHD details for this test.
        """
        requested_apns.append(apn)
        return {
            "summary": {"case_count": 13, "open_case_count": 1,
                        "violations_cited": 0, "unresolved_violation_count": 0,
                        "documented_issue_count": 13, "unresolved_issue_count": 1,
                        "latest_case_date": "2026-03-11"},
            "detail_status": {"live_records_available": True},
            "truncated": {"cases": False, "violations": False},
        }

    monkeypatch.setattr(listings, "fetch_lahd_property_record_details", fake_fetch)
    summary = listings.build_lahd_listing_summary({
        "city": "Los Angeles", "full_street_address": "3920 Marathon St #7a",
        "latitude": 34.0843, "longitude": -118.2987,
    })

    assert requested_apns == ["5539019017"]
    assert summary["documented_issue_count"] == 13
    assert summary["investigation_case_count"] == 13
    assert summary["latest_case_date"] == "2026-03-11"


def test_lahd_listing_summary_hides_stale_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not show snapshot totals when the live API cannot provide rows.

    A drawer fallback explicitly marks its summary as old; the popup should
    report unavailable data rather than presenting that count as current.

    Args:
        monkeypatch: Pytest fixture used to replace lookup and live fetch.

    Returns:
        None.
    """
    monkeypatch.setattr(listings, "is_listing_in_los_angeles_city", lambda **kwargs: True)
    monkeypatch.setattr(listings, "live_lahd_datasets_available", lambda: True)
    monkeypatch.setattr(listings, "lookup_lahd_property_for_listing", lambda **kwargs: {
        "matched": True, "data_available": True, "apn": "5539019017",
        "documented_issue_count": 70,
    })
    monkeypatch.setattr(listings, "fetch_lahd_property_record_details", lambda apn: {
        "summary": {"documented_issue_count": 70},
        "detail_status": {"live_records_available": False},
    })

    summary = listings.build_lahd_listing_summary({"city": "Los Angeles"})

    assert summary["data_available"] is False
    assert summary["matched"] is False


def test_lahd_records_drawer_fetches_popup_apn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep drawer details tied to the APN selected by the listing popup.

    An address lookup can have a different winner when the same normalized
    address belongs to multiple parcels.

    Args:
        monkeypatch: Pytest fixture used to replace the live fetch.

    Returns:
        None.
    """
    callbacks = []

    class FakeApp:
        """Capture the callback registered for the drawer event."""

        def callback(self, *args, **kwargs):
            """Return a decorator that records the drawer handler.

            Args:
                *args: Dash callback output and input declarations.
                **kwargs: Dash callback registration options.

            Returns:
                A decorator that captures the callback.
            """
            def capture(handler):
                """Keep the handler available for the event test.

                Args:
                    handler: Drawer callback registered by the UI.

                Returns:
                    The unchanged drawer callback.
                """
                callbacks.append(handler)
                return handler
            return capture

    requested_apns = []

    def fake_fetch(apn):
        """Record the requested parcel without contacting LAHD.

        Args:
            apn: APN passed by the drawer callback.

        Returns:
            Minimal details passed to the mocked renderer.
        """
        requested_apns.append(apn)
        return {"apn": apn, "summary": {}}

    monkeypatch.setattr(lahd_records_ui, "fetch_lahd_property_record_details", fake_fetch)
    monkeypatch.setattr(lahd_records_ui, "build_lahd_records_drawer_content", lambda details: details)
    lahd_records_ui.register_lahd_records_drawer_callback(FakeApp())

    opened, _, content = callbacks[0]({
        "detail.apn": "5539019017",
        "detail.address": "3920 W MARATHON ST, Los Angeles, CA 90029",
    })

    assert opened is True
    assert requested_apns == ["5539019017"]
    assert content["apn"] == "5539019017"


def test_lahd_records_grids_do_not_repeat_property_address() -> None:
    """Verify that lahd records grids do not repeat property address.

    The drawer title already identifies the property, so table rows should not repeat that address.

    Returns:
        None.
    """
    assert "address" not in {column["field"] for column in lahd_records_ui.CASE_COLUMN_DEFS}
    assert "address" not in {column["field"] for column in lahd_records_ui.VIOLATION_COLUMN_DEFS}


def test_lahd_scope_uses_official_la_city_boundary() -> None:
    """Verify that lahd scope uses official la city boundary.

    The jurisdiction check must follow the official boundary rather than a rough rectangle.

    Returns:
        None.
    """
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
