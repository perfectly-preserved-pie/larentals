from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeAlias, TypedDict
import concurrent.futures
import gzip
import math
import os
import re
import time

from loguru import logger
import orjson
import requests
from shapely.geometry import Point, shape


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAHD_INVESTIGATION_DATASET_URL = "https://data.lacity.org/resource/eagk-wq48.json"
LAHD_VIOLATION_DATASET_URL = "https://data.lacity.org/resource/cr8f-uc4j.json"
LAHD_INVESTIGATION_SOURCE_URL = "https://data.lacity.org/d/eagk-wq48"
LAHD_VIOLATION_SOURCE_URL = "https://data.lacity.org/d/cr8f-uc4j"
LAHD_PARCEL_QUERY_URL = "https://maps.lacity.org/lahub/rest/services/Landbase_Information/MapServer/7/query"
LAHD_LOCAL_ARTIFACT_PATH = PROJECT_ROOT / "assets" / "datasets" / "lahd_property_heatmap.json.gz"
LAHD_LOCAL_LOOKUP_ARTIFACT_PATH = PROJECT_ROOT / "assets" / "datasets" / "lahd_property_lookup.json.gz"
LAHD_GEOCODE_CACHE_PATH = PROJECT_ROOT / "assets" / "datasets" / "lahd_property_geocode_cache.json"
LA_CITY_BOUNDARY_PATH = PROJECT_ROOT / "assets" / "datasets" / "la_city_boundary.geojson"
LAHD_REQUEST_TIMEOUT_SECONDS = 180
LAHD_ARTIFACT_VERSION = 1
LAHD_DEFAULT_AGGREGATE_LIMIT = 25000
LAHD_DEFAULT_LOOKUP_LIMIT = 50000
LAHD_RECORD_DETAIL_LIMIT = 5000
LAHD_MAX_HEAT_POINTS = 10000
LAHD_MAX_MARKER_POINTS = 3000
LAHD_HEAT_INTENSITY_FLOOR = 0.12
LAHD_MARKER_ZOOM_MIN = 15
LAHD_HEAT_ZOOM_MAX = 16
LAHD_PARCEL_BATCH_SIZE = 500
LAHD_COORDINATE_BOUNDS = {
    "min_lat": 33.70,
    "max_lat": 34.35,
    "min_lon": -118.70,
    "max_lon": -118.10,
}

JsonDict: TypeAlias = dict[str, Any]
GeoJsonDict: TypeAlias = dict[str, Any]
HeatPointTuple: TypeAlias = list[float]
MarkerPointTuple: TypeAlias = list[float | int | str | None]

LAHD_LISTING_LOOKUP_MAX_DISTANCE_METERS = 65.0
LAHD_LOOKUP_SPATIAL_CELL_DEGREES = 0.001
_LA_CITY_LISTING_CITY_LABELS = {
    "ARLETA",
    "CANOGA PARK",
    "CHATSWORTH",
    "ENCINO",
    "GRANADA HILLS",
    "HARBOR CITY",
    "HOLLYWOOD",
    "LOS ANGELES",
    "NORTH HOLLYWOOD",
    "NORTHRIDGE",
    "PACIFIC PALISADES",
    "PACOIMA",
    "PANORAMA CITY",
    "PLAYA DEL REY",
    "RESEDA",
    "SAN PEDRO",
    "SHERMAN OAKS",
    "STUDIO CITY",
    "SUN VALLEY",
    "SUNLAND",
    "SYLMAR",
    "TARZANA",
    "TUJUNGA",
    "VALLEY GLEN",
    "VALLEY VILLAGE",
    "VAN NUYS",
    "VENICE",
    "WEST HILLS",
    "WESTCHESTER",
    "WESTWOOD",
    "WILMINGTON",
    "WINNETKA",
    "WOODLAND HILLS",
}
_STREET_SUFFIX_NORMALIZATION = {
    "ALY": "ALY",
    "AVE": "AVE",
    "AV": "AVE",
    "AVENUE": "AVE",
    "BLVD": "BLVD",
    "BL": "BLVD",
    "BOULEVARD": "BLVD",
    "CT": "CT",
    "COURT": "CT",
    "DR": "DR",
    "DRIVE": "DR",
    "HWY": "HWY",
    "HIGHWAY": "HWY",
    "LN": "LN",
    "LANE": "LN",
    "PKWY": "PKWY",
    "PARKWAY": "PKWY",
    "PL": "PL",
    "PLACE": "PL",
    "PLZ": "PLZ",
    "PLAZA": "PLZ",
    "RD": "RD",
    "ROAD": "RD",
    "ST": "ST",
    "STREET": "ST",
    "TER": "TER",
    "TERRACE": "TER",
    "WAY": "WAY",
}
_UNIT_RE = re.compile(
    r"\s+(?:#|APT|APARTMENT|UNIT|STE|SUITE|ROOM|RM|SPACE|SPC|BLDG|BUILDING|FL|FLOOR)\.?\s*.*$",
    re.IGNORECASE,
)


class LahdPropertyAggregate(TypedDict):
    """Merged LAHD property summary used by the client-side heat layer."""

    apn: str
    address: str
    investigation_case_count: int
    closed_case_count: int
    open_case_count: int
    violation_row_count: int
    violations_cited: int
    violations_cleared: int
    unresolved_violation_count: int
    documented_issue_count: int
    unresolved_issue_count: int
    problem_score: int
    first_case_date: str | None
    latest_case_date: str | None
    lat: float
    lon: float


class LahdLayerMetadata(TypedDict):
    """Metadata attached to the derived LAHD heatmap payload."""

    aggregate_limit: int
    heat_point_count: int
    marker_point_count: int
    geocoded_property_count: int
    max_problem_score: int
    investigation_source_url: str
    violation_source_url: str
    parcel_source_url: str
    data_source: str
    generated_at: str
    artifact_version: int


class LahdLookupMetadata(TypedDict):
    """Metadata attached to the LAHD property lookup payload."""

    aggregate_limit: int
    lookup_record_count: int
    max_problem_score: int
    investigation_source_url: str
    violation_source_url: str
    parcel_source_url: str
    data_source: str
    generated_at: str
    artifact_version: int


class LahdListingLookupResult(TypedDict):
    """Popup-ready LAHD summary for a listing marker."""

    matched: bool
    data_available: bool
    match_type: str | None
    match_distance_meters: float | None
    address: str | None
    apn: str | None
    problem_score: int
    documented_issue_count: int
    unresolved_issue_count: int
    investigation_case_count: int
    open_case_count: int
    violations_cited: int
    unresolved_violation_count: int
    latest_case_date: str | None
    jurisdiction_in_scope: bool | None


