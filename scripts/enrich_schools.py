from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence

import geopandas as gpd
import pandas as pd
import pyogrio
import requests

from functions.listing_enrichment_utils import (
    DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_PATH,
    DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL,
    DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_PATH,
    DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_URL,
    DEFAULT_DB_PATH,
    DEFAULT_REGION_NAME,
    ListingTable,
    build_source_version,
    expanded_total_bounds,
    guess_column_name,
    is_remote_url,
    load_listing_points,
    now_utc_iso,
    read_geospatial_dataset,
    resolve_region_bbox,
    upsert_listing_enrichment_rows,
)

DEFAULT_SCHOOL_NAME_CANDIDATES = (
    "School",
    "SchoolName",
    "School_Name",
    "school_name",
    "name",
    "Name",
)
DEFAULT_GRADE_SPAN_CANDIDATES = (
    "GSoffered",
    "GS_OFFERED",
    "grades_offered",
    "grade_span",
    "GradeSpan",
    "GRADES",
)
DEFAULT_LOW_GRADE_CANDIDATES = (
    "low_grade",
    "Low_Grade",
    "grade_low",
    "lowest_grade",
    "GSLow",
)
DEFAULT_HIGH_GRADE_CANDIDATES = (
    "high_grade",
    "High_Grade",
    "grade_high",
    "highest_grade",
    "GSHigh",
)
DEFAULT_DISTRICT_NAME_CANDIDATES = (
    "DistrictName",
    "district_name",
    "districtname",
    "Name",
    "name",
)
DEFAULT_DISTRICT_TYPE_CANDIDATES = (
    "DistrictType",
    "district_type",
    "TYPE",
    "Type",
    "EntityType",
)

GRADE_TOKEN_MAP = {
    "PK": -1,
    "P": -1,
    "PS": -1,
    "PREK": -1,
    "TK": 0,
    "K": 0,
    "KG": 0,
}
DEFAULT_USER_AGENT = "WhereToLive.LA/1.0 school enrichment downloader"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Populate buy_enrichment / lease_enrichment with school district and "
            "nearest elementary, middle, and high school fields."
        )
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--listing-table",
        choices=("buy", "lease", "all"),
        default="all",
        help="Listing table to enrich (default: all).",
    )
    parser.add_argument(
        "--region",
        choices=("southern-california", "all"),
        default=DEFAULT_REGION_NAME,
        help=(
            "Geographic scope used to pre-filter listings and dataset queries "
            f"(default: {DEFAULT_REGION_NAME})."
        ),
    )
    parser.add_argument(
        "--schools-path",
        default=str(DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_PATH),
        help=(
            "Path to the local school GeoPackage artifact. When the default path is "
            "missing, the script downloads the official California Public Schools "
            f"GeoPackage first (default: {DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_PATH})."
        ),
    )
    parser.add_argument("--schools-layer", default=None, help="Optional school layer name.")
    parser.add_argument(
        "--districts-path",
        default=str(DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_PATH),
        help=(
            "Path to the local district GeoJSON artifact. When the default path is "
            "missing, the script downloads the official California School District "
            f"Areas GeoJSON first (default: {DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_PATH})."
        ),
    )
    parser.add_argument("--districts-layer", default=None, help="Optional district layer name.")
    parser.add_argument(
        "--skip-districts",
        action="store_true",
        help="Skip district polygon enrichment and only compute nearest schools.",
    )
    parser.add_argument("--school-name-column", default=None, help="Override the school name column.")
    parser.add_argument("--grade-span-column", default=None, help="Override the grade span column.")
    parser.add_argument("--low-grade-column", default=None, help="Override the low grade column.")
    parser.add_argument("--high-grade-column", default=None, help="Override the high grade column.")
    parser.add_argument("--district-name-column", default=None, help="Override the district name column.")
    parser.add_argument("--district-type-column", default=None, help="Override the district type column.")
    return parser.parse_args(argv)


