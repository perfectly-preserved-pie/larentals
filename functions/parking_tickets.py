from dotenv import find_dotenv, load_dotenv
from datetime import date, datetime, timedelta
from loguru import logger
from typing import Any, TypeAlias, TypedDict
import math
import os
import requests
import time

load_dotenv(find_dotenv(), override=False)

PARKING_TICKETS_DATASET_URL = "https://data.lacity.org/resource/4f5p-udkv.json"
PARKING_TICKETS_V3_QUERY_URL = "https://data.lacity.org/api/v3/views/4f5p-udkv/query.json"
PARKING_TICKETS_WINDOW_DAYS = 30
PARKING_TICKETS_SPOT_DECIMALS = 4
PARKING_TICKETS_MAX_HEAT_POINTS = 50000
PARKING_TICKETS_HEAT_INTENSITY_FLOOR = 0.14
PARKING_TICKETS_REQUEST_TIMEOUT_SECONDS = 45
MIN_STABLE_DAILY_CITATIONS = 100
LATEST_ACTIVITY_LOOKBACK_START = date(2024, 1, 1)
MAX_REASONABLE_FINE_AMOUNT = 2500.0
LA_CITY_COORDINATE_BOUNDS = {
    "min_lat": 33.70,
    "max_lat": 34.35,
    "min_lon": -118.70,
    "max_lon": -118.10,
}
_SOCRATA_SESSION = requests.Session()
SOCRATA_V3_MAX_ACCEPTED_RETRIES = 5
_MISSING_SOCRATA_TOKEN_WARNING_EMITTED = False

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
    spot_decimals: int
    heat_point_count: int
    max_citation_count: int
    heat_max_intensity: float


GeoJsonDict: TypeAlias = dict[str, Any]
HeatPointTuple: TypeAlias = list[float]


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


def _find_latest_stable_issue_date(today: date | None = None) -> date | None:
    """
    Return the most recent citation date with a meaningful row count.

    The feed contains occasional future-dated or clearly anomalous one-off rows.
    This helper looks for the latest date whose grouped daily count exceeds a
    minimum threshold, then falls back to the raw max date if needed.

    Args:
        today: Optional override for the current date, primarily for testing.

    Returns:
        Most recent plausible issue date, or `None` when the dataset yields no
        usable dates after filtering.
    """
    current_day = today or date.today()
    valid_where = _build_valid_coordinate_where_clause()
    bounded_where = (
        f"{valid_where} AND issue_date >= '{_format_socrata_day(LATEST_ACTIVITY_LOOKBACK_START)}' "
        f"AND issue_date < '{_format_socrata_day(current_day + timedelta(days=1))}'"
    )

    latest_grouped_rows = _request_parking_ticket_rows(
        v3_query=(
            "SELECT `issue_date`, count(*) AS `citation_count` "
            f"WHERE {bounded_where} "
            "GROUP BY `issue_date` "
            "ORDER BY `issue_date` DESC"
        ),
        page_number=1,
        page_size=1200,
        legacy_params={
            "$select": "issue_date, count(*) AS citation_count",
            "$where": bounded_where,
            "$group": "issue_date",
            "$order": "issue_date DESC",
            "$limit": 1200,
        },
    )

    for row in latest_grouped_rows:
        issue_date = _parse_socrata_date(row.get("issue_date"))
        if issue_date is None:
            continue

        try:
            citation_count = int(row.get("citation_count", 0))
        except (TypeError, ValueError):
            citation_count = 0

        if citation_count >= MIN_STABLE_DAILY_CITATIONS:
            return issue_date

    fallback_rows = _request_parking_ticket_rows(
        v3_query=(
            "SELECT max(`issue_date`) AS `max_issue_date` "
            f"WHERE {bounded_where}"
        ),
        page_number=1,
        page_size=1,
        legacy_params={
            "$select": "max(issue_date) AS max_issue_date",
            "$where": bounded_where,
        },
    )
    if not fallback_rows:
        return None

    return _parse_socrata_date(fallback_rows[0].get("max_issue_date"))


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


def _build_heat_anchor_feature(points: list[ParkingHeatPoint]) -> GeoJsonDict:
    """
    Build the single invisible GeoJSON anchor used to mount the heat layer.

    Dash Leaflet's `GeoJSON` component renders one Leaflet layer per feature.
    Rather than returning tens of thousands of invisible markers, we return a
    single anchor point and store the real heat points on that feature itself.

    Args:
        points: Weighted hotspot rows used to determine a stable anchor position.

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

    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [anchor_lon, anchor_lat],
        },
        "properties": {
            "layer_role": "parking_tickets_heat_anchor",
            "heat_points": heat_points,
            "heat_max_intensity": 1.0,
        },
    }


def build_latest_parking_tickets_heat_geojson() -> GeoJsonDict:
    """
    Build the latest 30-day parking-ticket heatmap payload as GeoJSON.

    Returns:
        GeoJSON `FeatureCollection` containing a single invisible anchor feature
        whose properties hold the weighted heat points, plus metadata describing
        the current citation window.
    """
    try:
        latest_issue_date = _find_latest_stable_issue_date()
        if latest_issue_date is None:
            logger.warning("Parking tickets layer could not find a stable latest issue date.")
            return {"type": "FeatureCollection", "features": []}

        window_start = latest_issue_date - timedelta(days=PARKING_TICKETS_WINDOW_DAYS - 1)
        grouped_heat_rows = _fetch_grouped_parking_ticket_rows(
            window_start=window_start,
            window_end=latest_issue_date,
        )
        heat_points = _attach_heat_intensity(_coerce_grouped_heat_rows(grouped_heat_rows))

        max_citation_count = max((int(point["citation_count"]) for point in heat_points), default=0)
        metadata: ParkingLayerMetadata = {
            "window_start": window_start.isoformat(),
            "window_end": latest_issue_date.isoformat(),
            "spot_decimals": PARKING_TICKETS_SPOT_DECIMALS,
            "heat_point_count": len(heat_points),
            "max_citation_count": max_citation_count,
            "heat_max_intensity": 1.0,
        }

        logger.info(
            "Built parking tickets heatmap with {} weighted hotspots for {} through {}.",
            len(heat_points),
            window_start,
            latest_issue_date,
        )
        return {
            "type": "FeatureCollection",
            "features": [_build_heat_anchor_feature(heat_points)],
            "metadata": metadata,
        }
    except requests.RequestException as exc:
        logger.warning("Failed fetching parking tickets heatmap data: {}", exc)
    except Exception as exc:
        logger.exception("Failed building parking tickets heatmap: {}", exc)

    return {"type": "FeatureCollection", "features": []}