def _generated_timestamp() -> str:
    """
    Return an RFC 3339-like UTC timestamp for payload metadata.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_valid_heat_geojson(payload: Any) -> bool:
    """
    Check whether a decoded object looks like the expected LAHD layer payload.
    """
    return (
        isinstance(payload, dict)
        and payload.get("type") == "FeatureCollection"
        and isinstance(payload.get("features"), list)
    )


def load_local_lahd_property_heat_geojson() -> GeoJsonDict | None:
    """
    Load the precomputed LAHD property heatmap artifact when present.
    """
    artifact_path = LAHD_LOCAL_ARTIFACT_PATH
    if not artifact_path.exists():
        return None

    try:
        with gzip.open(artifact_path, "rb") as artifact_file:
            payload = orjson.loads(artifact_file.read())
    except OSError as exc:
        logger.warning(f"Failed reading LAHD property heatmap artifact from {artifact_path}: {exc}")
        return None
    except orjson.JSONDecodeError as exc:
        logger.warning(f"Failed decoding LAHD property heatmap artifact at {artifact_path}: {exc}")
        return None

    if not _is_valid_heat_geojson(payload):
        logger.warning(f"LAHD property heatmap artifact at {artifact_path} is not a valid FeatureCollection.")
        return None

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        metadata["data_source"] = "local_artifact"
        metadata.setdefault("artifact_version", LAHD_ARTIFACT_VERSION)

    logger.info(f"Loaded LAHD property heatmap artifact from {artifact_path}.")
    return payload


def write_local_lahd_property_heat_geojson(
    payload: GeoJsonDict,
    output_path: Path | None = None,
) -> Path:
    """
    Persist a derived LAHD heatmap payload to the local datasets folder.
    """
    if not _is_valid_heat_geojson(payload):
        raise ValueError("LAHD heatmap artifact payload must be a GeoJSON FeatureCollection.")

    artifact_path = (output_path or LAHD_LOCAL_ARTIFACT_PATH).resolve()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(artifact_path, "wb") as artifact_file:
        artifact_file.write(orjson.dumps(payload))

    logger.info(f"Wrote LAHD property heatmap artifact to {artifact_path}.")
    return artifact_path


def _is_valid_lookup_payload(payload: Any) -> bool:
    """
    Check whether a decoded object looks like the expected LAHD lookup payload.
    """
    return isinstance(payload, dict) and isinstance(payload.get("records"), list)


def write_local_lahd_property_lookup(
    payload: JsonDict,
    output_path: Path | None = None,
) -> Path:
    """
    Persist a derived LAHD property lookup payload to the local datasets folder.
    """
    if not _is_valid_lookup_payload(payload):
        raise ValueError("LAHD lookup artifact payload must contain a records list.")

    artifact_path = (output_path or LAHD_LOCAL_LOOKUP_ARTIFACT_PATH).resolve()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(artifact_path, "wb") as artifact_file:
        artifact_file.write(orjson.dumps(payload))

    logger.info(f"Wrote LAHD property lookup artifact to {artifact_path}.")
    return artifact_path


def _request_socrata_rows(url: str, params: dict[str, object]) -> list[JsonDict]:
    """
    Fetch rows from a Socrata SODA endpoint.
    """
    response = requests.get(
        url,
        params=params,
        timeout=LAHD_REQUEST_TIMEOUT_SECONDS,
        headers=_build_socrata_headers(),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(f"Unexpected Socrata payload from {url}; expected a row list.")
    return payload


def _get_socrata_app_token() -> str | None:
    """
    Return the configured Socrata app token from `.env` or the environment.
    """
    token = os.getenv("SOCRATA_APP_TOKEN")
    if not token:
        return None
    token = token.strip()
    return token or None


def _build_socrata_headers() -> dict[str, str]:
    """
    Build headers for city Socrata requests, including an optional app token.
    """
    headers = {
        "User-Agent": "WhereToLive.LA/1.0",
        "Accept": "application/json",
    }
    app_token = _get_socrata_app_token()
    if app_token:
        headers["X-App-Token"] = app_token
    return headers


def _fetch_investigation_rows(limit: int, *, offset: int = 0) -> list[JsonDict]:
    """
    Fetch top LAHD investigation/enforcement property aggregates.
    """
    return _request_socrata_rows(
        LAHD_INVESTIGATION_DATASET_URL,
        {
            "$select": (
                "apn, officialaddress, count(*) AS case_count, "
                "count(closed_date) AS closed_case_count, "
                "min(case_filed_date) AS first_case_date, "
                "max(case_filed_date) AS latest_case_date"
            ),
            "$where": "officialaddress IS NOT NULL AND officialaddress != ''",
            "$group": "apn, officialaddress",
            "$order": "case_count DESC",
            "$limit": limit,
            "$offset": offset,
        },
    )


def _fetch_violation_rows(limit: int, *, offset: int = 0) -> list[JsonDict]:
    """
    Fetch top LAHD code-violation property aggregates.
    """
    return _request_socrata_rows(
        LAHD_VIOLATION_DATASET_URL,
        {
            "$select": (
                "apn, address, count(*) AS violation_row_count, "
                "sum(violations_cited) AS violations_cited, "
                "sum(violations_cleared) AS violations_cleared"
            ),
            "$where": "address IS NOT NULL AND address != ''",
            "$group": "apn, address",
            "$order": "violations_cited DESC",
            "$limit": limit,
            "$offset": offset,
        },
    )


def _fetch_property_investigation_records(apn: str, limit: int) -> list[JsonDict]:
    """
    Fetch raw LAHD investigation/enforcement rows for one property APN.
    """
    return _request_socrata_rows(
        LAHD_INVESTIGATION_DATASET_URL,
        {
            "apn": apn,
            "$select": "apn, officialaddress, case_filed_date, closed_date, casetype",
            "$order": "case_filed_date DESC",
            "$limit": limit,
        },
    )


def _fetch_property_violation_records(apn: str, limit: int) -> list[JsonDict]:
    """
    Fetch raw LAHD code-violation rows for one property APN.
    """
    return _request_socrata_rows(
        LAHD_VIOLATION_DATASET_URL,
        {
            "apn": apn,
            "$select": "apn, address, violationtype, violations_cited, violations_cleared",
            "$order": "violations_cited DESC",
            "$limit": limit,
        },
    )


def _normalize_lahd_record_text(value: object) -> str:
    """
    Convert nullable Socrata values to compact display text.
    """
    return str(value or "").strip()


def _normalize_investigation_record(row: JsonDict) -> JsonDict:
    """
    Convert a raw investigation/enforcement row into drawer-ready data.
    """
    filed_date = _coerce_date_string(row.get("case_filed_date")) or ""
    closed_date = _coerce_date_string(row.get("closed_date")) or ""

    return {
        "filed_date": filed_date,
        "closed_date": closed_date,
        "status": "Closed" if closed_date else "No close date",
        "case_type": _normalize_lahd_record_text(row.get("casetype")) or "Unknown",
        "address": _normalize_lahd_record_text(row.get("officialaddress")),
    }


def _normalize_violation_record(row: JsonDict) -> JsonDict:
    """
    Convert a raw code-violation row into drawer-ready data.
    """
    cited = _parse_int(row.get("violations_cited"))
    cleared = min(cited, _parse_int(row.get("violations_cleared")))

    return {
        "violation_type": _normalize_lahd_record_text(row.get("violationtype")) or "Unknown",
        "violations_cited": cited,
        "violations_cleared": cleared,
        "uncleared_estimate": max(0, cited - cleared),
        "address": _normalize_lahd_record_text(row.get("address")),
    }


def _summarize_lahd_property_records(cases: list[JsonDict], violations: list[JsonDict]) -> JsonDict:
    """
    Build compact counts and address/date context for one APN's record drawer.
    """
    case_dates = [str(row.get("filed_date") or "") for row in cases if row.get("filed_date")]
    addresses = sorted(
        {
            str(row.get("address") or "").strip()
            for row in [*cases, *violations]
            if str(row.get("address") or "").strip()
        }
    )
    violations_cited = sum(_parse_int(row.get("violations_cited")) for row in violations)
    violations_cleared = sum(_parse_int(row.get("violations_cleared")) for row in violations)
    unresolved_violations = sum(_parse_int(row.get("uncleared_estimate")) for row in violations)
    open_cases = sum(1 for row in cases if not row.get("closed_date"))

    return {
        "case_count": len(cases),
        "open_case_count": open_cases,
        "violation_row_count": len(violations),
        "violations_cited": violations_cited,
        "violations_cleared": violations_cleared,
        "unresolved_violation_count": unresolved_violations,
        "documented_issue_count": len(cases) + violations_cited,
        "unresolved_issue_count": open_cases + unresolved_violations,
        "first_case_date": min(case_dates) if case_dates else None,
        "latest_case_date": max(case_dates) if case_dates else None,
        "addresses": addresses,
    }


def _summarize_lahd_lookup_record(record: JsonDict) -> JsonDict:
    """
    Build drawer summary counts from the local aggregate LAHD lookup snapshot.
    """
    address = str(record.get("address") or "").strip()
    return {
        "case_count": _parse_int(record.get("investigation_case_count")),
        "open_case_count": _parse_int(record.get("open_case_count")),
        "violation_row_count": _parse_int(record.get("violation_row_count")),
        "violations_cited": _parse_int(record.get("violations_cited")),
        "violations_cleared": _parse_int(record.get("violations_cleared")),
        "unresolved_violation_count": _parse_int(record.get("unresolved_violation_count")),
        "documented_issue_count": _parse_int(record.get("documented_issue_count")),
        "unresolved_issue_count": _parse_int(record.get("unresolved_issue_count")),
        "first_case_date": str(record.get("first_case_date") or "") or None,
        "latest_case_date": str(record.get("latest_case_date") or "") or None,
        "addresses": [address] if address else [],
    }


def _lahd_detail_unavailable_message(exc: Exception) -> str:
    """
    Return a user-facing explanation for live LAHD detail fetch failures.
    """
    if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 403:
        return (
            "The City data API is currently unavailable due to access restrictions. "
            "Showing the latest local aggregate snapshot instead."
        )
    return (
        "Row-level Housing Department records are unavailable from the City data API right now. "
        "Showing the latest local aggregate snapshot instead."
    )


def _build_lahd_detail_fallback_from_lookup(apn: str, exc: Exception) -> JsonDict | None:
    """
    Return aggregate-only LAHD details from the local lookup snapshot when live rows fail.
    """
    record = lookup_lahd_property_record_by_apn(apn)
    if record is None:
        return None

    lookup_metadata = get_lahd_property_lookup_metadata()
    detail_status = {
        "live_records_available": False,
        "message": _lahd_detail_unavailable_message(exc),
    }
    generated_at = lookup_metadata.get("generated_at")
    if generated_at:
        detail_status["snapshot_generated_at"] = generated_at

    return {
        "apn": apn,
        "cases": [],
        "violations": [],
        "summary": _summarize_lahd_lookup_record(record),
        "truncated": {
            "cases": False,
            "violations": False,
            "row_limit": LAHD_RECORD_DETAIL_LIMIT,
        },
        "detail_status": detail_status,
        "sources": {
            "investigation_source_url": LAHD_INVESTIGATION_SOURCE_URL,
            "violation_source_url": LAHD_VIOLATION_SOURCE_URL,
        },
        "fetched_at": _generated_timestamp(),
    }


@lru_cache(maxsize=512)
def fetch_lahd_property_record_details(
    apn: str,
    row_limit: int = LAHD_RECORD_DETAIL_LIMIT,
) -> JsonDict:
    """
    Return detailed LAHD case and violation rows for a property APN.

    The popup summary uses a local lookup artifact; this detail fetch is live
    and only runs when a user asks to inspect the underlying records.
    """
    normalized_apn = _normalize_apn(apn)
    if not normalized_apn:
        raise ValueError("A numeric APN is required to fetch LAHD property records.")

    limit = max(1, min(int(row_limit), LAHD_RECORD_DETAIL_LIMIT))
    fetch_limit = limit + 1

    # Fetch investigation and violation records concurrently since they have separate endpoints and can be slow to respond
    # We fetch one more than the requested limit to check whether there are more records than we return
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        cases_future = executor.submit(_fetch_property_investigation_records, normalized_apn, fetch_limit)
        violations_future = executor.submit(_fetch_property_violation_records, normalized_apn, fetch_limit)
        try:
            raw_cases = cases_future.result()
            raw_violations = violations_future.result()
        except requests.RequestException as exc:
            fallback = _build_lahd_detail_fallback_from_lookup(normalized_apn, exc)
            if fallback is not None:
                logger.warning(f"Falling back to local LAHD aggregate snapshot for APN {normalized_apn}: {exc}")
                return fallback
            raise

    cases_truncated = len(raw_cases) > limit
    violations_truncated = len(raw_violations) > limit
    cases = [_normalize_investigation_record(row) for row in raw_cases[:limit]]
    violations = [_normalize_violation_record(row) for row in raw_violations[:limit]]

    return {
        "apn": normalized_apn,
        "cases": cases,
        "violations": violations,
        "summary": _summarize_lahd_property_records(cases, violations),
        "truncated": {
            "cases": cases_truncated,
            "violations": violations_truncated,
            "row_limit": limit,
        },
        "detail_status": {
            "live_records_available": True,
        },
        "sources": {
            "investigation_source_url": LAHD_INVESTIGATION_SOURCE_URL,
            "violation_source_url": LAHD_VIOLATION_SOURCE_URL,
        },
        "fetched_at": _generated_timestamp(),
    }


def _parse_int(value: object) -> int:
    """
    Coerce Socrata numeric strings into non-negative integers.
    """
    try:
        parsed = int(float(str(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _normalize_apn(value: object) -> str:
    """
    Normalize APNs into the digit-only form used by the LAHub parcel layer.
    """
    digits = re.sub(r"\D+", "", str(value or ""))
    return digits


def _normalize_address(value: object) -> str:
    """
    Normalize address text for fallback de-duplication.
    """
    return re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()


def _aggregate_key(apn: str, address: str) -> str | None:
    """
    Build the stable property key used to merge LAHD sources.
    """
    if apn:
        return f"apn:{apn}"
    normalized_address = _normalize_address(address)
    if normalized_address:
        return f"address:{normalized_address}"
    return None


def _blank_aggregate(apn: str = "") -> LahdPropertyAggregate:
    """
    Create an empty LAHD property aggregate.
    """
    return {
        "apn": apn,
        "address": "",
        "investigation_case_count": 0,
        "closed_case_count": 0,
        "open_case_count": 0,
        "violation_row_count": 0,
        "violations_cited": 0,
        "violations_cleared": 0,
        "unresolved_violation_count": 0,
        "documented_issue_count": 0,
        "unresolved_issue_count": 0,
        "problem_score": 0,
        "first_case_date": None,
        "latest_case_date": None,
        "lat": 0.0,
        "lon": 0.0,
    }


def _coerce_date_string(value: object) -> str | None:
    """
    Convert a Socrata calendar-date value into a `YYYY-MM-DD` string.
    """
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized.split("T", 1)[0]


def _pick_earlier_date(existing: str | None, candidate: object) -> str | None:
    """
    Return the earlier non-empty ISO date string.
    """
    candidate_date = _coerce_date_string(candidate)
    if not candidate_date:
        return existing
    if not existing or candidate_date < existing:
        return candidate_date
    return existing


def _pick_later_date(existing: str | None, candidate: object) -> str | None:
    """
    Return the later non-empty ISO date string.
    """
    candidate_date = _coerce_date_string(candidate)
    if not candidate_date:
        return existing
    if not existing or candidate_date > existing:
        return candidate_date
    return existing


def _merge_lahd_rows(
    investigation_rows: list[JsonDict],
    violation_rows: list[JsonDict],
) -> list[LahdPropertyAggregate]:
    """
    Merge investigation and violation aggregates into one property list.
    """
    aggregates: dict[str, LahdPropertyAggregate] = {}
    address_scores: dict[str, dict[str, int]] = {}

    def ensure_record(apn: str, address: str) -> tuple[str, LahdPropertyAggregate] | None:
        key = _aggregate_key(apn, address)
        if not key:
            return None
        record = aggregates.setdefault(key, _blank_aggregate(apn=apn))
        if apn and not record["apn"]:
            record["apn"] = apn
        if address:
            address_scores.setdefault(key, {})
            address_scores[key][address] = address_scores[key].get(address, 0)
        return key, record

    for row in investigation_rows:
        apn = _normalize_apn(row.get("apn"))
        address = str(row.get("officialaddress") or "").strip()
        ensured = ensure_record(apn, address)
        if ensured is None:
            continue
        key, record = ensured
        case_count = _parse_int(row.get("case_count"))
        closed_case_count = _parse_int(row.get("closed_case_count"))
        record["investigation_case_count"] += case_count
        record["closed_case_count"] += min(case_count, closed_case_count)
        record["first_case_date"] = _pick_earlier_date(record["first_case_date"], row.get("first_case_date"))
        record["latest_case_date"] = _pick_later_date(record["latest_case_date"], row.get("latest_case_date"))
        if address:
            address_scores[key][address] += case_count

    for row in violation_rows:
        apn = _normalize_apn(row.get("apn"))
        address = str(row.get("address") or "").strip()
        ensured = ensure_record(apn, address)
        if ensured is None:
            continue
        key, record = ensured
        violation_row_count = _parse_int(row.get("violation_row_count"))
        violations_cited = _parse_int(row.get("violations_cited"))
        violations_cleared = _parse_int(row.get("violations_cleared"))
        record["violation_row_count"] += violation_row_count
        record["violations_cited"] += violations_cited
        record["violations_cleared"] += min(violations_cited, violations_cleared)
        if address:
            address_scores[key][address] += violations_cited

    merged: list[LahdPropertyAggregate] = []
    for key, record in aggregates.items():
        weighted_addresses = address_scores.get(key) or {}
        if weighted_addresses:
            record["address"] = max(
                weighted_addresses.items(),
                key=lambda item: (item[1], len(item[0])),
            )[0]

        record["open_case_count"] = max(
            0,
            int(record["investigation_case_count"]) - int(record["closed_case_count"]),
        )
        record["unresolved_violation_count"] = max(
            0,
            int(record["violations_cited"]) - int(record["violations_cleared"]),
        )
        record["documented_issue_count"] = int(record["investigation_case_count"]) + int(record["violations_cited"])
        record["unresolved_issue_count"] = int(record["open_case_count"]) + int(record["unresolved_violation_count"])
        record["problem_score"] = int(record["documented_issue_count"]) + int(record["unresolved_issue_count"])

        if record["problem_score"] > 0:
            merged.append(record)

    merged.sort(
        key=lambda record: (
            -int(record["problem_score"]),
            -int(record["documented_issue_count"]),
            record["address"],
        )
    )
    return merged


def _coordinates_in_bounds(lat: float, lon: float) -> bool:
    """
    Check whether a coordinate falls within the coarse LA City map bounds.
    """
    return (
        LAHD_COORDINATE_BOUNDS["min_lat"] <= lat <= LAHD_COORDINATE_BOUNDS["max_lat"]
        and LAHD_COORDINATE_BOUNDS["min_lon"] <= lon <= LAHD_COORDINATE_BOUNDS["max_lon"]
    )


def _coerce_float(value: object) -> float | None:
    """
    Convert a numeric-like value to a finite float.
    """
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _normalize_city_label(value: object) -> str:
    """
    Normalize an MLS city/community label for jurisdiction fallback checks.
    """
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


@lru_cache(maxsize=2)
def _load_la_city_boundary(boundary_path: str, boundary_mtime_ns: int):
    """
    Load the official City of Los Angeles boundary geometry.
    """
    del boundary_mtime_ns

    path = Path(boundary_path)
    try:
        payload = orjson.loads(path.read_bytes())
    except (OSError, orjson.JSONDecodeError) as exc:
        logger.warning(f"Failed loading City of Los Angeles boundary from {path}: {exc}")
        return None

    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list) or not features:
        logger.warning(f"City of Los Angeles boundary at {path} is missing GeoJSON features.")
        return None

    geometries = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        if isinstance(geometry, dict):
            geometries.append(shape(geometry))

    if not geometries:
        logger.warning(f"City of Los Angeles boundary at {path} has no usable geometries.")
        return None

    boundary = geometries[0]
    for geometry in geometries[1:]:
        boundary = boundary.union(geometry)
    return boundary


def is_listing_in_los_angeles_city(
    *,
    city: object,
    latitude: object,
    longitude: object,
    boundary_path: Path = LA_CITY_BOUNDARY_PATH,
) -> bool | None:
    """
    Return whether a listing appears to be within City of Los Angeles limits.

    `False` is returned only when coordinates place the listing outside the
    official city boundary and the MLS city label is not a known Los Angeles
    community label. `None` means jurisdiction could not be confidently
    determined, so callers should avoid hiding data based on scope alone.
    """
    normalized_city = _normalize_city_label(city)
    lat = _coerce_float(latitude)
    lon = _coerce_float(longitude)

    if lat is not None and lon is not None and not _coordinates_in_bounds(lat, lon):
        return None if normalized_city in _LA_CITY_LISTING_CITY_LABELS else False

    if lat is not None and lon is not None:
        try:
            boundary_mtime_ns = boundary_path.stat().st_mtime_ns
        except OSError:
            boundary_mtime_ns = 0

        boundary = _load_la_city_boundary(str(boundary_path), boundary_mtime_ns) if boundary_mtime_ns else None
        if boundary is not None:
            if boundary.covers(Point(lon, lat)):
                return True
            if normalized_city in _LA_CITY_LISTING_CITY_LABELS:
                return True
            return False

    if normalized_city == "LOS ANGELES":
        return True
    return None


def _load_geocode_cache(cache_path: Path) -> dict[str, JsonDict]:
    """
    Load cached LAHD property coordinate results.
    """
    if not cache_path.exists():
        return {}
    try:
        payload = orjson.loads(cache_path.read_bytes())
    except (OSError, orjson.JSONDecodeError) as exc:
        logger.warning(f"Failed reading LAHD geocode cache at {cache_path}: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_geocode_cache(cache_path: Path, cache: dict[str, JsonDict]) -> None:
    """
    Persist cached LAHD property coordinate results.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(orjson.dumps(cache, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))