def download_file(url: str, destination: Path) -> Path:
    """
    Download a remote file to disk.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(
        url,
        stream=True,
        timeout=300,
        headers={"User-Agent": DEFAULT_USER_AGENT},
    ) as response:
        response.raise_for_status()
        with destination.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_obj.write(chunk)
    return destination


def resolve_local_dataset_path(
    path_value: str,
    *,
    default_local_path: Path,
    default_remote_url: str,
    dataset_label: str,
) -> str:
    """
    Resolve a dataset path, auto-downloading only when the default local artifact is missing.
    """
    if not path_value:
        return path_value
    if is_remote_url(path_value):
        return path_value

    candidate = Path(path_value).expanduser()
    if candidate.exists():
        return str(candidate)

    default_candidate = default_local_path.expanduser()
    if candidate == default_candidate:
        download_file(default_remote_url, default_candidate)
        return str(default_candidate)

    raise FileNotFoundError(f"{dataset_label} dataset not found: {candidate}")


def resolve_input_dataset_paths(args: argparse.Namespace) -> argparse.Namespace:
    """
    Resolve local/default dataset paths before reading any geospatial inputs.
    """
    args.schools_path = resolve_local_dataset_path(
        args.schools_path,
        default_local_path=DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_PATH,
        default_remote_url=DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL,
        dataset_label="School",
    )
    if not args.skip_districts and args.districts_path:
        args.districts_path = resolve_local_dataset_path(
            args.districts_path,
            default_local_path=DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_PATH,
            default_remote_url=DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_URL,
            dataset_label="District",
        )
    return args


def resolve_listing_tables(selection: str) -> list[ListingTable]:
    if selection == "all":
        return ["buy", "lease"]
    return [selection]  # type: ignore[list-item]


def choose_column(columns: pd.Index, override: str | None, candidates: tuple[str, ...]) -> str | None:
    if override:
        if override not in columns:
            raise ValueError(f"Column not found: {override}")
        return override
    return guess_column_name(columns, candidates)


def dataset_columns_for_path(path: str, *, layer: str | None) -> pd.Index | None:
    """
    Return lightweight dataset column metadata for local files when available.
    """
    if is_remote_url(path):
        return None

    dataset_path = Path(path).expanduser()
    if not dataset_path.exists():
        return None

    try:
        info = pyogrio.read_info(dataset_path, layer=layer)
    except Exception:
        return None

    fields = info.get("fields")
    if fields is None or len(fields) == 0:
        return None
    return pd.Index([str(field) for field in fields])


def parse_grade_token(value: object) -> int | None:
    """
    Normalize a single grade token such as `K`, `TK`, `5`, or `12`.
    """
    if value is None:
        return None

    token = str(value).strip().upper()
    if not token or token in {"NAN", "NONE", "NULL", "UG", "ADULT", "AE"}:
        return None
    if token in GRADE_TOKEN_MAP:
        return GRADE_TOKEN_MAP[token]
    if token.isdigit():
        return int(token)
    return None


def extract_grade_span(value: object) -> tuple[int, int] | None:
    """
    Parse a grade-span string like `K-5`, `6-8`, or `9/12`.
    """
    if value is None:
        return None

    raw = str(value).strip().upper()
    if not raw or raw in {"NAN", "NONE", "NULL"}:
        return None

    match = re.match(r"^\s*([A-Z0-9]+)\s*[-/]\s*([A-Z0-9]+)\s*$", raw)
    if match:
        low = parse_grade_token(match.group(1))
        high = parse_grade_token(match.group(2))
        if low is None or high is None:
            return None
        return (min(low, high), max(low, high))

    single = parse_grade_token(raw)
    if single is not None:
        return (single, single)
    return None


def extract_grade_span_from_row(
    row: pd.Series,
    *,
    grade_span_col: str | None,
    low_grade_col: str | None,
    high_grade_col: str | None,
) -> tuple[int, int] | None:
    if grade_span_col:
        span = extract_grade_span(row.get(grade_span_col))
        if span is not None:
            return span

    if low_grade_col and high_grade_col:
        low = parse_grade_token(row.get(low_grade_col))
        high = parse_grade_token(row.get(high_grade_col))
        if low is not None and high is not None:
            return (min(low, high), max(low, high))

    return None


def grade_span_bands(span: tuple[int, int] | None) -> set[str]:
    """
    Return the school bands touched by a grade span.
    """
    if span is None:
        return set()

    low, high = span
    bands: set[str] = set()
    if low <= 5 and high >= 0:
        bands.add("elem")
    if low <= 8 and high >= 6:
        bands.add("mid")
    if low <= 12 and high >= 9:
        bands.add("high")
    return bands


def prepare_school_points(
    args: argparse.Namespace,
    *,
    bbox: tuple[float, float, float, float],
) -> tuple[gpd.GeoDataFrame, str]:
    available_columns = dataset_columns_for_path(args.schools_path, layer=args.schools_layer)
    columns_index = available_columns
    if columns_index is None:
        schools = read_geospatial_dataset(args.schools_path, layer=args.schools_layer, bbox=bbox)
        if schools.empty:
            raise ValueError("School dataset is empty.")
        columns_index = schools.columns
    else:
        schools = gpd.GeoDataFrame()

    name_col = choose_column(columns_index, args.school_name_column, DEFAULT_SCHOOL_NAME_CANDIDATES)
    if name_col is None:
        raise ValueError("Could not resolve a school name column. Pass --school-name-column.")

    grade_span_col = choose_column(columns_index, args.grade_span_column, DEFAULT_GRADE_SPAN_CANDIDATES)
    low_grade_col = choose_column(columns_index, args.low_grade_column, DEFAULT_LOW_GRADE_CANDIDATES)
    high_grade_col = choose_column(columns_index, args.high_grade_column, DEFAULT_HIGH_GRADE_CANDIDATES)
    if grade_span_col is None and (low_grade_col is None or high_grade_col is None):
        raise ValueError(
            "Could not resolve grade span columns. Pass --grade-span-column or both "
            "--low-grade-column and --high-grade-column."
        )

    if schools.empty:
        schools = read_geospatial_dataset(
            args.schools_path,
            layer=args.schools_layer,
            bbox=bbox,
            columns=[name_col, *[c for c in (grade_span_col, low_grade_col, high_grade_col) if c]],
        )
        if schools.empty:
            raise ValueError("School dataset is empty.")

    working = schools[[name_col, "geometry"] + [c for c in (grade_span_col, low_grade_col, high_grade_col) if c]].copy()
    working["school_name"] = working[name_col].astype("string")
    working["grade_span_tuple"] = working.apply(
        extract_grade_span_from_row,
        axis=1,
        grade_span_col=grade_span_col,
        low_grade_col=low_grade_col,
        high_grade_col=high_grade_col,
    )
    working["school_bands"] = working["grade_span_tuple"].apply(grade_span_bands)
    working = working[working["school_name"].notna() & (working["school_bands"].map(len) > 0)].copy()
    if working.empty:
        raise ValueError("No schools remained after grade-band parsing.")

    return working[["school_name", "school_bands", "geometry"]], "school_name"


def compute_nearest_school_band(
    listings: gpd.GeoDataFrame,
    schools: gpd.GeoDataFrame,
    *,
    band: str,
    result_name_col: str,
    result_distance_col: str,
) -> pd.DataFrame:
    band_schools = schools[schools["school_bands"].apply(lambda values: band in values)].copy()
    if band_schools.empty:
        return pd.DataFrame(columns=["mls_number", result_name_col, result_distance_col])

    listings_m = listings[["mls_number", "geometry"]].to_crs("EPSG:3857")
    schools_m = band_schools[["school_name", "geometry"]].to_crs("EPSG:3857")

    nearest = gpd.sjoin_nearest(
        listings_m,
        schools_m,
        how="left",
        distance_col="distance_meters",
    )

    result = nearest[["mls_number", "school_name", "distance_meters"]].copy()
    result[result_distance_col] = pd.to_numeric(result["distance_meters"], errors="coerce") / 1609.344
    result[result_distance_col] = result[result_distance_col].round(2)
    result = result.rename(columns={"school_name": result_name_col})
    return result[["mls_number", result_name_col, result_distance_col]]


def prepare_district_polygons(
    args: argparse.Namespace,
    *,
    bbox: tuple[float, float, float, float],
) -> tuple[gpd.GeoDataFrame, str, str | None] | None:
    if args.skip_districts or not args.districts_path:
        return None

    available_columns = dataset_columns_for_path(args.districts_path, layer=args.districts_layer)
    columns_index = available_columns
    if columns_index is None:
        districts = read_geospatial_dataset(args.districts_path, layer=args.districts_layer, bbox=bbox)
        if districts.empty:
            return None
        columns_index = districts.columns
    else:
        districts = gpd.GeoDataFrame()

    name_col = choose_column(columns_index, args.district_name_column, DEFAULT_DISTRICT_NAME_CANDIDATES)
    if name_col is None:
        raise ValueError("Could not resolve a district name column. Pass --district-name-column.")
    type_col = choose_column(columns_index, args.district_type_column, DEFAULT_DISTRICT_TYPE_CANDIDATES)
    if districts.empty:
        districts = read_geospatial_dataset(
            args.districts_path,
            layer=args.districts_layer,
            bbox=bbox,
            columns=[name_col, *([type_col] if type_col else [])],
        )
        if districts.empty:
            return None
    return districts, name_col, type_col


def compute_district_join(
    listings: gpd.GeoDataFrame,
    districts: gpd.GeoDataFrame,
    *,
    name_col: str,
    type_col: str | None,
) -> pd.DataFrame:
    columns = [name_col] + ([type_col] if type_col else []) + ["geometry"]
    joined = gpd.sjoin(
        listings[["mls_number", "geometry"]],
        districts[columns],
        how="left",
        predicate="intersects",
    )

    working = joined[["mls_number", name_col] + ([type_col] if type_col else [])].copy()
    rename_map = {name_col: "school_district_name"}
    if type_col:
        rename_map[type_col] = "school_district_type"
    working = working.rename(columns=rename_map)
    agg_map = {"school_district_name": "first"}
    if type_col:
        agg_map["school_district_type"] = "first"
    return working.groupby("mls_number", as_index=False).agg(agg_map)


def enrich_table(listing_table: ListingTable, args: argparse.Namespace) -> int:
    region_bbox = resolve_region_bbox(args.region)
    listings = load_listing_points(args.db_path, listing_table, bbox=region_bbox)
    if listings.empty:
        print(f"[{listing_table}] No listing points found inside {args.region}; skipping.")
        return 0

    bbox = expanded_total_bounds(listings)
    schools, _ = prepare_school_points(args, bbox=bbox)
    result = listings[["mls_number"]].copy()

    district_config = prepare_district_polygons(args, bbox=bbox)
    if district_config is not None:
        districts, district_name_col, district_type_col = district_config
        result = result.merge(
            compute_district_join(
                listings,
                districts,
                name_col=district_name_col,
                type_col=district_type_col,
            ),
            on="mls_number",
            how="left",
        )

    for band, name_col, dist_col in (
        ("elem", "nearest_elem_school_name", "nearest_elem_school_mi"),
        ("mid", "nearest_mid_school_name", "nearest_mid_school_mi"),
        ("high", "nearest_high_school_name", "nearest_high_school_mi"),
    ):
        result = result.merge(
            compute_nearest_school_band(
                listings,
                schools,
                band=band,
                result_name_col=name_col,
                result_distance_col=dist_col,
            ),
            on="mls_number",
            how="left",
        )

    result["coverage_city_only_flag"] = 0
    source_paths = [args.schools_path]
    if district_config is not None and args.districts_path:
        source_paths.append(args.districts_path)
    result["source_version"] = build_source_version(source_paths)
    result["enriched_at"] = now_utc_iso()

    written = upsert_listing_enrichment_rows(args.db_path, listing_table, result)
    print(f"[{listing_table}] Upserted {written:,} school enrichment rows.")
    return written


def main() -> None:
    args = resolve_input_dataset_paths(parse_args())
    Path(args.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    for listing_table in resolve_listing_tables(args.listing_table):
        enrich_table(listing_table, args)


if __name__ == "__main__":
    main()
