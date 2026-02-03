from typing import Dict, List, Any
from functools import lru_cache
from pathlib import Path
import json
import logging
import re
import requests
from shapely.geometry import Point, shape, box
from shapely.prepared import prep

logger = logging.getLogger(__name__)

_ZIP_RE = re.compile(r"^\d{5}$")
_DEFAULT_ZIP_GEOJSON_PATH = Path("assets/datasets/la_county_zip_codes.geojson")
_DEFAULT_PLACE_CACHE_PATH = Path("/mnt/cache/location/place_geocode_cache.json")
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def _normalize_place_query(query: str) -> str:
    normalized = " ".join(str(query).strip().split())
    if not normalized:
        return ""
    lowered = normalized.lower()
    if "los angeles" not in lowered and "ca" not in lowered and "california" not in lowered:
        normalized = f"{normalized}, Los Angeles, CA"
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

    item = payload[0]
    try:
        lat = float(item.get("lat"))
        lon = float(item.get("lon"))
    except (TypeError, ValueError):
        return None

    bbox_raw = item.get("boundingbox")
    bbox = None
    if isinstance(bbox_raw, (list, tuple)) and len(bbox_raw) == 4:
        try:
            bbox = [float(x) for x in bbox_raw]
        except (TypeError, ValueError):
            bbox = None

    result = {"lat": lat, "lon": lon, "query": normalized, "bbox": bbox}
    cache[cache_key] = result
    _save_place_cache(cache_file, cache)
    return result


@lru_cache(maxsize=4)
def _load_zip_boundaries(file_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Load LA County ZIP boundaries from a local GeoJSON file.

    Returns:
        Dict mapping ZIP code strings to GeoJSON Features.
    """
    path = Path(file_path)
    if not path.exists():
        logger.warning("ZIP boundary file not found: %s", path)
        return {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        logger.warning("Failed reading ZIP boundary file %s: %s", path, exc)
        return {}

    features = data.get("features", [])
    lookup: Dict[str, Dict[str, Any]] = {}
    for feature in features:
        props = feature.get("properties") or {}
        raw_zip = props.get("ZIPCODE")
        if raw_zip is None:
            continue
        zip_code = str(raw_zip).strip().zfill(5)
        if not _ZIP_RE.fullmatch(zip_code):
            continue
        geometry = feature.get("geometry")
        if not geometry:
            continue
        lookup[zip_code] = {
            "type": "Feature",
            "properties": {"zip_code": zip_code},
            "geometry": geometry,
        }

    return lookup


@lru_cache(maxsize=4)
def _load_zip_shapes(file_path: str) -> List[tuple[str, Any]]:
    path = Path(file_path)
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        logger.warning("Failed reading ZIP geometry %s: %s", path, exc)
        return []

    results: List[tuple[str, Any]] = []
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        raw_zip = props.get("ZIPCODE")
        if raw_zip is None:
            continue
        zip_code = str(raw_zip).strip().zfill(5)
        if not _ZIP_RE.fullmatch(zip_code):
            continue
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            polygon = prep(shape(geometry))
        except Exception:
            continue
        results.append((zip_code, polygon))

    return results


@lru_cache(maxsize=4)
def _load_zip_polygons(file_path: str) -> List[tuple[str, Any]]:
    path = Path(file_path)
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        logger.warning("Failed reading ZIP geometry %s: %s", path, exc)
        return []

    results: List[tuple[str, Any]] = []
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        raw_zip = props.get("ZIPCODE")
        if raw_zip is None:
            continue
        zip_code = str(raw_zip).strip().zfill(5)
        if not _ZIP_RE.fullmatch(zip_code):
            continue
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            polygon = shape(geometry)
        except Exception:
            continue
        results.append((zip_code, polygon))

    return results


def find_zip_features_for_bounds(
    bounds: List[float],
    file_path: str | None = None,
) -> List[Dict[str, Any]]:
    if not bounds or len(bounds) != 4:
        return []

    path = file_path or str(_DEFAULT_ZIP_GEOJSON_PATH)
    lookup = _load_zip_boundaries(path)

    try:
        south, north, west, east = [float(v) for v in bounds]
    except (TypeError, ValueError):
        return []

    bbox_polygon = box(west, south, east, north)
    matches: List[Dict[str, Any]] = []
    for zip_code, polygon in _load_zip_polygons(path):
        try:
            if polygon.intersects(bbox_polygon):
                feature = lookup.get(zip_code)
                if feature:
                    matches.append(feature)
        except Exception:
            continue

    return matches


def find_zip_for_point(lat: float, lon: float, file_path: str | None = None) -> str | None:
    path = file_path or str(_DEFAULT_ZIP_GEOJSON_PATH)
    shapes = _load_zip_shapes(path)
    point = Point(lon, lat)
    for zip_code, polygon in shapes:
        if polygon.contains(point):
            return zip_code
    return None


@lru_cache(maxsize=512)
def fetch_zip_boundary_feature(zip_code: str, file_path: str | None = None) -> Dict[str, Any] | None:
    """
    Fetch a LA County ZIP polygon from a local GeoJSON file.

    Args:
        zip_code: 5-digit ZIP code.
        file_path: Optional file path to the local ZIP GeoJSON.

    Returns:
        GeoJSON Feature dict or None when not found/invalid.
    """
    if not zip_code:
        return None

    zip_code = str(zip_code).strip()
    if not _ZIP_RE.fullmatch(zip_code):
        return None

    path = file_path or str(_DEFAULT_ZIP_GEOJSON_PATH)
    lookup = _load_zip_boundaries(path)
    return lookup.get(zip_code)