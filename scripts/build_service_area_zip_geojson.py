from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests
from functions.data_paths import LARENTALS_DB_PATH, SOCAL_SERVICE_AREA_ZIP_CODES_PATH

DEFAULT_DB_PATH = LARENTALS_DB_PATH
DEFAULT_OUTPUT_PATH = SOCAL_SERVICE_AREA_ZIP_CODES_PATH
DEFAULT_TABLES = ("buy", "lease")
DEFAULT_ZCTA_LAYER_URL = (
    "https://services5.arcgis.com/FlidZxdI0LGC9vAw/arcgis/rest/services/"
    "California_Census_ZIP_Code_Tabulation_Areas/FeatureServer/11"
)
DEFAULT_CA_ZIP_AREA_LAYER_URL = (
    "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/"
    "USA_ZIP_Code_Areas_anaylsis/FeatureServer/0"
)
DEFAULT_USER_AGENT = "WhereToLive.LA/1.0 service-area ZIP builder"
ZIP_PATTERN = re.compile(r"\b(\d{5})(?:-\d{4})?(?:\.0)?\b")
SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """
    Parse command-line arguments for the service-area ZIP/ZCTA builder.

    Returns:
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Build the ZIP/ZCTA boundary GeoJSON used by listing location filters. "
            "The output is limited to normalized ZIP codes found in the SQLite DB."
        )
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite database path (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help=f"Output GeoJSON path (default: {DEFAULT_OUTPUT_PATH}).",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        default=list(DEFAULT_TABLES),
        help=f"Listing tables to scan for zip_code values (default: {' '.join(DEFAULT_TABLES)}).",
    )
    parser.add_argument(
        "--source-url",
        default=DEFAULT_ZCTA_LAYER_URL,
        help="ArcGIS FeatureServer layer URL for California Census ZCTAs.",
    )
    parser.add_argument(
        "--fallback-source-url",
        default=DEFAULT_CA_ZIP_AREA_LAYER_URL,
        help=(
            "ArcGIS FeatureServer layer URL used to backfill California ZIPs "
            "that do not have Census ZCTA polygons."
        ),
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Do not backfill missing California ZIP polygons from the fallback source.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=75,
        help="Number of ZIP codes to request from ArcGIS per query.",
    )
    parser.add_argument(
        "--geometry-precision",
        type=int,
        default=6,
        help="Decimal precision for returned polygon coordinates.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="HTTP timeout in seconds for each ArcGIS request.",
    )
    return parser.parse_args(argv)


def normalize_zip_code(value: object) -> str | None:
    """
    Normalize a raw DB ZIP value to a five-digit ZIP string.

    Args:
        value: Raw value from SQLite, often a string like "90001.0".

    Returns:
        Five-digit ZIP code, or ``None`` when no ZIP-like value is present.
    """
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    match = ZIP_PATTERN.search(text)
    if match is None:
        return None

    return match.group(1)


def require_safe_identifier(value: str) -> str:
    """
    Validate a SQLite identifier used in generated SQL.

    Args:
        value: Candidate table name.

    Returns:
        The same identifier when safe.
    """
    if SAFE_IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Unsafe SQLite identifier: {value!r}")
    return value


def iter_chunks(values: Sequence[str], chunk_size: int) -> Iterable[list[str]]:
    """
    Yield ``values`` in fixed-size chunks.

    Args:
        values: Ordered values to chunk.
        chunk_size: Maximum chunk length.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be greater than zero")

    for index in range(0, len(values), chunk_size):
        yield list(values[index : index + chunk_size])


def read_listing_zip_codes(
    db_path: Path,
    table_names: Sequence[str] = DEFAULT_TABLES,
) -> tuple[list[str], list[str]]:
    """
    Read and normalize ZIP codes from listing tables.

    Args:
        db_path: SQLite database path.
        table_names: Tables with a ``zip_code`` column.

    Returns:
        Tuple of ``(zip_codes, skipped_raw_values)``.
    """
    zip_codes: set[str] = set()
    skipped_raw_values: Counter[str] = Counter()

    with sqlite3.connect(db_path) as conn:
        for table_name in table_names:
            safe_table = require_safe_identifier(table_name)
            rows = conn.execute(f"SELECT zip_code FROM {safe_table}").fetchall()
            for (raw_zip,) in rows:
                normalized = normalize_zip_code(raw_zip)
                if normalized:
                    zip_codes.add(normalized)
                elif raw_zip is not None and str(raw_zip).strip():
                    skipped_raw_values[str(raw_zip).strip()] += 1

    return sorted(zip_codes), sorted(skipped_raw_values)


