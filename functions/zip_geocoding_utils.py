from collections import defaultdict
from loguru import logger
from pathlib import Path
from shapely.geometry import Point, shape
from typing import Any, Callable, Sequence, TypeAlias, TypedDict
import bleach
import json
import pandas as pd
import re
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
_PLACE_CACHE_VERSION = "v5"
_DEFAULT_LOCATION_CONTEXT = "CA"
_SERVICE_AREA_COUNTY_PRIORITIES = {
    "los angeles": 0,
    "los angeles county": 0,
    "county of los angeles": 0,
    "orange county": 1,
    "county of orange": 1,
    "ventura county": 2,
    "county of ventura": 2,
    "san bernardino county": 3,
    "county of san bernardino": 3,
    "kern county": 4,
    "county of kern": 4,
}
_CALIFORNIA_BOUNDS = {
    "south": 32.4,
    "north": 42.1,
    "west": -124.6,
    "east": -114.0,
}


def _query_looks_like_street_address(query: str) -> bool:
    """Heuristically detect whether the user entered a street-style address.

    Args:
        query: Raw or normalized user-entered place text.

    Returns:
        `True` when the query looks like a street address with a number and
        street suffix, otherwise `False`.
    """
    lowered = str(query or "").strip().lower()
    if not lowered or not any(char.isdigit() for char in lowered):
        return False

    street_tokens = {
        "st",
        "street",
        "ave",
        "avenue",
        "blvd",
        "boulevard",
        "rd",
        "road",
        "dr",
        "drive",
        "ln",
        "lane",
        "way",
        "ct",
        "court",
        "pl",
        "place",
        "ter",
        "terrace",
        "pkwy",
        "parkway",
        "hwy",
        "highway",
    }
    tokens = {token.strip(",.#") for token in lowered.split()}
    return not street_tokens.isdisjoint(tokens)


def _query_has_location_context(query: str) -> bool:
    """Check whether a free-form query already includes a California/LA qualifier.

    Args:
        query: Raw or normalized user-entered place text.

    Returns:
        `True` when the query includes a state or Los Angeles qualifier.
    """
    lowered = str(query or "").strip().lower()
    if not lowered:
        return False
    if "california" in lowered or "los angeles" in lowered or "la county" in lowered:
        return True

    tokens = {
        token.strip(" ,.#")
        for token in lowered.replace(",", " ").split()
    }
    return "ca" in tokens


def _normalize_comparison_text(value: str) -> str:
    """Normalize place names for lightweight candidate comparisons.

    Args:
        value: Raw query or Nominatim-provided place text.

    Returns:
        Lowercase alphanumeric words joined by single spaces.
    """
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value).lower()).split())


def _query_place_name(query: str) -> str:
    """Extract the place-name portion of a free-form location query.

    Args:
        query: Raw or normalized user-entered place text.

    Returns:
        A comparison-ready place name with common location qualifiers removed.
    """
    name = str(query or "").strip()
    if "," in name:
        name = name.split(",", 1)[0]
    name = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", name)
    return _normalize_comparison_text(name)


def _query_requested_locality(query: str) -> str | None:
    """Extract an explicit city or neighborhood qualifier from an address.

    Args:
        query: User-entered place query being parsed or resolved.

    Returns:
        The query requested locality text, or ``None`` when unavailable.
    """
    if not _query_looks_like_street_address(query) or "," not in str(query):
        return None

    for raw_part in str(query).split(",")[1:]:
        locality = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", raw_part).strip()
        locality = re.sub(
            r"(?:^|\s)(?:ca|california|us|usa|united states)$",
            "",
            locality,
            flags=re.IGNORECASE,
        ).strip()
        if not locality:
            continue
        if re.match(
            r"^(?:(?:apt|apartment|unit|suite|ste|room|rm|floor|fl)\b|#)",
            locality,
            flags=re.IGNORECASE,
        ):
            continue

        normalized = _normalize_comparison_text(locality)
        if normalized.endswith(" county"):
            continue
        return normalized or None

    return None


def _normalize_locality_name(value: object) -> str:
    """Normalize Nominatim locality labels for exact comparisons.

    Args:
        value: Raw city or locality label returned by the geocoder.

    Returns:
        The normalized locality name text.
    """
    normalized = _normalize_comparison_text(str(value or ""))
    for prefix in ("city of ", "town of ", "village of "):
        if normalized.startswith(prefix):
            return normalized[len(prefix):]
    return normalized


