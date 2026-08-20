from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from functions.dataframe_utils import (
    merge_listing_dataframes,
    normalize_reported_inactive_flags,
    reconstruct_missing_address_components,
    remove_inactive_listings,
    remove_trailing_zero,
    update_dataframe_with_listing_data,
)
from functions.geocoding_utils import (
    fill_missing_location_fields_with_checkpoint,
    re_geocode_above_lat_threshold,
    update_dataframe_with_geocoding,
)
from functions.listing_pipeline_checkpoint import (
    ListingCheckpointStore,
    address_fingerprint,
    photo_fingerprint,
)


class RecordingS3Client:
    def __init__(self) -> None:
        """Initialize the instance.

        Returns:
            None.
        """
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_count = 0

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: BytesIO,
        **kwargs: object,
    ) -> dict[str, object]:
        """Handle put object.

        Args:
            Bucket: S3 bucket receiving or containing the object.
            Key: S3 object key identifying the uploaded or requested object.
            Body: Binary object body uploaded to S3.
            **kwargs: Additional keyword arguments forwarded to the dependency.

        Returns:
            A mapping containing the put object.
        """
        self.objects[(Bucket, Key)] = Body.read()
        self.put_count += 1
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, BytesIO]:
        """Handle get object.

        Args:
            Bucket: S3 bucket receiving or containing the object.
            Key: S3 object key identifying the uploaded or requested object.

        Returns:
            A mapping containing the requested object.
        """
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}


class FakeLocation:
    latitude = 34.05
    longitude = -118.25
    raw = {
        "address_components": [
            {"long_name": "Los Angeles", "types": ["locality"]},
            {"long_name": "90002", "types": ["postal_code"]},
        ]
    }


class FakeGeolocator:
    def __init__(self) -> None:
        """Initialize the instance.

        Returns:
            None.
        """
        self.calls = 0

    def geocode(self, *args: object, **kwargs: object) -> FakeLocation:
        """Handle geocode.

        Args:
            *args: Additional positional arguments forwarded to the dependency.
            **kwargs: Additional keyword arguments forwarded to the dependency.

        Returns:
            A fixed fake geocoder result for Los Angeles.
        """
        self.calls += 1
        return FakeLocation()


def test_checkpoint_is_committed_and_uploaded_as_valid_sqlite(tmp_path: Path) -> None:
    """Verify that checkpoint is committed and uploaded as valid sqlite.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    s3 = RecordingS3Client()
    checkpoint_path = tmp_path / "buy.sqlite"
    store = ListingCheckpointStore(
        checkpoint_path,
        listing_type="buy",
        s3_bucket="example-bucket",
        s3_key="checkpoints/buy.sqlite",
        s3_client=s3,
        restore_remote=False,
    )

    store.checkpoint(
        "MLS-1",
        scrape_status="success",
        listing_input_hash="input-1",
        listing_url="https://example.test/listing",
    )

    assert s3.put_count == 1
    assert s3.objects[("example-bucket", "checkpoints/buy.sqlite")].startswith(
        b"SQLite format 3"
    )
    with sqlite3.connect(checkpoint_path) as connection:
        row = connection.execute(
            """
            SELECT scrape_status, listing_url
            FROM listing_checkpoint
            WHERE listing_type = 'buy' AND mls_number = 'MLS-1'
            """
        ).fetchone()
    assert row == ("success", "https://example.test/listing")

    restored = ListingCheckpointStore(
        tmp_path / "restored.sqlite",
        listing_type="buy",
        s3_bucket="example-bucket",
        s3_key="checkpoints/buy.sqlite",
        s3_client=s3,
    )
    assert restored.get("MLS-1")["listing_url"] == "https://example.test/listing"


def test_checkpoint_store_upgrades_an_existing_older_schema(
    tmp_path: Path,
) -> None:
    """Verify that checkpoint store upgrades an existing older schema.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    checkpoint_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(checkpoint_path) as connection:
        connection.execute(
            """
            CREATE TABLE listing_checkpoint (
                listing_type TEXT NOT NULL,
                mls_number TEXT NOT NULL,
                scrape_status TEXT,
                listing_url TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (listing_type, mls_number)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO listing_checkpoint (
                listing_type,
                mls_number,
                scrape_status,
                listing_url,
                updated_at
            )
            VALUES ('buy', 'MLS-1', 'success', 'https://example.test/old', '2026-01-01')
            """
        )

    store = ListingCheckpointStore(
        checkpoint_path,
        listing_type="buy",
    )
    store.checkpoint(
        "MLS-1",
        geocode_status="success",
        latitude=34.05,
        longitude=-118.25,
    )

    restored = store.get("MLS-1")
    assert restored["listing_url"] == "https://example.test/old"
    assert restored["geocode_status"] == "success"
    assert restored["latitude"] == pytest.approx(34.05)


