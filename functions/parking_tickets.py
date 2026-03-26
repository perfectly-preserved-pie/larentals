from dotenv import find_dotenv, load_dotenv
from datetime import date, datetime, timedelta, timezone
from loguru import logger
from pathlib import Path
from typing import Any, TypeAlias, TypedDict
import gzip
import math
import os
import orjson
import re
import requests
import time

load_dotenv(find_dotenv(), override=False)

PARKING_TICKETS_DATASET_URL = "https://data.lacity.org/resource/4f5p-udkv.json"
PARKING_TICKETS_V3_QUERY_URL = "https://data.lacity.org/api/v3/views/4f5p-udkv/query.json"
PARKING_TICKETS_DATASET_YEAR = 2025
PARKING_TICKETS_WINDOW_START = date(PARKING_TICKETS_DATASET_YEAR, 1, 1)
PARKING_TICKETS_WINDOW_END = date(PARKING_TICKETS_DATASET_YEAR, 12, 31)
PARKING_TICKETS_SPOT_DECIMALS = 4
PARKING_TICKETS_MAX_HEAT_POINTS = 50000
PARKING_TICKETS_MAX_MARKER_POINTS = 8000
PARKING_TICKETS_HEAT_INTENSITY_FLOOR = 0.14
PARKING_TICKETS_MARKER_ZOOM_MIN = 15
PARKING_TICKETS_HEAT_ZOOM_MAX = 16
PARKING_TICKETS_MARKER_MERGE_DISTANCE_METERS = 40.0
PARKING_TICKETS_REQUEST_TIMEOUT_SECONDS = 45
PARKING_TICKETS_ARTIFACT_VERSION = 4
MAX_REASONABLE_FINE_AMOUNT = 2500.0
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARKING_TICKETS_LOCAL_ARTIFACT_PATH = (
    PROJECT_ROOT / "assets" / "datasets" / f"parking_tickets_heatmap_{PARKING_TICKETS_DATASET_YEAR}.json.gz"
)
LA_CITY_COORDINATE_BOUNDS = {
    "min_lat": 33.70,
    "max_lat": 34.35,
    "min_lon": -118.70,
    "max_lon": -118.10,
}
_SOCRATA_SESSION = requests.Session()
SOCRATA_V3_MAX_ACCEPTED_RETRIES = 5
_MISSING_SOCRATA_TOKEN_WARNING_EMITTED = False
_LOCATION_SUFFIX_NORMALIZATION = {
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

JsonDict: TypeAlias = dict[str, Any]


class ParkingHeatPoint(TypedDict):
    """Weighted parking hotspot used to build the client-side heat surface."""

    lat: float
    lon: float
    citation_count: int
    total_fine_amount: float
    intensity: float


class ParkingLayerMetadata(TypedDict):
    """Metadata attached to the derived parking heatmap payload."""

    window_start: str
    window_end: str
    dataset_year: int
    spot_decimals: int
    heat_point_count: int
    marker_point_count: int
    max_citation_count: int
    heat_max_intensity: float
    data_source: str
    generated_at: str
    artifact_version: int


GeoJsonDict: TypeAlias = dict[str, Any]
HeatPointTuple: TypeAlias = list[float]
MarkerPointTuple: TypeAlias = list[float | int | str]


class ParkingMarkerPoint(TypedDict):
    """Rich parking hotspot used for zoomed-in point rendering."""

    lat: float
    lon: float
    citation_count: int
    total_fine_amount: float
    average_fine_amount: float
    location: str
    merged_geocode_count: int


def _generated_timestamp() -> str:
    """
    Return an RFC 3339-like UTC timestamp for payload metadata.

    Returns:
        Timestamp string such as `2026-03-25T20:15:42Z`.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_valid_parking_heat_geojson(payload: Any) -> bool:
    """
    Check whether a decoded object looks like the expected parking layer payload.

    Args:
        payload: Decoded JSON object loaded from disk or built in memory.

    Returns:
        `True` when the payload is a GeoJSON `FeatureCollection` with a `features`
        list, otherwise `False`.
    """
    return (
        isinstance(payload, dict)
        and payload.get("type") == "FeatureCollection"
        and isinstance(payload.get("features"), list)
    )


def load_local_parking_tickets_heat_geojson() -> GeoJsonDict | None:
    """
    Load the precomputed local 2025 parking heatmap artifact when present.

    Returns:
        Parsed GeoJSON payload from `assets/datasets/parking_tickets_heatmap_2025.json.gz`,
        or `None` when the artifact is missing or invalid.
    """
    artifact_path = PARKING_TICKETS_LOCAL_ARTIFACT_PATH
    if not artifact_path.exists():
        return None

    try:
        with gzip.open(artifact_path, "rb") as artifact_file:
            payload = orjson.loads(artifact_file.read())
    except OSError as exc:
        logger.warning("Failed reading parking tickets artifact from {}: {}", artifact_path, exc)
        return None
    except orjson.JSONDecodeError as exc:
        logger.warning("Failed decoding parking tickets artifact at {}: {}", artifact_path, exc)
        return None

    if not _is_valid_parking_heat_geojson(payload):
        logger.warning("Parking tickets artifact at {} is not a valid GeoJSON FeatureCollection.", artifact_path)
        return None

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        metadata["data_source"] = "local_artifact"
        metadata.setdefault("artifact_version", PARKING_TICKETS_ARTIFACT_VERSION)

    logger.info("Loaded parking tickets heatmap artifact from {}.", artifact_path)
    return payload


def write_local_parking_tickets_heat_geojson(
    payload: GeoJsonDict,
    output_path: Path | None = None,
) -> Path:
    """
    Persist a derived parking heatmap payload to the local datasets folder.

    Args:
        payload: GeoJSON `FeatureCollection` to save as a gzipped JSON artifact.
        output_path: Optional artifact destination. Defaults to the canonical
            `assets/datasets/parking_tickets_heatmap_2025.json.gz` path.

    Returns:
        Absolute path to the saved artifact file.

    Raises:
        ValueError: If `payload` is not a valid parking heatmap `FeatureCollection`.
    """
    if not _is_valid_parking_heat_geojson(payload):
        raise ValueError("Parking tickets artifact payload must be a GeoJSON FeatureCollection.")

    artifact_path = (output_path or PARKING_TICKETS_LOCAL_ARTIFACT_PATH).resolve()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(artifact_path, "wb") as artifact_file:
        artifact_file.write(orjson.dumps(payload))

    logger.info("Wrote parking tickets heatmap artifact to {}.", artifact_path)
    return artifact_path


def _pick_quantile_threshold(values: list[int], fraction: float) -> int:
    """
    Return a stable integer quantile threshold from a sorted integer distribution.

    Args:
        values: Sorted positive integer values.
        fraction: Quantile fraction in the inclusive `(0, 1]` range.

    Returns:
        Integer threshold value for the requested quantile.
    """
    if not values:
        return 0
    if len(values) == 1:
        return int(values[0])

    index = min(len(values) - 1, max(0, math.ceil(fraction * len(values)) - 1))
    return int(values[index])


def _format_socrata_day(value: date) -> str:
    """
    Return a start-of-day timestamp string accepted by the Socrata API.

    Args:
        value: Calendar date to convert into a midnight timestamp string.

    Returns:
        Timestamp string in `YYYY-MM-DDT00:00:00` form for use in SoQL filters.
    """
    return f"{value.isoformat()}T00:00:00"


def _parse_socrata_date(value: str | None) -> date | None:
    """
    Parse a Socrata calendar-date string into a Python `date`.

    Args:
        value: Raw Socrata date string, usually in ISO-like timestamp form.

    Returns:
        Parsed `date` object, or `None` when the source value is blank or malformed.
    """
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        logger.warning("Failed parsing Socrata date value: {}", value)
        return None


def _build_valid_coordinate_where_clause() -> str:
    """
    Return the shared coordinate and data-quality filters for parking citations.

    Returns:
        SoQL boolean expression that excludes blank dates, missing coordinates,
        zero coordinates, and points outside the coarse Los Angeles City bounds.
    """
    return (
        "issue_date IS NOT NULL "
        "AND loc_lat IS NOT NULL AND loc_long IS NOT NULL "
        f"AND loc_lat != 0 AND loc_long != 0 "
        f"AND loc_lat >= {LA_CITY_COORDINATE_BOUNDS['min_lat']} "
        f"AND loc_lat <= {LA_CITY_COORDINATE_BOUNDS['max_lat']} "
        f"AND loc_long >= {LA_CITY_COORDINATE_BOUNDS['min_lon']} "
        f"AND loc_long <= {LA_CITY_COORDINATE_BOUNDS['max_lon']}"
    )


def _get_socrata_app_token() -> str | None:
    """
    Return the configured Socrata app token from `.env` or the environment.

    Returns:
        Trimmed token string when `SOCRATA_APP_TOKEN` is configured, otherwise `None`.
    """
    token = os.getenv("SOCRATA_APP_TOKEN")
    if not token:
        return None
    token = token.strip()
    return token or None


def _build_socrata_headers() -> dict[str, str]:
    """
    Build headers for Socrata requests, including an optional app token.

    Returns:
        Header mapping containing the app's user agent, JSON accept header, and
        `X-App-Token` when a Socrata token is configured.
    """
    headers = {
        "User-Agent": "WhereToLive.LA/1.0",
        "Accept": "application/json",
    }
    app_token = _get_socrata_app_token()
    if app_token:
        headers["X-App-Token"] = app_token
    return headers


def _coerce_socrata_payload_rows(payload: Any) -> list[JsonDict]:
    """
    Normalize Socrata response payloads into a list of row dictionaries.

    SODA 2.1 query responses are plain JSON arrays. The SODA 3 query endpoint is
    also documented as JSON, but this helper stays defensive in case the domain
    returns an object wrapper around the actual rows.

    Args:
        payload: Decoded JSON payload returned from a Socrata endpoint.

    Returns:
        Row list suitable for downstream typed coercion.

    Raises:
        ValueError: If the payload shape does not contain a row list.
    """
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("data", "results", "rows"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows

    raise ValueError("Unexpected Socrata response payload; expected a list of rows.")


def _request_socrata_rows_v3(
    *,
    query: str,
    page_number: int = 1,
    page_size: int = 50000,
) -> list[dict[str, Any]]:
    """
    Fetch rows from the Socrata v3 query endpoint.

    Args:
        query: SoQL query string to execute against the v3 endpoint.
        page_number: One-based page number for v3 pagination.
        page_size: Number of rows to request for the page.

    Returns:
        Row list returned by the v3 query endpoint.

    Raises:
        ValueError: If no `SOCRATA_APP_TOKEN` is configured.
        requests.HTTPError: If the Socrata endpoint returns a non-success status.
        TimeoutError: If the v3 async query never settles within the retry budget.
    """
    headers = _build_socrata_headers()
    if "X-App-Token" not in headers:
        raise ValueError(
            "Socrata v3 queries require an application token. Set SOCRATA_APP_TOKEN in the environment or .env."
        )

    body = {
        "query": query,
        "page": {
            "pageNumber": page_number,
            "pageSize": page_size,
        },
        "includeSynthetic": False,
    }

    for attempt in range(SOCRATA_V3_MAX_ACCEPTED_RETRIES + 1):
        response = _SOCRATA_SESSION.post(
            PARKING_TICKETS_V3_QUERY_URL,
            json=body,
            timeout=PARKING_TICKETS_REQUEST_TIMEOUT_SECONDS,
            headers={
                **headers,
                "Content-Type": "application/json",
            },
        )

        if response.status_code == 202 and attempt < SOCRATA_V3_MAX_ACCEPTED_RETRIES:
            retry_after_header = response.headers.get("Retry-After")
            try:
                retry_after_seconds = float(retry_after_header) if retry_after_header else (attempt + 1)
            except ValueError:
                retry_after_seconds = float(attempt + 1)
            time.sleep(max(0.5, retry_after_seconds))
            continue

        response.raise_for_status()
        return _coerce_socrata_payload_rows(response.json())

    raise TimeoutError("Socrata v3 query did not finish before the retry budget was exhausted.")


def _request_socrata_rows(params: dict[str, Any]) -> list[JsonDict]:
    """
    Fetch rows from the city Socrata SODA 2.1 endpoint with a stable app user-agent.

    This remains as a compatibility fallback when no app token is configured for
    the v3 API yet.

    Args:
        params: Query-string parameters to send to the public SODA 2.1 endpoint.

    Returns:
        Row list decoded from the response payload.

    Raises:
        requests.HTTPError: If the SODA 2.1 endpoint returns a non-success status.
    """
    response = _SOCRATA_SESSION.get(
        PARKING_TICKETS_DATASET_URL,
        params=params,
        timeout=PARKING_TICKETS_REQUEST_TIMEOUT_SECONDS,
        headers=_build_socrata_headers(),
    )
    response.raise_for_status()
    return _coerce_socrata_payload_rows(response.json())


def _request_parking_ticket_rows(
    *,
    v3_query: str,
    page_number: int = 1,
    page_size: int = 50000,
    legacy_params: dict[str, Any],
) -> list[JsonDict]:
    """
    Request parking-ticket rows, preferring Socrata v3 when a token is present.

    The user explicitly requested the v3 API, but the workspace may not have a
    token configured yet. In that case, we preserve a working lazy layer by
    falling back to the older public endpoint while logging a clear warning.

    Args:
        v3_query: SoQL query string for the Socrata v3 query endpoint.
        page_number: One-based page number to request.
        page_size: Maximum number of rows to request per page.
        legacy_params: SODA 2.1 query-string parameters used as a fallback.

    Returns:
        Row list from whichever Socrata endpoint is available.
    """
    global _MISSING_SOCRATA_TOKEN_WARNING_EMITTED

    if _get_socrata_app_token():
        return _request_socrata_rows_v3(
            query=v3_query,
            page_number=page_number,
            page_size=page_size,
        )

    if not _MISSING_SOCRATA_TOKEN_WARNING_EMITTED:
        logger.warning(
            "No Socrata app token found; parking tickets layer is falling back to the legacy public endpoint. "
            "Set SOCRATA_APP_TOKEN in the environment or .env to enable the v3 API."
        )
        _MISSING_SOCRATA_TOKEN_WARNING_EMITTED = True

    return _request_socrata_rows(legacy_params)


def _fetch_grouped_parking_ticket_rows(window_start: date, window_end: date) -> list[JsonDict]:
    """
    Fetch grouped parking hotspots for a recent window from the city dataset.

    The heat layer wants many individual hotspots, not a handful of coarse
    kilometer-wide buckets. We therefore aggregate at a much finer coordinate
    precision and keep only the highest-volume spots, similar to the reference
    map's "top 50,000 ticketed spots" framing.

    Args:
        window_start: Inclusive start date for the citation window.
        window_end: Inclusive end date for the citation window.

    Returns:
        Row list containing grouped hotspot buckets ordered by descending volume.
    """
    valid_where = _build_valid_coordinate_where_clause()
    where_clause = (
        f"{valid_where} "
        f"AND issue_date >= '{_format_socrata_day(window_start)}' "
        f"AND issue_date < '{_format_socrata_day(window_end + timedelta(days=1))}'"
    )

    all_rows: list[dict[str, Any]] = []
    page_size = 50000
    page_number = 1

    while len(all_rows) < PARKING_TICKETS_MAX_HEAT_POINTS:
        remaining_rows = PARKING_TICKETS_MAX_HEAT_POINTS - len(all_rows)
        requested_page_size = min(page_size, remaining_rows)
        rows = _request_parking_ticket_rows(
            v3_query=(
                f"SELECT round(`loc_lat`, {PARKING_TICKETS_SPOT_DECIMALS}) AS `lat_bin`, "
                f"round(`loc_long`, {PARKING_TICKETS_SPOT_DECIMALS}) AS `lon_bin`, "
                "count(*) AS `citation_count`, "
                "sum(`fine_amount`) AS `total_fine_amount` "
                f"WHERE {where_clause} "
                "GROUP BY `lat_bin`, `lon_bin` "
                "ORDER BY `citation_count` DESC, `lat_bin` ASC, `lon_bin` ASC"
            ),
            page_number=page_number,
            page_size=requested_page_size,
            legacy_params={
                "$select": (
                    f"round(loc_lat, {PARKING_TICKETS_SPOT_DECIMALS}) AS lat_bin, "
                    f"round(loc_long, {PARKING_TICKETS_SPOT_DECIMALS}) AS lon_bin, "
                    "count(*) AS citation_count, "
                    "sum(fine_amount) AS total_fine_amount"
                ),
                "$where": where_clause,
                "$group": "lat_bin, lon_bin",
                "$order": "citation_count DESC, lat_bin ASC, lon_bin ASC",
                "$limit": requested_page_size,
                "$offset": (page_number - 1) * page_size,
            },
        )
        if not rows:
            break

        all_rows.extend(rows)
        if len(rows) < requested_page_size:
            break
        page_number += 1

    return all_rows[:PARKING_TICKETS_MAX_HEAT_POINTS]


def _fetch_grouped_marker_rows(window_start: date, window_end: date) -> list[JsonDict]:
    """
    Fetch grouped parking hotspots for zoomed-in marker rendering.

    These rows keep the human-readable `location` string and the source point
    coordinates used by the Socrata `geocodelocation` field so close-up markers
    can sit on the original geocoded point instead of a rounded heatmap bin.
    We still aggregate server-side before sending the marker payload to the
    browser.

    Args:
        window_start: Inclusive start date for the citation window.
        window_end: Inclusive end date for the citation window.

    Returns:
        Row list containing grouped hotspot markers ordered by descending volume.
    """
    valid_where = _build_valid_coordinate_where_clause()
    where_clause = (
        f"{valid_where} "
        "AND location IS NOT NULL "
        "AND location != '' "
        f"AND issue_date >= '{_format_socrata_day(window_start)}' "
        f"AND issue_date < '{_format_socrata_day(window_end + timedelta(days=1))}'"
    )

    all_rows: list[dict[str, Any]] = []
    page_size = 50000
    page_number = 1

    while len(all_rows) < PARKING_TICKETS_MAX_MARKER_POINTS:
        remaining_rows = PARKING_TICKETS_MAX_MARKER_POINTS - len(all_rows)
        requested_page_size = min(page_size, remaining_rows)
        rows = _request_parking_ticket_rows(
            v3_query=(
                "SELECT `loc_lat` AS `lat_point`, "
                "`loc_long` AS `lon_point`, "
                "`location`, "
                "count(*) AS `citation_count`, "
                "sum(`fine_amount`) AS `total_fine_amount` "
                f"WHERE {where_clause} "
                "GROUP BY `lat_point`, `lon_point`, `location` "
                "ORDER BY `citation_count` DESC, `lat_point` ASC, `lon_point` ASC"
            ),
            page_number=page_number,
            page_size=requested_page_size,
            legacy_params={
                "$select": (
                    "loc_lat AS lat_point, "
                    "loc_long AS lon_point, "
                    "location, "
                    "count(*) AS citation_count, "
                    "sum(fine_amount) AS total_fine_amount"
                ),
                "$where": where_clause,
                "$group": "lat_point, lon_point, location",
                "$order": "citation_count DESC, lat_point ASC, lon_point ASC",
                "$limit": requested_page_size,
                "$offset": (page_number - 1) * page_size,
            },
        )
        if not rows:
            break

        all_rows.extend(rows)
        if len(rows) < requested_page_size:
            break
        page_number += 1

    return all_rows[:PARKING_TICKETS_MAX_MARKER_POINTS]


def _coerce_grouped_heat_rows(grouped_rows: list[JsonDict]) -> list[ParkingHeatPoint]:
    """
    Validate and normalize grouped hotspot rows returned from the city API.

    Args:
        grouped_rows: Raw grouped row payload emitted by the selected Socrata endpoint.

    Returns:
        Normalized hotspot rows with validated coordinates, counts, and total fines.
        The returned intensity is a placeholder and is filled in downstream.
    """
    normalized_rows: list[ParkingHeatPoint] = []

    for row in grouped_rows:
        try:
            lat = float(row["lat_bin"])
            lon = float(row["lon_bin"])
            citation_count = int(row["citation_count"])
        except (KeyError, TypeError, ValueError):
            continue

        if not math.isfinite(lat) or not math.isfinite(lon):
            continue
        if not (
            LA_CITY_COORDINATE_BOUNDS["min_lat"] <= lat <= LA_CITY_COORDINATE_BOUNDS["max_lat"]
            and LA_CITY_COORDINATE_BOUNDS["min_lon"] <= lon <= LA_CITY_COORDINATE_BOUNDS["max_lon"]
        ):
            continue
        if citation_count <= 0:
            continue

        raw_total_fine_amount = row.get("total_fine_amount")
        try:
            total_fine_amount = (
                float(raw_total_fine_amount) if raw_total_fine_amount not in (None, "") else 0.0
            )
        except (TypeError, ValueError):
            total_fine_amount = 0.0

        if not math.isfinite(total_fine_amount):
            total_fine_amount = 0.0
        if total_fine_amount < 0 or total_fine_amount > (citation_count * MAX_REASONABLE_FINE_AMOUNT):
            continue

        normalized_rows.append(
            {
                "lat": lat,
                "lon": lon,
                "citation_count": citation_count,
                "total_fine_amount": total_fine_amount,
                "intensity": 0.0,
            }
        )

    return normalized_rows


def _coerce_grouped_marker_rows(grouped_rows: list[JsonDict]) -> list[ParkingMarkerPoint]:
    """
    Validate and normalize grouped hotspot rows used for zoomed-in markers.

    Args:
        grouped_rows: Raw grouped marker payload emitted by the Socrata endpoint.

    Returns:
        Normalized marker rows with popup-ready values.
    """
    normalized_rows: list[ParkingMarkerPoint] = []

    for row in grouped_rows:
        lat_value = row.get("lat_point", row.get("lat_bin"))
        lon_value = row.get("lon_point", row.get("lon_bin"))

        try:
            lat = float(lat_value)
            lon = float(lon_value)
            citation_count = int(row["citation_count"])
        except (KeyError, TypeError, ValueError):
            continue

        location = str(row.get("location") or "").strip()
        if not location:
            continue
        if not math.isfinite(lat) or not math.isfinite(lon):
            continue
        if not (
            LA_CITY_COORDINATE_BOUNDS["min_lat"] <= lat <= LA_CITY_COORDINATE_BOUNDS["max_lat"]
            and LA_CITY_COORDINATE_BOUNDS["min_lon"] <= lon <= LA_CITY_COORDINATE_BOUNDS["max_lon"]
        ):
            continue
        if citation_count <= 0:
            continue

        raw_total_fine_amount = row.get("total_fine_amount")
        try:
            total_fine_amount = (
                float(raw_total_fine_amount) if raw_total_fine_amount not in (None, "") else 0.0
            )
        except (TypeError, ValueError):
            total_fine_amount = 0.0

        if not math.isfinite(total_fine_amount):
            total_fine_amount = 0.0
        if total_fine_amount < 0 or total_fine_amount > (citation_count * MAX_REASONABLE_FINE_AMOUNT):
            continue

        normalized_rows.append(
            {
                "lat": lat,
                "lon": lon,
                "citation_count": citation_count,
                "total_fine_amount": round(total_fine_amount, 2),
                "average_fine_amount": round(total_fine_amount / citation_count, 2),
                "location": location,
                "merged_geocode_count": 1,
            }
        )

    return normalized_rows


def _normalize_marker_location_key(location: str) -> str:
    """
    Return a stable normalized key for same-address marker merging.

    Args:
        location: Raw location string from the city dataset.

    Returns:
        Uppercased, whitespace-collapsed location key.
    """
    tokens = [
        re.sub(r"[^A-Z0-9]", "", token)
        for token in location.strip().upper().split()
    ]
    tokens = [token for token in tokens if token]

    if tokens:
        tokens[-1] = _LOCATION_SUFFIX_NORMALIZATION.get(tokens[-1], tokens[-1])

    return " ".join(tokens)


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Estimate the distance between two nearby coordinates in meters.

    Args:
        lat1: Latitude of point A.
        lon1: Longitude of point A.
        lat2: Latitude of point B.
        lon2: Longitude of point B.

    Returns:
        Approximate ground distance in meters.
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    mean_lat = (lat1_rad + lat2_rad) / 2
    x = math.radians(lon2 - lon1) * math.cos(mean_lat)
    y = math.radians(lat2 - lat1)
    return 6371000 * math.sqrt((x * x) + (y * y))


def _merge_marker_points_by_location_proximity(
    marker_points: list[ParkingMarkerPoint],
) -> list[ParkingMarkerPoint]:
    """
    Merge same-address marker points that are effectively the same curb spot.

    The source dataset can assign slightly different geocodes to the same block
    address, which creates duplicate-looking markers. We collapse those nearby
    duplicates into a citation-weighted centroid, while preserving separate
    markers when the same address is meaningfully farther apart.

    Args:
        marker_points: Normalized marker hotspots prior to de-duplication.

    Returns:
        Marker hotspots with near-duplicate same-address points merged.
    """
    if not marker_points:
        return []

    grouped_points: dict[str, list[ParkingMarkerPoint]] = {}
    for point in marker_points:
        grouped_points.setdefault(_normalize_marker_location_key(point["location"]), []).append(point)

    merged_points: list[ParkingMarkerPoint] = []

    for points_for_location in grouped_points.values():
        clusters: list[dict[str, float | int | str]] = []

        for point in sorted(points_for_location, key=lambda item: int(item["citation_count"]), reverse=True):
            matched_cluster: dict[str, float | int | str] | None = None

            for cluster in clusters:
                if _distance_meters(
                    point["lat"],
                    point["lon"],
                    float(cluster["lat"]),
                    float(cluster["lon"]),
                ) <= PARKING_TICKETS_MARKER_MERGE_DISTANCE_METERS:
                    matched_cluster = cluster
                    break

            if matched_cluster is None:
                clusters.append(
                    {
                        "lat": float(point["lat"]),
                        "lon": float(point["lon"]),
                        "citation_count": int(point["citation_count"]),
                        "total_fine_amount": float(point["total_fine_amount"]),
                        "location": point["location"],
                        "merged_geocode_count": int(point.get("merged_geocode_count", 1)),
                    }
                )
                continue

            existing_count = int(matched_cluster["citation_count"])
            added_count = int(point["citation_count"])
            total_count = existing_count + added_count

            matched_cluster["lat"] = (
                (float(matched_cluster["lat"]) * existing_count) + (float(point["lat"]) * added_count)
            ) / total_count
            matched_cluster["lon"] = (
                (float(matched_cluster["lon"]) * existing_count) + (float(point["lon"]) * added_count)
            ) / total_count
            matched_cluster["citation_count"] = total_count
            matched_cluster["total_fine_amount"] = (
                float(matched_cluster["total_fine_amount"]) + float(point["total_fine_amount"])
            )
            matched_cluster["merged_geocode_count"] = (
                int(matched_cluster["merged_geocode_count"]) + int(point.get("merged_geocode_count", 1))
            )

        for cluster in clusters:
            citation_count = int(cluster["citation_count"])
            total_fine_amount = round(float(cluster["total_fine_amount"]), 2)
            merged_points.append(
                {
                    "lat": round(float(cluster["lat"]), 6),
                    "lon": round(float(cluster["lon"]), 6),
                    "citation_count": citation_count,
                    "total_fine_amount": total_fine_amount,
                    "average_fine_amount": round(total_fine_amount / citation_count, 2),
                    "location": str(cluster["location"]),
                    "merged_geocode_count": int(cluster["merged_geocode_count"]),
                }
            )

    merged_points.sort(
        key=lambda point: (
            -int(point["citation_count"]),
            float(point["lat"]),
            float(point["lon"]),
        )
    )
    return merged_points[:PARKING_TICKETS_MAX_MARKER_POINTS]


def _attach_heat_intensity(points: list[ParkingHeatPoint]) -> list[ParkingHeatPoint]:
    """
    Attach normalized heat intensities to hotspot rows.

    Leaflet.heat supports weighted points, but raw citation counts create a map
    where one or two giant hotspots dominate the whole color scale. A square-root
    curve keeps dense corridors red while still allowing lower-volume streets to
    glow visibly.

    Args:
        points: Normalized hotspot rows without final heat intensities.

    Returns:
        Hotspot rows with `intensity` values in the `(0, 1]` range.
    """
    if not points:
        return []

    max_count = max(int(point["citation_count"]) for point in points)
    if max_count <= 0:
        return points

    weighted_points: list[ParkingHeatPoint] = []
    for point in points:
        citation_count = int(point["citation_count"])
        normalized_intensity = math.sqrt(citation_count / max_count)
        intensity = round(
            min(
                1.0,
                max(PARKING_TICKETS_HEAT_INTENSITY_FLOOR, normalized_intensity),
            ),
            4,
        )
        weighted_points.append(
            {
                **point,
                "intensity": intensity,
            }
        )

    return weighted_points


def _marker_frequency_thresholds(marker_points: list[ParkingMarkerPoint]) -> tuple[int, int, int, int]:
    """
    Derive discrete ticket-frequency thresholds for zoomed-in marker styling.

    Args:
        marker_points: Normalized hotspot rows used for close-up markers.

    Returns:
        Tuple of lower-bound thresholds for moderate, high, very-high, and
        extreme-frequency marker tiers.
    """
    counts = sorted(
        int(point["citation_count"])
        for point in marker_points
        if int(point["citation_count"]) > 0
    )
    if not counts:
        return (0, 0, 0, 0)

    return (
        _pick_quantile_threshold(counts, 0.50),
        _pick_quantile_threshold(counts, 0.75),
        _pick_quantile_threshold(counts, 0.90),
        _pick_quantile_threshold(counts, 0.975),
    )


def _build_heat_anchor_feature(
    points: list[ParkingHeatPoint],
    marker_points: list[ParkingMarkerPoint],
    *,
    window_start: date,
    window_end: date,
    max_citation_count: int,
    marker_frequency_breaks: tuple[int, int, int, int],
) -> GeoJsonDict:
    """
    Build the single invisible GeoJSON anchor used to mount the heat layer.

    Dash Leaflet's `GeoJSON` component renders one Leaflet layer per feature.
    Rather than returning tens of thousands of invisible markers, we return a
    single anchor point and store the real heat points on that feature itself.

    Args:
        points: Weighted hotspot rows used to determine a stable anchor position.
        marker_points: Rich hotspot rows used for zoomed-in marker rendering.
        window_start: Inclusive start date for the current citation window.
        window_end: Inclusive end date for the current citation window.
        max_citation_count: Largest citation count in the current hotspot set.
        marker_frequency_breaks: Quantile-derived citation-count thresholds for
            zoomed-in marker color tiers.

    Returns:
        A GeoJSON point feature positioned near the center of the hotspot cloud.
    """
    if not points:
        anchor_lat = (LA_CITY_COORDINATE_BOUNDS["min_lat"] + LA_CITY_COORDINATE_BOUNDS["max_lat"]) / 2
        anchor_lon = (LA_CITY_COORDINATE_BOUNDS["min_lon"] + LA_CITY_COORDINATE_BOUNDS["max_lon"]) / 2
    else:
        anchor_lat = round(sum(point["lat"] for point in points) / len(points), 6)
        anchor_lon = round(sum(point["lon"] for point in points) / len(points), 6)

    heat_points: list[HeatPointTuple] = [
        [
            round(point["lat"], 6),
            round(point["lon"], 6),
            round(point["intensity"], 4),
        ]
        for point in points
    ]
    marker_point_tuples: list[MarkerPointTuple] = [
        [
            round(point["lat"], 6),
            round(point["lon"], 6),
            int(point["citation_count"]),
            round(point["total_fine_amount"], 2),
            round(point["average_fine_amount"], 2),
            point["location"],
            int(point.get("merged_geocode_count", 1)),
        ]
        for point in marker_points
    ]

    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [anchor_lon, anchor_lat],
        },
        "properties": {
            "layer_role": "parking_tickets_heat_anchor",
            "heat_points": heat_points,
            "marker_points": marker_point_tuples,
            "heat_max_intensity": 1.0,
            "max_citation_count": max_citation_count,
            "marker_frequency_breaks": list(marker_frequency_breaks),
            "marker_zoom_min": PARKING_TICKETS_MARKER_ZOOM_MIN,
            "heat_zoom_max": PARKING_TICKETS_HEAT_ZOOM_MAX,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        },
    }


def _build_live_parking_tickets_heat_geojson() -> GeoJsonDict:
    """
    Build the full-year 2025 parking-ticket heatmap payload from Socrata.

    Returns:
        GeoJSON `FeatureCollection` containing a single invisible anchor feature
        whose properties hold the weighted heat points and zoomed-in marker
        hotspots, plus metadata describing the fixed 2025 citation window.
    """
    try:
        window_start = PARKING_TICKETS_WINDOW_START
        window_end = PARKING_TICKETS_WINDOW_END
        grouped_heat_rows = _fetch_grouped_parking_ticket_rows(
            window_start=window_start,
            window_end=window_end,
        )
        grouped_marker_rows = _fetch_grouped_marker_rows(
            window_start=window_start,
            window_end=window_end,
        )
        heat_points = _attach_heat_intensity(_coerce_grouped_heat_rows(grouped_heat_rows))
        marker_points = _merge_marker_points_by_location_proximity(
            _coerce_grouped_marker_rows(grouped_marker_rows)
        )

        max_citation_count = max((int(point["citation_count"]) for point in heat_points), default=0)
        marker_frequency_breaks = _marker_frequency_thresholds(marker_points)
        metadata: ParkingLayerMetadata = {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "dataset_year": PARKING_TICKETS_DATASET_YEAR,
            "spot_decimals": PARKING_TICKETS_SPOT_DECIMALS,
            "heat_point_count": len(heat_points),
            "marker_point_count": len(marker_points),
            "max_citation_count": max_citation_count,
            "heat_max_intensity": 1.0,
            "data_source": "socrata_live",
            "generated_at": _generated_timestamp(),
            "artifact_version": PARKING_TICKETS_ARTIFACT_VERSION,
        }

        logger.info(
            "Built parking tickets heatmap with {} weighted hotspots for calendar year {}.",
            len(heat_points),
            PARKING_TICKETS_DATASET_YEAR,
        )
        return {
            "type": "FeatureCollection",
            "features": [
                _build_heat_anchor_feature(
                    heat_points,
                    marker_points,
                    window_start=window_start,
                    window_end=window_end,
                    max_citation_count=max_citation_count,
                    marker_frequency_breaks=marker_frequency_breaks,
                )
            ],
            "metadata": metadata,
        }
    except requests.RequestException as exc:
        logger.warning("Failed fetching parking tickets heatmap data: {}", exc)
    except Exception as exc:
        logger.exception("Failed building parking tickets heatmap: {}", exc)

    return {"type": "FeatureCollection", "features": []}


def build_parking_tickets_heat_geojson() -> GeoJsonDict:
    """
    Return the preferred parking heatmap payload for the fixed 2025 dataset.

    The app should use the precomputed local artifact when present because that
    avoids re-querying and regrouping the same yearly dataset on every worker.
    When the artifact is missing, the function falls back to rebuilding the
    payload live from Socrata so local development still works.

    Returns:
        GeoJSON `FeatureCollection` loaded from the local artifact or, if needed,
        built live from Socrata.
    """
    local_payload = load_local_parking_tickets_heat_geojson()
    if local_payload is not None:
        return local_payload

    return _build_live_parking_tickets_heat_geojson()


def build_latest_parking_tickets_heat_geojson() -> GeoJsonDict:
    """
    Return the preferred parking heatmap payload.

    Returns:
        GeoJSON `FeatureCollection` for the fixed 2025 dataset.
    """
    return build_parking_tickets_heat_geojson()


def refresh_local_parking_tickets_heat_geojson(output_path: Path | None = None) -> Path:
    """
    Rebuild the parking heatmap payload from Socrata and write it to disk.

    Args:
        output_path: Optional artifact destination. Defaults to the canonical
            2025 parking heatmap artifact path.

    Returns:
        Absolute path to the refreshed local artifact.

    Raises:
        RuntimeError: If the live rebuild produced an empty payload.
    """
    payload = _build_live_parking_tickets_heat_geojson()
    if not payload.get("features"):
        raise RuntimeError("Live parking tickets heatmap build returned no features.")
    return write_local_parking_tickets_heat_geojson(payload, output_path=output_path)
