from collections import defaultdict
from loguru import logger
from pathlib import Path
from shapely.geometry import Point, shape, box
from shapely.prepared import prep
from typing import Any, Sequence, TypeAlias, TypedDict
import bleach
import json
import pandas as pd
import requests


class PlaceGeocodeResult(TypedDict):
    """Normalized geocoding payload stored in the local place cache."""

    lat: float
    lon: float
    query: str
    bbox: list[float]
    display_name: str | None


GeoJSONFeature: TypeAlias = dict[str, Any]
PlaceCache: TypeAlias = dict[str, PlaceGeocodeResult]

_DEFAULT_PLACE_CACHE_PATH = Path("/mnt/cache/location/place_geocode_cache.json")
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_CALIFORNIA_BOUNDS = {
    "south": 32.4,
    "north": 42.1,
    "west": -124.6,
    "east": -114.0,
}

def _normalize_place_query(query: str) -> str:
    """
    Normalize a user-entered place query before sending it to Nominatim.

    Args:
        query: Raw place text entered by the user.

    Returns:
        The cleaned query string, with `, CA` appended when no California
        qualifier is already present.
    """
    normalized = " ".join(str(query).strip().split())
    if not normalized:
        return ""
    lowered = normalized.lower()
    if "los angeles" not in lowered and "ca" not in lowered and "california" not in lowered:
        normalized = f"{normalized}, CA"
    return normalized


def _coordinates_look_like_california(lat: float, lon: float) -> bool:
    """
    Check whether a latitude/longitude pair falls within a California bbox.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.

    Returns:
        `True` when the point lies within the coarse California bounds used by
        the geocoder guardrail, otherwise `False`.
    """
    return (
        _CALIFORNIA_BOUNDS["south"] <= lat <= _CALIFORNIA_BOUNDS["north"]
        and _CALIFORNIA_BOUNDS["west"] <= lon <= _CALIFORNIA_BOUNDS["east"]
    )


def _result_is_california_match(result: dict[str, Any]) -> bool:
    """
    Decide whether a Nominatim candidate should be treated as a California hit.

    Args:
        result: Raw Nominatim response object for a single candidate.

    Returns:
        `True` when the candidate identifies California in its address metadata,
        display name, or fallback coordinates; otherwise `False`.
    """
    if not isinstance(result, dict):
        return False

    address = result.get("address")
    if isinstance(address, dict):
        state = str(address.get("state", "")).strip().lower()
        state_code = str(address.get("state_code", "")).strip().upper()
        iso_region_codes = [
            str(address.get("ISO3166-2-lvl4", "")).strip().upper(),
            str(address.get("ISO3166-2-lvl6", "")).strip().upper(),
        ]
        if state == "california" or state_code == "CA" or any(code.endswith("-CA") for code in iso_region_codes):
            return True

    display_name = str(result.get("display_name", "")).strip().lower()
    if ", california," in display_name or display_name.endswith(", california, united states"):
        return True

    try:
        lat = float(result.get("lat"))
        lon = float(result.get("lon"))
    except (TypeError, ValueError):
        return False

    return _coordinates_look_like_california(lat, lon)

def _load_place_cache(cache_path: Path) -> PlaceCache:
    """
    Load the on-disk place geocoding cache.

    Args:
        cache_path: File path where cached geocode results are stored.

    Returns:
        A mapping of normalized query strings to cached geocode payloads. If the
        cache file is missing or unreadable, an empty mapping is returned.
    """
    if not cache_path.exists():
        return {}
    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning(f"Failed loading place cache {cache_path}: {exc}")
        return {}


def _save_place_cache(cache_path: Path, cache: PlaceCache) -> None:
    """
    Persist the place geocoding cache to disk.

    Args:
        cache_path: Destination file path for the cache JSON.
        cache: Mapping of normalized queries to cached geocode payloads.

    Returns:
        None.
    """
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle)
    except Exception as exc:
        logger.warning(f"Failed writing place cache {cache_path}: {exc}")