def _cache_key_for_record(record: LahdPropertyAggregate) -> str:
    """
    Return the coordinate-cache key for an aggregate record.
    """
    if record["apn"]:
        return f"apn:{record['apn']}"
    return f"address:{_normalize_address(record['address'])}"


def _centroid_from_feature(feature: JsonDict) -> tuple[float, float] | None:
    """
    Extract a representative lon/lat point from a GeoJSON polygon feature.
    """
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        return None

    try:
        representative_point = shape(geometry).representative_point()
    except Exception:
        return None

    try:
        lon = float(representative_point.x)
        lat = float(representative_point.y)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(lat) or not math.isfinite(lon) or not _coordinates_in_bounds(lat, lon):
        return None
    return lat, lon


def _quote_sql_string(value: str) -> str:
    """
    Quote a string for the simple ArcGIS SQL `IN (...)` clauses used here.
    """
    return "'" + value.replace("'", "''") + "'"


def _query_parcel_centroid_chunk(
    session: requests.Session,
    apns: list[str],
) -> dict[str, tuple[float, float]]:
    """
    Query LAHub parcel polygons for one APN chunk and return representative points.
    """
    if not apns:
        return {}

    response = session.post(
        LAHD_PARCEL_QUERY_URL,
        data={
            "where": f"AIN IN ({','.join(_quote_sql_string(apn) for apn in apns)})",
            "outFields": "AIN",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        },
        timeout=LAHD_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload, dict) and payload.get("error"):
        if len(apns) > 1:
            midpoint = len(apns) // 2
            return {
                **_query_parcel_centroid_chunk(session, apns[:midpoint]),
                **_query_parcel_centroid_chunk(session, apns[midpoint:]),
            }
        logger.warning(f"LAHub parcel query failed for APN {apns[0]}: {payload.get('error')}")
        return {}

    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        return {}

    coordinates: dict[str, tuple[float, float]] = {}
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue
        apn = _normalize_apn(properties.get("AIN"))
        if not apn:
            continue
        centroid = _centroid_from_feature(feature)
        if centroid is not None:
            coordinates[apn] = centroid

    return coordinates


