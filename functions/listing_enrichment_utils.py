from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal, Sequence
import re
import tempfile
import sqlite3
import zipfile
from urllib.parse import urlparse
import requests

import geopandas as gpd
import pandas as pd
import pyogrio
from pyproj import Transformer

DEFAULT_DB_PATH = Path("assets/datasets/larentals.db")
LISTING_TABLES: tuple[str, str] = ("buy", "lease")
ListingTable = Literal["buy", "lease"]
DEFAULT_REGION_NAME = "southern-california"
REGION_BBOXES: dict[str, tuple[float, float, float, float] | None] = {
    "all": None,
    "southern-california": (-121.0, 32.0, -114.0, 35.9),
}
DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL = (
    "https://gis.data.ca.gov/api/download/v1/items/"
    "586424d4a1964277a2e0b73191da51bb/geoPackage?layers=0"
)
DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_PATH = Path(
    "assets/datasets/california_public_schools_2024_25.gpkg"
)
DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_URL = (
    "https://gis.data.ca.gov/api/download/v1/items/"
    "b0e3b936426a47ce9d9a2e77e2bb86cc/geojson?layers=0"
)
DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_PATH = Path(
    "assets/datasets/california_school_district_areas_2024_25.geojson"
)

COMMON_ENRICHMENT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("mls_number", "TEXT PRIMARY KEY"),
    ("coverage_city_only_flag", "INTEGER"),
    ("census_tract", "TEXT"),
    ("school_district_name", "TEXT"),
    ("school_district_type", "TEXT"),
    ("nearest_elem_school_name", "TEXT"),
    ("nearest_elem_school_mi", "REAL"),
    ("nearest_mid_school_name", "TEXT"),
    ("nearest_mid_school_mi", "REAL"),
    ("nearest_high_school_name", "TEXT"),
    ("nearest_high_school_mi", "REAL"),
    ("fire_hazard_severity", "TEXT"),
    ("fire_hazard_responsibility_area", "TEXT"),
    ("fire_hazard_rollout_phase", "TEXT"),
    ("fire_hazard_effective_date", "TEXT"),
    ("fire_hazard_source", "TEXT"),
    ("fire_hazard_source_version", "TEXT"),
    ("fire_hazard_enriched_at", "TEXT"),
    ("zoning_code", "TEXT"),
    ("permits_500ft_12mo", "INTEGER"),
    ("major_permits_0_5mi_12mo", "INTEGER"),
    ("new_res_permits_0_5mi_36mo", "INTEGER"),
    ("demo_permits_0_5mi_36mo", "INTEGER"),
    ("calls_for_service_0_5mi_6mo", "INTEGER"),
    ("violent_crimes_0_5mi_12mo", "INTEGER"),
    ("property_crimes_0_5mi_12mo", "INTEGER"),
    ("quality_of_life_calls_0_5mi_6mo", "INTEGER"),
    ("nearest_rail_station", "TEXT"),
    ("dist_rail_station_mi", "REAL"),
    ("dist_frequent_transit_stop_mi", "REAL"),
    ("frequent_stops_0_5mi", "INTEGER"),
    ("transit_access_score", "REAL"),
    ("ces_percentile", "REAL"),
    ("pm25_percentile", "REAL"),
    ("diesel_pm_percentile", "REAL"),
    ("traffic_percentile", "REAL"),
    ("nearest_traffic_count", "REAL"),
    ("max_traffic_count_0_25mi", "REAL"),
    ("grocery_count_1mi", "INTEGER"),
    ("pharmacy_count_1mi", "INTEGER"),
    ("childcare_count_1mi", "INTEGER"),
    ("fitness_count_1mi", "INTEGER"),
    ("dist_grocery_mi", "REAL"),
    ("dist_public_ev_charger_mi", "REAL"),
    ("public_ev_count_2mi", "INTEGER"),
    ("dc_fast_count_5mi", "INTEGER"),
    ("lahd_violation_case_count", "INTEGER"),
    ("lahd_enforcement_case_count", "INTEGER"),
    ("lahd_ccris_case_count", "INTEGER"),
    ("dbs_open_code_case_count", "INTEGER"),
    ("has_open_housing_or_code_case", "INTEGER"),
    ("source_version", "TEXT"),
    ("enriched_at", "TEXT"),
)

