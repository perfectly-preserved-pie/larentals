from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dt_time, timedelta
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from typing import Any, Iterable, TypeAlias, TypedDict
import os
import time

from dotenv import find_dotenv, load_dotenv
from loguru import logger
import requests

from functions.listing_report_utils import normalize_mls_number
from functions.zip_geocoding_utils import PlaceGeocodeResult

load_dotenv(find_dotenv(), override=False)

GeoJsonDict: TypeAlias = dict[str, Any]

COMMUTE_DEFAULT_MODE = "drive"
COMMUTE_MIN_MINUTES = 5
COMMUTE_MAX_MINUTES = 90
COMMUTE_STEP_MINUTES = 5
COMMUTE_DEFAULT_DEPARTURE_HOUR = 8
COMMUTE_DEFAULT_DEPARTURE_MINUTE = 0

COMMUTE_MODE_LABELS: dict[str, str] = {
    "drive": "Drive (typical)",
    "transit": "Transit",
    "bike": "Bike",
    "walk": "Walk",
}

COMMUTE_MODE_STATUS_LABELS: dict[str, str] = {
    "drive": "drive (typical)",
    "transit": "transit",
    "bike": "bike",
    "walk": "walk",
}

COMMUTE_MODE_OPTIONS = [
    {"label": label, "value": value}
    for value, label in COMMUTE_MODE_LABELS.items()
]

COMMUTE_VALHALLA_COSTING: dict[str, str] = {
    "drive": "auto",
    "transit": "multimodal",
    "bike": "bicycle",
    "walk": "pedestrian",
}

VALHALLA_BASE_URL = os.getenv(
    "VALHALLA_BASE_URL",
    "https://valhalla1.openstreetmap.de",
).rstrip("/")

def _env_flag(name: str, default: bool) -> bool:
    """
    Parse a boolean-like environment variable.

    Args:
        name: Environment variable name.
        default: Fallback value when the variable is unset.

    Returns:
        A normalized boolean flag.
    """
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def _default_valhalla_service_label(base_url: str) -> str:
    """
    Choose a user-facing Valhalla service label from the configured base URL.

    Args:
        base_url: The configured Valhalla base URL.

    Returns:
        A human-readable service label for status and helper text.
    """
    lowered = str(base_url).strip().lower()
    if "openstreetmap.de" in lowered:
        return "Public Valhalla demo API"
    if "localhost" in lowered or "127.0.0.1" in lowered or "://valhalla:" in lowered:
        return "Self-hosted Valhalla"
    return "Valhalla"


VALHALLA_IS_PUBLIC_DEMO = _env_flag(
    "VALHALLA_IS_PUBLIC_DEMO",
    "openstreetmap.de" in VALHALLA_BASE_URL.lower(),
)
VALHALLA_SERVICE_LABEL = os.getenv(
    "VALHALLA_SERVICE_LABEL",
    _default_valhalla_service_label(VALHALLA_BASE_URL),
)
VALHALLA_TIMEOUT_SECONDS = float(os.getenv("VALHALLA_TIMEOUT_SECONDS", "12"))
VALHALLA_EXACT_COMMUTE_MAX_CANDIDATES = max(
    1,
    int(
        os.getenv(
            "VALHALLA_EXACT_COMMUTE_MAX_CANDIDATES",
            "60" if VALHALLA_IS_PUBLIC_DEMO else "2000",
        )
    ),
)
VALHALLA_EXACT_COMMUTE_MAX_WORKERS = max(
    1,
    int(
        os.getenv(
            "VALHALLA_EXACT_COMMUTE_MAX_WORKERS",
            "4" if VALHALLA_IS_PUBLIC_DEMO else "16",
        )
    ),
)
VALHALLA_EXACT_COMMUTE_TRANSIT_MAX_WORKERS = max(
    1,
    int(
        os.getenv(
            "VALHALLA_EXACT_COMMUTE_TRANSIT_MAX_WORKERS",
            "1" if VALHALLA_IS_PUBLIC_DEMO else "4",
        )
    ),
)
VALHALLA_ROUTE_MAX_RETRIES = max(
    0,
    int(os.getenv("VALHALLA_ROUTE_MAX_RETRIES", "1")),
)
VALHALLA_ROUTE_RETRY_BACKOFF_SECONDS = max(
    0.0,
    float(os.getenv("VALHALLA_ROUTE_RETRY_BACKOFF_SECONDS", "0.75")),
)

COMMUTE_HELP_TEXT = (
    "Estimates depend on the selected departure time and can still differ from "
    "real traffic, hills, route comfort, and service changes."
)

VALHALLA_HTTP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "WhereToLive.LA/1.0",
}

MAPBOX_ACCESS_TOKEN = str(os.getenv("MAPBOX_ACCESS_TOKEN", "")).strip()
MAPBOX_DRIVE_EXACT_ENABLED = bool(MAPBOX_ACCESS_TOKEN) and _env_flag(
    "MAPBOX_DRIVE_EXACT_ENABLED",
    True,
)
MAPBOX_MATRIX_BASE_URL = os.getenv(
    "MAPBOX_MATRIX_BASE_URL",
    "https://api.mapbox.com",
).rstrip("/")
MAPBOX_MATRIX_TIMEOUT_SECONDS = float(os.getenv("MAPBOX_MATRIX_TIMEOUT_SECONDS", "12"))
MAPBOX_MATRIX_MAX_WORKERS = max(
    1,
    int(os.getenv("MAPBOX_MATRIX_MAX_WORKERS", "4")),
)
MAPBOX_MATRIX_COORDINATE_LIMIT = min(
    10,
    max(2, int(os.getenv("MAPBOX_MATRIX_COORDINATE_LIMIT", "10"))),
)
MAPBOX_DRIVE_EXACT_MAX_CANDIDATES = max(
    1,
    int(os.getenv("MAPBOX_DRIVE_EXACT_MAX_CANDIDATES", "80")),
)
MAPBOX_MATRIX_RETRY_WITHOUT_DEPART_AT = _env_flag(
    "MAPBOX_MATRIX_RETRY_WITHOUT_DEPART_AT",
    True,
)
MAPBOX_SERVICE_LABEL = "Mapbox traffic"