def _fetch_parcel_centroids(apns: list[str]) -> dict[str, tuple[float, float]]:
    """
    Fetch APN representative points from the LAHub parcel layer.
    """
    unique_apns = sorted({apn for apn in apns if apn})
    if not unique_apns:
        return {}

    session = requests.Session()
    session.headers.update({"User-Agent": "WhereToLive.LA/1.0"})
    centroids: dict[str, tuple[float, float]] = {}

    for start in range(0, len(unique_apns), LAHD_PARCEL_BATCH_SIZE):
        chunk = unique_apns[start : start + LAHD_PARCEL_BATCH_SIZE]
        centroids.update(_query_parcel_centroid_chunk(session, chunk))

    logger.info(f"Resolved {len(centroids)} of {len(unique_apns)} LAHD APNs through LAHub parcels.")
    return centroids


def _attach_coordinates(
    records: list[LahdPropertyAggregate],
    *,
    candidate_limit: int,
    cache_path: Path,
) -> list[LahdPropertyAggregate]:
    """
    Attach coordinates to top LAHD property records using cached and LAHub parcel points.
    """
    candidates = records[:candidate_limit]
    cache = _load_geocode_cache(cache_path)
    missing_apns: list[str] = []

    for record in candidates:
        cache_key = _cache_key_for_record(record)
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            try:
                lat = float(cached.get("lat"))
                lon = float(cached.get("lon"))
            except (TypeError, ValueError):
                lat = lon = math.nan
            if math.isfinite(lat) and math.isfinite(lon) and _coordinates_in_bounds(lat, lon):
                record["lat"] = lat
                record["lon"] = lon
                continue
        if record["apn"]:
            missing_apns.append(record["apn"])

    parcel_centroids = _fetch_parcel_centroids(missing_apns)
    for record in candidates:
        if record["lat"] and record["lon"]:
            continue
        if not record["apn"]:
            continue
        centroid = parcel_centroids.get(record["apn"])
        if centroid is None:
            continue
        lat, lon = centroid
        record["lat"] = lat
        record["lon"] = lon
        cache[_cache_key_for_record(record)] = {
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "source": "lahub_apn_parcel",
            "apn": record["apn"],
            "address": record["address"],
        }

    if parcel_centroids:
        _write_geocode_cache(cache_path, cache)

    geocoded = [
        record
        for record in candidates
        if record["lat"] and record["lon"] and _coordinates_in_bounds(record["lat"], record["lon"])
    ]
    geocoded.sort(
        key=lambda record: (
            -int(record["problem_score"]),
            -int(record["documented_issue_count"]),
            record["address"],
        )
    )
    return geocoded


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Estimate the distance between two nearby coordinates in meters.
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    mean_lat = (lat1_rad + lat2_rad) / 2
    x = math.radians(lon2 - lon1) * math.cos(mean_lat)
    y = math.radians(lat2 - lat1)
    return 6371000 * math.sqrt((x * x) + (y * y))