INDEX_COLUMNS: tuple[str, ...] = (
    "school_district_name",
    "fire_hazard_severity",
    "has_open_housing_or_code_case",
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ARCGIS_LAYER_URL_RE = re.compile(r"https?://.+/(FeatureServer|MapServer)/\d+/?$", re.IGNORECASE)


def require_safe_identifier(name: str, *, field_name: str) -> str:
    """
    Validate a SQL identifier used for a table or column name.

    Args:
        name: Candidate SQL identifier.
        field_name: Friendly field label for error messages.

    Returns:
        The original identifier when valid.

    Raises:
        ValueError: If the identifier contains unsafe characters.
    """
    if not _IDENTIFIER_RE.fullmatch(name):
        raise ValueError(f"Unsafe SQL identifier for {field_name}: {name!r}")
    return name


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """
    Return whether a SQLite table exists.
    """
    safe_table = require_safe_identifier(table_name, field_name="table_name")
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (safe_table,),
    ).fetchone()
    return row is not None


def existing_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """
    Return the declared column names for a SQLite table.
    """
    safe_table = require_safe_identifier(table_name, field_name="table_name")
    rows = conn.execute(f'PRAGMA table_info("{safe_table}")').fetchall()
    return {str(row[1]) for row in rows}


def create_enrichment_table(conn: sqlite3.Connection, table_name: str) -> None:
    """
    Create an enrichment table from the canonical schema.
    """
    safe_table = require_safe_identifier(table_name, field_name="table_name")
    column_sql = ",\n  ".join(
        f'"{column_name}" {column_type}'
        for column_name, column_type in COMMON_ENRICHMENT_COLUMNS
    )
    conn.execute(
        f'''
        CREATE TABLE IF NOT EXISTS "{safe_table}" (
          {column_sql}
        )
        '''
    )


def add_missing_enrichment_columns(conn: sqlite3.Connection, table_name: str) -> int:
    """
    Add any canonical enrichment columns missing from an existing table.
    """
    safe_table = require_safe_identifier(table_name, field_name="table_name")
    current_columns = existing_columns(conn, safe_table)
    added = 0

    for column_name, column_type in COMMON_ENRICHMENT_COLUMNS:
        if column_name in current_columns:
            continue
        if "PRIMARY KEY" in column_type:
            raise RuntimeError(
                f'Table "{safe_table}" is missing primary key column "{column_name}". '
                "Create the table fresh so the key can be declared correctly."
            )

        conn.execute(
            f'ALTER TABLE "{safe_table}" ADD COLUMN "{column_name}" {column_type}'
        )
        added += 1

    return added


def ensure_indexes(conn: sqlite3.Connection, table_name: str) -> int:
    """
    Ensure the standard enrichment indexes exist.
    """
    safe_table = require_safe_identifier(table_name, field_name="table_name")
    created = 0
    for column_name in INDEX_COLUMNS:
        safe_col = require_safe_identifier(column_name, field_name="column_name")
        index_name = f"idx_{safe_table}_{safe_col}"
        conn.execute(
            f'''
            CREATE INDEX IF NOT EXISTS "{index_name}"
            ON "{safe_table}"("{safe_col}")
            '''
        )
        created += 1
    return created


def ensure_enrichment_table(conn: sqlite3.Connection, table_name: str) -> tuple[int, int]:
    """
    Create or evolve a canonical enrichment table and its indexes.
    """
    safe_table = require_safe_identifier(table_name, field_name="table_name")
    if not table_exists(conn, safe_table):
        create_enrichment_table(conn, safe_table)
        added_columns = len(COMMON_ENRICHMENT_COLUMNS)
    else:
        added_columns = add_missing_enrichment_columns(conn, safe_table)

    created_indexes = ensure_indexes(conn, safe_table)
    return added_columns, created_indexes