def test_listing_scrape_and_image_are_reused_from_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify that listing scrape and image are reused from checkpoint.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    calls = {"scrape": 0, "image": 0}

    def fake_scrape(**kwargs: object) -> tuple[pd.Timestamp, str, str]:
        """Handle fake scrape.

        Args:
            **kwargs: Additional keyword arguments forwarded to the dependency.

        Returns:
            A tuple containing the fake scrape.
        """
        calls["scrape"] += 1
        return (
            pd.Timestamp("2026-07-20"),
            "https://images.example.test/MLS-1.jpg",
            "https://example.test/MLS-1",
        )

    def fake_image(
        source_url: str,
        mls: str,
        imagekit_instance: object,
        folder: str | None = None,
    ) -> str:
        """Handle fake image.

        Args:
            source_url: URL for the source.
            mls: MLS identifier for the listing.
            imagekit_instance: Configured ImageKit client used for image operations.
            folder: ImageKit destination folder for the listing image.

        Returns:
            The fake image text.
        """
        calls["image"] += 1
        assert folder == "/listings/buy"
        return "https://ik.example.test/listings/buy/MLS-1.jpg"

    monkeypatch.setattr("functions.dataframe_utils.webscrape_bhhs", fake_scrape)
    monkeypatch.setattr("functions.dataframe_utils.imagekit_transform", fake_image)

    store = ListingCheckpointStore(
        tmp_path / "buy.sqlite",
        listing_type="buy",
    )
    source = pd.DataFrame(
        [
            {
                "mls_number": "MLS-1",
                "full_street_address": "100 Main St, Los Angeles 90001",
                "list_price": 500_000,
                "listed_date": float("nan"),
                "listing_url": float("nan"),
                "source_photo_url": float("nan"),
                "mls_photo": float("nan"),
                "listing_input_hash": float("nan"),
                "scrape_status": float("nan"),
                "image_status": float("nan"),
                "image_source_hash": float("nan"),
            }
        ]
    )

    first = update_dataframe_with_listing_data(
        source.copy(),
        imagekit_instance=object(),
        listing_type="buy",
        checkpoint_store=store,
        source_file_hash="same-workbook",
    )
    second = update_dataframe_with_listing_data(
        source.copy(),
        imagekit_instance=object(),
        listing_type="buy",
        checkpoint_store=store,
        source_file_hash="same-workbook",
    )

    assert calls == {"scrape": 1, "image": 1}
    assert first.loc[0, "scrape_status"] == "success"
    assert first.loc[0, "image_status"] == "success"
    assert second.loc[0, "scrape_status"] == "cached"
    assert second.loc[0, "image_status"] == "cached"
    assert second.loc[0, "mls_photo"] == first.loc[0, "mls_photo"]