def _normalize_property_address_for_lookup(value: object) -> str:
    """
    Normalize a listing or LAHD address to a parcel-level street-address key.

    MLS rental addresses often include unit fragments (`#4`, `APT 2`, etc.) while
    LAHD records are property-level. This strips unit text and normalizes common
    street suffixes before comparison.
    """
    raw_value = str(value or "").strip().upper()
    if not raw_value:
        return ""

    street_only = raw_value.split(",", 1)[0]
    street_only = _UNIT_RE.sub("", street_only)
    street_only = re.sub(r"[^A-Z0-9/]+", " ", street_only)
    tokens = [token for token in street_only.split() if token]
    if tokens:
        tokens[-1] = _STREET_SUFFIX_NORMALIZATION.get(tokens[-1], tokens[-1])
    return " ".join(tokens)


def _coerce_marker_lookup_record(point: object) -> JsonDict | None:
    """
    Convert a compact marker tuple into a popup lookup record.
    """
    if not isinstance(point, list) or len(point) < 16:
        return None

    try:
        record: JsonDict = {
            "lat": float(point[0]),
            "lon": float(point[1]),
            "problem_score": _parse_int(point[2]),
            "documented_issue_count": _parse_int(point[3]),
            "unresolved_issue_count": _parse_int(point[4]),
            "investigation_case_count": _parse_int(point[5]),
            "open_case_count": _parse_int(point[6]),
            "violations_cited": _parse_int(point[7]),
            "unresolved_violation_count": _parse_int(point[8]),
            "violation_row_count": _parse_int(point[9]),
            "closed_case_count": _parse_int(point[10]),
            "violations_cleared": _parse_int(point[11]),
            "address": str(point[12] or "").strip(),
            "apn": str(point[13] or "").strip() or None,
            "first_case_date": str(point[14] or "").strip() or None,
            "latest_case_date": str(point[15] or "").strip() or None,
        }
    except (TypeError, ValueError):
        return None

    if not _coordinates_in_bounds(float(record["lat"]), float(record["lon"])):
        return None
    if not record["address"]:
        return None
    return record