def rebuild_enrichment_table(conn: sqlite3.Connection, table_name: str) -> tuple[int, int]:
    """
    Drop and recreate an enrichment table from the canonical schema.

    Returns:
        Tuple of `(dropped_row_count, created_index_count)`.
    """
    safe_table = require_safe_identifier(table_name, field_name="table_name")
    dropped_rows = 0

    if table_exists(conn, safe_table):
        row = conn.execute(f'SELECT COUNT(*) FROM "{safe_table}"').fetchone()
        dropped_rows = int(row[0]) if row and row[0] is not None else 0
        conn.execute(f'DROP TABLE "{safe_table}"')

    create_enrichment_table(conn, safe_table)
    created_indexes = ensure_indexes(conn, safe_table)
    return dropped_rows, created_indexes


def normalize_columns_key(value: str) -> str:
    """
    Collapse a column name to a comparison-friendly lookup key.
    """
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def guess_column_name(
    columns: Iterable[str],
    candidates: Sequence[str],
) -> str | None:
    """
    Return the first matching column name using normalized-name comparison.
    """
    normalized_lookup = {
        normalize_columns_key(str(column)): str(column)
        for column in columns
    }
    for candidate in candidates:
        resolved = normalized_lookup.get(normalize_columns_key(candidate))
        if resolved:
            return resolved
    return None


def read_geospatial_dataset(
    path: str | Path,
    layer: str | None = None,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    columns: Sequence[str] | None = None,
) -> gpd.GeoDataFrame:
    """
    Read a local or remote geospatial source and normalize it to WGS84.
    """
    dataset_path = str(path)
    if _ARCGIS_LAYER_URL_RE.match(dataset_path):
        dataset = read_arcgis_layer(dataset_path, bbox=bbox)
    elif is_remote_url(dataset_path):
        dataset = read_remote_geospatial_dataset(
            dataset_path,
            layer=layer,
            bbox=bbox,
            columns=columns,
        )
    else:
        dataset = read_local_geospatial_dataset(
            dataset_path,
            layer=layer,
            bbox=bbox,
            columns=columns,
        )

    if dataset.empty:
        return dataset
    if dataset.crs is None:
        raise ValueError(f"Dataset has no CRS: {path}")
    dataset = dataset.to_crs("EPSG:4326")
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        dataset = dataset.cx[minx:maxx, miny:maxy].copy()
    return dataset


def resolve_region_bbox(region_name: str) -> tuple[float, float, float, float] | None:
    """
    Resolve a named geographic scope into a WGS84 bounding box.
    """
    try:
        return REGION_BBOXES[region_name]
    except KeyError as exc:
        supported = ", ".join(sorted(REGION_BBOXES))
        raise ValueError(f"Unknown region {region_name!r}. Expected one of: {supported}") from exc


def filter_gdf_to_bbox(
    gdf: gpd.GeoDataFrame,
    bbox: tuple[float, float, float, float] | None,
) -> gpd.GeoDataFrame:
    """
    Return only rows whose geometry falls within a WGS84 bounding box.
    """
    if bbox is None or gdf.empty:
        return gdf.copy()

    working = gdf.to_crs("EPSG:4326") if gdf.crs != "EPSG:4326" else gdf.copy()
    minx, miny, maxx, maxy = bbox
    return working.cx[minx:maxx, miny:maxy].copy()


def is_remote_url(value: str) -> bool:
    """
    Return whether a string looks like an HTTP(S) URL.
    """
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def expanded_total_bounds(
    gdf: gpd.GeoDataFrame,
    *,
    pad_degrees: float = 0.05,
) -> tuple[float, float, float, float]:
    """
    Return an expanded WGS84 bounding box for a GeoDataFrame.
    """
    if gdf.empty:
        raise ValueError("Cannot compute bounds for an empty GeoDataFrame.")

    minx, miny, maxx, maxy = gdf.to_crs("EPSG:4326").total_bounds
    return (
        float(minx - pad_degrees),
        float(miny - pad_degrees),
        float(maxx + pad_degrees),
        float(maxy + pad_degrees),
    )


def _download_remote_file(url: str, target_path: Path) -> Path:
    """
    Download a remote file to a local path.
    """
    response = requests.get(
        url,
        stream=True,
        timeout=180,
        headers={"User-Agent": "WhereToLive.LA/1.0 enrichment downloader"},
    )
    response.raise_for_status()
    with target_path.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                fh.write(chunk)
    return target_path


