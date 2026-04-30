from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import geopandas as gpd
import pandas as pd

from functions.listing_enrichment_utils import (
    DEFAULT_DB_PATH,
    DEFAULT_REGION_NAME,
    ListingTable,
    build_source_version,
    expanded_total_bounds,
    load_listing_points,
    now_utc_iso,
    read_geospatial_dataset,
    resolve_region_bbox,
    upsert_listing_enrichment_rows,
)

DEFAULT_FIRE_HAZARD_LAYER_GEOJSON_PATH = Path(
    "assets/datasets/cal_fire_fhsz_southern_california.geojson"
)

CAL_FIRE_SRA_FHSZ_URL = (
    "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/"
    "FHSZ_in_SRA_for_FHSZ_in_LRA/FeatureServer/0"
)
CAL_FIRE_LRA_PHASE_LAYERS: tuple[tuple[str, str, str], ...] = (
    (
        "Phase 1",
        "2025-02-10",
        "https://utility.arcgis.com/usrsvcs/servers/4b1d73d4d1bf4957a3d4d8070f6d3df4/"
        "rest/services/FHSZLRA25_Phase1_v1/FeatureServer/0",
    ),
    (
        "Phase 2",
        "2025-02-24",
        "https://utility.arcgis.com/usrsvcs/servers/72a50f9e66f44c7a94a61d272e3fe515/"
        "rest/services/FHSZLRA25_Phase2_v1/FeatureServer/0",
    ),
    (
        "Phase 3",
        "2025-03-10",
        "https://utility.arcgis.com/usrsvcs/servers/a97239e9199c4187a4f65874958c4fd9/"
        "rest/services/FHSZLRA25_Phase3_v1/FeatureServer/0",
    ),
    (
        "Phase 4",
        "2025-03-24",
        "https://utility.arcgis.com/usrsvcs/servers/89aed69e4a144689b9cd67c1d80ef3bb/"
        "rest/services/FHSZLRA25_Phase4_v1/FeatureServer/0",
    ),
)
CAL_FIRE_SRA_EFFECTIVE_DATE = "2024-04-01"
CAL_FIRE_FHSZ_SOURCE_LABEL = "CAL FIRE Fire Hazard Severity Zones"
OUTSIDE_MAPPED_ZONE_LABEL = "Outside mapped zone"
UNKNOWN_FIRE_HAZARD_LABEL = "Unknown"
FIRE_HAZARD_SEVERITY_ORDER: dict[str, int] = {
    OUTSIDE_MAPPED_ZONE_LABEL: 0,
    "Moderate": 1,
    "High": 2,
    "Very High": 3,
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Populate listing enrichment tables with CAL FIRE Fire Hazard Severity "
            "Zone fields and optionally build the matching polygon overlay artifact."
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
        default="buy",
        help="Listing table to enrich (default: buy).",
    )
    parser.add_argument(
        "--region",
        choices=("southern-california", "all"),
        default=DEFAULT_REGION_NAME,
        help=(
            "Geographic scope used to pre-filter listing points "
            f"(default: {DEFAULT_REGION_NAME})."
        ),
    )
    parser.add_argument(
        "--overlay-geojson-path",
        default=str(DEFAULT_FIRE_HAZARD_LAYER_GEOJSON_PATH),
        help=(
            "GeoJSON artifact path used by the optional map overlay "
            f"(default: {DEFAULT_FIRE_HAZARD_LAYER_GEOJSON_PATH})."
        ),
    )
    parser.add_argument(
        "--skip-overlay",
        action="store_true",
        help="Only update listing enrichment fields; do not write the overlay GeoJSON.",
    )
    parser.add_argument(
        "--overlay-simplify-meters",
        type=float,
        default=30.0,
        help="Simplification tolerance for the overlay artifact in meters (default: 30).",
    )
    return parser.parse_args(argv)


def resolve_listing_tables(selection: str) -> list[ListingTable]:
    if selection == "all":
        return ["buy", "lease"]
    return [selection]  # type: ignore[list-item]


def normalize_fire_hazard_severity(value: object) -> str | None:
    """
    Normalize CAL FIRE severity text to the buyer-facing labels.
    """
    if value is None or pd.isna(value):
        return None

    normalized = str(value).strip().lower().replace("_", " ")
    normalized = " ".join(normalized.split())
    if not normalized:
        return None

    if "very" in normalized and "high" in normalized:
        return "Very High"
    if normalized == "high" or normalized.endswith(" high"):
        return "High"
    if normalized == "moderate" or normalized.endswith(" moderate"):
        return "Moderate"
    return None


