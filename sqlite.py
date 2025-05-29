#!/usr/bin/env python3
"""
Convert GeoJSON files into a SQLite database with two tables: 'lease' and 'buy'.
Each GeoJSON must have a 'context' property with {'pageType': 'lease'|'buy'},
or its filename must contain 'lease' or 'buy'.
"""

import os
import glob
import sqlite3
from typing import Optional

import geopandas as gpd


def convert_geojson_to_db(geojson_dir: str, db_path: str) -> None:
    """
    Scan a directory for GeoJSON files and append their contents into 
    SQLite tables 'lease' or 'buy', creating the DB if it doesn't exist.

    Args:
        geojson_dir (str): Directory containing GeoJSON files (*.geojson).
        db_path (str): Path to the SQLite database file.
    """
    # Ensure the database directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Open (or create) the SQLite database
    conn = sqlite3.connect(db_path)

    # Glob all .geojson files
    pattern = os.path.join(geojson_dir, "*.geojson")
    files = glob.glob(pattern)
    if not files:
        print(f"No GeoJSON files found in {geojson_dir!r}")
        conn.close()
        return

    for path in files:
        print(f"Processing {os.path.basename(path)}...")
        # Read the GeoJSON into a GeoDataFrame
        gdf = gpd.read_file(path)

        # Extract latitude/longitude from geometry
        if "geometry" in gdf:
            gdf["latitude"] = gdf.geometry.y
            gdf["longitude"] = gdf.geometry.x
            gdf = gdf.drop(columns=["geometry"])

        # Determine target table:
        table = _detect_table_from_context_or_name(gdf, path)

        # Append to table (will create it if needed, with columns matching the DF)
        gdf.to_sql(table, conn, if_exists="append", index=False)
        print(f" → Appended {len(gdf)} rows to '{table}'")

    conn.close()
    print("Done.")


def _detect_table_from_context_or_name(gdf: gpd.GeoDataFrame, 
                                       filepath: str) -> str:
    """
    Decide whether rows belong in 'lease' or 'buy'.

    Priority:
      1. If there's a dict column 'context' with key 'pageType'
      2. Else, look for 'lease' or 'buy' in the filename
      3. Default to 'lease'

    Args:
        gdf (gpd.GeoDataFrame): The data frame just read.
        filepath (str): The path to the GeoJSON file.

    Returns:
        str: 'lease' or 'buy'
    """
    ctx = gdf.get("context")
    if ctx is not None:
        # assume first row's context applies to all
        first = ctx.iloc[0]
        if isinstance(first, dict):
            pt = first.get("pageType")
            if pt in ("lease", "buy"):
                # drop the context column so it doesn't end up in the table
                gdf.drop(columns=["context"], inplace=True)
                return pt

    name = os.path.basename(filepath).lower()
    if "buy" in name:
        return "buy"
    if "lease" in name:
        return "lease"
    return "lease"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert GeoJSON files to a SQLite database."
    )
    parser.add_argument(
        "--geojson-dir", "-i", required=True,
        help="Directory where your .geojson files live"
    )
    parser.add_argument(
        "--db-path", "-d", default="assets/datasets/larentals.db",
        help="Target SQLite DB (will be created if missing)"
    )
    args = parser.parse_args()

    convert_geojson_to_db(args.geojson_dir, args.db_path)