class CommuteRequestData(TypedDict):
    """Normalized commute request metadata stored in Dash."""

    requested: bool
    active: bool
    signature: str | None
    destination: str
    query: str | None
    display_name: str | None
    mode: str
    mode_label: str
    minutes: int
    departure_datetime: str
    departure_label: str
    center_lat: float | None
    center_lon: float | None
    status: str
    error: str | None


class CommuteBoundaryResult(TypedDict):
    """Boundary overlay payload and request metadata."""

    geojson: GeoJsonDict
    status: str
    request: CommuteRequestData


class CommuteExactMatchResult(TypedDict):
    """Exact route-check result metadata for the current candidate set."""

    requested: bool
    active: bool
    signature: str | None
    commute_signature: str | None
    eligible_mls: list[str]
    excluded_mls: list[str]
    rough_mls: list[str]
    total_candidates: int
    attempted_candidates: int
    checked_candidates: int
    matched_candidates: int
    excluded_candidates: int
    rough_candidates: int
    failed_candidates: int
    mode: str | None
    mode_label: str | None
    minutes: int | None
    display_name: str | None
    provider: str | None
    partial: bool
    status: str
    error: str | None


class CommuteListingCandidate(TypedDict):
    """Normalized candidate listing point extracted from a GeoJSON feature."""

    mls_number: str
    lat: float
    lon: float


RouteDurationLookup: TypeAlias = dict[str, float | None]


def empty_feature_collection() -> GeoJsonDict:
    """
    Return an empty GeoJSON FeatureCollection.

    Returns:
        A GeoJSON FeatureCollection with no features.
    """
    return {"type": "FeatureCollection", "features": []}


def normalize_commute_mode(mode: str | None) -> str:
    """
    Normalize a raw commute mode value from the UI.

    Args:
        mode: Raw mode string from the browser.

    Returns:
        One of the supported commute mode keys.
    """
    normalized = str(mode or "").strip().lower()
    if normalized in COMMUTE_MODE_LABELS:
        return normalized
    return COMMUTE_DEFAULT_MODE


def commute_mode_status_label(mode: str | None) -> str:
    """
    Return the user-facing wording used in commute status lines.

    Args:
        mode: Raw mode string from the browser.

    Returns:
        A short display label for status messages.
    """
    normalized = normalize_commute_mode(mode)
    return COMMUTE_MODE_STATUS_LABELS[normalized]


def normalize_commute_minutes(minutes: int | float | None) -> int:
    """
    Clamp and snap a commute duration to the configured slider range.

    Args:
        minutes: Raw duration value from the browser.

    Returns:
        A duration snapped to `COMMUTE_STEP_MINUTES` within the supported range.
    """
    try:
        raw_value = float(minutes)
    except (TypeError, ValueError):
        raw_value = 30.0

    clamped = min(COMMUTE_MAX_MINUTES, max(COMMUTE_MIN_MINUTES, raw_value))
    snapped = int(round(clamped / COMMUTE_STEP_MINUTES) * COMMUTE_STEP_MINUTES)
    return min(COMMUTE_MAX_MINUTES, max(COMMUTE_MIN_MINUTES, snapped))


def valhalla_costing_for_mode(mode: str | None) -> str:
    """
    Map an app-level commute mode to a Valhalla costing profile.

    Args:
        mode: Raw app mode string.

    Returns:
        A Valhalla costing value such as `auto` or `multimodal`.
    """
    return COMMUTE_VALHALLA_COSTING[normalize_commute_mode(mode)]


def default_commute_departure_datetime() -> str:
    """
    Build the default local departure datetime used by the commute UI.

    Returns:
        An ISO-like local datetime string for the next weekday at 08:00.
    """
    now = datetime.now()
    candidate_date = now.date()
    if now.weekday() >= 5:
        candidate_date = candidate_date + timedelta(days=7 - now.weekday())
    candidate = datetime.combine(
        candidate_date,
        dt_time(hour=COMMUTE_DEFAULT_DEPARTURE_HOUR, minute=COMMUTE_DEFAULT_DEPARTURE_MINUTE),
    )
    if candidate <= now:
        candidate_date = candidate_date + timedelta(days=1)
        while candidate_date.weekday() >= 5:
            candidate_date = candidate_date + timedelta(days=1)
        candidate = datetime.combine(
            candidate_date,
            dt_time(hour=COMMUTE_DEFAULT_DEPARTURE_HOUR, minute=COMMUTE_DEFAULT_DEPARTURE_MINUTE),
        )
    return candidate.strftime("%Y-%m-%dT%H:%M")


def normalize_commute_departure_datetime(value: str | None) -> str:
    """
    Normalize a user-selected local departure datetime for Valhalla.

    Args:
        value: Raw datetime string from the UI.

    Returns:
        A local datetime string formatted as ``YYYY-MM-DDTHH:MM``.
    """
    if isinstance(value, str):
        raw_value = value.strip()
        if raw_value:
            cleaned_value = raw_value[:-1] if raw_value.endswith("Z") else raw_value
            try:
                parsed = datetime.fromisoformat(cleaned_value)
            except ValueError:
                pass
            else:
                return parsed.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M")
    return default_commute_departure_datetime()