def _read_fire_hazard_source(
    *,
    url: str,
    bbox: tuple[float, float, float, float],
    responsibility_area: str,
    effective_date: str,
    rollout_phase: str | None = None,
) -> gpd.GeoDataFrame:
    source = read_geospatial_dataset(url, bbox=bbox)
    if source.empty:
        return gpd.GeoDataFrame(
            columns=[
                "fire_hazard_severity",
                "fire_hazard_responsibility_area",
                "fire_hazard_rollout_phase",
                "fire_hazard_effective_date",
                "fire_hazard_source",
                "geometry",
            ],
            geometry="geometry",
            crs="EPSG:4326",
        )

    working = source.to_crs("EPSG:4326").copy()
    if responsibility_area == "SRA" and "SRA22_2" in working.columns:
        working = working[
            working["SRA22_2"].astype("string").str.upper().fillna("") == "SRA"
        ].copy()

    severity_source = (
        working["FHSZ_Description"]
        if "FHSZ_Description" in working.columns
        else working.get("FHSZ")
    )
    working["fire_hazard_severity"] = severity_source.apply(
        normalize_fire_hazard_severity
    )
    working = working[
        working["fire_hazard_severity"].isin(FIRE_HAZARD_SEVERITY_ORDER)
    ].copy()
    if working.empty:
        return working

    working["fire_hazard_responsibility_area"] = responsibility_area
    working["fire_hazard_rollout_phase"] = rollout_phase
    working["fire_hazard_effective_date"] = effective_date
    working["fire_hazard_source"] = CAL_FIRE_FHSZ_SOURCE_LABEL
    return working[
        [
            "fire_hazard_severity",
            "fire_hazard_responsibility_area",
            "fire_hazard_rollout_phase",
            "fire_hazard_effective_date",
            "fire_hazard_source",
            "geometry",
        ]
    ]