def _candidate_matches_requested_locality(
    result: dict[str, Any],
    requested_locality: str,
) -> bool:
    """Check that a geocoder candidate contains the requested locality.

    Args:
        result: Geocoder candidate result whose locality should be validated.
        requested_locality: Normalized city or locality explicitly requested by the user.

    Returns:
        Whether the geocoder candidate matches the requested locality.
    """
    address = result.get("address")
    if isinstance(address, dict):
        locality_names = (
            address.get(key)
            for key in (
                "neighbourhood",
                "quarter",
                "suburb",
                "city_district",
                "city",
                "town",
                "village",
                "hamlet",
                "municipality",
            )
        )
        if any(
            _normalize_locality_name(name) == requested_locality
            for name in locality_names
            if name
        ):
            return True

    display_parts = str(result.get("display_name", "")).split(",")
    return any(
        _normalize_locality_name(part) == requested_locality
        for part in display_parts
        if part.strip()
    )


def _normalize_place_query(query: str) -> str:
    """Normalize a user-entered place query before sending it to Nominatim.

    Args:
        query: Raw place text entered by the user.

    Returns:
        The cleaned query string, with `, CA` appended when no California
        qualifier is already present.
    """
    normalized = " ".join(str(query).strip().split())
    if not normalized:
        return ""
    if not _query_has_location_context(normalized):
        normalized = f"{normalized}, {_DEFAULT_LOCATION_CONTEXT}"
    return normalized


def _coordinates_look_like_california(lat: float, lon: float) -> bool:
    """Check whether a latitude/longitude pair falls within a California bbox.

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
    """Decide whether a Nominatim candidate should be treated as a California hit.

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


def _service_area_priority(result: dict[str, Any]) -> int:
    """Rank candidates by this app's local service area.

    Args:
        result: Raw Nominatim response object for a single candidate.

    Returns:
        A lower number for LA County, then nearby Orange and Ventura counties;
        non-service-area California results are ranked last.
    """
    if not isinstance(result, dict):
        return len(_SERVICE_AREA_COUNTY_PRIORITIES)

    address = result.get("address")
    if isinstance(address, dict):
        county = _normalize_comparison_text(str(address.get("county", "")))
        city = str(address.get("city", "")).strip().lower()
        if county in _SERVICE_AREA_COUNTY_PRIORITIES:
            return _SERVICE_AREA_COUNTY_PRIORITIES[county]
        if city == "los angeles":
            return _SERVICE_AREA_COUNTY_PRIORITIES["los angeles county"]

    display_name = _normalize_comparison_text(str(result.get("display_name", "")))
    for county, priority in _SERVICE_AREA_COUNTY_PRIORITIES.items():
        if county in display_name:
            return priority

    return len(_SERVICE_AREA_COUNTY_PRIORITIES)


def _candidate_name_priority(result: dict[str, Any], query: str) -> int:
    """Rank how closely a candidate's place name matches the query name.

    Args:
        result: Raw Nominatim response object for a single candidate.
        query: User-entered place query.

    Returns:
        `0` for exact name matches, `1` for partial matches, and `2` otherwise.
    """
    query_name = _query_place_name(query)
    if not query_name:
        return 2

    candidate_names = [result.get("name")]
    address = result.get("address")
    if isinstance(address, dict):
        candidate_names.extend(
            address.get(key)
            for key in (
                "neighbourhood",
                "quarter",
                "suburb",
                "city",
                "town",
                "village",
                "county",
            )
        )

    normalized_names = [
        _normalize_comparison_text(str(name))
        for name in candidate_names
        if name
    ]
    if query_name in normalized_names:
        return 0
    if any(query_name in name or name in query_name for name in normalized_names):
        return 1
    return 2


def _candidate_sort_key(result: dict[str, Any], query: str) -> tuple[float, float, float, float, int]:
    """Rank California Nominatim candidates for the current place query.

    Args:
        result: Raw Nominatim response object for a single candidate.
        query: User-entered place query used to guide address-vs-POI ranking.

    Returns:
        A tuple where smaller values indicate a better candidate.
    """
    score = 0.0
    address = result.get("address")
    address_dict = address if isinstance(address, dict) else {}
    addresstype = str(result.get("addresstype", "")).strip().lower()
    category = str(result.get("class", "")).strip().lower()
    result_type = str(result.get("type", "")).strip().lower()
    display_name = str(result.get("display_name", "")).strip()
    service_area_priority = _service_area_priority(result)
    name_priority = _candidate_name_priority(result, query)

    if _query_looks_like_street_address(query):
        if address_dict.get("house_number"):
            score -= 50.0
        if addresstype in {"house", "building", "residential", "place"}:
            score -= 20.0
        if result_type in {"house", "residential", "apartments", "building"}:
            score -= 10.0
        if category in {"building", "place", "highway"}:
            score -= 5.0
        if category in {"shop", "amenity", "tourism", "leisure"}:
            score += 30.0
        if result.get("name"):
            score += 5.0

    try:
        importance = float(result.get("importance", 0.0))
    except (TypeError, ValueError):
        importance = 0.0

    if _query_looks_like_street_address(query):
        return (score, service_area_priority, name_priority, -importance, len(display_name))

    return (name_priority, service_area_priority, score, -importance, len(display_name))

