from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional, Sequence
import geopandas as gpd
import pandas as pd
import sqlite3

ListingTable = Literal["lease", "buy"]

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
    predicate: Literal["intersects", "within", "contains"] = "intersects"


def write_provider_options_from_geopackage(cfg: ProviderJoinConfig) -> int:
    """
    Spatially join listings (lat/lon points) to provider polygons from a GeoPackage layer,
    and write the joined results back into the larentals SQLite database.

    This creates/overwrites `cfg.output_table` as a *normalized* table:
      - one row per (listing_id × matching provider polygon)

    Args:
        cfg: ProviderJoinConfig.

    Returns:
        Number of rows written to cfg.output_table.
    """
    # 1) Load provider polygons from GeoPackage
    providers = gpd.read_file(cfg.geopackage_path, layer=cfg.geopackage_layer)

    # Ensure CRS is WGS84 (EPSG:4326) to match listing lat/lon
    if providers.crs is None:
        providers = providers.set_crs("EPSG:4326")
    else:
        providers = providers.to_crs("EPSG:4326")

    # Choose provider columns
    if cfg.provider_cols is None:
        # Sensible defaults for the CPUC layer you showed (adjust as needed)
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
        cfg_provider_cols = [c for c in desired if c in providers.columns]
    else:
        missing = [c for c in cfg.provider_cols if c not in providers.columns]
        if missing:
            raise ValueError(f"Provider columns not found in GeoPackage layer: {missing}")
        cfg_provider_cols = list(cfg.provider_cols)

    providers = providers[cfg_provider_cols + ["geometry"]].copy()

    # 2) Load listing points from SQLite
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

    # 3) Spatial join
    joined = gpd.sjoin(points, providers, how="left", predicate=cfg.predicate)

    # 4) Write back to SQLite (drop geometry + join index)
    out_df = joined.drop(columns=[c for c in ("geometry", "index_right") if c in joined.columns]).copy()

    conn = sqlite3.connect(cfg.larentals_db_path)
    try:
        out_df.to_sql(cfg.output_table, conn, if_exists="replace", index=False)
    finally:
        conn.close()

    return int(out_df.shape[0])