def load_fire_hazard_polygons(
    *,
    bbox: tuple[float, float, float, float],
) -> gpd.GeoDataFrame:
    """
    Load and normalize CAL FIRE SRA plus 2025 LRA phase layers.
    """
    sources = [
        _read_fire_hazard_source(
            url=CAL_FIRE_SRA_FHSZ_URL,
            bbox=bbox,
            responsibility_area="SRA",
            effective_date=CAL_FIRE_SRA_EFFECTIVE_DATE,
        )
    ]
    for phase, effective_date, url in CAL_FIRE_LRA_PHASE_LAYERS:
        sources.append(
            _read_fire_hazard_source(
                url=url,
                bbox=bbox,
                responsibility_area="LRA",
                rollout_phase=phase,
                effective_date=effective_date,
            )
        )

    non_empty_sources = [source for source in sources if not source.empty]
    if not non_empty_sources:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    combined = gpd.GeoDataFrame(
        pd.concat(non_empty_sources, ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )
    return combined[~combined.geometry.is_empty & combined.geometry.notna()].copy()


def compute_fire_hazard_join(
    listings: gpd.GeoDataFrame,
    fire_zones: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """
    Assign each listing the highest matching CAL FIRE FHSZ severity.
    """
    result_columns = [
        "mls_number",
        "fire_hazard_severity",
        "fire_hazard_responsibility_area",
        "fire_hazard_rollout_phase",
        "fire_hazard_effective_date",
        "fire_hazard_source",
    ]
    if listings.empty:
        return pd.DataFrame(columns=result_columns)

    result = listings[["mls_number"]].copy()
    if fire_zones.empty:
        result["fire_hazard_severity"] = OUTSIDE_MAPPED_ZONE_LABEL
        result["fire_hazard_responsibility_area"] = None
        result["fire_hazard_rollout_phase"] = None
        result["fire_hazard_effective_date"] = None
        result["fire_hazard_source"] = CAL_FIRE_FHSZ_SOURCE_LABEL
        return result[result_columns]

    join_columns = [
        "fire_hazard_severity",
        "fire_hazard_responsibility_area",
        "fire_hazard_rollout_phase",
        "fire_hazard_effective_date",
        "fire_hazard_source",
        "geometry",
    ]
    joined = gpd.sjoin(
        listings[["mls_number", "geometry"]],
        fire_zones[join_columns],
        how="left",
        predicate="intersects",
    )
    joined["severity_priority"] = (
        joined["fire_hazard_severity"].map(FIRE_HAZARD_SEVERITY_ORDER).fillna(-1)
    )
    joined["area_priority"] = (
        joined["fire_hazard_responsibility_area"].map({"LRA": 2, "SRA": 1}).fillna(0)
    )
    joined = joined.sort_values(
        ["mls_number", "severity_priority", "area_priority"],
        ascending=[True, False, False],
    )
    best = joined.groupby("mls_number", as_index=False).first()
    result = result.merge(best[result_columns], on="mls_number", how="left")
    result["fire_hazard_severity"] = result["fire_hazard_severity"].fillna(
        OUTSIDE_MAPPED_ZONE_LABEL
    )
    result["fire_hazard_source"] = result["fire_hazard_source"].fillna(
        CAL_FIRE_FHSZ_SOURCE_LABEL
    )
    return result[result_columns]


def write_fire_hazard_overlay_geojson(
    fire_zones: gpd.GeoDataFrame,
    output_path: str | Path,
    *,
    simplify_meters: float,
) -> None:
    """
    Write the optional map overlay artifact consumed by Dash Leaflet.
    """
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    if fire_zones.empty:
        payload = {"type": "FeatureCollection", "features": []}
        path.write_text(json.dumps(payload), encoding="utf-8")
        return

    overlay = fire_zones[
        [
            "fire_hazard_severity",
            "fire_hazard_responsibility_area",
            "fire_hazard_rollout_phase",
            "fire_hazard_effective_date",
            "fire_hazard_source",
            "geometry",
        ]
    ].copy()
    overlay["fire_hazard_label"] = overlay.apply(
        lambda row: " ".join(
            value
            for value in (
                row.get("fire_hazard_responsibility_area"),
                row.get("fire_hazard_severity"),
            )
            if isinstance(value, str) and value
        ),
        axis=1,
    )

    if simplify_meters > 0:
        overlay_m = overlay.to_crs("EPSG:3857")
        overlay_m["geometry"] = overlay_m.geometry.simplify(
            simplify_meters,
            preserve_topology=True,
        )
        overlay = overlay_m.to_crs("EPSG:4326")

    payload = json.loads(overlay.to_json(drop_id=True))
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def enrich_table(
    listing_table: ListingTable,
    args: argparse.Namespace,
    *,
    fire_zones: gpd.GeoDataFrame,
) -> int:
    region_bbox = resolve_region_bbox(args.region)
    listings = load_listing_points(args.db_path, listing_table, bbox=region_bbox)
    if listings.empty:
        print(f"[{listing_table}] No listing points found inside {args.region}; skipping.")
        return 0

    result = compute_fire_hazard_join(listings, fire_zones)
    result["fire_hazard_source_version"] = build_source_version(
        [CAL_FIRE_SRA_FHSZ_URL, *[url for _, _, url in CAL_FIRE_LRA_PHASE_LAYERS]]
    )
    result["fire_hazard_enriched_at"] = now_utc_iso()

    written = upsert_listing_enrichment_rows(args.db_path, listing_table, result)
    counts = result["fire_hazard_severity"].value_counts(dropna=False).to_dict()
    print(f"[{listing_table}] Upserted {written:,} fire-hazard enrichment rows: {counts}")
    return written


def main() -> None:
    args = parse_args()
    Path(args.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    region_bbox = resolve_region_bbox(args.region)
    listing_frames = [
        load_listing_points(args.db_path, table_name, bbox=region_bbox)
        for table_name in resolve_listing_tables(args.listing_table)
    ]
    listing_frames = [frame for frame in listing_frames if not frame.empty]
    if not listing_frames:
        print(f"No listing points found inside {args.region}; nothing to enrich.")
        return

    listing_scope = gpd.GeoDataFrame(
        pd.concat(listing_frames, ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )
    bbox = expanded_total_bounds(listing_scope, pad_degrees=0.08)
    fire_zones = load_fire_hazard_polygons(bbox=bbox)
    if fire_zones.empty:
        print("No CAL FIRE FHSZ polygons found for the listing scope.")

    for listing_table in resolve_listing_tables(args.listing_table):
        enrich_table(listing_table, args, fire_zones=fire_zones)

    if not args.skip_overlay:
        write_fire_hazard_overlay_geojson(
            fire_zones,
            args.overlay_geojson_path,
            simplify_meters=args.overlay_simplify_meters,
        )
        print(f"Wrote fire-hazard overlay GeoJSON to {args.overlay_geojson_path}.")


if __name__ == "__main__":
    main()