def test_listing_progress_log_identifies_type_fallback_source_and_eta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that listing progress log identifies type fallback source and eta.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.

    Returns:
        None.
    """
    messages: list[str] = []

    monkeypatch.setattr(
        "functions.dataframe_utils.webscrape_bhhs",
        lambda **kwargs: (None, None, None),
    )
    monkeypatch.setattr(
        "functions.dataframe_utils.fetch_the_agency_data",
        lambda *args, **kwargs: (
            pd.Timestamp("2026-07-20").date(),
            "https://www.theagencyre.com/listing/MLS-2",
            "https://images.example.test/MLS-2.jpg",
        ),
    )
    monkeypatch.setattr(
        "functions.dataframe_utils.imagekit_transform",
        lambda *args, **kwargs: "https://ik.example.test/listings/buy/MLS-2.jpg",
    )
    monkeypatch.setattr(
        "functions.dataframe_utils.logger.info",
        messages.append,
    )

    result = update_dataframe_with_listing_data(
        pd.DataFrame([{"mls_number": "MLS-2"}]),
        imagekit_instance=object(),
        listing_type="buy",
    )

    assert result.loc[0, "scrape_status"] == "success"
    assert any(
        "[buy 1/1 (100.0%)] MLS MLS-2" in message
        and "source=The Agency" in message
        and "checked=BHHS→The Agency" in message
        and "ETA=" in message
        for message in messages
    )


def test_inactive_check_log_identifies_type_provider_result_and_eta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that inactive check log identifies type provider result and eta.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.

    Returns:
        None.
    """
    messages: list[str] = []
    agency_checks: list[tuple[str, str]] = []

    def fake_agency_check(url: str, mls: str) -> bool:
        """Handle fake agency check.

        Args:
            url: URL requested, validated, or downloaded by the function.
            mls: MLS identifier for the listing.

        Returns:
            Whether the fake agency reports the listing as inactive.
        """
        agency_checks.append((url, mls))
        return False

    monkeypatch.setattr(
        "functions.dataframe_utils.check_expired_listing_theagency",
        fake_agency_check,
    )
    monkeypatch.setattr(
        "functions.dataframe_utils.logger.info",
        messages.append,
    )

    source = pd.DataFrame(
        [
            {
                "mls_number": "MLS-3",
                "listing_url": "https://www.theagencyre.com/listing/MLS-3",
            }
        ]
    )
    result = remove_inactive_listings(source, table_name="lease")

    assert len(result) == 1
    assert agency_checks == [
        ("https://www.theagencyre.com/listing/MLS-3", "MLS-3")
    ]
    assert any(
        "[lease inactive-check 1/1 (100.0%)] MLS MLS-3" in message
        and "result=kept" in message
        and "checked=The Agency" in message
        and "ETA=" in message
        for message in messages
    )


def test_inactive_checks_resume_from_checkpoint_until_source_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify that inactive checks resume from checkpoint until source changes.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    checks: list[tuple[str, str]] = []
    deleted_images: list[str] = []

    def fake_agency_check(url: str, mls: str) -> bool:
        """Handle fake agency check.

        Args:
            url: URL requested, validated, or downloaded by the function.
            mls: MLS identifier for the listing.

        Returns:
            Whether the fake agency reports the listing as inactive.
        """
        checks.append((url, mls))
        return mls == "MLS-INACTIVE"

    monkeypatch.setattr(
        "functions.dataframe_utils.check_expired_listing_theagency",
        fake_agency_check,
    )
    monkeypatch.setattr(
        "functions.dataframe_utils.delete_single_mls_image",
        deleted_images.append,
    )
    store = ListingCheckpointStore(
        tmp_path / "lease.sqlite",
        listing_type="lease",
    )
    source = pd.DataFrame(
        [
            {
                "mls_number": "MLS-ACTIVE",
                "listing_url": "https://www.theagencyre.com/listing/active",
            },
            {
                "mls_number": "MLS-INACTIVE",
                "listing_url": "https://www.theagencyre.com/listing/inactive",
            },
        ]
    )

    first = remove_inactive_listings(
        source.copy(),
        table_name="lease",
        checkpoint_store=store,
        source_file_hash="report-1",
    )
    second = remove_inactive_listings(
        source.copy(),
        table_name="lease",
        checkpoint_store=store,
        source_file_hash="report-1",
    )
    third = remove_inactive_listings(
        source.copy(),
        table_name="lease",
        checkpoint_store=store,
        source_file_hash="report-2",
    )

    assert first["mls_number"].tolist() == ["MLS-ACTIVE"]
    assert second["mls_number"].tolist() == ["MLS-ACTIVE"]
    assert third["mls_number"].tolist() == ["MLS-ACTIVE"]
    assert checks == [
        ("https://www.theagencyre.com/listing/active", "MLS-ACTIVE"),
        ("https://www.theagencyre.com/listing/inactive", "MLS-INACTIVE"),
        ("https://www.theagencyre.com/listing/active", "MLS-ACTIVE"),
        ("https://www.theagencyre.com/listing/inactive", "MLS-INACTIVE"),
    ]
    assert deleted_images == ["MLS-INACTIVE", "MLS-INACTIVE", "MLS-INACTIVE"]
    assert store.get("MLS-ACTIVE")["inactive_check_status"] == "success"
    assert store.get("MLS-INACTIVE")["inactive_check_is_inactive"] == 1


