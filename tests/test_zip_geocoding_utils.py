from pathlib import Path

import pytest

from functions import zip_geocoding_utils as geocoding


class FakeNominatimResponse:
    def __init__(self, payload: list[dict]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict]:
        return self._payload


def test_normalize_place_query_defaults_generic_places_to_la_county() -> None:
    assert geocoding._normalize_place_query("Chinatown") == "Chinatown, Los Angeles County, CA"
    assert geocoding._normalize_place_query("Canoga Park") == "Canoga Park, Los Angeles County, CA"
    assert geocoding._normalize_place_query("Chinatown, CA") == "Chinatown, CA"


def test_geocode_place_cached_prefers_la_county_for_ambiguous_california_place(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = [
        {
            "lat": "37.7943011",
            "lon": "-122.4063757",
            "class": "boundary",
            "type": "administrative",
            "addresstype": "neighbourhood",
            "importance": 0.48710517537975206,
            "display_name": "Chinatown, South of Market, San Francisco, California, United States",
            "address": {
                "neighbourhood": "Chinatown",
                "suburb": "South of Market",
                "city": "San Francisco",
                "state": "California",
                "ISO3166-2-lvl4": "US-CA",
                "country": "United States",
                "country_code": "us",
            },
            "boundingbox": ["37.7901561", "37.7980200", "-122.4102750", "-122.4040590"],
        },
        {
            "lat": "34.0638402",
            "lon": "-118.2358676",
            "class": "place",
            "type": "suburb",
            "addresstype": "suburb",
            "importance": 0.45602303152811446,
            "display_name": "Chinatown, Los Angeles, Los Angeles County, California, 90086, United States",
            "address": {
                "suburb": "Chinatown",
                "city": "Los Angeles",
                "county": "Los Angeles County",
                "state": "California",
                "ISO3166-2-lvl4": "US-CA",
                "postcode": "90086",
                "country": "United States",
                "country_code": "us",
            },
            "boundingbox": ["34.0438402", "34.0838402", "-118.2558676", "-118.2158676"],
        },
    ]
    calls = []

    def fake_get(url: str, params: dict, timeout: int, headers: dict) -> FakeNominatimResponse:
        calls.append({"url": url, "params": params.copy(), "timeout": timeout, "headers": headers})
        return FakeNominatimResponse(payload)

    monkeypatch.setattr(geocoding.requests, "get", fake_get)

    result = geocoding.geocode_place_cached("chinatown, CA", cache_path=tmp_path / "place_cache.json")

    assert result is not None
    assert result["display_name"] == "Chinatown, Los Angeles, Los Angeles County, California, 90086, United States"
    assert result["lat"] == 34.0638402
    assert result["lon"] == -118.2358676
    assert calls[0]["params"]["q"] == "chinatown, CA"
