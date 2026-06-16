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


def test_normalize_place_query_defaults_unqualified_places_to_california() -> None:
    assert geocoding._normalize_place_query("Chinatown") == "Chinatown, CA"
    assert geocoding._normalize_place_query("Canoga Park") == "Canoga Park, CA"
    assert (
        geocoding._normalize_place_query("1910 S Union St #1073, Anaheim 92805")
        == "1910 S Union St #1073, Anaheim 92805, CA"
    )
    assert geocoding._normalize_place_query("Chinatown, CA") == "Chinatown, CA"


def test_service_area_priority_includes_direct_la_neighboring_counties() -> None:
    assert geocoding._service_area_priority({"address": {"county": "Los Angeles County"}}) == 0
    assert geocoding._service_area_priority({"address": {"county": "Orange County"}}) == 1
    assert geocoding._service_area_priority({"address": {"county": "Ventura County"}}) == 2
    assert geocoding._service_area_priority({"address": {"county": "San Bernardino County"}}) == 3
    assert geocoding._service_area_priority({"address": {"county": "Kern County"}}) == 4
    assert (
        geocoding._service_area_priority({"address": {"county": "Riverside County"}})
        == len(geocoding._SERVICE_AREA_COUNTY_PRIORITIES)
    )


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

    result = geocoding.geocode_place_cached("chinatown", cache_path=tmp_path / "place_cache.json")

    assert result is not None
    assert result["display_name"] == "Chinatown, Los Angeles, Los Angeles County, California, 90086, United States"
    assert result["lat"] == 34.0638402
    assert result["lon"] == -118.2358676
    assert calls[0]["params"]["q"] == "chinatown, CA"


def test_geocode_place_cached_keeps_exact_orange_county_address_ahead_of_la_county(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = [
        {
            "lat": "34.0505360",
            "lon": "-118.2478610",
            "class": "highway",
            "type": "residential",
            "addresstype": "road",
            "importance": 0.75,
            "display_name": "Union Street, Los Angeles, Los Angeles County, California, United States",
            "address": {
                "road": "Union Street",
                "city": "Los Angeles",
                "county": "Los Angeles County",
                "state": "California",
                "ISO3166-2-lvl4": "US-CA",
                "country": "United States",
                "country_code": "us",
            },
            "boundingbox": ["34.0455360", "34.0555360", "-118.2528610", "-118.2428610"],
        },
        {
            "lat": "33.8061200",
            "lon": "-117.9095340",
            "class": "building",
            "type": "apartments",
            "addresstype": "house",
            "importance": 0.2,
            "display_name": "1910, South Union Street, Platinum Triangle, Anaheim, Orange County, California, 92805, United States",
            "address": {
                "house_number": "1910",
                "road": "South Union Street",
                "city": "Anaheim",
                "county": "Orange County",
                "state": "California",
                "ISO3166-2-lvl4": "US-CA",
                "postcode": "92805",
                "country": "United States",
                "country_code": "us",
            },
            "boundingbox": ["33.8056200", "33.8066200", "-117.9100340", "-117.9090340"],
        },
    ]
    calls = []

    def fake_get(url: str, params: dict, timeout: int, headers: dict) -> FakeNominatimResponse:
        calls.append({"url": url, "params": params.copy(), "timeout": timeout, "headers": headers})
        return FakeNominatimResponse(payload)

    monkeypatch.setattr(geocoding.requests, "get", fake_get)

    result = geocoding.geocode_place_cached(
        "1910 S Union St #1073, Anaheim 92805",
        cache_path=tmp_path / "place_cache.json",
    )

    assert result is not None
    assert result["display_name"] == (
        "1910, South Union Street, Platinum Triangle, Anaheim, "
        "Orange County, California, 92805, United States"
    )
    assert result["lat"] == 33.80612
    assert result["lon"] == -117.909534
    assert calls[0]["params"]["q"] == "1910 S Union St #1073, Anaheim 92805, CA"
