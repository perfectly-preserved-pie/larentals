from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path
from typing import Any

import requests

LOCATION_PATTERN = re.compile(r"\((-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\)")
DEFAULT_VALID_BOUNDS = (-125.0, -113.0, 32.0, 35.5)
DEFAULT_NAICS_CODES = ("445100", "445110")
DEFAULT_OUTPUT_PATH = Path("assets/datasets/supermarkets_and_grocery_stores.geojson")
DEFAULT_GEOCODE_CACHE_PATH = Path("assets/datasets/santa_monica_supermarkets_geocode_cache.json")
DEFAULT_SANTA_MONICA_RESOURCE_ID = "484fe63d-a388-43fa-9714-8601254afcf0"
DEFAULT_SANTA_MONICA_API_URL = "https://data.santamonica.gov/api/3/action/datastore_search_sql"
DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_NOMINATIM_USER_AGENT = "WhereToLive.LA/1.0 (Codex supermarket dataset builder)"
DEFAULT_NOMINATIM_DELAY_SECONDS = 1.1
SANTA_MONICA_GROCERY_BUSINESS_TYPE = "Grocery, Food Products"
EXCLUDED_BUSINESS_NAME_PATTERNS = (
    re.compile(r"\b(?:chevron|cheveron|shell|exxon|mobil|valero)\b", re.IGNORECASE),
    re.compile(r"\bgas\b", re.IGNORECASE),
    re.compile(r"\bfuels?\b", re.IGNORECASE),
    re.compile(r"\bpetrol(?:eum)?\b", re.IGNORECASE),
    re.compile(r"\bstations?\b", re.IGNORECASE),
    re.compile(r"\barco\b(?=\s*(?:#\s*\d+|\d+|gas\b|stations?\b))", re.IGNORECASE),
)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the merged supermarket GeoJSON builder.

    Returns:
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Build a merged GeoJSON point dataset for supermarkets and grocery stores "
            "from City of Los Angeles business data plus Santa Monica grocery licenses."
        )
    )
    parser.add_argument(
        "--input",
        default="assets/datasets/Listing_of_Active_Businesses_20260321.csv",
        help="Path to the source City of Los Angeles active-businesses CSV.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Path to the output GeoJSON file.",
    )
    parser.add_argument(
        "--naics",
        nargs="+",
        default=list(DEFAULT_NAICS_CODES),
        help="One or more Los Angeles NAICS codes to include.",
    )
    parser.add_argument(
        "--skip-santa-monica",
        action="store_true",
        help="Skip fetching and merging Santa Monica grocery-license data.",
    )
    parser.add_argument(
        "--santa-monica-api-url",
        default=DEFAULT_SANTA_MONICA_API_URL,
        help="Santa Monica CKAN SQL API endpoint.",
    )
    parser.add_argument(
        "--santa-monica-resource-id",
        default=DEFAULT_SANTA_MONICA_RESOURCE_ID,
        help="Santa Monica active-business-licenses resource id.",
    )
    parser.add_argument(
        "--geocode-cache",
        default=str(DEFAULT_GEOCODE_CACHE_PATH),
        help="Path to the JSON cache of Nominatim geocode results.",
    )
    parser.add_argument(
        "--nominatim-url",
        default=DEFAULT_NOMINATIM_URL,
        help="Nominatim search endpoint.",
    )
    parser.add_argument(
        "--nominatim-user-agent",
        default=DEFAULT_NOMINATIM_USER_AGENT,
        help="Custom User-Agent sent to Nominatim requests.",
    )
    parser.add_argument(
        "--nominatim-delay-seconds",
        type=float,
        default=DEFAULT_NOMINATIM_DELAY_SECONDS,
        help="Delay between uncached Nominatim lookups to respect rate limits.",
    )
    return parser.parse_args()


def parse_location(location_value: str) -> tuple[float, float] | None:
    """
    Parse the source CSV LOCATION column into latitude/longitude values.

    Args:
        location_value: Raw LOCATION string from the CSV, e.g. "(34.10, -118.23)".

    Returns:
        Tuple of `(latitude, longitude)` when parseable, else `None`.
    """
    match = LOCATION_PATTERN.search(location_value or "")
    if match is None:
        return None

    latitude = float(match.group(1))
    longitude = float(match.group(2))
    return latitude, longitude


