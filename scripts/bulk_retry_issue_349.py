"""Retry unresolved issue #349 buildings with at most two query variants each."""

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
from functions.listing_pipeline_checkpoint import ListingCheckpointStore
from scripts.bulk_repair_issue_349 import apply_result, component, prepare, street_key


def suffix(value: str) -> str | None:
    match = re.search(r"\b(street|st|avenue|ave|boulevard|blvd|road|rd|lane|ln|drive|dr|way|wy|place|pl|court|ct)\s*$", value, re.I)
    if not match:
        return None
    aliases = {"street": "st", "avenue": "ave", "boulevard": "blvd", "road": "rd", "lane": "ln", "drive": "dr", "way": "wy", "place": "pl", "court": "ct"}
    value = match.group(1).lower()
    return aliases.get(value, value)


def variants(details: dict) -> list[tuple[str, bool]]:
    street = details["street"]
    city = details["city"]
    zip_code = details["zip"]
    number = details["number"]
    candidates = []
    grid = re.sub(r"\b(Avenue|Ave)\s+([A-Z])(\d+)\b", r"\1 \2-\3", street, flags=re.I)
    if grid != street:
        candidates.append((f"{number} {grid}, {city}, CA {zip_code}", True))
    elif re.match(r"^1/2\s+", street):
        candidates.append((f"{number} {re.sub(r'^1/2\s+', '', street)}, {city}, CA {zip_code}", True))
    elif suffix(street) is None and not re.search(r"\b(?:avenue|ave|blvd|boulevard)\b", street, re.I):
        candidates.append((f"{number} {street} St, {city}, CA {zip_code}", True))
    candidates.append((f"{number} {street}, {city}, CA", False))
    return candidates[:2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=Path("data/audits/issue_349/zip_coordinate_audit_live_pass2.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/audits/issue_349/bulk_retry.jsonl"))
    parser.add_argument("--max-requests", type=int, default=200)
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
    groups = defaultdict(list)
    for row in flagged[flagged.audit_status == "outside_zip"].to_dict("records"):
        details = prepare(row)
        if details:
            groups[details["query"].casefold() + "|" + details["zip"]].append(row)
    ordered = sorted(groups.items(), key=lambda pair: max(r["distance_outside_zip_miles"] for r in pair[1]), reverse=True)
    existing = {}
    if args.output.exists():
        for line in args.output.read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                existing[entry["group_key"]] = entry
    stores = {
        t: ListingCheckpointStore(CHECKPOINT_DIR / f"{t}.sqlite", listing_type=t)
        for t in ("buy", "lease")
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    requests = accepted = updated = 0
    with sqlite3.connect(LARENTALS_DB_PATH) as conn, args.output.open("a", encoding="utf-8") as report:
        for index, (group_key, rows) in enumerate(ordered, start=1):
            if group_key in existing:
                entry = existing[group_key]
            else:
                details = prepare(rows[0])
                assert details is not None
                entry = {
                    "group_key": group_key, "source_query": details["query"], "source_zip": details["zip"],
                    "members": [
                        {"listing_type": r["listing_type"], "mls_number": str(r["mls_number"]),
                         "latitude": r["latitude"], "longitude": r["longitude"]}
                        for r in rows
                    ], "attempts": [], "accepted": False,
                }
                for query, restricted in variants(details):
                    if requests >= args.max_requests:
                        entry["reason"] = "request_cap"
                        break
                    try:
                        components = {"country": "US"}
                        if restricted:
                            components["postal_code"] = details["zip"]
                        else:
                            components["administrative_area"] = "CA"
                        location = geocoder.geocode(query, timeout=12, exactly_one=True, components=components)
                        requests += 1
                        attempt = {"query": query, "restricted": restricted}
                        if location is None:
                            attempt["reason"] = "no_result"
                        else:
                            raw = location.raw
                            number = component(raw, "street_number")
                            route = component(raw, "route")
                            returned_zip = component(raw, "postal_code")
                            precision = raw.get("geometry", {}).get("location_type")
                            score = SequenceMatcher(None, street_key(details["street"]), street_key(route or "")).ratio()
                            point = gpd.GeoSeries([Point(location.longitude, location.latitude)], crs="EPSG:4326").to_crs("EPSG:3310").iloc[0]
                            miles_outside = point.distance(polygons[details["zip"]]) / 1609.344
                            same_suffix = suffix(details["street"]) in {None, suffix(route or "")}
                            precise = precision in {"ROOFTOP", "RANGE_INTERPOLATED", "GEOMETRIC_CENTER"}
                            partial_ok = not raw.get("partial_match") or (precision == "ROOFTOP" and same_suffix)
                            valid = bool(
                                number == details["number"] and returned_zip == details["zip"]
                                and score >= 0.65 and miles_outside <= 1.0 and precise and partial_ok
                            )
                            attempt.update({
                                "returned_address": location.address, "returned_number": number,
                                "returned_route": route, "returned_zip": returned_zip,
                                "location_type": precision, "partial_match": bool(raw.get("partial_match")),
                                "route_score": round(score, 3), "miles_outside_zip": round(miles_outside, 4),
                                "latitude": location.latitude, "longitude": location.longitude,
                                "reason": "validated" if valid else "validation_failed",
                            })
                            if valid:
                                entry.update({"accepted": True, "reason": "validated", "new_latitude": location.latitude, "new_longitude": location.longitude})
                        entry["attempts"].append(attempt)
                        if entry["accepted"]:
                            break
                    except Exception as exc:
                        requests += 1
                        entry["attempts"].append({"query": query, "reason": f"error:{type(exc).__name__}"})
                    time.sleep(0.1)
                if "reason" not in entry:
                    entry["reason"] = "unresolved"
                report.write(json.dumps(entry, ensure_ascii=False) + "\n")
                report.flush()
                existing[group_key] = entry
            if entry["accepted"]:
                accepted += 1
                if args.apply:
                    updated += apply_result(conn, stores, entry)
            if index % 20 == 0:
                print(f"{index}/{len(ordered)} groups; {requests} new requests; {updated} rows updated", flush=True)
    print(f"Done: {len(ordered)} groups; {requests} new requests; {accepted} accepted groups; {updated} rows updated", flush=True)


if __name__ == "__main__":
    main()
