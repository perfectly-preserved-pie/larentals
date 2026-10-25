"""Official property records and mapped hazards loaded independently of listings.

ZIMAS supplies city parcel records; CAL FIRE and FEMA cover the wider search
area. Source failures remain separate from successful queries with no records.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import sqlite3
from threading import Lock
import time
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
from loguru import logger
import requests

from functions.lahd import _property_address_parts, is_listing_in_los_angeles_city
from functions.data_paths import PROPERTY_CONTEXT_CACHE_PATH

ZIMAS_ORIGIN = "https://zimas.lacity.org"
ZIMAS_QUERY = f"{ZIMAS_ORIGIN}/arcgis/rest/services/zm4/landbase/MapServer/dynamicLayer/query"
ZIMAS_PROFILE = f"{ZIMAS_ORIGIN}/zm4WS/GetProjectData"
PERMIT_API = "https://data.lacity.org/resource/pi9x-tg5x.json"
PERMIT_SOURCE = "https://data.lacity.org/d/pi9x-tg5x"
FIRE_BASE = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/ArcGIS/rest/services"
FIRE_LRA = f"{FIRE_BASE}/FHSALRA25_v1_All/FeatureServer/0"
FIRE_SRA = f"{FIRE_BASE}/FHSZSRA_23_3/FeatureServer/0"
FIRE_SOURCE = "https://osfm.fire.ca.gov/what-we-do/community-wildfire-preparedness-and-mitigation/fire-hazard-severity-zones"
FLOOD_LAYER = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28"
FLOOD_SOURCE = "https://msc.fema.gov/portal/home"
SOURCE_TIMEOUT = (3.05, 8)
PERMIT_LIMIT = 25
CACHE_SECONDS = 6 * 60 * 60
FAILURE_CACHE_SECONDS = 60
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = Lock()

# Preserve the official labels and full zone strings: both zoning code systems
# and parcel-specific qualifiers can affect what a buyer can build.
PLANNING_FIELDS = {
    "Zoning", "Prior Zone", "Site Specific Condition", "Special Notes",
    "General Plan Land Use", "General Plan Note(s)", "Zoning Information (ZI)",
    "Minimum Density Requirement", "Hillside Area (Zoning Code)",
    "Specific Plan Area", "Historic Preservation Review", "HistoricPlacesLA",
    "Historic Preservation Overlay Zone", "Other Historic Designations",
    "Mills Act Contract", "CDO: Community Design Overlay",
    "CPIO: Community Plan Imp. Overlay", "HCR: Hillside Construction Regulation",
    "RFA: Residential Floor Area District", "Building Line",
    "SB 9 Eligibility", "AB 2097: Within a half mile of a Major Transit Stop",
}
HAZARD_FIELDS = {
    "Very High Fire Hazard Severity Zone", "Flood Zone", "Methane Hazard Site",
    "Alquist-Priolo Fault Zone", "Landslide", "Liquefaction",
    "Preliminary Fault Rupture Study Area", "Tsunami Hazard Area",
    "Tsunami Inundation Zone", "Coastal Zone", "Coastal Bluff Potential",
    "Canyon Bluff Potential", "Sea Level Rise Area", "High Wind Velocity Areas",
    "Special Grading Area (BOE Basic Grid Map A-13372)", "Watercourse", "Wells",
    "Oil Well Adjacency", "Active (1000 ft)", "Idle (200 ft)", "Plugged (100 ft)",
    "Any (100 ft)", "Airport Hazard", "Hazardous Waste / Border Zone Properties",
}
HOUSING_FIELDS = {
    "Rent Stabilization Ordinance (RSO)", "Ellis Act Property", "Date Filed on",
    "AB 1482: Tenant Protection Act", "Just Cause For Eviction Ordinance (JCO)",
    "Housing Use within Prior 5 Years", "Notes", "Address", "Year Built",
    "Use Code", "Assessor Parcel No. (APN)",
}


def _text(raw: object) -> str:
    """Strip source markup without interpreting it as application HTML.

    ZIMAS occasionally embeds formatting in field values. Plain text also keeps
    official descriptions safe when the browser builds the records drawer.
    """
    return BeautifulSoup(str(raw or ""), "html.parser").get_text(" ", strip=True)


def _source_json(url: str, params: dict[str, Any]) -> Any:
    """Read a fixed official endpoint and reject service-level errors.

    ArcGIS can return HTTP 200 with an error object or a truncated feature list;
    neither is evidence that the property has no records or hazards.
    """
    # The city's dynamic table and full profile routinely take about nine
    # seconds, so they need a longer budget than the smaller hazard queries.
    timeout = (3.05, 15) if url in {ZIMAS_QUERY, ZIMAS_PROFILE} else SOURCE_TIMEOUT
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and (payload.get("error") or payload.get("exceededTransferLimit")):
        raise ValueError("Official service returned an error or incomplete records")
    return payload


def _point_query(layer: str, latitude: float, longitude: float) -> list[dict[str, Any]]:
    """Intersect the listing point with an official hazard polygon layer.

    Empty intersections remain distinct from errors and are never converted to
    a low-hazard rating. Coordinates describe the listing point, not its parcel.
    """
    payload = _source_json(f"{layer}/query", {
        "f": "json", "geometry": f"{longitude},{latitude}",
        "geometryType": "esriGeometryPoint", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
        "returnGeometry": "false",
    })
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise ValueError("Missing hazard features")
    return [feature["attributes"] for feature in payload["features"]]


def _coordinates(listing: dict[str, Any]) -> tuple[float, float] | None:
    """Validate the point before querying statewide or federal services.

    The search serves Southern California. Reject zeroes, non-finite numbers,
    and points outside California rather than showing unrelated hazard data.
    """
    try:
        lat, lon = float(listing.get("latitude")), float(listing.get("longitude"))
    except (TypeError, ValueError):
        return None
    return (lat, lon) if math.isfinite(lat) and math.isfinite(lon) and 32 <= lat <= 42.1 and -125 <= lon <= -114 else None


def fetch_fire_context(listing: dict[str, Any]) -> dict[str, Any]:
    """Check current statewide SRA and recommended LRA fire hazard polygons.

    Both responsibility areas are queried: absence from LRA alone would miss
    properties covered by SRA. Local adoption may differ from recommendations.
    """
    context: dict[str, Any] = {"status": "unavailable", "source": "CAL FIRE", "source_url": FIRE_SOURCE, "zones": []}
    point = _coordinates(listing)
    if point is None:
        context["status"] = "missing_location"
        return context
    zones = []
    for area, layer in (("LRA (2025 recommended)", FIRE_LRA), ("SRA (effective April 2024)", FIRE_SRA)):
        for row in _point_query(layer, *point):
            label = _text(row.get("FHSZ_Description"))
            if label == "NonWildland":
                label = "Non-wildland (mapped)"
            if label:
                zones.append({"designation": label, "responsibility": area})
    context.update(status="available" if zones else "no_intersection", zones=zones)
    return context


def fetch_flood_context(listing: dict[str, Any]) -> dict[str, Any]:
    """Read FEMA zones at the listing point, preserving zone X subtypes.

    Zone X can describe different mapped conditions. Preserve its subtype and
    never interpret no returned polygon as proof of no flood exposure.
    """
    context: dict[str, Any] = {"status": "unavailable", "source": "FEMA NFHL", "source_url": FLOOD_SOURCE, "zones": []}
    point = _coordinates(listing)
    if point is None:
        context["status"] = "missing_location"
        return context
    rows = _point_query(FLOOD_LAYER, *point)
    zones = [{"zone": _text(row.get("FLD_ZONE")), "subtype": _text(row.get("ZONE_SUBTY")),
              "special_flood_hazard_area": row.get("SFHA_TF")} for row in rows if row.get("FLD_ZONE")]
    context.update(status="available" if zones else "no_intersection", zones=zones)
    return context


def _match_zimas_address(listing: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a unique city PIN by street address and ZIP, never proximity.

    A directionless MLS address is accepted only when one PIN remains. Distinct
    parcels with the same address stay unmatched even if one has more records.
    """
    parts = _property_address_parts(listing.get("full_street_address"))
    if parts is None:
        return None
    number, direction, route = parts
    # The public service accepts exact address lists. Broad multi-clause
    # searches can be rejected by its edge firewall even for valid ArcGIS SQL.
    directions = [direction] if direction else ["", "N", "S", "E", "W", "NE", "NW", "SE", "SW"]
    addresses = [" ".join(part for part in (number, candidate_direction, route) if part) for candidate_direction in directions]
    literals = ",".join("'" + address.replace("'", "''") + "'" for address in addresses)
    layer = {"source": {"type": "dataLayer", "dataSource": {
        "type": "table", "workspaceId": "w2", "dataSourceName": "zim4s.pin_address",
    }}}
    payload = _source_json(ZIMAS_QUERY, {
        "f": "json", "layer": json.dumps(layer),
        "where": f"ADDRESS IN ({literals})",
        "outFields": "PIN,ADDRESS,ZIP", "returnGeometry": "false",
    })
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise ValueError("Missing ZIMAS address features")
    postal = str(listing.get("zip_code") or "").strip().removesuffix(".0")[:5]
    candidates = {}
    for feature in payload["features"]:
        row = feature["attributes"]
        candidate = _property_address_parts(row.get("ADDRESS"))
        if candidate is None or candidate[0] != number or candidate[2] != route:
            continue
        if direction and direction != candidate[1]:
            continue
        if postal and str(row.get("ZIP")) != postal:
            continue
        if row.get("PIN"):
            candidates[row["PIN"]] = row
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def _zimas_row(row: dict[str, Any]) -> dict[str, str]:
    """Keep a source field's label, text, and safe official drill-through link.

    Private assessor fields are excluded by the caller. Only ZIMAS links are
    retained so source markup cannot introduce executable or unrelated URLs.
    """
    link = urljoin(ZIMAS_ORIGIN, str(row.get("Link") or ""))
    parsed = urlparse(link)
    return {"label": _text(row.get("Description")), "value": _text(row.get("Value")) or "Not reported",
            "url": link if row.get("Link") and parsed.scheme == "https" and parsed.netloc == "zimas.lacity.org" else ""}


