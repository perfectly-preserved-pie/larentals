"""Run one resumable, ZIP-restricted Google lookup per flagged building."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import geopandas as gpd
import pandas as pd
from dotenv import load_dotenv
from geopy.geocoders import GoogleV3
from shapely.geometry import Point

from functions.data_paths import CHECKPOINT_DIR, LA_COUNTY_ZIP_CODES_PATH, LARENTALS_DB_PATH, SOCAL_SERVICE_AREA_ZIP_CODES_PATH
from functions.listing_pipeline_checkpoint import ListingCheckpointStore, address_fingerprint


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


def prepare(row: dict) -> dict | None:
    address = str(row.get("full_street_address") or "")
    match = re.match(r"\s*(\d+)\s+([^,]+),\s*(.+)$", address)
    zip_match = re.fullmatch(r"(\d{5})(?:\.0)?", str(row.get("zip_code") or "").strip())
    if not match or not zip_match:
        return None
    number, street, locality = match.groups()
    street = re.split(r"\s+(?:#{1,2}|apt\b|unit\b|ste\b)", street, maxsplit=1, flags=re.I)[0].strip()
    city = str(row.get("city") or "").strip()
    if city.casefold() in {"", "none", "nan", "assessor"}:
        city = re.sub(r"\s+\d{5}(?:\.0)?\s*$", "", locality).strip()
    zip_code = zip_match.group(1)
    query = re.sub(r"\s+", " ", f"{number} {street}, {city}, CA {zip_code}").strip()
    return {"number": number, "street": street, "city": city, "zip": zip_code, "query": query}


def apply_result(conn: sqlite3.Connection, stores: dict, entry: dict) -> int:
    if not entry.get("accepted"):
        return 0
    changed = 0
    for row in entry["members"]:
        table, mls = row["listing_type"], row["mls_number"]
        current = conn.execute(
            f"SELECT full_street_address, latitude, longitude FROM {table} WHERE mls_number = ?", (mls,)
        ).fetchone()
        if current is None:
            raise RuntimeError(f"Missing listing {table} {mls}")
        address, lat, lon = current
        new_lat, new_lon = entry["new_latitude"], entry["new_longitude"]
        if abs(float(lat) - new_lat) < 1e-8 and abs(float(lon) - new_lon) < 1e-8:
            continue
        if abs(float(lat) - float(row["latitude"])) > 1e-8 or abs(float(lon) - float(row["longitude"])) > 1e-8:
            raise RuntimeError(f"Listing changed during repair: {table} {mls}")
        stores[table].checkpoint(
            mls, geocode_status="success", geocode_error=None, geocode_provider="google",
            geocode_address_hash=address_fingerprint(address), latitude=new_lat, longitude=new_lon,
        )
        cursor = conn.execute(
            f"UPDATE {table} SET latitude = ?, longitude = ?, geocode_status = 'success', "
            f"geocode_provider = 'google', geocode_address_hash = ? "
            f"WHERE mls_number = ? AND latitude = ? AND longitude = ?",
            (new_lat, new_lon, address_fingerprint(address), mls, lat, lon),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"Listing changed during repair: {table} {mls}")
        changed += 1
    conn.commit()
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=Path("data/audits/issue_349/zip_coordinate_audit_after.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/audits/issue_349/bulk_pass1.jsonl"))
    parser.add_argument("--db", type=Path, default=LARENTALS_DB_PATH)
    parser.add_argument("--max-requests", type=int, default=400)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.max_requests < 0:
        parser.error("--max-requests must be nonnegative")
    load_dotenv()
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        parser.error("GOOGLE_API_KEY is unavailable")
    geocoder = GoogleV3(api_key=key)
    polygons = pd.concat([
        gpd.read_file(LA_COUNTY_ZIP_CODES_PATH)[["ZIPCODE", "geometry"]],
        gpd.read_file(SOCAL_SERVICE_AREA_ZIP_CODES_PATH)[["ZIPCODE", "geometry"]],
    ], ignore_index=True)
    polygons["ZIPCODE"] = polygons["ZIPCODE"].astype(str).str.zfill(5)
    polygons = polygons.dissolve(by="ZIPCODE").to_crs("EPSG:3310").geometry.to_dict()
    flagged = pd.read_csv(args.audit, dtype={"mls_number": "string", "zip_code": "string"})
    flagged = flagged[flagged["audit_status"] == "outside_zip"]
    groups = defaultdict(list)
    skipped = []
    for row in flagged.to_dict("records"):
        details = prepare(row)
        if details is None:
            skipped.append(row["mls_number"])
            continue
        key_tuple = (details["query"].casefold(), details["zip"])
        groups[key_tuple].append(row)
    ordered = sorted(groups.values(), key=lambda rows: max(r["distance_outside_zip_miles"] for r in rows), reverse=True)
    existing = {}
    if args.output.exists():
        for line in args.output.read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                existing[entry["group_key"]] = entry
    stores = {
        table: ListingCheckpointStore(CHECKPOINT_DIR / f"{table}.sqlite", listing_type=table)
        for table in ("buy", "lease")
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    requests = accepted = updated = 0
    with sqlite3.connect(args.db) as conn, args.output.open("a", encoding="utf-8") as report:
        for index, rows in enumerate(ordered, start=1):
            details = prepare(rows[0])
            assert details is not None
            group_key = details["query"].casefold() + "|" + details["zip"]
            if group_key in existing:
                entry = existing[group_key]
            else:
                if requests >= args.max_requests:
                    print(f"Stopped at request cap {args.max_requests}", flush=True)
                    break
                entry = {
                    "group_key": group_key, "query": details["query"], "source_zip": details["zip"],
                    "members": [
                        {"listing_type": r["listing_type"], "mls_number": str(r["mls_number"]),
                         "latitude": r["latitude"], "longitude": r["longitude"]}
                        for r in rows
                    ],
                    "accepted": False,
                }
                try:
                    location = geocoder.geocode(
                        details["query"], timeout=12, exactly_one=True,
                        components={"postal_code": details["zip"], "country": "US"},
                    )
                    requests += 1
                    if location is None:
                        entry["reason"] = "no_result"
                    else:
                        raw = location.raw
                        number = component(raw, "street_number")
                        route = component(raw, "route")
                        returned_zip = component(raw, "postal_code")
                        location_type = raw.get("geometry", {}).get("location_type")
                        route_score = SequenceMatcher(
                            None, street_key(details["street"]), street_key(route or "")
                        ).ratio()
                        point = gpd.GeoSeries(
                            [Point(location.longitude, location.latitude)], crs="EPSG:4326"
                        ).to_crs("EPSG:3310").iloc[0]
                        miles_outside = point.distance(polygons[details["zip"]]) / 1609.344
                        entry.update({
                            "returned_address": location.address, "returned_number": number,
                            "returned_route": route, "returned_zip": returned_zip,
                            "location_type": location_type, "partial_match": bool(raw.get("partial_match")),
                            "route_score": round(route_score, 3), "miles_outside_zip": round(miles_outside, 4),
                            "new_latitude": location.latitude, "new_longitude": location.longitude,
                        })
                        entry["accepted"] = bool(
                            not raw.get("partial_match") and number == details["number"]
                            and returned_zip == details["zip"] and route_score >= 0.65
                            and location_type in {"ROOFTOP", "RANGE_INTERPOLATED"}
                            and miles_outside <= 1.0
                        )
                        entry["reason"] = "validated" if entry["accepted"] else "validation_failed"
                except Exception as exc:
                    requests += 1
                    entry["reason"] = f"error:{type(exc).__name__}"
                report.write(json.dumps(entry, ensure_ascii=False) + "\n")
                report.flush()
                existing[group_key] = entry
                time.sleep(0.1)
            if entry.get("accepted"):
                accepted += 1
                if args.apply:
                    updated += apply_result(conn, stores, entry)
            if index % 25 == 0:
                print(f"{index}/{len(ordered)} groups; {requests} new requests; {accepted} accepted groups; {updated} rows updated", flush=True)
    print(f"Done: {len(ordered)} groups, {requests} new requests, {accepted} accepted groups, {updated} rows updated, {len(skipped)} unparseable rows", flush=True)


if __name__ == "__main__":
    main()
