import sqlite3
import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from functions.listing_enrichment_utils import (
    DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_PATH,
    DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL,
    DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_PATH,
    DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_URL,
    DEFAULT_REGION_NAME,
    build_source_version,
    ensure_enrichment_table,
    filter_gdf_to_bbox,
    read_local_geospatial_dataset,
    rebuild_enrichment_table,
    resolve_region_bbox,
    upsert_listing_enrichment_rows,
)
from scripts.enrich_schools import (
    extract_grade_span,
    grade_span_bands,
    parse_args as parse_school_args,
    resolve_local_dataset_path,
)
from scripts.enrich_fire_hazard import (
    OUTSIDE_MAPPED_ZONE_LABEL,
    compute_fire_hazard_join,
    normalize_fire_hazard_severity,
)

def test_extract_grade_span_and_band_classification() -> None:
    assert extract_grade_span("K-5") == (0, 5)
    assert extract_grade_span("6/8") == (6, 8)
    assert extract_grade_span("PK-5") == (-1, 5)
    assert grade_span_bands((0, 8)) == {"elem", "mid"}
    assert grade_span_bands((9, 12)) == {"high"}


def test_normalize_fire_hazard_severity_labels() -> None:
    assert normalize_fire_hazard_severity("Very High") == "Very High"
    assert normalize_fire_hazard_severity("SRA High") == "High"
    assert normalize_fire_hazard_severity("Moderate") == "Moderate"
    assert normalize_fire_hazard_severity("Non-Wildland") is None


def test_compute_fire_hazard_join_prefers_highest_intersecting_severity() -> None:
    listings = gpd.GeoDataFrame(
        {"mls_number": ["MLS-1", "MLS-2"]},
        geometry=gpd.points_from_xy([-118.25, -118.10], [34.05, 34.05]),
        crs="EPSG:4326",
    )
    fire_zones = gpd.GeoDataFrame(
        {
            "fire_hazard_severity": ["Moderate", "Very High"],
            "fire_hazard_responsibility_area": ["SRA", "LRA"],
            "fire_hazard_rollout_phase": [None, "Phase 2"],
            "fire_hazard_effective_date": ["2024-04-01", "2025-02-24"],
            "fire_hazard_source": ["CAL FIRE", "CAL FIRE"],
        },
        geometry=gpd.GeoSeries.from_wkt(
            [
                "POLYGON((-118.30 34.00, -118.20 34.00, -118.20 34.10, -118.30 34.10, -118.30 34.00))",
                "POLYGON((-118.30 34.00, -118.20 34.00, -118.20 34.10, -118.30 34.10, -118.30 34.00))",
            ],
            crs="EPSG:4326",
        ),
        crs="EPSG:4326",
    )

    result = compute_fire_hazard_join(listings, fire_zones)

    assert result.set_index("mls_number").loc["MLS-1", "fire_hazard_severity"] == "Very High"
    assert result.set_index("mls_number").loc["MLS-2", "fire_hazard_severity"] == OUTSIDE_MAPPED_ZONE_LABEL


def test_school_parse_args_use_official_defaults() -> None:
    args = parse_school_args([])
    assert args.region == DEFAULT_REGION_NAME
    assert args.schools_path == str(DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_PATH)
    assert args.districts_path == str(DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_PATH)
    assert args.skip_districts is False


