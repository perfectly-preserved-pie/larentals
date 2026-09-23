"""Flag listing pins that disagree with their source ZIP, without API calls."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import geopandas as gpd
import pandas as pd

from functions.data_paths import LA_COUNTY_ZIP_CODES_PATH, LARENTALS_DB_PATH, SOCAL_SERVICE_AREA_ZIP_CODES_PATH


def audit_coordinates(
    db_path: Path,
    zip_path: Path,
    *,
    tolerance_miles: float = 1.0,
) -> pd.DataFrame:
    """Return listings whose pin lies beyond the tolerance of their ZIP polygon."""
    zip_areas = gpd.read_file(zip_path)[["ZIPCODE", "geometry"]]
    if SOCAL_SERVICE_AREA_ZIP_CODES_PATH.exists():
        # The county layer clips border ZIPs such as 90631. The service-area
        # layer has full ZIP shapes, so union both sources before measuring.
        service_areas = gpd.read_file(SOCAL_SERVICE_AREA_ZIP_CODES_PATH)[
            ["ZIPCODE", "geometry"]
        ]
        zip_areas = pd.concat([zip_areas, service_areas], ignore_index=True)
    zip_areas["ZIPCODE"] = zip_areas["ZIPCODE"].astype(str).str.zfill(5)
    zip_areas = zip_areas.dissolve(by="ZIPCODE").to_crs("EPSG:3310")
    zip_geometries = zip_areas.geometry.to_dict()

    with sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True) as conn:
        listings = pd.concat(
            [
                pd.read_sql_query(
                    f"SELECT mls_number, full_street_address, city, zip_code, "
                    f"latitude, longitude, geocode_status FROM {table}",
                    conn,
                ).assign(listing_type=table)
                for table in ("buy", "lease")
            ],
            ignore_index=True,
        )

    listings["zip_code"] = listings["zip_code"].astype("string").str.extract(
        r"^(\d{5})(?:\.0)?$", expand=False
    )
    address_zip = listings["full_street_address"].astype("string").str.extract(
        r"(?<!\d)(\d{5})(?:-\d{4})?\s*$", expand=False
    )
    listings["zip_source"] = "source_column"
    listings.loc[listings["zip_code"].isna(), "zip_source"] = "missing"
    listings.loc[listings["zip_code"].isna() & address_zip.notna(), "zip_source"] = (
        "address_suffix"
    )
    listings["zip_code"] = listings["zip_code"].fillna(address_zip)
    listings["latitude"] = pd.to_numeric(listings["latitude"], errors="coerce")
    listings["longitude"] = pd.to_numeric(listings["longitude"], errors="coerce")
    valid_coordinates = (
        listings["latitude"].between(-90, 90)
        & listings["longitude"].between(-180, 180)
    )
    listings["audit_status"] = "within_tolerance"
    listings.loc[~valid_coordinates, "audit_status"] = "missing_or_invalid_coordinates"
    listings.loc[valid_coordinates & listings["zip_code"].isna(), "audit_status"] = (
        "missing_zip"
    )
    listings.loc[
        valid_coordinates
        & listings["zip_code"].notna()
        & ~listings["zip_code"].isin(zip_geometries),
        "audit_status",
    ] = "zip_polygon_unavailable"
    listings["distance_outside_zip_miles"] = pd.Series(dtype="float64")

    comparable = valid_coordinates & listings["zip_code"].isin(zip_geometries)
    points = gpd.GeoSeries(
        gpd.points_from_xy(
            listings.loc[comparable, "longitude"],
            listings.loc[comparable, "latitude"],
        ),
        index=listings.index[comparable],
        crs="EPSG:4326",
    ).to_crs("EPSG:3310")
    distances = pd.Series(index=points.index, dtype="float64")
    for zip_code, indexes in listings.loc[comparable].groupby("zip_code").groups.items():
        distances.loc[indexes] = points.loc[indexes].distance(
            zip_geometries[zip_code]
        ) / 1609.344
    listings.loc[comparable, "distance_outside_zip_miles"] = distances
    listings.loc[
        comparable & listings["distance_outside_zip_miles"].gt(tolerance_miles),
        "audit_status",
    ] = "outside_zip"
    return listings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=LARENTALS_DB_PATH)
    parser.add_argument("--zip-polygons", type=Path, default=LA_COUNTY_ZIP_CODES_PATH)
    parser.add_argument("--tolerance-miles", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.tolerance_miles < 0:
        parser.error("--tolerance-miles must be nonnegative")

    results = audit_coordinates(
        args.db, args.zip_polygons, tolerance_miles=args.tolerance_miles
    )
    print(results["audit_status"].value_counts().to_string())
    flagged = results.loc[results["audit_status"] != "within_tolerance"].copy()
    flagged.sort_values("distance_outside_zip_miles", ascending=False, inplace=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        flagged.to_csv(args.output, index=False)
        print(f"Wrote {len(flagged)} flagged listings to {args.output}")
    else:
        print(flagged.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