def _load_place_cache(cache_path: Path) -> PlaceCache:
    """Load the on-disk place geocoding cache.

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
    """Persist the place geocoding cache to disk.

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
    """Sanitize free-form location text before geocoding.

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
    """Geocode a place name with Nominatim and a small local JSON cache.

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
    cache_key = f"{_PLACE_CACHE_VERSION}:{normalized.lower()}"
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

    california_results = [result for result in payload if _result_is_california_match(result)]
    if not california_results:
        candidate_labels = [result.get("display_name", "<unknown>") for result in payload[:3]]
        logger.warning(
            f"Rejecting Nominatim results for '{query}': no California match found in candidates {candidate_labels}"
        )
        return None

    requested_locality = _query_requested_locality(sanitized_query)
    if requested_locality:
        locality_results = [
            result
            for result in california_results
            if _candidate_matches_requested_locality(result, requested_locality)
        ]
        if not locality_results:
            candidate_labels = [
                result.get("display_name", "<unknown>")
                for result in california_results[:3]
            ]
            logger.warning(
                f"Rejecting Nominatim results for '{query}': no candidate "
                f"matched requested locality '{requested_locality}' in "
                f"{candidate_labels}"
            )
            return None
        california_results = locality_results

    selected_result = min(
        california_results,
        key=lambda result: _candidate_sort_key(result, sanitized_query or normalized),
    )

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
    """Load ZIP code polygons from a GeoJSON file.

    Args:
        geojson_path: Path to a GeoJSON file with a top-level FeatureCollection.

    Returns:
        A list of GeoJSON feature dicts (may be empty).
    """
    with open(geojson_path, "r", encoding="utf-8") as handle:
        geojson = json.load(handle)
    return geojson.get("features", [])