def sanitize_location_input(user_input: str) -> str:
    """
    Sanitize free-form location text before geocoding.

    Args:
        user_input: The raw input string from the user.

    Returns:
        A markup-stripped, whitespace-normalized version of the input.
    """
    if not user_input:
        return ""
    # Use bleach to clean the input
    cleaned = bleach.clean(user_input, tags=[], attributes={}, strip=True)
    # Collapse multiple spaces and trim
    normalized = " ".join(cleaned.strip().split())
    return normalized


def geocode_place_cached(
    query: str,
    cache_path: Path | None = None,
) -> PlaceGeocodeResult | None:
    """
    Geocode a place name with Nominatim and a small local JSON cache.

    Args:
        query: User-entered place string to geocode.
        cache_path: Optional override for the cache file location.

    Returns:
        A normalized geocode payload containing latitude, longitude, bbox, and
        display name when a California match is found; otherwise `None`.
    """
    sanitized_query = sanitize_location_input(query)
    normalized = _normalize_place_query(sanitized_query)
    if not normalized:
        return None

    cache_file = cache_path or _DEFAULT_PLACE_CACHE_PATH
    cache = _load_place_cache(cache_file)
    cache_key = normalized.lower()
    if cache_key in cache:
        cached_result = cache[cache_key]
        if _result_is_california_match(cached_result):
            return cached_result

        logger.warning(
            f"Ignoring cached geocode for '{query}': cached result is outside California: {cached_result}"
        )
        cache.pop(cache_key, None)
        _save_place_cache(cache_file, cache)

    params = {
        "format": "json",
        "q": normalized,
        "limit": 5,
        "countrycodes": "us",
        "addressdetails": 1,
    }
    try:
        response = requests.get(
            _NOMINATIM_URL,
            params=params,
            timeout=10,
            headers={"User-Agent": "WhereToLive.LA/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning(f"Nominatim geocoding request failed for '{query}': {exc}")
        return None

    if not payload:
        logger.info(f"No Nominatim candidates found for '{query}' after normalizing to '{normalized}'.")
        return None

    logger.debug(f"Nominatim response for '{query}': {payload}")

    selected_result = next((result for result in payload if _result_is_california_match(result)), None)
    if not selected_result:
        candidate_labels = [result.get("display_name", "<unknown>") for result in payload[:3]]
        logger.warning(
            f"Rejecting Nominatim results for '{query}': no California match found in candidates {candidate_labels}"
        )
        return None

    try:
        lat = float(selected_result.get("lat"))
        lon = float(selected_result.get("lon"))
    except (TypeError, ValueError):
        logger.warning(f"Nominatim returned invalid coordinates for '{query}': {selected_result}")
        return None

    # Get the bounding box if available and convert it to a list of floats
    bbox_values = selected_result.get("boundingbox") or [lat, lat, lon, lon]
    try:
        bbox = [float(coords) for coords in bbox_values]
    except (TypeError, ValueError):
        logger.warning(f"Nominatim returned invalid bounding box for '{query}': {selected_result}")
        bbox = [lat, lat, lon, lon]

    result: PlaceGeocodeResult = {
        "lat": lat,
        "lon": lon,
        "query": normalized,
        "bbox": bbox,
        "display_name": selected_result.get("display_name"),
    }
    cache[cache_key] = result
    _save_place_cache(cache_file, cache)
    logger.debug(f"Geocoded place '{query}' to {result}")
    return result


def load_zip_polygons(geojson_path: str | Path) -> list[GeoJSONFeature]:
    """
    Load ZIP code polygons from a GeoJSON file.

    Args:
        geojson_path: Path to a GeoJSON file with a top-level FeatureCollection.

    Returns:
        A list of GeoJSON feature dicts (may be empty).
    """
    with open(geojson_path, "r", encoding="utf-8") as handle:
        geojson = json.load(handle)
    return geojson.get("features", [])


def intersect_bbox_with_zip_polygons(
    nominatim_bbox: Sequence[float],
    zip_polygons: list[GeoJSONFeature],
) -> list[GeoJSONFeature]:
    """
    Return ZIP polygon features that intersect a Nominatim bounding box.

    Args:
        nominatim_bbox: Nominatim bbox as [south, north, west, east] floats.
        zip_polygons: List of GeoJSON feature dicts (Polygon/MultiPolygon).

    Returns:
        A list of feature dicts that intersect the bbox.
    """
    # Initalize an empty list to hold matching features
    matches: list[GeoJSONFeature] = []
    # Turn the Nominatim bbox into a Shapely box
    bbox_shape = box(nominatim_bbox[2], nominatim_bbox[0], nominatim_bbox[3], nominatim_bbox[1])
    # Prepare the box for faster intersection tests
    prepared_bbox = prep(bbox_shape)
    # Since the ZIP features are already polygons we can prepare them directly
    for feature in zip_polygons:
        # Get the geometry from the feature
        geometry = feature.get("geometry")
        if not geometry:
            continue
        # Turn the feature geometry into a Shapely shape
        feature_boundary = shape(geometry)
        # Now check for intersection
        if prepared_bbox.intersects(feature_boundary):
            matches.append(feature)

    return matches


def get_zip_feature_for_point(
    lat: float,
    lon: float,
    zip_polygons: list[GeoJSONFeature],
) -> GeoJSONFeature | None:
    """
    Find the ZIP code feature that contains the given point.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        zip_polygons: ZIP polygon features to search.

    Returns:
        The GeoJSON feature dict if found, else None.
    """
    point = Point(lon, lat)

    for feature in zip_polygons:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        feature_boundary = shape(geometry)
        if point.within(feature_boundary):
            return feature

    return None

def load_zip_place_crosswalk(
    csv_path: str | Path,
    state: str | None = "CA",
) -> dict[str, set[str]]:
    """
    Load a city-to-ZIP lookup from the HUD ZIP crosswalk CSV.

    Args:
        csv_path: Path to the HUD ZIP-COUNTY crosswalk CSV.
        state: Only include rows matching this USPS_ZIP_PREF_STATE (default "CA").
                Pass None to include all states.

    Returns:
        Dict mapping e.g. "SANTA MONICA" → {"90401", "90402", "90403", ...}.
    """
    mapping: dict[str, set[str]] = defaultdict(set)
    df = pd.read_csv(csv_path, dtype=str)
    for row in df.itertuples():
        # Skip rows that don't match the specified state (if given)
        if state and getattr(row, "USPS_ZIP_PREF_STATE", None) != state:
            continue
        city = (getattr(row, "USPS_ZIP_PREF_CITY", "") or "").strip().upper()
        zip_code = (getattr(row, "ZIP", "") or "").strip()
        if city and zip_code:
            mapping[city].add(zip_code)

    return dict(mapping)

def get_zip_features_for_place(
    place_name: str,
    zip_place_crosswalk: dict[str, set[str]],
    zip_polygons: list[GeoJSONFeature],
) -> list[GeoJSONFeature]:
    """
    Return all ZIP polygon features belonging to a place using the HUD crosswalk.

    Args:
        place_name: User-entered place name (e.g. "Santa Monica").
        zip_place_crosswalk: Mapping from uppercase city → set of ZIP strings.
        zip_polygons: List of GeoJSON feature dicts with a "ZIPCODE" property.

    Returns:
        List of matching GeoJSON feature dicts.
    """
    normalized = place_name.strip().upper()
    # Strip trailing state/country info like ", CA" or ", California"
    for suffix in [", CA", ", CALIFORNIA", ", LOS ANGELES", " CA"]:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()

    target_zips = zip_place_crosswalk.get(normalized)
    if not target_zips:
        return []

    features: list[GeoJSONFeature] = []
    for feature in zip_polygons:
        zip_code = feature.get("properties", {}).get("ZIPCODE", "")
        if zip_code in target_zips:
            features.append(feature)
    return features