def within_bounds(
    latitude: float,
    longitude: float,
    bounds: tuple[float, float, float, float] = DEFAULT_VALID_BOUNDS,
) -> bool:
    """
    Check whether a point falls inside the accepted lon/lat bounding box.

    Args:
        latitude: Latitude value to test.
        longitude: Longitude value to test.
        bounds: Tuple of `(min_lon, max_lon, min_lat, max_lat)`.

    Returns:
        `True` when the point is inside the supplied bounds, else `False`.
    """
    min_lon, max_lon, min_lat, max_lat = bounds
    return min_lon <= longitude <= max_lon and min_lat <= latitude <= max_lat


def normalize_value(value: str | None) -> str | None:
    """
    Normalize raw string values to trimmed strings or `None`.

    Args:
        value: Raw string value.

    Returns:
        Trimmed string value, or `None` when the input is blank.
    """
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def build_full_address(parts: list[str | None]) -> str | None:
    """
    Join address fragments into a display-ready address string.

    Args:
        parts: Ordered address fragments.

    Returns:
        Comma-separated address string, or `None` when all parts are blank.
    """
    normalized_parts = [part for part in (normalize_value(value) for value in parts) if part]
    return ", ".join(normalized_parts) if normalized_parts else None


def should_exclude_business(
    dba_name: str | None,
    business_name: str | None,
) -> bool:
    """
    Check whether a business name looks like a gas-station-style record.

    Args:
        dba_name: Display-facing DBA name from the source dataset.
        business_name: Registered business name from the source dataset.

    Returns:
        `True` when the business should be excluded from the supermarket layer.
    """
    search_value = " | ".join(
        value
        for value in (
            normalize_value(dba_name),
            normalize_value(business_name),
        )
        if value
    )

    return any(
        pattern.search(search_value) is not None
        for pattern in EXCLUDED_BUSINESS_NAME_PATTERNS
    )


def build_geojson_feature(
    *,
    properties: dict[str, Any],
    latitude: float,
    longitude: float,
) -> dict[str, Any] | None:
    """
    Build a GeoJSON point feature from normalized properties and coordinates.

    Args:
        properties: GeoJSON feature properties.
        latitude: Point latitude.
        longitude: Point longitude.

    Returns:
        GeoJSON `Feature` dict, or `None` when the point falls outside bounds.
    """
    if not within_bounds(latitude=latitude, longitude=longitude):
        return None

    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Point",
            "coordinates": [longitude, latitude],
        },
    }


def build_la_feature(row: dict[str, str]) -> dict[str, Any] | None:
    """
    Convert one Los Angeles CSV row into a GeoJSON point feature.

    Args:
        row: CSV row keyed by source column names.

    Returns:
        A GeoJSON `Feature` dict, or `None` when the row is unusable.
    """
    business_name = normalize_value(row.get("BUSINESS NAME"))
    dba_name = normalize_value(row.get("DBA NAME"))
    if should_exclude_business(dba_name=dba_name, business_name=business_name):
        return None

    parsed_location = parse_location(row.get("LOCATION", ""))
    if parsed_location is None:
        return None

    latitude, longitude = parsed_location
    street_address = normalize_value(row.get("STREET ADDRESS"))
    city = normalize_value(row.get("CITY"))
    zip_code = normalize_value(row.get("ZIP CODE"))
    full_address = build_full_address([street_address, city, zip_code])

    properties = {
        "source": "Los Angeles",
        "location_account_number": normalize_value(row.get("LOCATION ACCOUNT #")),
        "license_number": None,
        "business_name": business_name,
        "dba_name": dba_name,
        "street_address": street_address,
        "city": city,
        "state": "CA",
        "zip_code": zip_code,
        "full_address": full_address,
        "naics": normalize_value(row.get("NAICS")),
        "primary_naics_description": normalize_value(row.get("PRIMARY NAICS DESCRIPTION")),
        "business_type": None,
        "council_district": normalize_value(row.get("COUNCIL DISTRICT")),
        "location_start_date": normalize_value(row.get("LOCATION START DATE")),
        "location_description": normalize_value(row.get("LOCATION DESCRIPTION")),
        "business_status": None,
        "license_status": None,
        "latitude": latitude,
        "longitude": longitude,
    }

    return build_geojson_feature(
        properties=properties,
        latitude=latitude,
        longitude=longitude,
    )