def get_zip_feature_for_point(
    lat: float,
    lon: float,
    zip_polygons: list[GeoJSONFeature],
) -> GeoJSONFeature | None:
    """Find the ZIP code feature that contains the given point.

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
    """Load a city-to-ZIP lookup from the HUD ZIP crosswalk CSV.

    Args:
        csv_path: Path to the HUD ZIP-COUNTY crosswalk CSV.
        state: Only include rows matching this USPS_ZIP_PREF_STATE (default "CA").
                Pass None to include all states.

    Returns:
        Dict mapping e.g. "SANTA MONICA" → {"90401", "90402", "90403", ...}.
    """
    mapping: dict[str, set[str]] = defaultdict(set)
    df = pd.read_csv(csv_path, dtype="str")
    for row in df.itertuples():
        # Skip rows that don't match the specified state (if given)
        if state and getattr(row, "USPS_ZIP_PREF_STATE", None) != state:
            continue
        raw_city = getattr(row, "USPS_ZIP_PREF_CITY", None)
        raw_zip_code = getattr(row, "ZIP", None)
        city = "" if pd.isna(raw_city) else str(raw_city).strip().upper()
        zip_code = (
            ""
            if pd.isna(raw_zip_code)
            else str(raw_zip_code).strip()
        )
        if city and zip_code:
            mapping[city].add(zip_code)

    return dict(mapping)


def get_zip_codes_for_place(
    place_name: str,
    zip_place_crosswalk: dict[str, set[str]],
) -> set[str]:
    """Return ZIP codes belonging to a place using the HUD crosswalk.

    Args:
        place_name: User-entered place name (e.g. "Santa Monica").
        zip_place_crosswalk: Mapping from uppercase city → set of ZIP strings.

    Returns:
        Set of matching ZIP code strings. Empty when the place is unknown.
    """
    normalized = place_name.strip().upper()
    # Strip trailing state/country info like ", CA" or ", California"
    for suffix in [", CA", ", CALIFORNIA", ", LOS ANGELES", " CA"]:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()

    return set(zip_place_crosswalk.get(normalized, set()))


def get_zip_features_for_place(
    place_name: str,
    zip_place_crosswalk: dict[str, set[str]],
    zip_polygons: list[GeoJSONFeature],
) -> list[GeoJSONFeature]:
    """Return all ZIP polygon features belonging to a place using the HUD crosswalk.

    Args:
        place_name: User-entered place name (e.g. "Santa Monica").
        zip_place_crosswalk: Mapping from uppercase city → set of ZIP strings.
        zip_polygons: List of GeoJSON feature dicts with a "ZIPCODE" property.

    Returns:
        List of matching GeoJSON feature dicts.
    """
    target_zips = get_zip_codes_for_place(place_name, zip_place_crosswalk)
    if not target_zips:
        return []

    features: list[GeoJSONFeature] = []
    for feature in zip_polygons:
        zip_code = feature.get("properties", {}).get("ZIPCODE", "")
        if zip_code in target_zips:
            features.append(feature)
    return features


def get_zip_features_by_code(
    zip_codes: Sequence[str] | set[str],
    zip_polygons: list[GeoJSONFeature],
) -> list[GeoJSONFeature]:
    """Return available ZIP polygon features for the requested ZIP codes.

    Args:
        zip_codes: ZIP codes whose GeoJSON features should be returned.
        zip_polygons: ZIP-code polygon features used for spatial matching.

    Returns:
        A list containing the requested ZIP features by code.
    """
    targets = {str(zip_code).strip() for zip_code in zip_codes if zip_code}
    if not targets:
        return []

    return [
        feature
        for feature in zip_polygons
        if str(feature.get("properties", {}).get("ZIPCODE") or "").strip()
        in targets
    ]


def get_adjacent_zip_features(
    base_features: Sequence[GeoJSONFeature],
    zip_polygons: list[GeoJSONFeature],
) -> list[GeoJSONFeature]:
    """Return one ring of ZIP polygons that touch any base ZIP polygon.

    Bounding boxes from a geocoder have different meanings for addresses,
    neighborhoods, cities, and postcodes. Polygon adjacency gives the nearby
    switch one consistent meaning after each input has resolved to base ZIPs.

    Args:
        base_features: Starting ZIP features whose immediate neighbors should be found.
        zip_polygons: ZIP-code polygon features used for spatial matching.

    Returns:
        A list containing the requested adjacent ZIP features.
    """
    base_zip_codes: set[str] = set()
    base_shapes = []
    for feature in base_features:
        zip_code = str(
            feature.get("properties", {}).get("ZIPCODE") or ""
        ).strip()
        geometry = feature.get("geometry")
        if not zip_code or not geometry or zip_code in base_zip_codes:
            continue
        base_zip_codes.add(zip_code)
        base_shapes.append(shape(geometry))

    if not base_shapes:
        return []

    adjacent: list[GeoJSONFeature] = []
    for feature in zip_polygons:
        zip_code = str(
            feature.get("properties", {}).get("ZIPCODE") or ""
        ).strip()
        geometry = feature.get("geometry")
        if not zip_code or not geometry or zip_code in base_zip_codes:
            continue
        candidate_shape = shape(geometry)
        if any(candidate_shape.touches(base_shape) for base_shape in base_shapes):
            adjacent.append(feature)

    return adjacent


def _explicit_zip_code(location: str) -> str | None:
    """Return a standalone ZIP, optionally qualified with a CA suffix.

    Args:
        location: Place, address, or geocoder result being resolved.

    Returns:
        The explicit ZIP code text, or ``None`` when unavailable.
    """
    match = re.fullmatch(
        r"(\d{5})(?:-\d{4})?(?:(?:\s*,\s*|\s+)(?:CA|California))?",
        str(location).strip(),
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def resolve_locations_to_zip_boundaries(
    locations: Sequence[str] | str | None,
    zip_place_crosswalk: dict[str, set[str]],
    zip_polygons: list[GeoJSONFeature],
    *,
    include_nearby: bool = False,
    geocode: Callable[[str], PlaceGeocodeResult | None] | None = None,
) -> tuple[dict[str, Any], str]:
    """Resolve one or more user-entered locations to a combined ZIP boundary.

    Each location is resolved independently so commas can remain part of a
    single value such as ``"Pasadena, CA"``. Matching ZIP codes and polygon
    features are combined with OR semantics and deduplicated by ZIP code.

    Args:
        locations: Location values from a tags input. A string is accepted for
            backwards compatibility and is treated as one complete location.
        zip_place_crosswalk: Mapping from uppercase city names to ZIP codes.
        zip_polygons: ZIP polygon features available to the listing filter.
        include_nearby: Whether to include one ring of ZIP polygons touching
            the ZIP polygons resolved from the supplied locations.
        geocode: Optional geocoder override, primarily for deterministic tests.

    Returns:
        A tuple containing the combined boundary-store payload and a status
        message suitable for display below the location control.
    """
    raw_locations = (
        [locations]
        if isinstance(locations, str)
        else list(locations or [])
    )
    cleaned_locations: list[str] = []
    seen_locations: set[str] = set()
    for raw_location in raw_locations:
        cleaned = sanitize_location_input(str(raw_location or ""))
        comparison_key = cleaned.casefold()
        if not cleaned or comparison_key in seen_locations:
            continue
        seen_locations.add(comparison_key)
        cleaned_locations.append(cleaned)

    if not cleaned_locations:
        return {"zip_codes": [], "features": [], "error": None}, ""

    geocode_location = geocode or geocode_place_cached
    zip_codes: set[str] = set()
    features_by_zip: dict[str, GeoJSONFeature] = {}
    base_features_by_zip: dict[str, GeoJSONFeature] = {}
    not_found: list[str] = []
    outside_service_area: list[str] = []

    def add_features(features: Sequence[GeoJSONFeature]) -> None:
        """Add features and their ZIP codes to the combined result.

        Args:
            features: GeoJSON features to merge into the resolved result set.

        Returns:
            None.
        """
        for feature in features:
            zip_code = str(
                feature.get("properties", {}).get("ZIPCODE") or ""
            ).strip()
            if not zip_code:
                continue
            zip_codes.add(zip_code)
            features_by_zip.setdefault(zip_code, feature)

    def add_base_features(features: Sequence[GeoJSONFeature]) -> None:
        """Add resolved base features and retain them for nearby expansion.

        Args:
            features: GeoJSON features to merge into the resolved result set.

        Returns:
            None.
        """
        add_features(features)
        for feature in features:
            zip_code = str(
                feature.get("properties", {}).get("ZIPCODE") or ""
            ).strip()
            if zip_code:
                base_features_by_zip.setdefault(zip_code, feature)

    known_crosswalk_zips = {
        str(zip_code).strip()
        for place_zips in zip_place_crosswalk.values()
        for zip_code in place_zips
        if zip_code
    }

    for location in cleaned_locations:
        crosswalk_zips = get_zip_codes_for_place(location, zip_place_crosswalk)
        if crosswalk_zips:
            zip_codes.update(zip_code for zip_code in crosswalk_zips if zip_code)
            add_base_features(
                get_zip_features_for_place(
                    location,
                    zip_place_crosswalk,
                    zip_polygons,
                )
            )
            continue

        explicit_zip = _explicit_zip_code(location)
        explicit_features = get_zip_features_by_code(
            [explicit_zip] if explicit_zip else [],
            zip_polygons,
        )
        if explicit_zip and (
            explicit_features or explicit_zip in known_crosswalk_zips
        ):
            zip_codes.add(explicit_zip)
            add_base_features(explicit_features)
            continue

        geocoded = geocode_location(location)
        if not geocoded:
            not_found.append(location)
            continue

        location_features: list[GeoJSONFeature] = []
        point_feature = get_zip_feature_for_point(
            geocoded["lat"],
            geocoded["lon"],
            zip_polygons,
        )
        if point_feature:
            location_features.append(point_feature)

        if not location_features:
            outside_service_area.append(location)
            continue

        add_base_features(location_features)

    if include_nearby:
        add_features(
            get_adjacent_zip_features(
                list(base_features_by_zip.values()),
                zip_polygons,
            )
        )

    sorted_zip_codes = sorted(zip_codes)
    status_parts: list[str] = []
    if sorted_zip_codes:
        label = ", ".join(sorted_zip_codes[:5])
        if len(sorted_zip_codes) > 5:
            label = f"{label} +{len(sorted_zip_codes) - 5} more"
        status_parts.append(f"Filtering by ZIP codes: {label}.")

    if not_found:
        if len(not_found) == 1:
            status_parts.append(
                f"Could not find a California location matching '{not_found[0]}'."
            )
        else:
            labels = ", ".join(f"'{location}'" for location in not_found)
            status_parts.append(
                f"Could not find California locations matching: {labels}."
            )

    if outside_service_area:
        if len(outside_service_area) == 1 and not sorted_zip_codes:
            status_parts.append(
                "No ZIP code boundaries found for the specified location."
            )
        else:
            labels = ", ".join(
                f"'{location}'" for location in outside_service_area
            )
            status_parts.append(f"No ZIP code boundaries found for: {labels}.")

    error: str | None = None
    if not sorted_zip_codes:
        error = "place_outside" if outside_service_area else "place_not_found"

    return (
        {
            "zip_codes": sorted_zip_codes,
            "features": list(features_by_zip.values()),
            "error": error,
        },
        " ".join(status_parts),
    )