def fetch_zimas_context(listing: dict[str, Any]) -> dict[str, Any]:
    """Load useful city parcel fields after an unambiguous address match.

    Request the full PIN profile without APN: supplying an APN makes ZIMAS
    return only assessor information. A profile with a different address or
    PIN is rejected before its zoning, housing, or permit records are exposed.
    """
    context: dict[str, Any] = {"status": "unavailable", "source": "LA City ZIMAS", "source_url": ZIMAS_ORIGIN,
                               "planning": [], "hazards": [], "housing": [], "cases": [], "apns": [], "pin": None}
    scope = is_listing_in_los_angeles_city(city=listing.get("city"), latitude=listing.get("latitude"), longitude=listing.get("longitude"))
    if scope is False:
        context["status"] = "outside_coverage"
        return context
    matched = _match_zimas_address(listing)
    if matched is None:
        context["status"] = "unmatched"
        return context
    pin = matched["PIN"]
    payload = _source_json(ZIMAS_PROFILE, {"PIN": pin, "APN": "", "project": ""})
    if not isinstance(payload, list):
        raise ValueError("Missing ZIMAS profile groups")
    groups = {group["Key"]: group["Value"] for group in payload}
    legal = groups.get("Address/Legal Information", [])
    addresses = [row.get("Value") for row in legal if row.get("Description") == "Site Address"]
    pins = [row.get("Value") for row in legal if row.get("Description") == "PIN Number"]
    if pin not in pins or not any(_property_address_parts(address) == _property_address_parts(matched["ADDRESS"]) for address in addresses):
        raise ValueError("ZIMAS profile does not match the selected address and PIN")
    context.update(status="available", pin=pin, address=matched["ADDRESS"],
                   source_url=f"{ZIMAS_ORIGIN}/?{urlencode({'pin': pin})}")
    for group, rows in groups.items():
        for row in rows:
            if row.get("IsPrivate"):
                continue
            label = _text(row.get("Description"))
            if group == "Address/Legal Information" and label == "Assessor Parcel No. (APN)":
                context["apns"].extend(re.findall(r"\b\d{10}\b", _text(row.get("Value"))))
            if group == "Planning and Zoning Information" and label in PLANNING_FIELDS:
                context["planning"].append(_zimas_row(row))
            elif group in {"Additional Information", "Seismic Hazards"} and label in HAZARD_FIELDS:
                context["hazards"].append(_zimas_row(row))
            elif group == "Housing" and label in HOUSING_FIELDS:
                context["housing"].append(_zimas_row(row))
            elif group == "Case Numbers" and _text(row.get("Value")) not in {"", "None"}:
                context["cases"].append(_zimas_row(row))
    context["apns"] = sorted(set(context["apns"]))
    return context