def _lahd_spatial_bucket(lat: float, lon: float) -> tuple[int, int]:
    """
    Return the lookup-grid bucket for a latitude/longitude pair.
    """
    return (
        math.floor(lat / LAHD_LOOKUP_SPATIAL_CELL_DEGREES),
        math.floor(lon / LAHD_LOOKUP_SPATIAL_CELL_DEGREES),
    )


def _lahd_spatial_neighbor_span() -> int:
    """
    Return the number of adjacent coordinate buckets to inspect for nearby matches.
    """
    conservative_degrees = LAHD_LISTING_LOOKUP_MAX_DISTANCE_METERS / 60_000
    return max(1, math.ceil(conservative_degrees / LAHD_LOOKUP_SPATIAL_CELL_DEGREES))


def _candidate_lahd_records_near(
    spatial_index: dict[tuple[int, int], list[JsonDict]],
    *,
    latitude: float,
    longitude: float,
) -> list[JsonDict]:
    """
    Return lookup records in nearby coordinate buckets for distance matching.
    """
    bucket_lat, bucket_lon = _lahd_spatial_bucket(latitude, longitude)
    span = _lahd_spatial_neighbor_span()
    candidates: list[JsonDict] = []
    for lat_offset in range(-span, span + 1):
        for lon_offset in range(-span, span + 1):
            candidates.extend(spatial_index.get((bucket_lat + lat_offset, bucket_lon + lon_offset), []))
    return candidates


def _empty_lahd_listing_lookup_result(
    *,
    data_available: bool,
    jurisdiction_in_scope: bool | None = True,
) -> LahdListingLookupResult:
    """
    Return the default no-match payload used by listing popups.
    """
    return {
        "matched": False,
        "data_available": data_available,
        "match_type": None,
        "match_distance_meters": None,
        "address": None,
        "apn": None,
        "problem_score": 0,
        "documented_issue_count": 0,
        "unresolved_issue_count": 0,
        "investigation_case_count": 0,
        "open_case_count": 0,
        "violations_cited": 0,
        "unresolved_violation_count": 0,
        "latest_case_date": None,
        "jurisdiction_in_scope": jurisdiction_in_scope,
    }


def out_of_scope_lahd_listing_lookup_result() -> LahdListingLookupResult:
    """
    Return a hidden-by-client payload for listings outside LAHD jurisdiction.
    """
    return _empty_lahd_listing_lookup_result(data_available=True, jurisdiction_in_scope=False)


def _matched_lahd_listing_lookup_result(
    record: JsonDict,
    *,
    match_type: str,
    match_distance_meters: float | None = None,
) -> LahdListingLookupResult:
    """
    Convert a lookup record into the serializable popup payload.
    """
    return {
        "matched": True,
        "data_available": True,
        "match_type": match_type,
        "match_distance_meters": (
            round(match_distance_meters, 1)
            if match_distance_meters is not None and math.isfinite(match_distance_meters)
            else None
        ),
        "address": str(record.get("address") or "") or None,
        "apn": str(record.get("apn") or "") or None,
        "problem_score": _parse_int(record.get("problem_score")),
        "documented_issue_count": _parse_int(record.get("documented_issue_count")),
        "unresolved_issue_count": _parse_int(record.get("unresolved_issue_count")),
        "investigation_case_count": _parse_int(record.get("investigation_case_count")),
        "open_case_count": _parse_int(record.get("open_case_count")),
        "violations_cited": _parse_int(record.get("violations_cited")),
        "unresolved_violation_count": _parse_int(record.get("unresolved_violation_count")),
        "latest_case_date": str(record.get("latest_case_date") or "") or None,
        "jurisdiction_in_scope": True,
    }


@lru_cache(maxsize=4)
def _load_lahd_listing_lookup(
    artifact_path: str,
    artifact_mtime_ns: int,
) -> dict[str, Any]:
    """
    Load the LAHD property lookup records for listing popups.
    """
    del artifact_mtime_ns

    path = Path(artifact_path)
    if not path.exists():
        return {"records": [], "address_index": {}, "apn_index": {}, "spatial_index": {}, "metadata": {}}

    try:
        with gzip.open(path, "rb") as artifact_file:
            payload = orjson.loads(artifact_file.read())
    except (OSError, orjson.JSONDecodeError) as exc:
        logger.warning(f"Failed loading LAHD listing lookup from {path}: {exc}")
        return {"records": [], "address_index": {}, "apn_index": {}, "spatial_index": {}, "metadata": {}}

    marker_points = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(marker_points, list):
        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list) or not features:
            return {"records": [], "address_index": {}}

        properties = features[0].get("properties") if isinstance(features[0], dict) else None
        marker_points = properties.get("marker_points") if isinstance(properties, dict) else None
        if not isinstance(marker_points, list):
            return {"records": [], "address_index": {}, "apn_index": {}, "spatial_index": {}, "metadata": {}}

    records = [
        record
        for record in (_coerce_marker_lookup_record(point) for point in marker_points)
        if record is not None
    ]
    address_index: dict[str, JsonDict] = {}
    apn_index: dict[str, JsonDict] = {}
    spatial_index: dict[tuple[int, int], list[JsonDict]] = {}
    for record in records:
        address_key = _normalize_property_address_for_lookup(record.get("address"))
        if not address_key:
            continue
        existing = address_index.get(address_key)
        if existing is None or _parse_int(record.get("problem_score")) > _parse_int(existing.get("problem_score")):
            address_index[address_key] = record

        apn = _normalize_apn(record.get("apn"))
        if apn:
            existing_by_apn = apn_index.get(apn)
            if existing_by_apn is None or _parse_int(record.get("problem_score")) > _parse_int(
                existing_by_apn.get("problem_score")
            ):
                apn_index[apn] = record

        spatial_index.setdefault(_lahd_spatial_bucket(float(record["lat"]), float(record["lon"])), []).append(record)

    metadata = payload.get("metadata") if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict) else {}
    return {
        "records": records,
        "address_index": address_index,
        "apn_index": apn_index,
        "spatial_index": spatial_index,
        "metadata": metadata,
    }


def _load_lahd_lookup_artifact(artifact_path: Path = LAHD_LOCAL_LOOKUP_ARTIFACT_PATH) -> dict[str, Any]:
    """
    Load the cached LAHD lookup artifact with indexes.
    """
    try:
        artifact_mtime_ns = artifact_path.stat().st_mtime_ns
    except OSError:
        return {"records": [], "address_index": {}, "apn_index": {}, "spatial_index": {}, "metadata": {}}

    return _load_lahd_listing_lookup(str(artifact_path), artifact_mtime_ns)