def _resolve_zip_dataset_path(extract_dir: Path) -> Path:
    """
    Resolve the first usable geospatial dataset inside an extracted ZIP directory.
    """
    gdb_dirs = sorted(path for path in extract_dir.rglob("*.gdb") if path.is_dir())
    if gdb_dirs:
        return gdb_dirs[0]

    gpkg_files = sorted(path for path in extract_dir.rglob("*.gpkg") if path.is_file())
    if gpkg_files:
        return gpkg_files[0]

    shp_files = sorted(path for path in extract_dir.rglob("*.shp") if path.is_file())
    if shp_files:
        return shp_files[0]

    geojson_files = sorted(
        path
        for path in extract_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".geojson", ".json"}
    )
    if geojson_files:
        return geojson_files[0]

    raise ValueError(f"No readable geospatial dataset found inside {extract_dir}")


def _guess_default_layer_name(path: str | Path) -> str | None:
    """
    Pick a default layer when a container dataset exposes multiple layers.
    """
    try:
        import fiona
    except ImportError:
        return None

    try:
        layers = list(fiona.listlayers(str(path)))
    except Exception:
        return None

    if not layers:
        return None
    if len(layers) == 1:
        return layers[0]

    preferred = sorted(
        layers,
        key=lambda name: (
            "fhsz" not in name.lower(),
            "haz" not in name.lower(),
            "district" not in name.lower(),
            "school" not in name.lower(),
            name.lower(),
        ),
    )
    return preferred[0]


def _dataset_info(
    path: str | Path,
    *,
    layer: str | None,
) -> dict[str, object] | None:
    """
    Return lightweight driver/CRS metadata for a local dataset when available.
    """
    try:
        return pyogrio.read_info(path, layer=layer)
    except Exception:
        return None


def _project_bbox_to_dataset_crs(
    bbox: tuple[float, float, float, float] | None,
    *,
    dataset_crs: object | None,
) -> tuple[float, float, float, float] | None:
    """
    Reproject a WGS84 bbox into the dataset CRS expected by local readers.
    """
    if bbox is None or not dataset_crs:
        return bbox

    dataset_crs_text = str(dataset_crs)
    if dataset_crs_text.upper() == "EPSG:4326":
        return bbox

    minx, miny, maxx, maxy = bbox
    transformer = Transformer.from_crs("EPSG:4326", dataset_crs_text, always_xy=True)
    xs, ys = transformer.transform(
        [minx, maxx, minx, maxx],
        [miny, miny, maxy, maxy],
    )
    return (
        float(min(xs)),
        float(min(ys)),
        float(max(xs)),
        float(max(ys)),
    )


@contextmanager
def _temporary_gdal_config(options: dict[str, object] | None):
    """
    Temporarily apply GDAL config options for a single read.
    """
    if not options:
        yield
        return

    previous = {
        key: pyogrio.get_gdal_config_option(key)
        for key in options
    }
    pyogrio.set_gdal_config_options(options)
    try:
        yield
    finally:
        pyogrio.set_gdal_config_options(previous)


def read_local_geospatial_dataset(
    path: str | Path,
    layer: str | None = None,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    columns: Sequence[str] | None = None,
) -> gpd.GeoDataFrame:
    """
    Read a local geospatial dataset, including ZIP archives.
    """
    dataset_path = Path(path)
    if dataset_path.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="larentals-geozip-") as temp_dir:
            extract_dir = Path(temp_dir)
            with zipfile.ZipFile(dataset_path) as archive:
                archive.extractall(extract_dir)
            extracted_path = _resolve_zip_dataset_path(extract_dir)
            return read_local_geospatial_dataset(
                extracted_path,
                layer=layer,
                bbox=bbox,
                columns=columns,
            )

    resolved_layer = layer or _guess_default_layer_name(dataset_path)
    info = _dataset_info(dataset_path, layer=resolved_layer)
    read_kwargs: dict[str, object] = {}
    local_bbox = _project_bbox_to_dataset_crs(bbox, dataset_crs=(info or {}).get("crs"))
    if local_bbox is not None:
        read_kwargs["bbox"] = local_bbox
    if columns is not None:
        read_kwargs["columns"] = list(columns)

    gdal_config: dict[str, object] = {}
    if (info or {}).get("driver") == "OpenFileGDB":
        # Some FileGDB polygon layers emit expensive ring re-organization warnings;
        # ONLY_CCW matches common ring orientation and is materially faster here.
        gdal_config["OGR_ORGANIZE_POLYGONS"] = "ONLY_CCW"

    with _temporary_gdal_config(gdal_config):
        return (
            gpd.read_file(dataset_path, layer=resolved_layer, **read_kwargs)
            if resolved_layer
            else gpd.read_file(dataset_path, **read_kwargs)
        )


