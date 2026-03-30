import os

from dotenv import find_dotenv, load_dotenv
from functools import lru_cache
from loguru import logger
import requests
from typing import Any, TypeAlias, TypedDict
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
COMMUTE_VALHALLA_COSTING: dict[str, str] = {
    "drive": "auto",
    "transit": "multimodal",
    "bike": "bicycle",
    "walk": "pedestrian",
}
COMMUTE_MODE_OPTIONS: list[dict[str, str]] = [
    {"label": COMMUTE_MODE_LABELS[mode], "value": mode}
    for mode in ("drive", "transit", "bike", "walk")
]
VALHALLA_BASE_URL = os.getenv(
    "VALHALLA_BASE_URL",
    "https://valhalla1.openstreetmap.de",
).rstrip("/")
VALHALLA_TIMEOUT_SECONDS = float(os.getenv("VALHALLA_TIMEOUT_SECONDS", "20"))
VALHALLA_HTTP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "WhereToLive.LA/1.0",
}
COMMUTE_HELP_TEXT = (
    "Travel-time area powered by the public Valhalla demo API. "
    "This service has fair-use limits and may occasionally be unavailable."
)


class CommuteBoundaryResult(TypedDict):
    """Return payload for commute-boundary callbacks."""

    geojson: GeoJsonDict
    status: str


def empty_feature_collection() -> GeoJsonDict:
    """
    Build an empty GeoJSON FeatureCollection payload.

    Returns:
        GeoJSON dict with an empty `features` list.
    """
    return {"type": "FeatureCollection", "features": []}


def normalize_commute_mode(mode: str | None) -> str:
    """
    Normalize a commute mode to one of the supported values.

    Args:
        mode: User-selected commute mode, such as `"drive"` or `"transit"`.

    Returns:
        A supported commute mode string. Falls back to the default mode when
        the supplied value is missing or unknown.
    """
    if mode in COMMUTE_VALHALLA_COSTING:
        return mode
    return COMMUTE_DEFAULT_MODE


def normalize_commute_minutes(minutes: int | float | None) -> int:
    """
    Clamp a commute duration to the supported slider range.

    Args:
        minutes: Raw slider value from the UI.

    Returns:
        An integer minute value constrained to the configured min/max range.
        Invalid input falls back to 30 minutes.
    """
    if minutes is None:
        return 30
    try:
        parsed = int(minutes)
    except (TypeError, ValueError):
        return 30
    return max(COMMUTE_MIN_MINUTES, min(COMMUTE_MAX_MINUTES, parsed))


def valhalla_costing_for_mode(mode: str | None) -> str:
    """
    Map a UI commute mode to the corresponding Valhalla costing model.

    Args:
        mode: User-selected commute mode, such as `"drive"` or `"transit"`.

    Returns:
        Valhalla costing string for the normalized commute mode.
    """
    normalized_mode = normalize_commute_mode(mode)
    return COMMUTE_VALHALLA_COSTING[normalized_mode]


def build_valhalla_isochrone_request(
    *,
    lat: float,
    lon: float,
    mode: str,
    minutes: int,
) -> dict[str, Any]:
    """
    Build the JSON payload expected by Valhalla's isochrone endpoint.

    Args:
        lat: Destination latitude in decimal degrees.
        lon: Destination longitude in decimal degrees.
        mode: Commute mode from the UI.
        minutes: Maximum commute duration in minutes.

    Returns:
        Request payload for the Valhalla isochrone API.
    """
    return {
        "locations": [{"lat": lat, "lon": lon}],
        "costing": valhalla_costing_for_mode(mode),
        "contours": [{"time": float(minutes), "color": "f4a261"}],
        "polygons": True,
        "denoise": 0.0,
        "reverse": True,
        "show_locations": False,
        "date_time": {"type": 0},
    }


def decorate_valhalla_isochrone_geojson(
    *,
    geojson: GeoJsonDict,
    query: str,
    mode: str,
    minutes: int,
    display_name: str | None = None,
) -> GeoJsonDict:
    """
    Add app-specific metadata to Valhalla isochrone features.

    Args:
        geojson: Raw GeoJSON response from the Valhalla API.
        query: User-entered destination string.
        mode: Commute mode from the UI.
        minutes: Maximum commute duration in minutes.
        display_name: Optional geocoder-provided label for the destination.

    Returns:
        GeoJSON response with normalized feature properties.
    """
    mode_label = COMMUTE_MODE_LABELS[normalize_commute_mode(mode)]
    decorated_features: list[GeoJsonDict] = []
    for feature in geojson.get("features", []):
        decorated_features.append(
            {
                **feature,
                "properties": {
                    **(feature.get("properties") or {}),
                    "query": query,
                    "display_name": display_name or query,
                    "mode": normalize_commute_mode(mode),
                    "mode_label": mode_label,
                    "minutes": minutes,
                    "source": "valhalla_public_demo",
                    "approximate": False,
                },
            }
        )

    return {
        **geojson,
        "features": decorated_features,
    }


