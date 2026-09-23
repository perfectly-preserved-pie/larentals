"""Repair a reviewed set of issue #349 pins with bounded Google requests.

Each accepted result must match the source street number and ZIP, have no
partial-match flag, and land within the ZIP polygon. Results are recorded before
any database update. Run only for a small, reviewed MLS list.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path

import geopandas as gpd
from dotenv import load_dotenv
from geopy.geocoders import GoogleV3
from shapely.geometry import Point

from functions.data_paths import CHECKPOINT_DIR, LA_COUNTY_ZIP_CODES_PATH, LARENTALS_DB_PATH
from functions.listing_pipeline_checkpoint import address_fingerprint


QUERY_OVERRIDES = {
    "WS26159447MR": "181 Promenade St, Pomona, CA 91767",
    "PW26202374MR": "2020 Thomas St, Los Angeles, CA 90031",
    "SR26187357MR": "15328 E Avenue Q-1, Lake Los Angeles, CA 93591",
}

REVIEWED_IDS = {
    "buy": ("WS26159447MR", "PW26202374MR"),
    "lease": ("SR26187357MR", "SR25188918MR", "SR25037140MR", "26857683", "26832609"),
}


def component(raw: dict, kind: str) -> str | None:
    for item in raw.get("address_components", []):
        if kind in item.get("types", []):
            return str(item.get("long_name", ""))
    return None


def street_key(value: str) -> str:
    value = re.sub(r"[^a-z0-9]", "", value.casefold())
    for suffix in ("boulevard", "blvd", "avenue", "ave", "street", "st", "road", "rd"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-requests", type=int, default=6)
    parser.add_argument("--only-mls", nargs="*", help="Restrict the reviewed MLS numbers")
    parser.add_argument("--db", type=Path, default=LARENTALS_DB_PATH)
    parser.add_argument("--output", type=Path, default=Path("data/audits/issue_349/repair_results.json"))
    parser.add_argument("--apply", action="store_true", help="Write accepted fixes to the local database and checkpoints")
    args = parser.parse_args()
    if not 0 <= args.max_requests <= 10:
        parser.error("--max-requests must be between 0 and 10")
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        parser.error("GOOGLE_API_KEY is unavailable")

    polygons = gpd.read_file(LA_COUNTY_ZIP_CODES_PATH)[["ZIPCODE", "geometry"]]
    polygons["ZIPCODE"] = polygons["ZIPCODE"].astype(str).str.zfill(5)
    polygons = polygons.dissolve(by="ZIPCODE").to_crs("EPSG:3310").geometry.to_dict()
    geocoder = GoogleV3(api_key=api_key)
    rows = []
    with sqlite3.connect(f"file:{args.db.resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        for table, ids in REVIEWED_IDS.items():
            for mls in ids:
                if args.only_mls and mls not in args.only_mls:
                    continue
                row = conn.execute(
                    f"SELECT mls_number, full_street_address, city, zip_code, latitude, longitude "
                    f"FROM {table} WHERE mls_number = ?", (mls,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"Missing {table} listing {mls}")
                rows.append({"listing_type": table, **dict(row)})

    requested = {}
    results = []
    for row in rows:
        address = row["full_street_address"]
        zip_match = re.fullmatch(r"(\d{5})(?:\.0)?", str(row["zip_code"]).strip())
        if not zip_match:
            zip_match = re.search(r"(?<!\d)(\d{5})(?:\.0)?\s*$", str(address))
        street_match = re.match(r"\s*(\d+)\s+([^,]+)", str(address))
        if not zip_match or not street_match:
            raise ValueError(f"Unusable address for {row['mls_number']}: {address}")
        zip_code = zip_match.group(1)
        number = street_match.group(1)
        street = re.split(r"\s+(?:#|apt\b|unit\b|ste\b)", street_match.group(2), maxsplit=1, flags=re.I)[0]
        city = row["city"]
        if not city or str(city).strip().casefold() in {"none", "nan", "assessor"}:
            city = re.sub(
                r"\s+\d{5}(?:\.0)?$", "", str(address).split(",", 1)[-1]
            ).strip()
        query = QUERY_OVERRIDES.get(
            row["mls_number"], f"{number} {street.strip()}, {city}, CA {zip_code}"
        )
        outcome = {**row, "query": query, "accepted": False}
        if zip_code in polygons:
            old_point = gpd.GeoSeries(
                [Point(row["longitude"], row["latitude"])], crs="EPSG:4326"
            ).to_crs("EPSG:3310").iloc[0]
            if old_point.distance(polygons[zip_code]) / 1609.344 <= 1.0:
                outcome["reason"] = "already_within_zip"
                results.append(outcome)
                continue
        if query not in requested:
            if len(requested) >= args.max_requests:
                outcome["reason"] = "request_cap"
                results.append(outcome)
                continue
            try:
                requested[query] = geocoder.geocode(
                    query, timeout=10, exactly_one=True,
                    components={"postal_code": zip_code, "country": "US"},
                )
            except Exception as exc:
                requested[query] = exc
        location = requested[query]
        if isinstance(location, Exception):
            outcome["reason"] = f"geocoder_error:{type(location).__name__}"
        elif location is None:
            outcome["reason"] = "no_result"
        else:
            raw = location.raw
            result_number = component(raw, "street_number")
            result_zip = component(raw, "postal_code")
            result_route = component(raw, "route")
            route_score = SequenceMatcher(
                None, street_key(street), street_key(result_route or "")
            ).ratio()
            point = gpd.GeoSeries([Point(location.longitude, location.latitude)], crs="EPSG:4326").to_crs("EPSG:3310").iloc[0]
            miles_outside = point.distance(polygons[zip_code]) / 1609.344 if zip_code in polygons else None
            outcome.update({
                "returned_address": location.address,
                "new_latitude": location.latitude,
                "new_longitude": location.longitude,
                "returned_street_number": result_number,
                "returned_zip": result_zip,
                "returned_route": result_route,
                "route_score": round(route_score, 3),
                "partial_match": bool(raw.get("partial_match")),
                "location_type": raw.get("geometry", {}).get("location_type"),
                "miles_outside_zip": miles_outside,
            })
            accepted = (
                not raw.get("partial_match")
                and result_number == number
                and result_zip == zip_code
                and route_score >= 0.65
                and miles_outside is not None
                and miles_outside <= 1.0
                and outcome["location_type"] in {"ROOFTOP", "RANGE_INTERPOLATED"}
            )
            outcome["accepted"] = accepted
            outcome["reason"] = "validated" if accepted else "validation_failed"
        results.append(outcome)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"request_count": len(requested), "results": results}, indent=2) + "\n")
    print(f"Requests: {len(requested)}; validated: {sum(r['accepted'] for r in results)}; report: {args.output}")
    if not args.apply:
        return

    with sqlite3.connect(args.db) as conn:
        for result in results:
            if not result["accepted"]:
                continue
            table = result["listing_type"]
            cursor = conn.execute(
                f"UPDATE {table} SET latitude = ?, longitude = ?, geocode_status = 'success', "
                f"geocode_provider = 'google', geocode_address_hash = ? "
                f"WHERE mls_number = ? AND latitude = ? AND longitude = ?",
                (result["new_latitude"], result["new_longitude"],
                 address_fingerprint(result["full_street_address"]), result["mls_number"],
                 result["latitude"], result["longitude"]),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Listing changed during repair: {table} {result['mls_number']}")
    for table in REVIEWED_IDS:
        with sqlite3.connect(CHECKPOINT_DIR / f"{table}.sqlite") as conn:
            for result in results:
                if result["listing_type"] != table or not result["accepted"]:
                    continue
                conn.execute(
                    "UPDATE listing_checkpoint SET latitude = ?, longitude = ?, "
                    "geocode_status = 'success', geocode_error = NULL, geocode_provider = 'google', "
                    "geocode_address_hash = ? WHERE mls_number = ?",
                    (result["new_latitude"], result["new_longitude"],
                     address_fingerprint(result["full_street_address"]), result["mls_number"]),
                )
    print("Applied validated coordinates to the listing database and existing checkpoints")


if __name__ == "__main__":
    main()