def read_remote_geospatial_dataset(
    url: str,
    layer: str | None = None,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    columns: Sequence[str] | None = None,
) -> gpd.GeoDataFrame:
    """
    Read a remote geospatial file by downloading it to a temporary directory first.
    """
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".bin"

    if suffix.lower() in {".geojson", ".json"}:
        response = requests.get(
            url,
            timeout=180,
            headers={"User-Agent": "WhereToLive.LA/1.0 enrichment downloader"},
        )
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features")
        if not isinstance(features, list):
            raise ValueError(f"Remote dataset did not return GeoJSON features: {url}")
        return gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")

    with tempfile.TemporaryDirectory(prefix="larentals-remote-geo-") as temp_dir:
        temp_path = Path(temp_dir) / f"dataset{suffix}"
        _download_remote_file(url, temp_path)
        return read_local_geospatial_dataset(
            temp_path,
            layer=layer,
            bbox=bbox,
            columns=columns,
        )


def _build_arcgis_query_params(
    *,
    bbox: tuple[float, float, float, float] | None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    params: dict[str, object] = {"where": "1=1"}
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        params.update(
            {
                "geometry": f"{minx},{miny},{maxx},{maxy}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
            }
        )
    if extra:
        params.update(extra)
    return params


def read_arcgis_layer(
    layer_url: str,
    *,
    bbox: tuple[float, float, float, float] | None = None,
) -> gpd.GeoDataFrame:
    """
    Read an ArcGIS FeatureServer/MapServer layer URL into a GeoDataFrame.
    """
    query_url = layer_url.rstrip("/") + "/query"
    session = requests.Session()
    session.headers.update({"User-Agent": "WhereToLive.LA/1.0 enrichment downloader"})

    id_response = session.post(
        query_url,
        data=_build_arcgis_query_params(
            bbox=bbox,
            extra={"returnIdsOnly": "true", "returnGeometry": "false", "f": "json"},
        ),
        timeout=180,
    )
    id_response.raise_for_status()
    id_payload = id_response.json()
    if "error" in id_payload:
        raise ValueError(f"ArcGIS ID query failed for {layer_url}: {id_payload['error']}")

    object_ids = id_payload.get("objectIds") or []
    if not object_ids:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    def fetch_feature_chunk(chunk: list[object]) -> list[dict[str, object]]:
        try:
            feature_response = session.post(
                query_url,
                data={
                    "objectIds": ",".join(str(object_id) for object_id in chunk),
                    "outFields": "*",
                    "returnGeometry": "true",
                    "outSR": 4326,
                    "f": "geojson",
                },
                timeout=180,
            )
            feature_response.raise_for_status()
            payload = feature_response.json()
            if "error" in payload:
                raise ValueError(f"ArcGIS feature query failed for {layer_url}: {payload['error']}")
            return list(payload.get("features") or [])
        except (requests.HTTPError, ValueError):
            if len(chunk) <= 1:
                raise
            midpoint = len(chunk) // 2
            return fetch_feature_chunk(chunk[:midpoint]) + fetch_feature_chunk(chunk[midpoint:])

    features: list[dict[str, object]] = []
    chunk_size = 500
    for start in range(0, len(object_ids), chunk_size):
        chunk = object_ids[start : start + chunk_size]
        features.extend(fetch_feature_chunk(list(chunk)))

    if not features:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")


def load_listing_points(
    db_path: str | Path,
    listing_table: ListingTable,
    *,
    bbox: tuple[float, float, float, float] | None = None,
) -> gpd.GeoDataFrame:
    """
    Load listing points from SQLite as a WGS84 GeoDataFrame.
    """
    safe_table = require_safe_identifier(listing_table, field_name="listing_table")
    where_clauses = [
        "latitude IS NOT NULL",
        "longitude IS NOT NULL",
        "TRIM(CAST(mls_number AS TEXT)) != ''",
        "TRIM(CAST(latitude AS TEXT)) != ''",
        "TRIM(CAST(longitude AS TEXT)) != ''",
    ]
    params: list[object] = []
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        where_clauses.extend(
            [
                "CAST(latitude AS REAL) >= ?",
                "CAST(latitude AS REAL) <= ?",
                "CAST(longitude AS REAL) >= ?",
                "CAST(longitude AS REAL) <= ?",
            ]
        )
        params.extend([miny, maxy, minx, maxx])

    with sqlite3.connect(str(db_path)) as conn:
        df = pd.read_sql_query(
            f"""
            SELECT
              mls_number,
              latitude,
              longitude
            FROM {safe_table}
            WHERE {" AND ".join(where_clauses)}
            """,
            conn,
            params=params,
        )

    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["mls_number", "latitude", "longitude"]).copy()
    df = df.drop_duplicates(subset=["mls_number"]).reset_index(drop=True)
    listings = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326",
    )
    return filter_gdf_to_bbox(listings, bbox)