@lru_cache(maxsize=256)
def fetch_valhalla_isochrone(
    *,
    lat: float,
    lon: float,
    query: str,
    mode: str,
    minutes: int,
    display_name: str | None = None,
) -> GeoJsonDict | None:
    """
    Request a commute isochrone from the public Valhalla demo API.

    Args:
        lat: Destination latitude in decimal degrees.
        lon: Destination longitude in decimal degrees.
        query: User-entered destination string.
        mode: Commute mode from the UI.
        minutes: Maximum commute duration in minutes.
        display_name: Optional geocoder-provided label for the destination.

    Returns:
        Decorated GeoJSON FeatureCollection when the request succeeds, else
        `None`.
    """
    payload = build_valhalla_isochrone_request(
        lat=lat,
        lon=lon,
        mode=mode,
        minutes=minutes,
    )

    try:
        response = requests.post(
            f"{VALHALLA_BASE_URL}/isochrone",
            json=payload,
            headers=VALHALLA_HTTP_HEADERS,
            timeout=VALHALLA_TIMEOUT_SECONDS,
        )
        if not response.ok:
            logger.warning(
                "Valhalla public isochrone request failed for {} ({}, {}, {} min) "
                "with HTTP {}: {}",
                query,
                lat,
                lon,
                minutes,
                response.status_code,
                response.text[:500],
            )
            return None
        geojson = response.json()
    except Exception as exc:
        logger.warning(
            "Valhalla public isochrone request failed for {} ({}, {}, {} min): {}",
            query,
            lat,
            lon,
            minutes,
            exc,
        )
        return None

    if geojson.get("type") != "FeatureCollection" or not geojson.get("features"):
        logger.warning(
            "Valhalla public isochrone returned no features for {} ({}, {}, {} min).",
            query,
            lat,
            lon,
            minutes,
        )
        return None

    return decorate_valhalla_isochrone_geojson(
        geojson=geojson,
        query=query,
        mode=mode,
        minutes=minutes,
        display_name=display_name,
    )


def build_commute_boundary_result(
    *,
    destination: str | None,
    geocoded: PlaceGeocodeResult | None,
    mode: str | None,
    minutes: int | float | None,
) -> CommuteBoundaryResult:
    """
    Build the GeoJSON payload and status text for the commute filter.

    Args:
        destination: User-entered destination text.
        geocoded: Cached or freshly geocoded destination payload.
        mode: User-selected commute mode.
        minutes: User-selected maximum commute duration.

    Returns:
        A typed payload containing the commute GeoJSON overlay and the status
        message shown beneath the filter controls.
    """
    if not destination or not destination.strip():
        return {
            "geojson": empty_feature_collection(),
            "status": "",
        }

    normalized_mode = normalize_commute_mode(mode)
    normalized_minutes = normalize_commute_minutes(minutes)
    cleaned_destination = " ".join(destination.strip().split())

    if not geocoded:
        return {
            "geojson": empty_feature_collection(),
            "status": f"Could not find a California destination matching '{cleaned_destination}'.",
        }

    geojson = fetch_valhalla_isochrone(
        lat=round(float(geocoded["lat"]), 6),
        lon=round(float(geocoded["lon"]), 6),
        query=cleaned_destination,
        mode=normalized_mode,
        minutes=normalized_minutes,
        display_name=geocoded.get("display_name"),
    )
    mode_label = COMMUTE_MODE_LABELS[normalized_mode]

    if geojson is not None:
        return {
            "geojson": geojson,
            "status": (
                f"Public Valhalla API: reach {cleaned_destination} within "
                f"{normalized_minutes} minutes by {mode_label.lower()}."
            ),
        }

    return {
        "geojson": empty_feature_collection(),
        "status": (
            f"Public Valhalla API unavailable; could not load a "
            f"{normalized_minutes}-minute {mode_label.lower()} commute area "
            f"for {cleaned_destination}."
        ),
    }