def fetch_permit_context(zimas: dict[str, Any]) -> dict[str, Any]:
    """Read recent issued building permits for the verified city PIN.

    PIN matching includes a shared site's records without guessing a condo's
    APN. Fetch one extra row to disclose truncation; issued permits are never
    presented as proof of completed work or a comprehensive permit history.
    """
    context: dict[str, Any] = {"status": zimas["status"], "source_url": PERMIT_SOURCE, "records": [], "has_more": False}
    if zimas["status"] != "available":
        return context
    pin = str(zimas["pin"]).replace("'", "''")
    rows = _source_json(PERMIT_API, {
        "$where": f"pin_nbr = '{pin}'", "$order": "issue_date DESC, permit_nbr DESC",
        "$select": "permit_nbr,primary_address,permit_type,work_desc,issue_date,status_desc,status_date,cofo_date,refresh_time",
        "$limit": PERMIT_LIMIT + 1,
    })
    if not isinstance(rows, list):
        raise ValueError("Missing city permit records")
    context.update(status="available", has_more=len(rows) > PERMIT_LIMIT,
                   records=[{key: _text(raw) for key, raw in row.items()} for row in rows[:PERMIT_LIMIT]])
    return context


def _safe_fetch(fetcher: Any, argument: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    """Isolate agency failures so the other property sections still load.

    The fallback carries an unavailable status, not an empty successful lookup.
    Logs identify the adapter while keeping third-party response bodies private.
    """
    try:
        return fetcher(argument)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        logger.warning("Property context {} unavailable: {}", fetcher.__name__, type(exc).__name__)
        return fallback


def _read_cached_context(key: str, now: float) -> dict[str, Any] | None:
    """Reuse a fresh snapshot across browser requests and Gunicorn workers.

    The disk cache is optional: a missing, corrupt, or unwritable artifact must
    never prevent a live lookup. Expired snapshots are not shown as current.
    """
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] > now:
            return deepcopy(cached[1])
    if not PROPERTY_CONTEXT_CACHE_PATH.exists():
        return None
    try:
        with sqlite3.connect(f"file:{PROPERTY_CONTEXT_CACHE_PATH}?mode=ro", uri=True, timeout=1) as conn:
            row = conn.execute("SELECT payload FROM property_context_cache WHERE cache_key = ? AND expires_at > ?", (key, now)).fetchone()
        return json.loads(row[0]) if row else None
    except (sqlite3.Error, OSError, ValueError):
        return None