def build_la_features(
    input_path: Path,
    included_naics_codes: set[str],
) -> list[dict[str, Any]]:
    """
    Build Los Angeles supermarket features from the active-businesses CSV.

    Args:
        input_path: Path to the source CSV file.
        included_naics_codes: Set of NAICS codes that should be retained.

    Returns:
        List of GeoJSON point features for qualifying Los Angeles businesses.
    """
    features: list[dict[str, Any]] = []
    with input_path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            naics_code = normalize_value(row.get("NAICS"))
            if naics_code not in included_naics_codes:
                continue

            feature = build_la_feature(row)
            if feature is not None:
                features.append(feature)
    return features


def load_existing_features(output_path: Path) -> list[dict[str, Any]]:
    """
    Load the current derived GeoJSON as a fallback base dataset.

    Args:
        output_path: Path to the derived supermarket GeoJSON file.

    Returns:
        Existing GeoJSON features, or an empty list when the file is absent.
    """
    if not output_path.exists():
        return []

    with output_path.open(encoding="utf-8") as geojson_file:
        existing_data = json.load(geojson_file)

    existing_features = existing_data.get("features", [])
    for feature in existing_features:
        properties = feature.setdefault("properties", {})
        properties.setdefault("source", "Los Angeles")
        properties.setdefault("state", "CA")

    return existing_features


def fetch_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any],
) -> dict[str, Any]:
    """
    Perform a JSON GET request and return the parsed payload.

    Args:
        session: Reusable HTTP session.
        url: Request URL.
        params: Query-string parameters.

    Returns:
        Parsed JSON response.

    Raises:
        requests.HTTPError: If the request fails.
    """
    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def fetch_santa_monica_grocery_records(
    session: requests.Session,
    *,
    api_url: str,
    resource_id: str,
) -> list[dict[str, Any]]:
    """
    Fetch Santa Monica grocery-license records from the CKAN SQL API.

    Args:
        session: Reusable HTTP session.
        api_url: Santa Monica CKAN datastore SQL endpoint.
        resource_id: Active-business-licenses resource id.

    Returns:
        List of Santa Monica grocery-license records.
    """
    sql = (
        f'SELECT license_number, dba, address, city, state, zip_code, business_type, '
        f'business_status, license_status FROM "{resource_id}" '
        f"WHERE business_type = '{SANTA_MONICA_GROCERY_BUSINESS_TYPE}' "
        f"AND city = 'SANTA MONICA' ORDER BY dba"
    )
    payload = fetch_json(session, api_url, params={"sql": sql})
    return payload["result"]["records"]


def load_geocode_cache(cache_path: Path) -> dict[str, Any]:
    """
    Load cached Nominatim geocoding results from disk.

    Args:
        cache_path: Path to the JSON cache file.

    Returns:
        Cache mapping normalized addresses to geocode results or `None`.
    """
    if not cache_path.exists():
        return {}

    with cache_path.open(encoding="utf-8") as cache_file:
        return json.load(cache_file)


