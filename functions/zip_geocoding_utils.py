from loguru import logger
from pathlib import Path
from shapely.geometry import Point, shape, box
from shapely.prepared import prep
from typing import Dict, List, Any, Sequence
import json
import requests

_DEFAULT_PLACE_CACHE_PATH = Path("/mnt/cache/location/place_geocode_cache.json")
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def _normalize_place_query(query: str) -> str:
    normalized = " ".join(str(query).strip().split())
    if not normalized:
        return ""
    lowered = normalized.lower()
    if "los angeles" not in lowered and "ca" not in lowered and "california" not in lowered:
        normalized = f"{normalized}, CA"
    return normalized


def _load_place_cache(cache_path: Path) -> Dict[str, Dict[str, Any]]:
    if not cache_path.exists():
        return {}
    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed reading place cache %s: %s", cache_path, exc)
        return {}


def _save_place_cache(cache_path: Path, cache: Dict[str, Dict[str, Any]]) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle)
    except Exception as exc:
        logger.warning("Failed writing place cache %s: %s", cache_path, exc)


def geocode_place_cached(query: str, cache_path: Path | None = None) -> Dict[str, Any] | None:
    """
    Geocode a place name using Nominatim with a local on-disk cache.

    Returns:
        Dict with "lat" and "lon" floats on success, or None.
    """
    normalized = _normalize_place_query(query)
    if not normalized:
        return None

    cache_file = cache_path or _DEFAULT_PLACE_CACHE_PATH
    cache = _load_place_cache(cache_file)
    cache_key = normalized.lower()
    if cache_key in cache:
        return cache[cache_key]

    params = {
        "format": "json",
        "q": normalized,
        "limit": 1,
        "countrycodes": "us",
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
        logger.warning("Geocoding failed for %s: %s", normalized, exc)
        return None

    if not payload:
        return None

    logger.debug(f"Nominatim response for '{query}': {payload}")

    lat = float(payload[0].get("lat", None))
    lon = float(payload[0].get("lon", None))

    # Get the bounding box if available and convert it to a list of floats
    bbox = [float(coords) for coords in (payload[0].get("boundingbox", None))]

    result = {"lat": lat, "lon": lon, "query": normalized, "bbox": bbox}
    cache[cache_key] = result
    _save_place_cache(cache_file, cache)
    logger.debug(f"Geocoded place '{query}' to {result}")
    return result

def load_zip_polygons(geojson_path: str | Path) -> List[Dict[str, Any]]:
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
    zip_polygons: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Return ZIP polygon features that intersect a Nominatim bounding box.

    Args:
        nominatim_bbox: Nominatim bbox as [south, north, west, east] floats.
        zip_polygons: List of GeoJSON feature dicts (Polygon/MultiPolygon).

    Returns:
        A list of feature dicts that intersect the bbox.
    """
    # Initalize an empty list to hold matching features
    matches = []
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

def get_zip_feature_for_point(lat: float, lon: float, zip_polygons: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """
    Find the ZIP code feature that contains the given point.

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