def _cache_context(key: str, context: dict[str, Any], ttl: int) -> None:
    """Persist a bounded snapshot cache without making disk writes mandatory.

    Sharing six-hour successes avoids repeating slow city lookups in each
    worker. Partial outages expire after a minute so recovery stays visible.
    """
    expires = time.time() + ttl
    with _CACHE_LOCK:
        if len(_CACHE) >= 512:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = (expires, deepcopy(context))
    try:
        PROPERTY_CONTEXT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(PROPERTY_CONTEXT_CACHE_PATH, timeout=1) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS property_context_cache (cache_key TEXT PRIMARY KEY, expires_at REAL NOT NULL, payload TEXT NOT NULL)")
            conn.execute("INSERT OR REPLACE INTO property_context_cache VALUES (?, ?, ?)", (key, expires, json.dumps(context)))
            conn.execute("DELETE FROM property_context_cache WHERE expires_at <= ?", (time.time(),))
            conn.execute("DELETE FROM property_context_cache WHERE cache_key IN (SELECT cache_key FROM property_context_cache ORDER BY expires_at DESC LIMIT -1 OFFSET 2048)")
    except (sqlite3.Error, OSError):
        logger.warning("Property context disk cache unavailable; using process cache")


def get_property_context(listing: dict[str, Any]) -> dict[str, Any]:
    """Combine independently fetched hazards and verified city parcel records.

    Bounded memory and disk caches include address, ZIP, and coordinates so
    relisted homes and multiple workers share work while corrected listings
    cannot inherit an old location. Partial failures expire after a minute;
    successful snapshots last six hours.
    """
    identity = json.dumps([listing.get(field) for field in ("full_street_address", "zip_code", "city", "latitude", "longitude")], default=str)
    # Bump the version when changing matching rules or cached payload semantics.
    key = "v1:" + hashlib.sha256(identity.encode()).hexdigest()
    cached = _read_cached_context(key, time.time())
    if cached is not None:
        return cached
    with ThreadPoolExecutor(max_workers=3) as pool:
        fire = pool.submit(_safe_fetch, fetch_fire_context, listing, {"status": "unavailable", "source_url": FIRE_SOURCE, "zones": []})
        flood = pool.submit(_safe_fetch, fetch_flood_context, listing, {"status": "unavailable", "source_url": FLOOD_SOURCE, "zones": []})
        zimas = _safe_fetch(fetch_zimas_context, listing, {"status": "unavailable", "source_url": ZIMAS_ORIGIN, "planning": [], "hazards": [], "housing": [], "cases": [], "apns": [], "pin": None})
        permits = _safe_fetch(fetch_permit_context, zimas, {"status": "unavailable", "source_url": PERMIT_SOURCE, "records": [], "has_more": False})
        context = {"address": listing.get("full_street_address"), "checked_at": datetime.now(timezone.utc).isoformat(),
                   "fire": fire.result(), "flood": flood.result(), "zimas": zimas, "permits": permits}
    ttl = FAILURE_CACHE_SECONDS if any(context[section]["status"] == "unavailable" for section in ("fire", "flood", "zimas", "permits")) else CACHE_SECONDS
    _cache_context(key, context, ttl)
    return context