def test_geocode_is_reused_for_the_same_address(
    tmp_path: Path,
) -> None:
    """Verify that geocode is reused for the same address.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    store = ListingCheckpointStore(
        tmp_path / "lease.sqlite",
        listing_type="lease",
    )
    geolocator = FakeGeolocator()
    source = pd.DataFrame(
        [
            {
                "mls_number": "MLS-2",
                "full_street_address": "200 Main St, Los Angeles 90002",
                "latitude": float("nan"),
                "longitude": float("nan"),
                "geocode_status": float("nan"),
                "geocode_provider": float("nan"),
                "geocode_address_hash": float("nan"),
            }
        ]
    )

    first = update_dataframe_with_geocoding(
        source.copy(),
        geolocator=geolocator,
        checkpoint_store=store,
    )
    second = update_dataframe_with_geocoding(
        source.copy(),
        geolocator=geolocator,
        checkpoint_store=store,
    )

    assert geolocator.calls == 1
    assert first.loc[0, "geocode_status"] == "success"
    assert second.loc[0, "geocode_status"] == "cached"
    assert second.loc[0, "latitude"] == pytest.approx(34.05)


def test_missing_location_fields_and_coordinates_share_one_lookup(
    tmp_path: Path,
) -> None:
    """Verify that missing location fields and coordinates share one lookup.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        None.
    """
    store = ListingCheckpointStore(
        tmp_path / "lease.sqlite",
        listing_type="lease",
    )
    geolocator = FakeGeolocator()
    source = pd.DataFrame(
        [
            {
                "mls_number": "MLS-2",
                "street_address": "200 Main St",
                "city": None,
                "zip_code": None,
            }
        ]
    )

    first = fill_missing_location_fields_with_checkpoint(
        source.copy(),
        geolocator=geolocator,
        checkpoint_store=store,
        street_column="street_address",
    )
    first["full_street_address"] = (
        first["street_address"] + ", " + first["city"] + " " + first["zip_code"]
    )
    first = update_dataframe_with_geocoding(
        first,
        geolocator=geolocator,
        checkpoint_store=store,
    )

    second = fill_missing_location_fields_with_checkpoint(
        source.copy(),
        geolocator=geolocator,
        checkpoint_store=store,
        street_column="street_address",
    )
    second["full_street_address"] = (
        second["street_address"]
        + ", "
        + second["city"]
        + " "
        + second["zip_code"]
    )
    second = update_dataframe_with_geocoding(
        second,
        geolocator=geolocator,
        checkpoint_store=store,
    )

    assert geolocator.calls == 1
    assert first.loc[0, "location_status"] == "success"
    assert first.loc[0, "geocode_status"] == "success"
    assert second.loc[0, "location_status"] == "cached"
    assert second.loc[0, "geocode_status"] == "cached"


def test_missing_location_fields_accept_text_in_float_inferred_columns() -> None:
    """Verify that missing location fields accept text in float inferred columns.

    Returns:
        None.
    """
    geolocator = FakeGeolocator()
    source = pd.DataFrame(
        [
            {
                "mls_number": "MLS-1",
                "street_address": "100 Main St",
                "city": "Los Angeles",
                "zip_code": 90001.0,
                "location_status": float("nan"),
            },
            {
                "mls_number": "MLS-2",
                "street_address": "200 Main St",
                "city": None,
                "zip_code": None,
                "location_status": float("nan"),
            },
        ]
    )

    result = fill_missing_location_fields_with_checkpoint(
        source,
        geolocator=geolocator,
        checkpoint_store=None,
        street_column="street_address",
    )

    assert geolocator.calls == 1
    assert result.loc[0, "zip_code"] == 90001.0
    assert result.loc[1, "city"] == "Los Angeles"
    assert result.loc[1, "zip_code"] == "90002"
    assert result.loc[1, "location_status"] == "success"


def test_re_geocode_assigns_text_metadata_into_numeric_columns() -> None:
    """Verify that re geocode assigns text metadata into numeric columns.

    Returns:
        None.
    """
    source = pd.DataFrame(
        [
            {
                "mls_number": "MLS-1",
                "full_street_address": "100 Main St, Los Angeles 90001",
                "latitude": 40.0,
                "longitude": -118.25,
                "geocode_status": float("nan"),
                "geocode_provider": float("nan"),
                "geocode_address_hash": float("nan"),
            }
        ]
    )

    result = re_geocode_above_lat_threshold(
        source,
        geolocator=FakeGeolocator(),
    )

    assert result.loc[0, "latitude"] == pytest.approx(34.05)
    assert result.loc[0, "geocode_status"] == "success"
    assert result.loc[0, "geocode_provider"] == "google"


def test_address_reconstruction_handles_empty_arrow_string_selection() -> None:
    """Verify that address reconstruction handles empty arrow string selection.

    Returns:
        None.
    """
    source = pd.DataFrame(
        {
            "street_address": pd.Series(["100 Main St"], dtype="string"),
            "full_street_address": pd.Series(
                ["100 Main St, Los Angeles 90001"],
                dtype="string",
            ),
            "city": pd.Series(["Los Angeles"], dtype="string"),
            "zip_code": [90001.0],
            "street_number": [100.0],
        }
    )

    result = reconstruct_missing_address_components(source)

    assert result.loc[0, "zip_code"] == 90001.0
    assert result.loc[0, "street_number"] == 100.0


def test_address_reconstruction_assigns_text_into_numeric_columns() -> None:
    """Verify that address reconstruction assigns text into numeric columns.

    Returns:
        None.
    """
    source = pd.DataFrame(
        {
            "street_address": pd.Series(["100 Main St", pd.NA], dtype="string"),
            "full_street_address": pd.Series(
                [
                    "100 Main St, Los Angeles 90001",
                    "200 Oak Ave, Pasadena 91101",
                ],
                dtype="string",
            ),
            "city": pd.Series(["Los Angeles", pd.NA], dtype="string"),
            "zip_code": [90001.0, None],
            "street_number": [100.0, None],
        }
    )

    result = reconstruct_missing_address_components(source)

    assert result.loc[1, "street_address"] == "200 Oak Ave"
    assert result.loc[1, "city"] == "Pasadena"
    assert result.loc[1, "zip_code"] == "91101"
    assert result.loc[1, "street_number"] == "200"


def test_reported_inactive_flags_normalize_sqlite_and_string_values() -> None:
    """Verify that reported inactive flags normalize sqlite and string values.

    Returns:
        None.
    """
    source = pd.Series(
        [0, 1, 0.0, 1.0, "0", "0.0", "False", "1", "1.0", "true", pd.NA]
    )

    result = normalize_reported_inactive_flags(source)

    assert str(result.dtype) == "boolean"
    assert result.tolist() == [
        False,
        True,
        False,
        True,
        False,
        False,
        False,
        True,
        True,
        True,
        False,
    ]


def test_remove_trailing_zero_handles_pandas_3_string_dtype() -> None:
    """Verify that remove trailing zero handles pandas 3 string dtype.

    Returns:
        None.
    """
    source = pd.DataFrame(
        {
            "default_string": pd.Series(["90001.0", None], dtype="str"),
            "nullable_string": pd.Series(["200.0", pd.NA], dtype="string"),
            "numeric": [3.0, None],
        }
    )

    result = remove_trailing_zero(source)

    assert result["default_string"].tolist()[0] == "90001"
    assert result["nullable_string"].tolist()[0] == "200"
    assert result["numeric"].tolist()[0] == "3"
    assert result.loc[1].isna().all()


def test_column_merge_preserves_old_enrichment_after_failed_refresh() -> None:
    """Verify that column merge preserves old enrichment after failed refresh.

    Returns:
        None.
    """
    address = "100 Main St, Los Angeles 90001"
    old_photo_hash = photo_fingerprint("https://images.example.test/old.jpg")
    old = pd.DataFrame(
        [
            {
                "mls_number": "MLS-1",
                "list_price": 500_000,
                "full_street_address": address,
                "geocode_address_hash": address_fingerprint(address),
                "latitude": 34.05,
                "longitude": -118.25,
                "listing_url": "https://example.test/old",
                "mls_photo": "https://ik.example.test/old.jpg",
                "image_source_hash": old_photo_hash,
            }
        ]
    )
    new = pd.DataFrame(
        [
            {
                "mls_number": "MLS-1",
                "list_price": 525_000,
                "full_street_address": address,
                "geocode_address_hash": address_fingerprint(address),
                "geocode_status": "failed",
                "latitude": None,
                "longitude": None,
                "scrape_status": "failed",
                "listing_url": None,
                "image_status": "failed",
                "mls_photo": None,
                "image_source_hash": old_photo_hash,
            }
        ]
    )

    merged = merge_listing_dataframes(new, old).set_index("mls_number")

    assert merged.at["MLS-1", "list_price"] == 525_000
    assert merged.at["MLS-1", "latitude"] == pytest.approx(34.05)
    assert merged.at["MLS-1", "listing_url"] == "https://example.test/old"
    assert merged.at["MLS-1", "mls_photo"] == "https://ik.example.test/old.jpg"
    assert merged.at["MLS-1", "geocode_status"] == "failed"


def test_merge_accepts_legacy_object_dtypes_and_pandas_3_strings() -> None:
    """Verify that merge accepts legacy object dtypes and pandas 3 strings.

    Returns:
        None.
    """
    old = pd.DataFrame(
        {
            "mls_number": pd.Series(["MLS-1", "MLS-OLD"], dtype="object"),
            "zip_code": [90001.0, 91101.0],
            "street_number": [100.0, 200.0],
            "street_address": pd.Series(
                ["100 Main St", None],
                dtype="object",
            ),
            "city": pd.Series(["Los Angeles", None], dtype="object"),
            "full_street_address": pd.Series(
                [
                    "100 Main St, Los Angeles 90001",
                    "200 Oak Ave, Pasadena 91101",
                ],
                dtype="object",
            ),
            "listing_url": pd.Series(
                ["https://example.test/old", "https://example.test/legacy"],
                dtype="object",
            ),
            "latitude": [34.05, 34.15],
            "longitude": [-118.25, -118.15],
            "reported_as_inactive": pd.Series(["1", "0.0"], dtype="object"),
        }
    )
    new = pd.DataFrame(
        {
            "mls_number": pd.Series(["MLS-1"], dtype="str"),
            "zip_code": pd.Series(["90001"], dtype="str"),
            "street_number": pd.Series(["100"], dtype="str"),
            "street_address": pd.Series(["100 Main St"], dtype="str"),
            "city": pd.Series(["Los Angeles"], dtype="str"),
            "full_street_address": pd.Series(
                ["100 Main St, Los Angeles 90001"],
                dtype="str",
            ),
            "listing_url": pd.Series([None], dtype="str"),
            "scrape_status": pd.Series(["failed"], dtype="str"),
            "geocode_status": pd.Series(["failed"], dtype="str"),
            "image_status": pd.Series(["failed"], dtype="str"),
            "latitude": [None],
            "longitude": [None],
        }
    )

    merged = merge_listing_dataframes(new, old)
    merged = reconstruct_missing_address_components(merged)
    merged["reported_as_inactive"] = normalize_reported_inactive_flags(
        merged["reported_as_inactive"]
    )
    merged = merged.set_index("mls_number")

    assert merged.at["MLS-1", "listing_url"] == "https://example.test/old"
    assert merged.at["MLS-1", "latitude"] == pytest.approx(34.05)
    assert merged.at["MLS-1", "reported_as_inactive"]
    assert merged.at["MLS-OLD", "street_address"] == "200 Oak Ave"
    assert merged.at["MLS-OLD", "city"] == "Pasadena"
    assert merged.at["MLS-OLD", "zip_code"] == "91101"


def test_changed_address_and_photo_invalidate_failed_enrichment() -> None:
    """Verify that changed address and photo invalidate failed enrichment.

    Returns:
        None.
    """
    old_address = "100 Main St, Los Angeles 90001"
    new_address = "900 New St, Los Angeles 90002"
    old = pd.DataFrame(
        [
            {
                "mls_number": "MLS-1",
                "full_street_address": old_address,
                # Legacy rows may have the new hash column but no populated value.
                "geocode_address_hash": None,
                "latitude": 34.05,
                "longitude": -118.25,
                "mls_photo": "https://ik.example.test/old.jpg",
                "image_source_hash": photo_fingerprint(
                    "https://images.example.test/old.jpg"
                ),
            }
        ]
    )
    new = pd.DataFrame(
        [
            {
                "mls_number": "MLS-1",
                "full_street_address": new_address,
                "geocode_address_hash": address_fingerprint(new_address),
                "geocode_status": "failed",
                "latitude": None,
                "longitude": None,
                "image_status": "failed",
                "mls_photo": None,
                "image_source_hash": photo_fingerprint(
                    "https://images.example.test/new.jpg"
                ),
            }
        ]
    )

    merged = merge_listing_dataframes(new, old).set_index("mls_number")

    assert pd.isna(merged.at["MLS-1", "latitude"])
    assert pd.isna(merged.at["MLS-1", "longitude"])
    assert pd.isna(merged.at["MLS-1", "mls_photo"])