def now_utc_iso() -> str:
    """
    Return the current UTC timestamp as an ISO-8601 string.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_source_version(paths: Sequence[str | Path]) -> str:
    """
    Build a compact source-version string from input path mtimes.
    """
    parts: list[str] = []
    for raw_path in paths:
        if not raw_path:
            continue
        if is_remote_url(str(raw_path)):
            parts.append(f"url:{raw_path}")
            continue
        path = Path(raw_path)
        if not path.exists():
            continue
        stat = path.stat()
        parts.append(f"{path.name}:{stat.st_mtime_ns}")
    return ";".join(parts)


def _python_value(value: object) -> object:
    """
    Convert pandas/numpy scalar values into SQLite-friendly Python values.
    """
    if pd.isna(value):
        return None
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return value.item()
        except Exception:
            return value
    return value


def upsert_listing_enrichment_rows(
    db_path: str | Path,
    listing_table: ListingTable,
    rows_df: pd.DataFrame,
) -> int:
    """
    Upsert listing enrichment rows into ``<listing_table>_enrichment``.
    """
    if "mls_number" not in rows_df.columns:
        raise ValueError("rows_df must include an mls_number column")

    safe_table = require_safe_identifier(
        f"{listing_table}_enrichment",
        field_name="enrichment_table",
    )
    rows_df = rows_df.drop_duplicates(subset=["mls_number"]).copy()
    rows_df["mls_number"] = rows_df["mls_number"].astype(str).str.strip()
    rows_df = rows_df[rows_df["mls_number"] != ""].copy()
    if rows_df.empty:
        return 0

    with sqlite3.connect(str(db_path)) as conn:
        ensure_enrichment_table(conn, safe_table)
        allowed_columns = existing_columns(conn, safe_table)

        columns_to_write = [
            column
            for column in rows_df.columns
            if column in allowed_columns
        ]
        if "mls_number" not in columns_to_write:
            columns_to_write.insert(0, "mls_number")

        placeholders = ", ".join("?" for _ in columns_to_write)
        insert_columns = ", ".join(f'"{column}"' for column in columns_to_write)
        update_columns = [column for column in columns_to_write if column != "mls_number"]
        update_clause = ", ".join(
            f'"{column}" = excluded."{column}"'
            for column in update_columns
        )

        sql = (
            f'INSERT INTO "{safe_table}" ({insert_columns}) VALUES ({placeholders}) '
            f'ON CONFLICT("mls_number") DO UPDATE SET {update_clause}'
            if update_clause
            else f'INSERT OR IGNORE INTO "{safe_table}" ({insert_columns}) VALUES ({placeholders})'
        )

        records = [
            tuple(_python_value(row[column]) for column in columns_to_write)
            for _, row in rows_df[columns_to_write].iterrows()
        ]
        conn.executemany(sql, records)
        conn.commit()

    return len(records)
