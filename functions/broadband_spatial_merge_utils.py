from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional, Sequence
import geopandas as gpd
import pandas as pd
import sqlite3

ListingTable = Literal["lease", "buy"]
JoinHow = Literal["left", "inner"]
Predicate = Literal["intersects", "within", "contains"]

@dataclass(frozen=True)
class ProviderJoinConfig:
    """
    Configuration for joining listing points in a SQLite DB to provider polygons in a GeoPackage.
    """
    larentals_db_path: str
    listing_table: ListingTable
    geopackage_path: str
    geopackage_layer: str
    output_table: str = "listing_provider_options"
    listing_id_col: str = "mls_number"
    lat_col: str = "latitude"
    lon_col: str = "longitude"
    provider_cols: Optional[Sequence[str]] = None
    predicate: Predicate = "intersects"

    # help match polygons when listing coords are slightly off
    buffer_meters: float = 50.0

    # avoid writing null-provider rows
    join_how: JoinHow = "inner"


def write_provider_options_from_geopackage(cfg: ProviderJoinConfig) -> int:
    """
    Spatially join listings (lat/lon points) to provider polygons from a GeoPackage layer,
    and write the joined results back into the SQLite database.

    Writes a normalized table: one row per (listing_id × matching provider polygon).

    Notes:
      - If cfg.buffer_meters > 0, listing points are buffered in meters (after reprojection)
        to be robust to small coordinate differences.
      - If cfg.join_how == "inner", only matched provider rows are written.

    Args:
        cfg: ProviderJoinConfig.

    Returns:
        Number of rows written to cfg.output_table.
    """
    providers = gpd.read_file(cfg.geopackage_path, layer=cfg.geopackage_layer)

    # Be cautious about guessing CRS. If it's missing, better to fail loudly than be wrong.
    if providers.crs is None:
        raise ValueError(
            "Provider layer has no CRS. Set it in the GeoPackage or assign providers.set_crs(...) correctly."
        )

    # Load listing points from SQLite
    conn = sqlite3.connect(cfg.larentals_db_path)
    try:
        df = pd.read_sql_query(
            f"""
            SELECT
              {cfg.listing_id_col} AS listing_id,
              {cfg.lat_col} AS latitude,
              {cfg.lon_col} AS longitude
            FROM {cfg.listing_table}
            WHERE {cfg.lat_col} IS NOT NULL
              AND {cfg.lon_col} IS NOT NULL
            """,
            conn,
        )
    finally:
        conn.close()

    points = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326",
    )

    # Choose provider columns
    if cfg.provider_cols is None:
        desired = [
            "DBA",
            "TechCode",
            "MaxAdDn",
            "MaxAdUp",
            "MaxDnTier",
            "MaxUpTier",
            "MinDnTier",
            "MinUpTier",
            "Contact",
            "Busconsm",
            "Service_Type",
        ]
        provider_cols = [c for c in desired if c in providers.columns]
    else:
        missing = [c for c in cfg.provider_cols if c not in providers.columns]
        if missing:
            raise ValueError(f"Provider columns not found in GeoPackage layer: {missing}")
        provider_cols = list(cfg.provider_cols)

    providers = providers[provider_cols + ["geometry"]].copy()

    # --- Buffer in meters (project to meters first) ---
    if cfg.buffer_meters > 0:
        # Use Web Mercator for buffering; OK for small distances like 25–100m.
        providers_m = providers.to_crs("EPSG:3857")
        points_m = points.to_crs("EPSG:3857")

        points_m["geometry"] = points_m.geometry.buffer(cfg.buffer_meters)

        joined_m = gpd.sjoin(points_m, providers_m, how=cfg.join_how, predicate=cfg.predicate)

        # Back to WGS84 for consistent downstream usage (optional)
        joined = joined_m.to_crs("EPSG:4326")
    else:
        # No buffer: do the join directly (still reproject providers to points CRS)
        providers_wgs = providers.to_crs(points.crs)
        joined = gpd.sjoin(points, providers_wgs, how=cfg.join_how, predicate=cfg.predicate)

    # Drop geometry + join index
    out_df = joined.drop(columns=[c for c in ("geometry", "index_right") if c in joined.columns]).copy()

    # If we used join_how="left" for any reason, ensure we don't write null-provider rows
    if "DBA" in out_df.columns:
        out_df = out_df[out_df["DBA"].notna()].copy()

    conn = sqlite3.connect(cfg.larentals_db_path)
    try:
        out_df.to_sql(cfg.output_table, conn, if_exists="replace", index=False)
    finally:
        conn.close()

    return int(out_df.shape[0])
