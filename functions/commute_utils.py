from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import Any, Iterable, TypeAlias, TypedDict
import os

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

COMMUTE_MODE_LABELS: dict[str, str] = {
    "drive": "Drive",
    "transit": "Transit",
    "bike": "Bike",
    "walk": "Walk",
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
            "60" if VALHALLA_IS_PUBLIC_DEMO else "400",
        )
    ),
)
VALHALLA_EXACT_COMMUTE_MAX_WORKERS = max(
    1,
    int(
        os.getenv(
            "VALHALLA_EXACT_COMMUTE_MAX_WORKERS",
            "4" if VALHALLA_IS_PUBLIC_DEMO else "8",
        )
    ),
)

COMMUTE_HELP_TEXT = (
    (
        f"Travel-time filtering uses {VALHALLA_SERVICE_LABEL}: a coarse area "
        "first, then exact route-time checks for the remaining listings. This "
        "service has fair-use limits and may occasionally be unavailable. Drive "
        "times reflect Valhalla's routing model and can still differ from real "
        "LA traffic."
    )
    if VALHALLA_IS_PUBLIC_DEMO
    else (
        f"Travel-time filtering uses {VALHALLA_SERVICE_LABEL}: a coarse area "
        "first, then exact route-time checks for the remaining listings. Drive "
        "times still reflect Valhalla's routing model rather than guaranteed "
        "live traffic."
    )
)

VALHALLA_HTTP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "WhereToLive.LA/1.0",
}


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
    center_lat: float | None
    center_lon: float | None
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
    total_candidates: int
    checked_candidates: int
    matched_candidates: int
    failed_candidates: int
    mode: str | None
    mode_label: str | None
    minutes: int | None
    display_name: str | None
    status: str
    error: str | None


class CommuteListingCandidate(TypedDict):
    """Normalized candidate listing point extracted from a GeoJSON feature."""

    mls_number: str
    lat: float
    lon: float


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
        "center_lat": None,
        "center_lon": None,
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
        "total_candidates": 0,
        "checked_candidates": 0,
        "matched_candidates": 0,
        "failed_candidates": 0,
        "mode": None,
        "mode_label": None,
        "minutes": None,
        "display_name": None,
        "status": "",
        "error": None,
    }


def build_commute_signature(
    lat: float,
    lon: float,
    mode: str | None,
    minutes: int | float | None,
) -> str:
    """
    Build a stable signature for a destination/mode/time commute request.

    Args:
        lat: Destination latitude.
        lon: Destination longitude.
        mode: Selected commute mode.
        minutes: Selected max minutes.

    Returns:
        A stable string signature for caching and store comparisons.
    """
    normalized_mode = normalize_commute_mode(mode)
    normalized_minutes = normalize_commute_minutes(minutes)
    return f"{normalized_mode}:{normalized_minutes}:{lat:.6f}:{lon:.6f}"


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
    active: bool,
    error: str | None,
) -> CommuteRequestData:
    """
    Build normalized commute request metadata for the browser.

    Args:
        destination: Sanitized destination text from the user.
        geocoded: Geocoded destination payload when available.
        mode: Selected commute mode.
        minutes: Selected maximum commute duration.
        active: Whether a coarse commute polygon was successfully loaded.
        error: Optional error code or message for the current request.

    Returns:
        A request metadata object stored in `dcc.Store`.
    """
    normalized_mode = normalize_commute_mode(mode)
    normalized_minutes = normalize_commute_minutes(minutes)
    display_name = (
        geocoded.get("display_name")
        if geocoded and geocoded.get("display_name")
        else destination or None
    )
    lat = geocoded.get("lat") if geocoded else None
    lon = geocoded.get("lon") if geocoded else None
    signature = (
        build_commute_signature(lat, lon, normalized_mode, normalized_minutes)
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
        "center_lat": lat,
        "center_lon": lon,
        "error": error,
    }