def format_commute_departure_label(value: str | None) -> str:
    """
    Format a normalized departure datetime for user-facing status text.

    Args:
        value: Raw or normalized datetime string.

    Returns:
        A compact human-readable local datetime label.
    """
    normalized = normalize_commute_departure_datetime(value)
    parsed = datetime.fromisoformat(normalized)
    month_day = parsed.strftime("%a %b %d").replace(" 0", " ")
    time_label = parsed.strftime("%I:%M %p").lstrip("0")
    return f"{month_day} at {time_label}"


def build_valhalla_date_time(value: str | None) -> GeoJsonDict:
    """
    Build a Valhalla ``date_time`` object from the selected departure.

    Args:
        value: Raw or normalized local departure datetime string.

    Returns:
        A Valhalla ``date_time`` payload using a specified departure time.
    """
    return {
        "type": 1,
        "value": normalize_commute_departure_datetime(value),
    }


def empty_commute_request_data() -> CommuteRequestData:
    """
    Build an empty commute request payload for Dash stores.

    Returns:
        A default request object representing "no commute filter applied".
    """
    return {
        "requested": False,
        "active": False,
        "signature": None,
        "destination": "",
        "query": None,
        "display_name": None,
        "mode": COMMUTE_DEFAULT_MODE,
        "mode_label": COMMUTE_MODE_LABELS[COMMUTE_DEFAULT_MODE],
        "minutes": normalize_commute_minutes(30),
        "departure_datetime": default_commute_departure_datetime(),
        "departure_label": format_commute_departure_label(None),
        "center_lat": None,
        "center_lon": None,
        "status": "",
        "error": None,
    }


def empty_commute_exact_result() -> CommuteExactMatchResult:
    """
    Build an empty exact commute result payload for Dash stores.

    Returns:
        A default exact-match result representing "nothing to verify".
    """
    return {
        "requested": False,
        "active": False,
        "signature": None,
        "commute_signature": None,
        "eligible_mls": [],
        "excluded_mls": [],
        "rough_mls": [],
        "total_candidates": 0,
        "attempted_candidates": 0,
        "checked_candidates": 0,
        "matched_candidates": 0,
        "excluded_candidates": 0,
        "rough_candidates": 0,
        "failed_candidates": 0,
        "mode": None,
        "mode_label": None,
        "minutes": None,
        "display_name": None,
        "provider": None,
        "partial": False,
        "status": "",
        "error": None,
    }


def build_commute_signature(
    lat: float,
    lon: float,
    mode: str | None,
    minutes: int | float | None,
    departure_datetime: str | None,
) -> str:
    """
    Build a stable signature for a destination/mode/time commute request.

    Args:
        lat: Destination latitude.
        lon: Destination longitude.
        mode: Selected commute mode.
        minutes: Selected max minutes.
        departure_datetime: Selected departure datetime.

    Returns:
        A stable string signature for caching and store comparisons.
    """
    normalized_mode = normalize_commute_mode(mode)
    normalized_minutes = normalize_commute_minutes(minutes)
    normalized_departure = normalize_commute_departure_datetime(departure_datetime)
    return (
        f"{normalized_mode}:{normalized_minutes}:{normalized_departure}:"
        f"{lat:.6f}:{lon:.6f}"
    )


def build_candidate_signature(
    commute_signature: str | None,
    mls_numbers: Iterable[object],
) -> str | None:
    """
    Build a stable signature for the current exact-check candidate set.

    Args:
        commute_signature: Base signature for the destination/mode/time request.
        mls_numbers: Listing ids present in the coarse prefilter result.

    Returns:
        A stable signature string, or `None` when no commute request is active.
    """
    if not commute_signature:
        return None

    normalized_ids = sorted(
        normalize_mls_number(value)
        for value in mls_numbers
        if str(value).strip()
    )
    return f"{commute_signature}|{','.join(normalized_ids)}"


def _truncate_response_text(text: str, limit: int = 300) -> str:
    """
    Trim a response body for logging.

    Args:
        text: Raw response text.
        limit: Maximum number of characters to keep.

    Returns:
        A single-line truncated body preview.
    """
    collapsed = " ".join(str(text or "").split())
    return collapsed[:limit]


def _normalize_point_coordinates(coords: object) -> tuple[float, float] | None:
    """
    Normalize a point coordinate pair into `(lat, lon)`.

    Args:
        coords: Raw GeoJSON coordinate payload.

    Returns:
        A `(lat, lon)` tuple when the coordinates look valid, otherwise `None`.
    """
    if not isinstance(coords, list) or len(coords) < 2:
        return None

    first = coords[0]
    second = coords[1]
    if not isinstance(first, (int, float)) or not isinstance(second, (int, float)):
        return None

    if abs(first) <= 90 and abs(second) > 90:
        return float(first), float(second)

    return float(second), float(first)