def lookup_lahd_property_record_by_apn(
    apn: object,
    artifact_path: Path = LAHD_LOCAL_LOOKUP_ARTIFACT_PATH,
) -> JsonDict | None:
    """
    Return a local aggregate LAHD lookup record by APN.
    """
    normalized_apn = _normalize_apn(apn)
    if not normalized_apn:
        return None

    lookup = _load_lahd_lookup_artifact(artifact_path)
    apn_index: dict[str, JsonDict] = lookup.get("apn_index") or {}
    return apn_index.get(normalized_apn)


def get_lahd_property_lookup_metadata(
    artifact_path: Path = LAHD_LOCAL_LOOKUP_ARTIFACT_PATH,
) -> JsonDict:
    """
    Return metadata for the local LAHD aggregate lookup snapshot.
    """
    lookup = _load_lahd_lookup_artifact(artifact_path)
    metadata = lookup.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def prewarm_lahd_listing_lookup_cache() -> None:
    """
    Load local LAHD lookup data during app startup instead of the first popup.
    """
    started_at = time.time()
    try:
        lookup = _load_lahd_lookup_artifact(LAHD_LOCAL_LOOKUP_ARTIFACT_PATH)
        try:
            boundary_mtime_ns = LA_CITY_BOUNDARY_PATH.stat().st_mtime_ns
        except OSError:
            boundary_mtime_ns = 0
        if boundary_mtime_ns:
            _load_la_city_boundary(str(LA_CITY_BOUNDARY_PATH), boundary_mtime_ns)
    except Exception as exc:
        logger.warning(f"Failed prewarming LAHD listing lookup cache: {exc}")
        return

    logger.info(
        "Prewarmed LAHD listing lookup cache with "
        f"{len(lookup.get('records') or []):,} records in {time.time() - started_at:.2f}s."
    )


def lookup_lahd_property_for_listing(
    *,
    address: object,
    latitude: object,
    longitude: object,
    artifact_path: Path = LAHD_LOCAL_LOOKUP_ARTIFACT_PATH,
) -> LahdListingLookupResult:
    """
    Return an LAHD issue summary for a listing popup.

    Matching uses a normalized property-level address first, then falls back to a
    conservative nearest-parcel search against the LAHD lookup artifact.
    """
    try:
        artifact_mtime_ns = artifact_path.stat().st_mtime_ns
    except OSError:
        return _empty_lahd_listing_lookup_result(data_available=False)

    lookup = _load_lahd_listing_lookup(str(artifact_path), artifact_mtime_ns)
    records: list[JsonDict] = lookup.get("records") or []
    address_index: dict[str, JsonDict] = lookup.get("address_index") or {}
    spatial_index: dict[tuple[int, int], list[JsonDict]] = lookup.get("spatial_index") or {}
    if not records:
        return _empty_lahd_listing_lookup_result(data_available=False)

    address_key = _normalize_property_address_for_lookup(address)
    if address_key and address_key in address_index:
        return _matched_lahd_listing_lookup_result(
            address_index[address_key],
            match_type="address",
        )

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return _empty_lahd_listing_lookup_result(data_available=True)

    if not math.isfinite(lat) or not math.isfinite(lon) or not _coordinates_in_bounds(lat, lon):
        return _empty_lahd_listing_lookup_result(data_available=True)

    candidate_records = _candidate_lahd_records_near(spatial_index, latitude=lat, longitude=lon) if spatial_index else records
    if not candidate_records:
        return _empty_lahd_listing_lookup_result(data_available=True)

    nearest_record: JsonDict | None = None
    nearest_distance = math.inf
    for record in candidate_records:
        distance = _distance_meters(lat, lon, float(record["lat"]), float(record["lon"]))
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_record = record

    if nearest_record is not None and nearest_distance <= LAHD_LISTING_LOOKUP_MAX_DISTANCE_METERS:
        return _matched_lahd_listing_lookup_result(
            nearest_record,
            match_type="nearby_parcel",
            match_distance_meters=nearest_distance,
        )

    return _empty_lahd_listing_lookup_result(data_available=True)


def _pick_quantile_threshold(values: list[int], fraction: float) -> int:
    """
    Return a stable integer quantile threshold from a sorted integer distribution.
    """
    if not values:
        return 0
    index = min(len(values) - 1, max(0, math.ceil(fraction * len(values)) - 1))
    return int(values[index])


def _marker_score_thresholds(marker_records: list[LahdPropertyAggregate]) -> tuple[int, int, int, int]:
    """
    Derive discrete score thresholds for zoomed-in marker styling.
    """
    scores = sorted(
        int(record["problem_score"])
        for record in marker_records
        if int(record["problem_score"]) > 0
    )
    if not scores:
        return (0, 0, 0, 0)
    return (
        _pick_quantile_threshold(scores, 0.50),
        _pick_quantile_threshold(scores, 0.75),
        _pick_quantile_threshold(scores, 0.90),
        _pick_quantile_threshold(scores, 0.975),
    )


def _build_heat_points(records: list[LahdPropertyAggregate]) -> list[HeatPointTuple]:
    """
    Convert geocoded records into Leaflet.heat weighted point tuples.
    """
    if not records:
        return []

    max_score = max(int(record["problem_score"]) for record in records)
    if max_score <= 0:
        return []

    points: list[HeatPointTuple] = []
    for record in records:
        score = int(record["problem_score"])
        intensity = round(
            min(1.0, max(LAHD_HEAT_INTENSITY_FLOOR, math.sqrt(score / max_score))),
            4,
        )
        points.append([round(record["lat"], 6), round(record["lon"], 6), intensity])
    return points


def _build_marker_points(records: list[LahdPropertyAggregate]) -> list[MarkerPointTuple]:
    """
    Convert geocoded records into compact popup-ready marker tuples.
    """
    return [
        [
            round(record["lat"], 6),
            round(record["lon"], 6),
            int(record["problem_score"]),
            int(record["documented_issue_count"]),
            int(record["unresolved_issue_count"]),
            int(record["investigation_case_count"]),
            int(record["open_case_count"]),
            int(record["violations_cited"]),
            int(record["unresolved_violation_count"]),
            int(record["violation_row_count"]),
            int(record["closed_case_count"]),
            int(record["violations_cleared"]),
            record["address"],
            record["apn"],
            record["first_case_date"],
            record["latest_case_date"],
        ]
        for record in records
    ]


def _build_heat_anchor_feature(
    heat_records: list[LahdPropertyAggregate],
    marker_records: list[LahdPropertyAggregate],
) -> GeoJsonDict:
    """
    Build the single invisible GeoJSON anchor used to mount the LAHD heat layer.
    """
    if not heat_records:
        anchor_lat = (LAHD_COORDINATE_BOUNDS["min_lat"] + LAHD_COORDINATE_BOUNDS["max_lat"]) / 2
        anchor_lon = (LAHD_COORDINATE_BOUNDS["min_lon"] + LAHD_COORDINATE_BOUNDS["max_lon"]) / 2
    else:
        anchor_lat = round(sum(record["lat"] for record in heat_records) / len(heat_records), 6)
        anchor_lon = round(sum(record["lon"] for record in heat_records) / len(heat_records), 6)

    max_problem_score = max((int(record["problem_score"]) for record in heat_records), default=0)
    first_dates = [record["first_case_date"] for record in marker_records if record["first_case_date"]]
    latest_dates = [record["latest_case_date"] for record in marker_records if record["latest_case_date"]]

    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [anchor_lon, anchor_lat],
        },
        "properties": {
            "layer_role": "lahd_property_heat_anchor",
            "heat_points": _build_heat_points(heat_records),
            "marker_points": _build_marker_points(marker_records),
            "heat_max_intensity": 1.0,
            "max_problem_score": max_problem_score,
            "marker_score_breaks": list(_marker_score_thresholds(marker_records)),
            "marker_zoom_min": LAHD_MARKER_ZOOM_MIN,
            "heat_zoom_max": LAHD_HEAT_ZOOM_MAX,
            "window_start": min(first_dates) if first_dates else None,
            "window_end": max(latest_dates) if latest_dates else None,
        },
    }


