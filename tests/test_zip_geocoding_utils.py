from pathlib import Path

import pandas as pd
import pytest

from functions import zip_geocoding_utils as geocoding


class FakeNominatimResponse:
    def __init__(self, payload: list[dict]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict]:
        return self._payload


def _zip_feature(
    zip_code: str,
    *,
    west: float,
    south: float,
    east: float,
    north: float,
) -> dict:
    """Build a rectangular ZIP polygon fixture."""
    return {
        "type": "Feature",
        "properties": {"ZIPCODE": zip_code},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]],
        },
    }


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


def test_get_zip_codes_for_place_returns_crosswalk_zips_without_polygons() -> None:
    crosswalk = {
        "ANAHEIM": {"92805"},
        "SAN CLEMENTE": {"92672", "92673", "92674"},
    }

    assert geocoding.get_zip_codes_for_place("Anaheim", crosswalk) == {"92805"}
    assert geocoding.get_zip_codes_for_place("San Clemente, CA", crosswalk) == {
        "92672",
        "92673",
        "92674",
    }
    assert geocoding.get_zip_features_for_place("Anaheim", crosswalk, []) == []


def test_resolve_locations_combines_tags_without_splitting_commas() -> None:
    crosswalk = {
        "PASADENA": {"91101"},
        "GLENDALE": {"91201"},
    }
    polygons = [
        _zip_feature(
            "91101",
            west=-118.16,
            south=34.13,
            east=-118.14,
            north=34.16,
        ),
        _zip_feature(
            "91201",
            west=-118.28,
            south=34.15,
            east=-118.25,
            north=34.19,
        ),
    ]
    geocode_calls: list[str] = []

    def fake_geocode(location: str) -> None:
        geocode_calls.append(location)
        return None

    payload, status = geocoding.resolve_locations_to_zip_boundaries(
        [" Pasadena, CA ", "<b>Glendale</b>", "pasadena, ca"],
        crosswalk,
        polygons,
        geocode=fake_geocode,
    )

    assert payload["zip_codes"] == ["91101", "91201"]
    assert [
        feature["properties"]["ZIPCODE"] for feature in payload["features"]
    ] == ["91101", "91201"]
    assert payload["error"] is None
    assert status == "Filtering by ZIP codes: 91101, 91201."
    assert geocode_calls == []


def test_resolve_locations_reports_partial_failures_without_dropping_matches() -> None:
    polygon = _zip_feature(
        "91101",
        west=-118.16,
        south=34.13,
        east=-118.14,
        north=34.16,
    )

    payload, status = geocoding.resolve_locations_to_zip_boundaries(
        ["Pasadena", "Atlantis"],
        {"PASADENA": {"91101"}},
        [polygon],
        geocode=lambda _location: None,
    )

    assert payload == {
        "zip_codes": ["91101"],
        "features": [polygon],
        "error": None,
    }
    assert status == (
        "Filtering by ZIP codes: 91101. "
        "Could not find a California location matching 'Atlantis'."
    )


def test_resolve_locations_expands_nearby_zips_for_each_tag() -> None:
    polygons = [
        _zip_feature(
            "91101",
            west=-118.16,
            south=34.13,
            east=-118.14,
            north=34.16,
        ),
        _zip_feature(
            "91102",
            west=-118.14,
            south=34.13,
            east=-118.12,
            north=34.16,
        ),
        _zip_feature(
            "91201",
            west=-118.28,
            south=34.15,
            east=-118.25,
            north=34.19,
        ),
        _zip_feature(
            "91202",
            west=-118.25,
            south=34.15,
            east=-118.22,
            north=34.19,
        ),
    ]
    geocoded = {
        "Pasadena": {
            "lat": 34.145,
            "lon": -118.15,
            "query": "Pasadena, CA",
            "bbox": [34.14, 34.15, -118.15, -118.13],
            "display_name": "Pasadena, California",
        },
        "Glendale": {
            "lat": 34.17,
            "lon": -118.26,
            "query": "Glendale, CA",
            "bbox": [34.16, 34.18, -118.26, -118.24],
            "display_name": "Glendale, California",
        },
    }

    payload, _status = geocoding.resolve_locations_to_zip_boundaries(
        ["Pasadena", "Glendale"],
        {"PASADENA": {"91101"}, "GLENDALE": {"91201"}},
        polygons,
        include_nearby=True,
        geocode=geocoded.get,
    )

    assert payload["zip_codes"] == ["91101", "91102", "91201", "91202"]
    assert len(payload["features"]) == 4
    assert payload["error"] is None


def test_load_zip_place_crosswalk_skips_pandas_string_missing_values(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "crosswalk.csv"
    pd.DataFrame(
        [
            {
                "USPS_ZIP_PREF_STATE": "CA",
                "USPS_ZIP_PREF_CITY": "Los Angeles",
                "ZIP": "90001",
            },
            {
                "USPS_ZIP_PREF_STATE": "CA",
                "USPS_ZIP_PREF_CITY": None,
                "ZIP": "90002",
            },
            {
                "USPS_ZIP_PREF_STATE": "CA",
                "USPS_ZIP_PREF_CITY": "Pasadena",
                "ZIP": None,
            },
        ]
    ).to_csv(csv_path, index=False)

    result = geocoding.load_zip_place_crosswalk(csv_path)

    assert result == {"LOS ANGELES": {"90001"}}


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
