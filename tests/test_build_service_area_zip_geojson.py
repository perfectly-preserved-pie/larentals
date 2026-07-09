import sqlite3
from pathlib import Path

import pytest

from scripts import build_service_area_zip_geojson as builder


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_normalize_zip_code_handles_listing_values() -> None:
    assert builder.normalize_zip_code("90001") == "90001"
    assert builder.normalize_zip_code("90001.0") == "90001"
    assert builder.normalize_zip_code("92805-1234") == "92805"
    assert builder.normalize_zip_code(None) is None
    assert builder.normalize_zip_code("1335") is None
    assert builder.normalize_zip_code("nan") is None


def test_read_listing_zip_codes_uses_configured_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "listings.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE buy (zip_code TEXT)")
        conn.execute("CREATE TABLE lease (zip_code TEXT)")
        conn.executemany(
            "INSERT INTO buy (zip_code) VALUES (?)",
            [("90001.0",), ("92805",), ("nan",)],
        )
        conn.executemany(
            "INSERT INTO lease (zip_code) VALUES (?)",
            [("92805-1234",), ("1335",), ("92672",)],
        )

    zip_codes, skipped = builder.read_listing_zip_codes(db_path, ("buy", "lease"))

    assert zip_codes == ["90001", "92672", "92805"]
    assert skipped == ["1335", "nan"]


def test_fallback_fetch_queries_only_california_zip_areas(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_post(url: str, data: dict, headers: dict, timeout: int) -> FakeResponse:
        calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return FakeResponse(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": []},
                        "properties": {"ZIP_CODE": "90704", "STATE": "CA"},
                    }
                ],
            }
        )

    monkeypatch.setattr(builder.requests, "post", fake_post)

    features, missing = builder.fetch_ca_zip_area_features(
        ["90704", "60660"],
        "https://example.test/FeatureServer/0",
    )

    assert calls[0]["url"] == "https://example.test/FeatureServer/0/query"
    assert calls[0]["data"]["where"] == "ZIP_CODE IN ('90704','60660') AND STATE = 'CA'"
    assert features == [
        {
            "type": "Feature",
            "properties": {"ZIPCODE": "90704"},
            "geometry": {"type": "Polygon", "coordinates": []},
        }
    ]
    assert missing == ["60660"]