def save_geocode_cache(cache_path: Path, cache: dict[str, Any]) -> None:
    """
    Persist the Nominatim geocode cache to disk.

    Args:
        cache_path: Path to the JSON cache file.
        cache: Cache content to save.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def geocode_with_nominatim(
    session: requests.Session,
    *,
    nominatim_url: str,
    street_address: str,
    city: str,
    state: str,
    zip_code: str | None,
    delay_seconds: float,
    cache: dict[str, Any],
    last_request_timestamp: float | None,
) -> tuple[tuple[float, float] | None, float | None]:
    """
    Geocode a single address using cached Nominatim lookups.

    Args:
        session: Reusable HTTP session.
        nominatim_url: Nominatim search endpoint.
        street_address: Street-address line to geocode.
        city: City name.
        state: State name or abbreviation.
        zip_code: Optional ZIP code.
        delay_seconds: Delay between uncached Nominatim requests.
        cache: In-memory geocode cache.
        last_request_timestamp: Monotonic timestamp of the previous uncached request.

    Returns:
        Tuple of geocode result `(latitude, longitude)` or `None`, plus the latest
        uncached request timestamp.
    """
    full_lookup_address = build_full_address([street_address, city, state, zip_code])
    if full_lookup_address is None:
        return None, last_request_timestamp

    cache_key = full_lookup_address.lower()
    cached_value = cache.get(cache_key)
    if cache_key in cache:
        if cached_value is None:
            return None, last_request_timestamp

        return (
            float(cached_value["latitude"]),
            float(cached_value["longitude"]),
        ), last_request_timestamp

    if last_request_timestamp is not None:
        elapsed = time.monotonic() - last_request_timestamp
        if elapsed < delay_seconds:
            time.sleep(delay_seconds - elapsed)

    response = session.get(
        nominatim_url,
        params={
            "street": street_address,
            "city": city,
            "state": state,
            "postalcode": zip_code,
            "country": "USA",
            "countrycodes": "us",
            "format": "jsonv2",
            "limit": 1,
        },
        timeout=60,
    )
    last_request_timestamp = time.monotonic()
    response.raise_for_status()
    results = response.json()

    if not results:
        cache[cache_key] = None
        return None, last_request_timestamp

    best_match = results[0]
    geocode_result = (
        float(best_match["lat"]),
        float(best_match["lon"]),
    )
    cache[cache_key] = {
        "latitude": geocode_result[0],
        "longitude": geocode_result[1],
        "display_name": best_match.get("display_name"),
    }
    return geocode_result, last_request_timestamp


def build_santa_monica_features(
    session: requests.Session,
    *,
    api_url: str,
    resource_id: str,
    nominatim_url: str,
    delay_seconds: float,
    cache_path: Path,
) -> list[dict[str, Any]]:
    """
    Fetch, geocode, and convert Santa Monica grocery-license records into features.

    Args:
        session: Reusable HTTP session.
        api_url: Santa Monica CKAN datastore SQL endpoint.
        resource_id: Active-business-licenses resource id.
        nominatim_url: Nominatim search endpoint.
        delay_seconds: Delay between uncached Nominatim requests.
        cache_path: Path to the JSON geocode cache file.

    Returns:
        List of GeoJSON point features for Santa Monica grocery businesses.
    """
    records = fetch_santa_monica_grocery_records(
        session,
        api_url=api_url,
        resource_id=resource_id,
    )
    cache = load_geocode_cache(cache_path)
    features: list[dict[str, Any]] = []
    last_request_timestamp: float | None = None

    for record in records:
        dba_name = normalize_value(record.get("dba"))
        business_name = dba_name
        if should_exclude_business(dba_name=dba_name, business_name=business_name):
            continue

        street_address = normalize_value(record.get("address"))
        city = normalize_value(record.get("city"))
        state = normalize_value(record.get("state")) or "CA"
        zip_code = normalize_value(record.get("zip_code"))
        if street_address is None or city is None:
            continue

        geocode_result, last_request_timestamp = geocode_with_nominatim(
            session,
            nominatim_url=nominatim_url,
            street_address=street_address,
            city=city,
            state=state,
            zip_code=zip_code,
            delay_seconds=delay_seconds,
            cache=cache,
            last_request_timestamp=last_request_timestamp,
        )
        if geocode_result is None:
            continue

        latitude, longitude = geocode_result
        full_address = build_full_address([street_address, city, zip_code])
        properties = {
            "source": "Santa Monica",
            "location_account_number": normalize_value(record.get("license_number")),
            "license_number": normalize_value(record.get("license_number")),
            "business_name": business_name,
            "dba_name": dba_name,
            "street_address": street_address,
            "city": city,
            "state": state,
            "zip_code": zip_code,
            "full_address": full_address,
            "naics": None,
            "primary_naics_description": None,
            "business_type": normalize_value(record.get("business_type")),
            "council_district": None,
            "location_start_date": None,
            "location_description": None,
            "business_status": normalize_value(record.get("business_status")),
            "license_status": normalize_value(record.get("license_status")),
            "latitude": latitude,
            "longitude": longitude,
        }

        feature = build_geojson_feature(
            properties=properties,
            latitude=latitude,
            longitude=longitude,
        )
        if feature is not None:
            features.append(feature)

    save_geocode_cache(cache_path, cache)
    return features


def feature_dedup_key(feature: dict[str, Any]) -> str:
    """
    Build a stable deduplication key for a supermarket feature.

    Args:
        feature: GeoJSON feature to key.

    Returns:
        String key that identifies the feature across rebuilds.
    """
    properties = feature.get("properties", {})
    source = normalize_value(properties.get("source")) or ""
    license_number = normalize_value(properties.get("license_number"))
    location_account_number = normalize_value(properties.get("location_account_number"))
    full_address = normalize_value(properties.get("full_address")) or ""
    dba_name = normalize_value(properties.get("dba_name")) or ""

    if source.lower() == "santa monica" and license_number is not None:
        return f"sm:{license_number}"
    if location_account_number is not None:
        return f"la:{location_account_number}"
    return f"fallback:{source.lower()}|{full_address.lower()}|{dba_name.lower()}"


def merge_features(feature_groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """
    Merge multiple feature lists while deduplicating by source-aware keys.

    Args:
        feature_groups: Ordered feature groups to merge.

    Returns:
        Deduplicated list of GeoJSON features.
    """
    merged_by_key: dict[str, dict[str, Any]] = {}
    for features in feature_groups:
        for feature in features:
            merged_by_key[feature_dedup_key(feature)] = feature
    return list(merged_by_key.values())


def build_feature_collection(
    *,
    input_path: Path,
    output_path: Path,
    included_naics_codes: set[str],
    include_santa_monica: bool,
    santa_monica_api_url: str,
    santa_monica_resource_id: str,
    geocode_cache_path: Path,
    nominatim_url: str,
    nominatim_user_agent: str,
    nominatim_delay_seconds: float,
) -> dict[str, Any]:
    """
    Build the merged supermarket GeoJSON FeatureCollection.

    Args:
        input_path: Path to the Los Angeles source CSV.
        output_path: Path to the derived output GeoJSON.
        included_naics_codes: Los Angeles NAICS codes to include.
        include_santa_monica: Whether to merge Santa Monica grocery records.
        santa_monica_api_url: Santa Monica CKAN datastore SQL endpoint.
        santa_monica_resource_id: Active-business-licenses resource id.
        geocode_cache_path: Path to the JSON geocode cache file.
        nominatim_url: Nominatim search endpoint.
        nominatim_user_agent: Custom Nominatim User-Agent string.
        nominatim_delay_seconds: Delay between uncached Nominatim requests.

    Returns:
        GeoJSON FeatureCollection containing the merged supermarket features.
    """
    if input_path.exists():
        base_features = build_la_features(
            input_path=input_path,
            included_naics_codes=included_naics_codes,
        )
    else:
        base_features = load_existing_features(output_path)
        print(
            f"Input CSV {input_path} not found. Using existing {output_path} as the base dataset."
        )

    feature_groups = [base_features]
    if include_santa_monica:
        session = requests.Session()
        session.headers.update({"User-Agent": nominatim_user_agent})
        santa_monica_features = build_santa_monica_features(
            session,
            api_url=santa_monica_api_url,
            resource_id=santa_monica_resource_id,
            nominatim_url=nominatim_url,
            delay_seconds=nominatim_delay_seconds,
            cache_path=geocode_cache_path,
        )
        feature_groups.append(santa_monica_features)

    return {
        "type": "FeatureCollection",
        "features": merge_features(feature_groups),
    }


def main() -> None:
    """
    Build and write the merged supermarket GeoJSON dataset.
    """
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    geocode_cache_path = Path(args.geocode_cache)
    included_naics_codes = {code.strip() for code in args.naics if code.strip()}

    feature_collection = build_feature_collection(
        input_path=input_path,
        output_path=output_path,
        included_naics_codes=included_naics_codes,
        include_santa_monica=not args.skip_santa_monica,
        santa_monica_api_url=args.santa_monica_api_url,
        santa_monica_resource_id=args.santa_monica_resource_id,
        geocode_cache_path=geocode_cache_path,
        nominatim_url=args.nominatim_url,
        nominatim_user_agent=args.nominatim_user_agent,
        nominatim_delay_seconds=args.nominatim_delay_seconds,
    )

    output_path.write_text(json.dumps(feature_collection), encoding="utf-8")
    print(
        f"Wrote {len(feature_collection['features'])} features to {output_path} "
        f"for Los Angeles NAICS codes {sorted(included_naics_codes)} "
        f"with Santa Monica merge {'enabled' if not args.skip_santa_monica else 'disabled'}."
    )


if __name__ == "__main__":
    main()