def _haversine_distance_miles(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Return the great-circle distance between two points in miles.

    Args:
        lat1: First latitude.
        lon1: First longitude.
        lat2: Second latitude.
        lon2: Second longitude.

    Returns:
        Great-circle distance in miles.
    """
    radius_miles = 3958.7613
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    )
    return 2 * radius_miles * asin(sqrt(a))


def _prioritize_candidates_by_distance(
    candidates: list[CommuteListingCandidate],
    destination_lat: float,
    destination_lon: float,
) -> list[CommuteListingCandidate]:
    """
    Rank candidates by straight-line distance to the destination.

    Args:
        candidates: Candidate listings extracted from the current shortlist.
        destination_lat: Destination latitude.
        destination_lon: Destination longitude.

    Returns:
        A new list ordered nearest-first, preserving original order for ties.
    """
    return sorted(
        candidates,
        key=lambda item: (
            _haversine_distance_miles(
                item["lat"],
                item["lon"],
                destination_lat,
                destination_lon,
            ),
            item["mls_number"],
        ),
    )


def _extract_candidate_listings(prefiltered_geojson: GeoJsonDict | None) -> list[CommuteListingCandidate]:
    """
    Extract route-checkable listing points from a FeatureCollection.

    Args:
        prefiltered_geojson: Current coarse-filtered GeoJSON payload.

    Returns:
        A list of candidate listings with MLS ids and point coordinates.
    """
    features = prefiltered_geojson.get("features") if isinstance(prefiltered_geojson, dict) else None
    if not isinstance(features, list):
        return []

    candidates: list[CommuteListingCandidate] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue

        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            continue

        mls_number = normalize_mls_number(properties.get("mls_number"))
        if not mls_number:
            continue

        coordinates = _normalize_point_coordinates(geometry.get("coordinates"))
        if coordinates is None:
            continue

        lat, lon = coordinates
        candidates.append(
            {
                "mls_number": mls_number,
                "lat": lat,
                "lon": lon,
            }
        )

    return candidates


def build_commute_request_data(
    *,
    destination: str,
    geocoded: PlaceGeocodeResult | None,
    mode: str | None,
    minutes: int | float | None,
    departure_datetime: str | None,
    active: bool,
    status: str,
    error: str | None,
) -> CommuteRequestData:
    """
    Build normalized commute request metadata for the browser.

    Args:
        destination: Sanitized destination text from the user.
        geocoded: Geocoded destination payload when available.
        mode: Selected commute mode.
        minutes: Selected maximum commute duration.
        departure_datetime: Selected local departure datetime.
        active: Whether a coarse commute polygon was successfully loaded.
        error: Optional error code or message for the current request.

    Returns:
        A request metadata object stored in `dcc.Store`.
    """
    normalized_mode = normalize_commute_mode(mode)
    normalized_minutes = normalize_commute_minutes(minutes)
    normalized_departure = normalize_commute_departure_datetime(departure_datetime)
    display_name = (
        geocoded.get("display_name")
        if geocoded and geocoded.get("display_name")
        else destination or None
    )
    lat = geocoded.get("lat") if geocoded else None
    lon = geocoded.get("lon") if geocoded else None
    signature = (
        build_commute_signature(
            lat,
            lon,
            normalized_mode,
            normalized_minutes,
            normalized_departure,
        )
        if lat is not None and lon is not None
        else None
    )

    return {
        "requested": bool(destination),
        "active": active,
        "signature": signature,
        "destination": destination,
        "query": geocoded.get("query") if geocoded else None,
        "display_name": display_name,
        "mode": normalized_mode,
        "mode_label": COMMUTE_MODE_LABELS[normalized_mode],
        "minutes": normalized_minutes,
        "departure_datetime": normalized_departure,
        "departure_label": format_commute_departure_label(normalized_departure),
        "center_lat": lat,
        "center_lon": lon,
        "status": status,
        "error": error,
    }


def _exact_commute_provider_label(mode: str | None) -> str:
    """
    Choose the exact-route provider label for the selected mode.

    Args:
        mode: Selected commute mode.

    Returns:
        A human-readable provider label.
    """
    normalized_mode = normalize_commute_mode(mode)
    if normalized_mode == "drive" and MAPBOX_DRIVE_EXACT_ENABLED:
        return MAPBOX_SERVICE_LABEL
    return VALHALLA_SERVICE_LABEL


def _exact_commute_candidate_limit(mode: str | None) -> int:
    """
    Return the maximum number of candidates to exact-check for the current mode.

    Args:
        mode: Selected commute mode.

    Returns:
        Candidate limit for exact route checks.
    """
    normalized_mode = normalize_commute_mode(mode)
    if normalized_mode == "drive" and MAPBOX_DRIVE_EXACT_ENABLED:
        return MAPBOX_DRIVE_EXACT_MAX_CANDIDATES
    return VALHALLA_EXACT_COMMUTE_MAX_CANDIDATES


def _mapbox_depart_at_value(value: str | None) -> str | None:
    """
    Build a Mapbox-compatible `depart_at` value when the selected time is usable.

    Args:
        value: Raw or normalized local departure datetime string.

    Returns:
        A normalized local datetime string, or `None` when the selected time is
        in the past and should fall back to present-time traffic.
    """
    normalized = normalize_commute_departure_datetime(value)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed < datetime.now():
        return None
    return normalized


def _fetch_mapbox_drive_batch_durations(
    batch: list[CommuteListingCandidate],
    destination_lat: float,
    destination_lon: float,
    departure_datetime: str | None,
) -> RouteDurationLookup:
    """
    Fetch many-to-one traffic-aware durations for a batch of listings.

    Args:
        batch: Origin listings to verify.
        destination_lat: Destination latitude.
        destination_lon: Destination longitude.
        departure_datetime: Selected local departure datetime.

    Returns:
        A mapping from MLS id to duration seconds, or `None` when unavailable.
    """
    if not batch:
        return {}

    coordinates = [
        f"{candidate['lon']:.6f},{candidate['lat']:.6f}"
        for candidate in batch
    ]
    destination_index = len(batch)
    coordinates.append(f"{destination_lon:.6f},{destination_lat:.6f}")
    sources = ";".join(str(index) for index in range(len(batch)))
    params: dict[str, str] = {
        "access_token": MAPBOX_ACCESS_TOKEN,
        "annotations": "duration",
        "sources": sources,
        "destinations": str(destination_index),
    }
    depart_at = _mapbox_depart_at_value(departure_datetime)
    if depart_at:
        params["depart_at"] = depart_at

    url = (
        f"{MAPBOX_MATRIX_BASE_URL}/directions-matrix/v1/mapbox/driving-traffic/"
        f"{';'.join(coordinates)}"
    )

    try:
        response = requests.get(
            url,
            params=params,
            headers=VALHALLA_HTTP_HEADERS,
            timeout=MAPBOX_MATRIX_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning(f"Mapbox Matrix request failed for {len(batch)} drive candidates: {exc}")
        return {candidate["mls_number"]: None for candidate in batch}

    if (
        not response.ok
        and "depart_at" in params
        and MAPBOX_MATRIX_RETRY_WITHOUT_DEPART_AT
    ):
        retry_params = dict(params)
        retry_params.pop("depart_at", None)
        try:
            response = requests.get(
                url,
                params=retry_params,
                headers=VALHALLA_HTTP_HEADERS,
                timeout=MAPBOX_MATRIX_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Mapbox Matrix retry without depart_at failed for "
                f"{len(batch)} drive candidates: {exc}"
            )
            return {candidate["mls_number"]: None for candidate in batch}

    if not response.ok:
        logger.warning(
            "Mapbox Matrix request failed for "
            f"{len(batch)} drive candidates: HTTP {response.status_code} "
            f"{response.reason}; {_truncate_response_text(response.text)}"
        )
        return {candidate["mls_number"]: None for candidate in batch}

    try:
        payload_json = response.json()
    except ValueError as exc:
        logger.warning(f"Mapbox Matrix returned invalid JSON: {exc}")
        return {candidate["mls_number"]: None for candidate in batch}

    if not isinstance(payload_json, dict):
        return {candidate["mls_number"]: None for candidate in batch}

    durations = payload_json.get("durations")
    if not isinstance(durations, list):
        logger.warning(
            "Mapbox Matrix returned no duration matrix: "
            f"{_truncate_response_text(response.text)}"
        )
        return {candidate["mls_number"]: None for candidate in batch}

    results: RouteDurationLookup = {}
    for index, candidate in enumerate(batch):
        row = durations[index] if index < len(durations) else None
        value = row[0] if isinstance(row, list) and row else None
        results[candidate["mls_number"]] = (
            float(value) if isinstance(value, (int, float)) else None
        )

    return results


def fetch_mapbox_drive_route_times_seconds(
    candidates: list[CommuteListingCandidate],
    destination_lat: float,
    destination_lon: float,
    departure_datetime: str | None,
) -> RouteDurationLookup:
    """
    Fetch traffic-aware Mapbox durations for prioritized drive candidates.

    Args:
        candidates: Origin listings to verify.
        destination_lat: Destination latitude.
        destination_lon: Destination longitude.
        departure_datetime: Selected local departure datetime.

    Returns:
        A mapping from MLS id to duration seconds, or `None` when unavailable.
    """
    if not candidates:
        return {}

    batch_size = max(1, MAPBOX_MATRIX_COORDINATE_LIMIT - 1)
    batches = [
        candidates[start:start + batch_size]
        for start in range(0, len(candidates), batch_size)
    ]

    if len(batches) == 1:
        return _fetch_mapbox_drive_batch_durations(
            batches[0],
            destination_lat,
            destination_lon,
            departure_datetime,
        )

    results: RouteDurationLookup = {}
    max_workers = min(MAPBOX_MATRIX_MAX_WORKERS, len(batches))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_batch = {
            executor.submit(
                _fetch_mapbox_drive_batch_durations,
                batch,
                destination_lat,
                destination_lon,
                departure_datetime,
            ): batch
            for batch in batches
        }

        for future in as_completed(future_to_batch):
            batch = future_to_batch[future]
            try:
                batch_results = future.result()
            except Exception as exc:
                logger.warning(
                    f"Mapbox Matrix batch verification crashed for {len(batch)} listings: {exc}"
                )
                batch_results = {
                    candidate["mls_number"]: None
                    for candidate in batch
                }
            results.update(batch_results)

    return results


def build_valhalla_isochrone_request(
    lat: float,
    lon: float,
    mode: str | None,
    minutes: int | float | None,
    departure_datetime: str | None,
) -> GeoJsonDict:
    """
    Build a Valhalla isochrone request payload.

    Args:
        lat: Destination latitude.
        lon: Destination longitude.
        mode: Selected commute mode.
        minutes: Selected max duration.
        departure_datetime: Selected local departure datetime.

    Returns:
        A JSON-serializable Valhalla isochrone request payload.
    """
    normalized_mode = normalize_commute_mode(mode)
    normalized_minutes = normalize_commute_minutes(minutes)
    return {
        "locations": [{"lat": lat, "lon": lon}],
        "costing": COMMUTE_VALHALLA_COSTING[normalized_mode],
        "contours": [{"time": float(normalized_minutes), "color": "f4a261"}],
        "polygons": True,
        "denoise": 0.0,
        "reverse": True,
        "show_locations": False,
        "date_time": build_valhalla_date_time(departure_datetime),
    }


def decorate_valhalla_isochrone_geojson(
    geojson: GeoJsonDict,
    *,
    query: str,
    mode: str | None,
    minutes: int | float | None,
    display_name: str | None,
) -> GeoJsonDict:
    """
    Annotate a Valhalla isochrone response with app metadata.

    Args:
        geojson: Raw GeoJSON returned by Valhalla.
        query: Sanitized destination query string.
        mode: Selected commute mode.
        minutes: Selected max duration.
        display_name: Human-readable destination label.

    Returns:
        The same GeoJSON object with app-specific feature properties attached.
    """
    normalized_mode = normalize_commute_mode(mode)
    normalized_minutes = normalize_commute_minutes(minutes)
    features = geojson.get("features")
    if not isinstance(features, list):
        return geojson

    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.setdefault("properties", {})
        if not isinstance(properties, dict):
            continue
        properties.update(
            {
                "query": query,
                "display_name": display_name or query,
                "mode": normalized_mode,
                "mode_label": COMMUTE_MODE_LABELS[normalized_mode],
                "minutes": normalized_minutes,
                "source": "valhalla_public_demo",
                "approximate": False,
                "prefilter_only": True,
            }
        )

    return geojson


@lru_cache(maxsize=256)
def fetch_valhalla_isochrone(
    lat: float,
    lon: float,
    mode: str | None,
    minutes: int | float | None,
    departure_datetime: str | None,
    display_name: str,
) -> GeoJsonDict | None:
    """
    Fetch a reverse isochrone polygon from the configured Valhalla service.

    Args:
        lat: Destination latitude.
        lon: Destination longitude.
        mode: Selected commute mode.
        minutes: Selected max duration.
        departure_datetime: Selected local departure datetime.
        display_name: Human-readable label used for logs and feature metadata.

    Returns:
        A decorated GeoJSON FeatureCollection on success, otherwise `None`.
    """
    normalized_mode = normalize_commute_mode(mode)
    normalized_minutes = normalize_commute_minutes(minutes)
    normalized_departure = normalize_commute_departure_datetime(departure_datetime)
    payload = build_valhalla_isochrone_request(
        lat,
        lon,
        normalized_mode,
        normalized_minutes,
        normalized_departure,
    )

    try:
        response = requests.post(
            f"{VALHALLA_BASE_URL}/isochrone",
            json=payload,
            headers=VALHALLA_HTTP_HEADERS,
            timeout=VALHALLA_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning(
            "Valhalla isochrone request failed for "
            f"{display_name} ({lat}, {lon}, {normalized_minutes} min): {exc}"
        )
        return None

    if not response.ok:
        logger.warning(
            "Valhalla isochrone request failed for "
            f"{display_name} ({lat}, {lon}, {normalized_minutes} min): "
            f"HTTP {response.status_code} {response.reason}; "
            f"{_truncate_response_text(response.text)}"
        )
        return None

    try:
        geojson = response.json()
    except ValueError as exc:
        logger.warning(
            f"Valhalla isochrone returned invalid JSON for {display_name}: {exc}"
        )
        return None

    if not isinstance(geojson, dict):
        logger.warning(f"Valhalla isochrone returned a non-dict payload for {display_name}.")
        return None

    features = geojson.get("features")
    if not isinstance(features, list) or not features:
        logger.warning(f"Valhalla isochrone returned no features for {display_name}.")
        return None

    return decorate_valhalla_isochrone_geojson(
        geojson,
        query=display_name,
        mode=normalized_mode,
        minutes=normalized_minutes,
        display_name=display_name,
    )


def build_commute_boundary_result(
    *,
    destination: str,
    geocoded: PlaceGeocodeResult | None,
    mode: str | None,
    minutes: int | float | None,
    departure_datetime: str | None,
) -> CommuteBoundaryResult:
    """
    Build the commute boundary overlay payload and request metadata.

    Args:
        destination: Sanitized destination text entered by the user.
        geocoded: Geocoded destination when available.
        mode: Selected commute mode.
        minutes: Selected max commute duration.
        departure_datetime: Selected local departure datetime.

    Returns:
        A dict containing overlay GeoJSON, status text, and normalized request metadata.
    """
    normalized_mode = normalize_commute_mode(mode)
    normalized_minutes = normalize_commute_minutes(minutes)
    normalized_departure = normalize_commute_departure_datetime(departure_datetime)
    mode_label = COMMUTE_MODE_LABELS[normalized_mode]
    mode_status_label = commute_mode_status_label(normalized_mode)
    departure_label = format_commute_departure_label(normalized_departure)

    if not destination:
        return {
            "geojson": empty_feature_collection(),
            "status": "",
            "request": empty_commute_request_data(),
        }

    if geocoded is None:
        return {
            "geojson": empty_feature_collection(),
            "status": "Destination not found.",
            "request": build_commute_request_data(
                destination=destination,
                geocoded=None,
                mode=normalized_mode,
                minutes=normalized_minutes,
                departure_datetime=normalized_departure,
                active=False,
                status="Destination not found.",
                error="place_not_found",
            ),
        }

    display_name = geocoded.get("display_name") or destination
    geojson = fetch_valhalla_isochrone(
        geocoded["lat"],
        geocoded["lon"],
        normalized_mode,
        normalized_minutes,
        normalized_departure,
        display_name,
    )

    if geojson is None:
        return {
            "geojson": empty_feature_collection(),
            "status": "Commute area unavailable right now.",
            "request": build_commute_request_data(
                destination=destination,
                geocoded=geocoded,
                mode=normalized_mode,
                minutes=normalized_minutes,
                departure_datetime=normalized_departure,
                active=False,
                status="Commute area unavailable right now.",
                error="isochrone_unavailable",
            ),
        }

    status = (
        f"Estimated {mode_status_label} area loaded for "
        f"{display_name or 'the destination'} departing {departure_label}."
    )
    return {
        "geojson": geojson,
        "status": status,
        "request": build_commute_request_data(
            destination=destination,
            geocoded=geocoded,
            mode=normalized_mode,
            minutes=normalized_minutes,
            departure_datetime=normalized_departure,
            active=True,
            status=status,
            error=None,
        ),
    }


def build_valhalla_route_request(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    mode: str | None,
    departure_datetime: str | None,
) -> GeoJsonDict:
    """
    Build a Valhalla route request payload for an origin/destination pair.

    Args:
        origin_lat: Listing latitude.
        origin_lon: Listing longitude.
        destination_lat: Destination latitude.
        destination_lon: Destination longitude.
        mode: Selected commute mode.
        departure_datetime: Selected local departure datetime.

    Returns:
        A JSON-serializable Valhalla route request payload.
    """
    normalized_mode = normalize_commute_mode(mode)
    return {
        "locations": [
            {"lat": origin_lat, "lon": origin_lon},
            {"lat": destination_lat, "lon": destination_lon},
        ],
        "costing": COMMUTE_VALHALLA_COSTING[normalized_mode],
        "units": "miles",
        "date_time": build_valhalla_date_time(departure_datetime),
    }


@lru_cache(maxsize=4096)
def fetch_valhalla_route_time_seconds(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    mode: str | None,
    departure_datetime: str | None,
) -> float | None:
    """
    Fetch an exact Valhalla route duration between a listing and a destination.

    Args:
        origin_lat: Listing latitude.
        origin_lon: Listing longitude.
        destination_lat: Destination latitude.
        destination_lon: Destination longitude.
        mode: Selected commute mode.
        departure_datetime: Selected local departure datetime.

    Returns:
        The route duration in seconds when available, otherwise `None`.
    """
    normalized_mode = normalize_commute_mode(mode)
    payload = build_valhalla_route_request(
        origin_lat,
        origin_lon,
        destination_lat,
        destination_lon,
        normalized_mode,
        departure_datetime,
    )

    max_attempts = VALHALLA_ROUTE_MAX_RETRIES + 1
    response: requests.Response | None = None
    for attempt in range(max_attempts):
        try:
            response = requests.post(
                f"{VALHALLA_BASE_URL}/route",
                json=payload,
                headers=VALHALLA_HTTP_HEADERS,
                timeout=VALHALLA_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Valhalla route request failed for "
                f"({origin_lat}, {origin_lon}) -> ({destination_lat}, {destination_lon}) "
                f"via {normalized_mode}: {exc}"
            )
            return None

        if response.ok:
            break

        if response.status_code == 429 and attempt + 1 < max_attempts:
            time.sleep(VALHALLA_ROUTE_RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue

        logger.warning(
            "Valhalla route request failed for "
            f"({origin_lat}, {origin_lon}) -> ({destination_lat}, {destination_lon}) "
            f"via {normalized_mode}: HTTP {response.status_code} {response.reason}; "
            f"{_truncate_response_text(response.text)}"
        )
        return None

    try:
        payload_json = response.json()
    except ValueError as exc:
        logger.warning(
            "Valhalla route returned invalid JSON for "
            f"({origin_lat}, {origin_lon}) -> ({destination_lat}, {destination_lon}): {exc}"
        )
        return None

    if not isinstance(payload_json, dict):
        return None

    trip = payload_json.get("trip")
    if not isinstance(trip, dict):
        return None

    summary = trip.get("summary")
    if not isinstance(summary, dict):
        return None

    time_seconds = summary.get("time")
    if isinstance(time_seconds, (int, float)):
        return float(time_seconds)

    return None


def fetch_valhalla_route_times_seconds(
    candidates: list[CommuteListingCandidate],
    destination_lat: float,
    destination_lon: float,
    mode: str | None,
    departure_datetime: str | None,
) -> RouteDurationLookup:
    """
    Fetch exact Valhalla durations for a prioritized listing subset.

    Args:
        candidates: Origin listings to verify.
        destination_lat: Destination latitude.
        destination_lon: Destination longitude.
        mode: Selected commute mode.
        departure_datetime: Selected local departure datetime.

    Returns:
        A mapping from MLS id to duration seconds, or `None` when unavailable.
    """
    if not candidates:
        return {}

    normalized_mode = normalize_commute_mode(mode)
    worker_limit = (
        VALHALLA_EXACT_COMMUTE_TRANSIT_MAX_WORKERS
        if normalized_mode == "transit"
        else VALHALLA_EXACT_COMMUTE_MAX_WORKERS
    )
    max_workers = min(worker_limit, len(candidates))

    if max_workers == 1:
        return {
            candidate["mls_number"]: fetch_valhalla_route_time_seconds(
                candidate["lat"],
                candidate["lon"],
                destination_lat,
                destination_lon,
                normalized_mode,
                departure_datetime,
            )
            for candidate in candidates
        }

    results: RouteDurationLookup = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_candidate = {
            executor.submit(
                fetch_valhalla_route_time_seconds,
                candidate["lat"],
                candidate["lon"],
                destination_lat,
                destination_lon,
                normalized_mode,
                departure_datetime,
            ): candidate
            for candidate in candidates
        }

        for future in as_completed(future_to_candidate):
            candidate = future_to_candidate[future]
            try:
                results[candidate["mls_number"]] = future.result()
            except Exception as exc:
                logger.warning(
                    "Exact Valhalla route verification crashed for "
                    f"MLS {candidate['mls_number']}: {exc}"
                )
                results[candidate["mls_number"]] = None

    return results


def verify_exact_commute_matches(
    *,
    prefiltered_geojson: GeoJsonDict | None,
    commute_request: dict[str, Any] | None,
) -> CommuteExactMatchResult:
    """
    Route-check each coarse commute match against the exact Valhalla duration.

    Args:
        prefiltered_geojson: Current listing FeatureCollection after all clientside
            filters, including the coarse commute polygon prefilter.
        commute_request: Normalized request metadata from `build_commute_boundary_result`.

    Returns:
        A result object containing the eligible MLS ids, status text, and any
        verification errors for the current candidate set.
    """
    base_result = empty_commute_exact_result()
    if not isinstance(commute_request, dict):
        return base_result

    requested = bool(commute_request.get("requested"))
    active = bool(commute_request.get("active"))
    commute_signature = commute_request.get("signature")
    display_name = commute_request.get("display_name")
    mode = normalize_commute_mode(commute_request.get("mode"))
    mode_label = COMMUTE_MODE_LABELS[mode]
    mode_status_label = commute_mode_status_label(mode)
    minutes = normalize_commute_minutes(commute_request.get("minutes"))
    destination_lat = commute_request.get("center_lat")
    destination_lon = commute_request.get("center_lon")
    departure_datetime = normalize_commute_departure_datetime(
        commute_request.get("departure_datetime")
    )
    departure_label = format_commute_departure_label(departure_datetime)

    base_result.update(
        {
            "requested": requested,
            "active": active,
            "commute_signature": commute_signature if isinstance(commute_signature, str) else None,
            "mode": mode,
            "mode_label": mode_label,
            "minutes": minutes,
            "display_name": str(display_name) if display_name else None,
            "provider": _exact_commute_provider_label(mode),
        }
    )

    if not requested:
        return base_result

    if (
        not active
        or not isinstance(commute_signature, str)
        or not isinstance(destination_lat, (int, float))
        or not isinstance(destination_lon, (int, float))
    ):
        return base_result

    candidates = _extract_candidate_listings(prefiltered_geojson)
    candidate_signature = build_candidate_signature(
        commute_signature,
        (candidate["mls_number"] for candidate in candidates),
    )

    base_result.update(
        {
            "active": True,
            "signature": candidate_signature,
            "total_candidates": len(candidates),
        }
    )

    if not candidates:
        base_result["status"] = "No listings match this commute."
        return base_result

    prioritized_candidates = _prioritize_candidates_by_distance(
        candidates,
        float(destination_lat),
        float(destination_lon),
    )
    exact_limit = _exact_commute_candidate_limit(mode)
    attempt_candidates = prioritized_candidates[:exact_limit]
    attempted_candidates = len(attempt_candidates)

    provider = _exact_commute_provider_label(mode)
    if provider == MAPBOX_SERVICE_LABEL:
        duration_lookup = fetch_mapbox_drive_route_times_seconds(
            attempt_candidates,
            float(destination_lat),
            float(destination_lon),
            departure_datetime,
        )
    else:
        duration_lookup = fetch_valhalla_route_times_seconds(
            attempt_candidates,
            float(destination_lat),
            float(destination_lon),
            mode,
            departure_datetime,
        )

    eligible_mls: list[str] = []
    excluded_mls: list[str] = []
    checked_candidates = 0
    failed_candidates = 0
    for candidate in attempt_candidates:
        time_seconds = duration_lookup.get(candidate["mls_number"])
        if time_seconds is None:
            failed_candidates += 1
            continue

        checked_candidates += 1
        if time_seconds <= minutes * 60:
            eligible_mls.append(candidate["mls_number"])
        else:
            excluded_mls.append(candidate["mls_number"])

    matched_candidates = len(eligible_mls)
    excluded_candidates = len(excluded_mls)
    verified_ids = set(eligible_mls) | set(excluded_mls)
    rough_mls = [
        candidate["mls_number"]
        for candidate in candidates
        if candidate["mls_number"] not in verified_ids
    ]
    rough_candidates = len(rough_mls)
    partial = rough_candidates > 0
    base_result.update(
        {
            "eligible_mls": sorted(set(eligible_mls)),
            "excluded_mls": sorted(set(excluded_mls)),
            "rough_mls": rough_mls,
            "attempted_candidates": attempted_candidates,
            "checked_candidates": checked_candidates,
            "matched_candidates": matched_candidates,
            "excluded_candidates": excluded_candidates,
            "rough_candidates": rough_candidates,
            "failed_candidates": failed_candidates,
            "partial": partial,
        }
    )

    if checked_candidates == 0:
        error = "Exact commute estimates unavailable right now. Showing rough matches only."
        base_result.update({"status": error, "error": error})
        return base_result

    destination_label = str(display_name) if display_name else "the destination"
    if matched_candidates:
        status = (
            f"Verified {matched_candidates} listings within {minutes} minutes by "
            f"{mode_status_label} to {destination_label} departing {departure_label}."
        )
    else:
        status = (
            f"No verified listings were found within {minutes} minutes by "
            f"{mode_status_label} to {destination_label} departing {departure_label}."
        )

    if partial:
        status = (
            f"{status} Checked the closest {attempted_candidates} of "
            f"{len(candidates)} candidate listings using {provider}. "
            f"{rough_candidates} rough matches remain."
        )
    elif attempted_candidates:
        status = f"{status} Checked {attempted_candidates} listings using {provider}."

    if failed_candidates:
        status = f"{status} Some listings could not be verified."

    base_result["status"] = status
    return base_result