def _build_lahd_property_lookup_payload(
    lookup_records: list[LahdPropertyAggregate],
    *,
    aggregate_limit: int,
) -> JsonDict:
    """
    Build the compact property lookup artifact used by listing popups.
    """
    max_problem_score = max((int(record["problem_score"]) for record in lookup_records), default=0)
    metadata: LahdLookupMetadata = {
        "aggregate_limit": aggregate_limit,
        "lookup_record_count": len(lookup_records),
        "max_problem_score": max_problem_score,
        "investigation_source_url": LAHD_INVESTIGATION_SOURCE_URL,
        "violation_source_url": LAHD_VIOLATION_SOURCE_URL,
        "parcel_source_url": LAHD_PARCEL_QUERY_URL.rsplit("/", 1)[0],
        "data_source": "socrata_lahub_live",
        "generated_at": _generated_timestamp(),
        "artifact_version": LAHD_ARTIFACT_VERSION,
    }

    return {
        "records": _build_marker_points(lookup_records),
        "metadata": metadata,
    }


def _build_live_lahd_property_lookup(
    *,
    aggregate_limit: int = LAHD_DEFAULT_LOOKUP_LIMIT,
    geocode_cache_path: Path = LAHD_GEOCODE_CACHE_PATH,
) -> JsonDict:
    """
    Build the full listing-popup LAHD property lookup payload.
    """
    started_at = time.time()
    investigation_rows = _fetch_investigation_rows(aggregate_limit)
    violation_rows = _fetch_violation_rows(aggregate_limit)
    merged_records = _merge_lahd_rows(investigation_rows, violation_rows)
    lookup_records = _attach_coordinates(
        merged_records,
        candidate_limit=aggregate_limit,
        cache_path=geocode_cache_path,
    )
    payload = _build_lahd_property_lookup_payload(
        lookup_records,
        aggregate_limit=aggregate_limit,
    )
    logger.info(f"Built LAHD property lookup with {len(lookup_records)} records in {time.time() - started_at:.2f}s.")
    return payload


def _build_live_lahd_property_heat_geojson(
    *,
    aggregate_limit: int = LAHD_DEFAULT_AGGREGATE_LIMIT,
    max_heat_points: int = LAHD_MAX_HEAT_POINTS,
    max_marker_points: int = LAHD_MAX_MARKER_POINTS,
    geocode_cache_path: Path = LAHD_GEOCODE_CACHE_PATH,
) -> GeoJsonDict:
    """
    Build the LAHD property heatmap payload from Socrata and LAHub parcels.
    """
    started_at = time.time()
    investigation_rows = _fetch_investigation_rows(aggregate_limit)
    violation_rows = _fetch_violation_rows(aggregate_limit)
    merged_records = _merge_lahd_rows(investigation_rows, violation_rows)
    geocoded_records = _attach_coordinates(
        merged_records,
        candidate_limit=max(max_heat_points, max_marker_points) * 2,
        cache_path=geocode_cache_path,
    )

    heat_records = geocoded_records[:max_heat_points]
    marker_records = geocoded_records[:max_marker_points]
    max_problem_score = max((int(record["problem_score"]) for record in heat_records), default=0)
    metadata: LahdLayerMetadata = {
        "aggregate_limit": aggregate_limit,
        "heat_point_count": len(heat_records),
        "marker_point_count": len(marker_records),
        "geocoded_property_count": len(geocoded_records),
        "max_problem_score": max_problem_score,
        "investigation_source_url": LAHD_INVESTIGATION_SOURCE_URL,
        "violation_source_url": LAHD_VIOLATION_SOURCE_URL,
        "parcel_source_url": LAHD_PARCEL_QUERY_URL.rsplit("/", 1)[0],
        "data_source": "socrata_lahub_live",
        "generated_at": _generated_timestamp(),
        "artifact_version": LAHD_ARTIFACT_VERSION,
    }

    logger.info(
        f"Built LAHD property heatmap with {len(heat_records)} heat points "
        f"and {len(marker_records)} marker points in {time.time() - started_at:.2f}s."
    )
    return {
        "type": "FeatureCollection",
        "features": [_build_heat_anchor_feature(heat_records, marker_records)] if heat_records else [],
        "metadata": metadata,
    }


def build_lahd_property_heat_geojson() -> GeoJsonDict:
    """
    Return the preferred LAHD property heatmap payload.
    """
    local_payload = load_local_lahd_property_heat_geojson()
    if local_payload is not None:
        return local_payload

    logger.warning(
        f"LAHD property heatmap artifact is missing at {LAHD_LOCAL_ARTIFACT_PATH}. "
        "Generate it offline with `uv run build-lahd-property-heatmap`."
    )
    return {"type": "FeatureCollection", "features": []}


def refresh_local_lahd_property_heat_geojson(
    *,
    output_path: Path | None = None,
    aggregate_limit: int = LAHD_DEFAULT_AGGREGATE_LIMIT,
    max_heat_points: int = LAHD_MAX_HEAT_POINTS,
    max_marker_points: int = LAHD_MAX_MARKER_POINTS,
    geocode_cache_path: Path = LAHD_GEOCODE_CACHE_PATH,
) -> Path:
    """
    Rebuild the LAHD heatmap payload and write it to disk.
    """
    payload = _build_live_lahd_property_heat_geojson(
        aggregate_limit=aggregate_limit,
        max_heat_points=max_heat_points,
        max_marker_points=max_marker_points,
        geocode_cache_path=geocode_cache_path,
    )
    if not payload.get("features"):
        raise RuntimeError("Live LAHD property heatmap build returned no features.")
    return write_local_lahd_property_heat_geojson(payload, output_path=output_path)


def refresh_local_lahd_property_lookup(
    *,
    output_path: Path | None = None,
    aggregate_limit: int = LAHD_DEFAULT_LOOKUP_LIMIT,
    geocode_cache_path: Path = LAHD_GEOCODE_CACHE_PATH,
) -> Path:
    """
    Rebuild the listing-popup LAHD lookup payload and write it to disk.
    """
    payload = _build_live_lahd_property_lookup(
        aggregate_limit=aggregate_limit,
        geocode_cache_path=geocode_cache_path,
    )
    if not payload.get("records"):
        raise RuntimeError("Live LAHD property lookup build returned no records.")
    return write_local_lahd_property_lookup(payload, output_path=output_path)