def arcgis_where_for_zips(zip_codes: Sequence[str], field_name: str = "GEOID") -> str:
    """
    Build a safe ArcGIS SQL where clause for five-digit ZIP codes.

    Args:
        zip_codes: Normalized ZIP codes.
        field_name: ZIP-code field to query.

    Returns:
        SQL where clause.
    """
    if not zip_codes:
        return "1=0"

    invalid = [zip_code for zip_code in zip_codes if not re.fullmatch(r"\d{5}", zip_code)]
    if invalid:
        raise ValueError(f"ZIP codes must be five digits: {invalid!r}")
    require_safe_identifier(field_name)

    quoted = ",".join(f"'{zip_code}'" for zip_code in zip_codes)
    return f"{field_name} IN ({quoted})"


def fetch_zcta_features(
    zip_codes: Sequence[str],
    source_url: str = DEFAULT_ZCTA_LAYER_URL,
    *,
    chunk_size: int = 75,
    geometry_precision: int = 6,
    timeout: int = 120,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Fetch California ZCTA polygons for ZIP codes from ArcGIS.

    Args:
        zip_codes: Normalized ZIP codes to fetch.
        source_url: ArcGIS FeatureServer layer URL.
        chunk_size: Number of ZIP codes per query.
        geometry_precision: Decimal precision for polygon coordinates.
        timeout: HTTP timeout in seconds.

    Returns:
        Tuple of ``(features, missing_zip_codes)``.
    """
    features_by_zip: dict[str, dict[str, Any]] = {}
    query_url = f"{source_url.rstrip('/')}/query"
    headers = {"User-Agent": DEFAULT_USER_AGENT}

    for chunk in iter_chunks(list(zip_codes), chunk_size):
        response = requests.post(
            query_url,
            data={
                "f": "geojson",
                "where": arcgis_where_for_zips(chunk),
                "outFields": "GEOID,ZCTA5",
                "returnGeometry": "true",
                "geometryPrecision": str(geometry_precision),
            },
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if "error" in payload:
            raise RuntimeError(f"ArcGIS query failed: {payload['error']}")

        for feature in payload.get("features") or []:
            properties = feature.get("properties") or {}
            zip_code = properties.get("GEOID") or properties.get("ZCTA5")
            zip_code = normalize_zip_code(zip_code)
            if not zip_code:
                continue

            features_by_zip[zip_code] = {
                "type": "Feature",
                "properties": {"ZIPCODE": zip_code},
                "geometry": feature.get("geometry"),
            }

    missing_zip_codes = sorted(set(zip_codes) - set(features_by_zip))
    features = [features_by_zip[zip_code] for zip_code in sorted(features_by_zip)]
    return features, missing_zip_codes


def fetch_ca_zip_area_features(
    zip_codes: Sequence[str],
    source_url: str = DEFAULT_CA_ZIP_AREA_LAYER_URL,
    *,
    chunk_size: int = 75,
    geometry_precision: int = 6,
    timeout: int = 120,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Fetch California ZIP area polygons for ZIPs missing from Census ZCTAs.

    Args:
        zip_codes: Normalized ZIP codes to fetch.
        source_url: ArcGIS FeatureServer layer URL.
        chunk_size: Number of ZIP codes per query.
        geometry_precision: Decimal precision for polygon coordinates.
        timeout: HTTP timeout in seconds.

    Returns:
        Tuple of ``(features, missing_zip_codes)``.
    """
    features_by_zip: dict[str, dict[str, Any]] = {}
    query_url = f"{source_url.rstrip('/')}/query"
    headers = {"User-Agent": DEFAULT_USER_AGENT}

    for chunk in iter_chunks(list(zip_codes), chunk_size):
        response = requests.post(
            query_url,
            data={
                "f": "geojson",
                "where": f"{arcgis_where_for_zips(chunk, 'ZIP_CODE')} AND STATE = 'CA'",
                "outFields": "ZIP_CODE,STATE",
                "returnGeometry": "true",
                "geometryPrecision": str(geometry_precision),
            },
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if "error" in payload:
            raise RuntimeError(f"ArcGIS fallback query failed: {payload['error']}")

        for feature in payload.get("features") or []:
            properties = feature.get("properties") or {}
            zip_code = normalize_zip_code(properties.get("ZIP_CODE"))
            if not zip_code:
                continue

            features_by_zip[zip_code] = {
                "type": "Feature",
                "properties": {"ZIPCODE": zip_code},
                "geometry": feature.get("geometry"),
            }

    missing_zip_codes = sorted(set(zip_codes) - set(features_by_zip))
    features = [features_by_zip[zip_code] for zip_code in sorted(features_by_zip)]
    return features, missing_zip_codes


def build_service_area_geojson(args: argparse.Namespace) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Build the final service-area ZIP/ZCTA GeoJSON payload.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Tuple of ``(payload, db_zip_codes, skipped_raw_values)``.
    """
    db_path = Path(args.db).expanduser()
    zip_codes, skipped_raw_values = read_listing_zip_codes(db_path, args.tables)
    primary_features, primary_missing_zip_codes = fetch_zcta_features(
        zip_codes,
        args.source_url,
        chunk_size=args.chunk_size,
        geometry_precision=args.geometry_precision,
        timeout=args.timeout,
    )
    features_by_zip = {
        feature["properties"]["ZIPCODE"]: feature
        for feature in primary_features
        if feature.get("properties", {}).get("ZIPCODE")
    }
    fallback_zip_codes: list[str] = []

    if primary_missing_zip_codes and not args.no_fallback and args.fallback_source_url:
        fallback_features, _fallback_missing_zip_codes = fetch_ca_zip_area_features(
            primary_missing_zip_codes,
            args.fallback_source_url,
            chunk_size=args.chunk_size,
            geometry_precision=args.geometry_precision,
            timeout=args.timeout,
        )
        fallback_zip_codes = [
            feature["properties"]["ZIPCODE"]
            for feature in fallback_features
            if feature.get("properties", {}).get("ZIPCODE")
        ]
        for feature in fallback_features:
            zip_code = feature.get("properties", {}).get("ZIPCODE")
            if zip_code:
                features_by_zip[zip_code] = feature

    features = [features_by_zip[zip_code] for zip_code in sorted(features_by_zip)]
    missing_zip_codes = sorted(set(zip_codes) - set(features_by_zip))

    payload: dict[str, Any] = {
        "type": "FeatureCollection",
        "metadata": {
            "primary_source": "California Census ZIP Code Tabulation Areas (ZCTA)",
            "primary_source_url": args.source_url,
            "fallback_source": "CA Zip Code Boundaries",
            "fallback_source_url": None if args.no_fallback else args.fallback_source_url,
            "db_path": str(db_path),
            "tables": list(args.tables),
            "db_zip_count": len(zip_codes),
            "feature_count": len(features),
            "primary_missing_zip_codes": primary_missing_zip_codes,
            "fallback_zip_codes": sorted(fallback_zip_codes),
            "missing_zip_codes": missing_zip_codes,
            "skipped_raw_zip_values": skipped_raw_values,
        },
        "features": features,
    }
    return payload, zip_codes, skipped_raw_values


def write_geojson(payload: dict[str, Any], output_path: Path) -> None:
    """
    Write a compact ASCII GeoJSON payload.

    Args:
        payload: FeatureCollection payload.
        output_path: Destination path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    payload, zip_codes, skipped_raw_values = build_service_area_geojson(args)
    output_path = Path(args.output).expanduser()
    write_geojson(payload, output_path)

    metadata = payload["metadata"]
    print(
        f"Wrote {metadata['feature_count']:,} ZIP/ZCTA features to {output_path} "
        f"from {metadata['db_zip_count']:,} normalized DB ZIPs."
    )
    if metadata["fallback_zip_codes"]:
        print(f"Backfilled CA ZIP polygons: {', '.join(metadata['fallback_zip_codes'])}")
    if metadata["missing_zip_codes"]:
        print(f"Missing polygons after fallback: {', '.join(metadata['missing_zip_codes'])}")
    if skipped_raw_values:
        print(f"Skipped non-ZIP raw values: {', '.join(skipped_raw_values)}")
    if zip_codes and metadata["feature_count"] == 0:
        raise SystemExit("No ZIP/ZCTA features were fetched.")


if __name__ == "__main__":
    main()
