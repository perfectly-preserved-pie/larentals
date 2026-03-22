from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

LOCATION_PATTERN = re.compile(r"\((-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\)")
DEFAULT_VALID_BOUNDS = (-125.0, -113.0, 32.0, 35.5)
DEFAULT_NAICS_CODES = ("445100", "445110")
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
    Parse command-line arguments for the active-businesses GeoJSON builder.

    Returns:
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Build a filtered GeoJSON point dataset from the City of Los Angeles "
            "active businesses CSV."
        )
    )
    parser.add_argument(
        "--input",
        default="assets/datasets/Listing_of_Active_Businesses_20260321.csv",
        help="Path to the source active-businesses CSV.",
    )
    parser.add_argument(
        "--output",
        default="assets/datasets/supermarkets_and_grocery_stores.geojson",
        help="Path to the output GeoJSON file.",
    )
    parser.add_argument(
        "--naics",
        nargs="+",
        default=list(DEFAULT_NAICS_CODES),
        help="One or more NAICS codes to include.",
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
    Normalize raw CSV cell values to trimmed strings or `None`.

    Args:
        value: Raw CSV cell value.

    Returns:
        Trimmed string value, or `None` when the cell is blank.
    """
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


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


def build_feature(row: dict[str, str]) -> dict[str, Any] | None:
    """
    Convert one CSV row into a GeoJSON point feature.

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
    if not within_bounds(latitude=latitude, longitude=longitude):
        return None

    street_address = normalize_value(row.get("STREET ADDRESS"))
    city = normalize_value(row.get("CITY"))
    zip_code = normalize_value(row.get("ZIP CODE"))
    address_parts = [part for part in (street_address, city, zip_code) if part]
    full_address = ", ".join(address_parts) if address_parts else None

    properties = {
        "location_account_number": normalize_value(row.get("LOCATION ACCOUNT #")),
        "business_name": business_name,
        "dba_name": dba_name,
        "street_address": street_address,
        "city": city,
        "zip_code": zip_code,
        "full_address": full_address,
        "naics": normalize_value(row.get("NAICS")),
        "primary_naics_description": normalize_value(row.get("PRIMARY NAICS DESCRIPTION")),
        "council_district": normalize_value(row.get("COUNCIL DISTRICT")),
        "location_start_date": normalize_value(row.get("LOCATION START DATE")),
        "location_description": normalize_value(row.get("LOCATION DESCRIPTION")),
        "latitude": latitude,
        "longitude": longitude,
    }

    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Point",
            "coordinates": [longitude, latitude],
        },
    }


def build_feature_collection(
    input_path: Path,
    included_naics_codes: set[str],
) -> dict[str, Any]:
    """
    Build a GeoJSON FeatureCollection from a filtered active-businesses CSV.

    Args:
        input_path: Path to the source CSV file.
        included_naics_codes: Set of NAICS codes that should be retained.

    Returns:
        GeoJSON FeatureCollection containing only rows that match the NAICS filter
        and contain valid point coordinates.
    """
    features: list[dict[str, Any]] = []
    with input_path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            naics_code = normalize_value(row.get("NAICS"))
            if naics_code not in included_naics_codes:
                continue

            feature = build_feature(row)
            if feature is not None:
                features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def main() -> None:
    """
    Build and write a filtered GeoJSON dataset from the active-businesses CSV.
    """
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    included_naics_codes = {code.strip() for code in args.naics if code.strip()}

    feature_collection = build_feature_collection(
        input_path=input_path,
        included_naics_codes=included_naics_codes,
    )

    output_path.write_text(json.dumps(feature_collection), encoding="utf-8")
    print(
        f"Wrote {len(feature_collection['features'])} features to {output_path} "
        f"for NAICS codes {sorted(included_naics_codes)}."
    )


if __name__ == "__main__":
    main()