def test_resolve_local_dataset_path_downloads_missing_default_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    default_path = tmp_path / "schools.gpkg"
    calls: list[tuple[str, Path]] = []

    def fake_download(url: str, destination: Path) -> Path:
        calls.append((url, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("stub", encoding="utf-8")
        return destination

    monkeypatch.setattr("scripts.enrich_schools.download_file", fake_download)

    resolved = resolve_local_dataset_path(
        str(default_path),
        default_local_path=default_path,
        default_remote_url=DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL,
        dataset_label="School",
    )

    assert resolved == str(default_path)
    assert calls == [(DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL, default_path)]


def test_resolve_local_dataset_path_raises_for_missing_non_default_artifact(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "custom-schools.gpkg"

    with pytest.raises(FileNotFoundError, match="School dataset not found"):
        resolve_local_dataset_path(
            str(missing_path),
            default_local_path=tmp_path / "default-schools.gpkg",
            default_remote_url=DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_URL,
            dataset_label="School",
        )


def test_resolve_region_bbox_for_southern_california() -> None:
    assert resolve_region_bbox("southern-california") == (-121.0, 32.0, -114.0, 35.9)
    assert resolve_region_bbox("all") is None


def test_filter_gdf_to_bbox_keeps_only_southern_california_points() -> None:
    points = gpd.GeoDataFrame(
        {"name": ["los_angeles", "san_francisco"]},
        geometry=gpd.points_from_xy([-118.2437, -122.4194], [34.0522, 37.7749]),
        crs="EPSG:4326",
    )

    filtered = filter_gdf_to_bbox(points, resolve_region_bbox("southern-california"))

    assert filtered["name"].tolist() == ["los_angeles"]


def test_read_local_geospatial_dataset_reprojects_bbox_to_dataset_crs() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "points.gpkg"
        points = gpd.GeoDataFrame(
            {"name": ["los_angeles", "san_francisco"]},
            geometry=gpd.points_from_xy([-118.2437, -122.4194], [34.0522, 37.7749]),
            crs="EPSG:4326",
        ).to_crs("EPSG:3857")
        points.to_file(path, layer="points", driver="GPKG")

        filtered = read_local_geospatial_dataset(
            path,
            layer="points",
            bbox=(-119.0, 33.0, -117.0, 35.0),
        )

        assert filtered["name"].tolist() == ["los_angeles"]


def test_build_source_version_keeps_remote_urls() -> None:
    version = build_source_version(
        [
            DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL,
            DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_URL,
        ]
    )
    assert f"url:{DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL}" in version
    assert f"url:{DEFAULT_CA_SCHOOL_DISTRICTS_GEOJSON_URL}" in version


def test_rebuild_enrichment_table_drops_legacy_columns_and_rows() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "enrichment.db"

        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE buy_enrichment (
                  mls_number TEXT PRIMARY KEY,
                  school_district_name TEXT,
                  fema_sfha_flag INTEGER
                );

                INSERT INTO buy_enrichment (mls_number, school_district_name, fema_sfha_flag)
                VALUES ('MLS-1', 'District A', 1);
                """
            )
            dropped_rows, created_indexes = rebuild_enrichment_table(conn, "buy_enrichment")
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(buy_enrichment)").fetchall()
            }
            remaining_rows = conn.execute("SELECT COUNT(*) FROM buy_enrichment").fetchone()[0]

        assert dropped_rows == 1
        assert created_indexes >= 1
        assert "school_district_name" in columns
        assert "nearest_high_school_mi" in columns
        assert "fire_hazard_severity" in columns
        assert "fema_sfha_flag" not in columns
        assert remaining_rows == 0


def test_upsert_listing_enrichment_rows_updates_existing_records() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "enrichment.db"

        with sqlite3.connect(db_path) as conn:
            ensure_enrichment_table(conn, "buy_enrichment")

        first = pd.DataFrame(
            [
                {
                    "mls_number": "MLS-1",
                    "school_district_name": "District A",
                    "nearest_high_school_mi": 2.5,
                }
            ]
        )
        second = pd.DataFrame(
            [
                {
                    "mls_number": "MLS-1",
                    "school_district_name": "District B",
                    "nearest_high_school_mi": 1.25,
                }
            ]
        )

        assert upsert_listing_enrichment_rows(db_path, "buy", first) == 1
        assert upsert_listing_enrichment_rows(db_path, "buy", second) == 1

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT school_district_name, nearest_high_school_mi
                FROM buy_enrichment
                WHERE mls_number = ?
                """,
                ("MLS-1",),
            ).fetchone()

        assert row == ("District B", 1.25)