def build_valhalla_isochrone_request(
    lat: float,
    lon: float,
    mode: str | None,
    minutes: int | float | None,
) -> GeoJsonDict:
    """
    Build a Valhalla isochrone request payload.

    Args:
        lat: Destination latitude.
        lon: Destination longitude.
        mode: Selected commute mode.
        minutes: Selected max duration.

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
        "date_time": {"type": 0},
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
    display_name: str,
) -> GeoJsonDict | None:
    """
    Fetch a reverse isochrone polygon from the configured Valhalla service.

    Args:
        lat: Destination latitude.
        lon: Destination longitude.
        mode: Selected commute mode.
        minutes: Selected max duration.
        display_name: Human-readable label used for logs and feature metadata.

    Returns:
        A decorated GeoJSON FeatureCollection on success, otherwise `None`.
    """
    normalized_mode = normalize_commute_mode(mode)
    normalized_minutes = normalize_commute_minutes(minutes)
    payload = build_valhalla_isochrone_request(lat, lon, normalized_mode, normalized_minutes)

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
) -> CommuteBoundaryResult:
    """
    Build the commute boundary overlay payload and request metadata.

    Args:
        destination: Sanitized destination text entered by the user.
        geocoded: Geocoded destination when available.
        mode: Selected commute mode.
        minutes: Selected max commute duration.

    Returns:
        A dict containing overlay GeoJSON, status text, and normalized request metadata.
    """
    normalized_mode = normalize_commute_mode(mode)
    normalized_minutes = normalize_commute_minutes(minutes)
    mode_label = COMMUTE_MODE_LABELS[normalized_mode].lower()

    if not destination:
        return {
            "geojson": empty_feature_collection(),
            "status": "",
            "request": empty_commute_request_data(),
        }

    if geocoded is None:
        return {
            "geojson": empty_feature_collection(),
            "status": f"Could not find a California location matching '{destination}'.",
            "request": build_commute_request_data(
                destination=destination,
                geocoded=None,
                mode=normalized_mode,
                minutes=normalized_minutes,
                active=False,
                error="place_not_found",
            ),
        }

    display_name = geocoded.get("display_name") or destination
    geojson = fetch_valhalla_isochrone(
        geocoded["lat"],
        geocoded["lon"],
        normalized_mode,
        normalized_minutes,
        display_name,
    )

    if geojson is None:
        return {
            "geojson": empty_feature_collection(),
            "status": (
                f"{VALHALLA_SERVICE_LABEL} unavailable; could not load a "
                f"{mode_label} commute area for {display_name}."
            ),
            "request": build_commute_request_data(
                destination=destination,
                geocoded=geocoded,
                mode=normalized_mode,
                minutes=normalized_minutes,
                active=False,
                error="isochrone_unavailable",
            ),
        }

    return {
        "geojson": geojson,
        "status": (
            f"{VALHALLA_SERVICE_LABEL}: coarse "
            f"{mode_label} area loaded for {display_name}. Exact route checks "
            f"will keep only listings that can arrive within {normalized_minutes} minutes."
        ),
        "request": build_commute_request_data(
            destination=destination,
            geocoded=geocoded,
            mode=normalized_mode,
            minutes=normalized_minutes,
            active=True,
            error=None,
        ),
    }


def build_valhalla_route_request(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    mode: str | None,
) -> GeoJsonDict:
    """
    Build a Valhalla route request payload for an origin/destination pair.

    Args:
        origin_lat: Listing latitude.
        origin_lon: Listing longitude.
        destination_lat: Destination latitude.
        destination_lon: Destination longitude.
        mode: Selected commute mode.

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
        "date_time": {"type": 0},
    }


@lru_cache(maxsize=4096)
def fetch_valhalla_route_time_seconds(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    mode: str | None,
) -> float | None:
    """
    Fetch an exact Valhalla route duration between a listing and a destination.

    Args:
        origin_lat: Listing latitude.
        origin_lon: Listing longitude.
        destination_lat: Destination latitude.
        destination_lon: Destination longitude.
        mode: Selected commute mode.

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
    )

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

    if not response.ok:
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
    minutes = normalize_commute_minutes(commute_request.get("minutes"))
    destination_lat = commute_request.get("center_lat")
    destination_lon = commute_request.get("center_lon")

    base_result.update(
        {
            "requested": requested,
            "active": active,
            "commute_signature": commute_signature if isinstance(commute_signature, str) else None,
            "mode": mode,
            "mode_label": mode_label,
            "minutes": minutes,
            "display_name": str(display_name) if display_name else None,
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

    if len(candidates) > VALHALLA_EXACT_COMMUTE_MAX_CANDIDATES:
        error = (
            "Exact route checks are limited to "
            f"{VALHALLA_EXACT_COMMUTE_MAX_CANDIDATES} coarse-match listings at a "
            f"time with {VALHALLA_SERVICE_LABEL}. {len(candidates)} listings "
            "matched the coarse area, so narrow the other filters or lower the "
            "commute time."
        )
        base_result.update({"status": error, "error": error})
        return base_result

    if not candidates:
        base_result["status"] = "Exact route check: no listings left after the coarse commute area."
        return base_result

    eligible_mls: list[str] = []
    checked_candidates = 0
    failed_candidates = 0

    max_workers = min(VALHALLA_EXACT_COMMUTE_MAX_WORKERS, len(candidates))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_candidate = {
            executor.submit(
                fetch_valhalla_route_time_seconds,
                candidate["lat"],
                candidate["lon"],
                float(destination_lat),
                float(destination_lon),
                mode,
            ): candidate
            for candidate in candidates
        }

        for future in as_completed(future_to_candidate):
            candidate = future_to_candidate[future]
            try:
                time_seconds = future.result()
            except Exception as exc:
                logger.warning(
                    "Exact Valhalla route verification crashed for "
                    f"MLS {candidate['mls_number']}: {exc}"
                )
                failed_candidates += 1
                continue

            if time_seconds is None:
                failed_candidates += 1
                continue

            checked_candidates += 1
            if time_seconds <= minutes * 60:
                eligible_mls.append(candidate["mls_number"])

    matched_candidates = len(eligible_mls)
    base_result.update(
        {
            "eligible_mls": sorted(set(eligible_mls)),
            "checked_candidates": checked_candidates,
            "matched_candidates": matched_candidates,
            "failed_candidates": failed_candidates,
        }
    )

    if checked_candidates == 0:
        error = (
            f"{VALHALLA_SERVICE_LABEL} could not verify any exact commute routes for "
            f"{display_name or 'this destination'} right now. Try again later or "
            "narrow the other filters."
        )
        base_result.update({"status": error, "error": error})
        return base_result

    status = (
        "Exact route check: "
        f"{matched_candidates} of {len(candidates)} listings can reach "
        f"{display_name or 'the destination'} within {minutes} minutes by "
        f"{mode_label.lower()}."
    )
    if failed_candidates:
        status = f"{status} {failed_candidates} route checks could not be verified."

    base_result["status"] = status
    return base_result
