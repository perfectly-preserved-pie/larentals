from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from typing import Any, TypeAlias
import gzip
import hashlib
import json
import urllib.request

from loguru import logger
import orjson

GeoJsonDict: TypeAlias = dict[str, Any]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ALPR_CAMERA_SOURCE_URL = "https://data.dontgetflocked.com/cameras.geojson.gz"
DEFAULT_ALPR_CAMERA_OUTPUT_PATH = PROJECT_ROOT / "assets" / "datasets" / "alpr_cameras.geojson.gz"
ALPR_CAMERA_ARTIFACT_VERSION = 1
ALPR_CAMERA_USER_AGENT = "WhereToLive.LA alpr-camera-fetch/1.0"

SOCAL_ALPR_BOUNDS: dict[str, float] = {
    "min_lon": -125.0,
    "max_lon": -113.0,
    "min_lat": 32.0,
    "max_lat": 35.5,
}

ALPR_CAMERA_ATTRIBUTION: dict[str, str] = {
    "DeFlock Maps": "https://maps.deflock.org/",
    "FlockHopper": "https://dontgetflocked.com/",
    "OpenStreetMap": "https://www.openstreetmap.org/copyright",
}


@dataclass(frozen=True)
class AlprCameraDatasetConfig:
    """
    Runtime configuration for refreshing the local ALPR camera layer artifact.

    The source feed is national, so the default output is clipped to the same
    Southern California bounds used by other optional map overlays.
    """

    source_url: str
    output_path: Path
    bounds: dict[str, float]
    force: bool = False

    @property
    def metadata_path(self) -> Path:
        return self.output_path.with_suffix(f"{self.output_path.suffix}.metadata.json")


def default_alpr_camera_dataset_config(*, force: bool = False) -> AlprCameraDatasetConfig:
    return AlprCameraDatasetConfig(
        source_url=DEFAULT_ALPR_CAMERA_SOURCE_URL,
        output_path=DEFAULT_ALPR_CAMERA_OUTPUT_PATH,
        bounds=dict(SOCAL_ALPR_BOUNDS),
        force=force,
    )


def _interesting_headers(headers: Message) -> dict[str, str]:
    return {
        header: value
        for header in ("ETag", "Last-Modified", "Content-Length")
        if (value := headers.get(header)) is not None
    }


def probe_source(url: str) -> dict[str, str]:
    """
    Fetch lightweight source validators without downloading the full camera feed.
    """

    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={
            "Accept": "application/geo+json, application/json",
            "User-Agent": ALPR_CAMERA_USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return _interesting_headers(response.headers)


def load_metadata(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    try:
        with path.open() as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"Could not read ALPR camera metadata {path}: {exc}")
        return None

    return payload if isinstance(payload, dict) else None


def source_matches_metadata(
    config: AlprCameraDatasetConfig,
    source_headers: dict[str, str],
) -> bool:
    metadata = load_metadata(config.metadata_path)
    if not metadata or not config.output_path.exists():
        return False

    if metadata.get("source_url") != config.source_url:
        return False
    if metadata.get("artifact_version") != ALPR_CAMERA_ARTIFACT_VERSION:
        return False
    if metadata.get("bounds") != config.bounds:
        return False

    previous_headers = metadata.get("source_headers")
    return isinstance(previous_headers, dict) and previous_headers == source_headers


def _maybe_decompress_response(body: bytes, headers: Message) -> bytes:
    content_encoding = (headers.get("Content-Encoding") or "").lower()
    if "gzip" in content_encoding or body.startswith(b"\x1f\x8b"):
        return gzip.decompress(body)
    return body


def download_source_payload(url: str) -> tuple[dict[str, str], str, Any]:
    """
    Download and parse the upstream ALPR camera feed.

    The upstream URL currently ends with `.gz`, but can be served either as
    plain GeoJSON or a gzip-compressed response depending on its CDN behavior.
    """

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/geo+json, application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": ALPR_CAMERA_USER_AGENT,
        },
    )
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read()
        digest.update(body)
        source_headers = _interesting_headers(response.headers)
        payload = orjson.loads(_maybe_decompress_response(body, response.headers))
        return source_headers, digest.hexdigest(), payload


def _to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _coordinates_in_bounds(lon: float, lat: float, bounds: dict[str, float]) -> bool:
    return (
        bounds["min_lon"] <= lon <= bounds["max_lon"]
        and bounds["min_lat"] <= lat <= bounds["max_lat"]
    )


def _osm_url(osm_type: Any, osm_id: Any) -> str | None:
    normalized_type = str(osm_type or "node").strip().lower()
    if normalized_type not in {"node", "way", "relation"}:
        normalized_type = "node"
    try:
        normalized_id = int(osm_id)
    except (TypeError, ValueError):
        return None
    return f"https://www.openstreetmap.org/{normalized_type}/{normalized_id}"


def _normalize_properties(properties: dict[str, Any]) -> dict[str, Any]:
    keep_keys = (
        "osmId",
        "osmType",
        "operator",
        "brand",
        "model",
        "direction",
        "directions",
        "directionCardinal",
        "surveillanceZone",
        "mountType",
        "ref",
        "startDate",
        "osmTimestamp",
        "osmVersion",
        "wikimediaCommons",
    )
    normalized = {
        key: value
        for key in keep_keys
        if (value := properties.get(key)) is not None
    }
    if "osmType" not in normalized:
        normalized["osmType"] = "node"

    osm_link = _osm_url(normalized.get("osmType"), normalized.get("osmId"))
    if osm_link is not None:
        normalized["osmUrl"] = osm_link

    return normalized


def _feature_from_geojson_feature(feature: dict[str, Any], bounds: dict[str, float]) -> GeoJsonDict | None:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if geometry.get("type") != "Point" or len(coordinates) < 2:
        return None

    lon = _to_float(coordinates[0])
    lat = _to_float(coordinates[1])
    if lat is None or lon is None or not _coordinates_in_bounds(lon, lat, bounds):
        return None

    properties = feature.get("properties") or {}
    if not isinstance(properties, dict):
        properties = {}

    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": _normalize_properties(properties),
    }


def build_alpr_camera_feature_collection(
    payload: Any,
    *,
    bounds: dict[str, float] | None = None,
    source_url: str = DEFAULT_ALPR_CAMERA_SOURCE_URL,
) -> GeoJsonDict:
    """
    Normalize the upstream ALPR payload into a SoCal-clipped GeoJSON layer.

    The pipeline intentionally targets the live DeFlock/FlockHopper GeoJSON
    endpoint only. No brand/operator filtering is applied; all ALPR records
    inside the configured bounds are preserved.
    """

    active_bounds = bounds or SOCAL_ALPR_BOUNDS
    features: list[GeoJsonDict] = []
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("Live ALPR camera source must return a GeoJSON FeatureCollection.")

    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("Live ALPR camera GeoJSON response must include a features array.")

    source_feature_count = len(raw_features)
    for feature in raw_features:
        if not isinstance(feature, dict):
            continue
        normalized = _feature_from_geojson_feature(feature, active_bounds)
        if normalized is not None:
            features.append(normalized)

    features.sort(
        key=lambda feature: (
            str(feature["properties"].get("osmType", "")),
            int(feature["properties"].get("osmId") or 0),
        )
    )

    return {
        "type": "FeatureCollection",
        "metadata": {
            "title": "ALPR Cameras",
            "description": (
                "Automatic license plate reader camera locations in Southern California, "
                "derived from DeFlock/FlockHopper's OpenStreetMap ALPR feed."
            ),
            "artifact_version": ALPR_CAMERA_ARTIFACT_VERSION,
            "source_url": source_url,
            "source_feature_count": source_feature_count,
            "feature_count": len(features),
            "bounds": active_bounds,
            "attribution": ALPR_CAMERA_ATTRIBUTION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "features": features,
    }


def _is_valid_alpr_camera_geojson(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("type") == "FeatureCollection"
        and isinstance(payload.get("features"), list)
    )


def write_local_alpr_camera_geojson(
    payload: GeoJsonDict,
    output_path: Path | None = None,
) -> Path:
    if not _is_valid_alpr_camera_geojson(payload):
        raise ValueError("ALPR camera artifact payload must be a GeoJSON FeatureCollection.")

    artifact_path = (output_path or DEFAULT_ALPR_CAMERA_OUTPUT_PATH).resolve()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(artifact_path, "wb") as artifact_file:
        artifact_file.write(orjson.dumps(payload))

    logger.info(f"Wrote ALPR camera artifact to {artifact_path}.")
    return artifact_path


def write_metadata(
    config: AlprCameraDatasetConfig,
    source_headers: dict[str, str],
    source_sha256: str,
    feature_count: int,
    source_feature_count: int,
) -> None:
    metadata = {
        "title": "ALPR Cameras",
        "artifact_version": ALPR_CAMERA_ARTIFACT_VERSION,
        "source_url": config.source_url,
        "source_headers": source_headers,
        "source_sha256": source_sha256,
        "output_path": str(config.output_path),
        "bounds": config.bounds,
        "feature_count": feature_count,
        "source_feature_count": source_feature_count,
        "attribution": ALPR_CAMERA_ATTRIBUTION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    config.metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with config.metadata_path.open("w") as file:
        json.dump(metadata, file, indent=2, sort_keys=True)
        file.write("\n")


def refresh_local_alpr_camera_geojson(config: AlprCameraDatasetConfig) -> Path:
    source_headers: dict[str, str] = {}
    if not config.force:
        try:
            source_headers = probe_source(config.source_url)
        except Exception as exc:
            logger.warning(f"Could not probe ALPR camera source; rebuilding: {exc}")
        else:
            if source_headers and source_matches_metadata(config, source_headers):
                logger.success(f"ALPR camera source is unchanged; reusing {config.output_path}")
                return config.output_path

    logger.info(f"Downloading ALPR camera data from {config.source_url}")
    download_headers, source_sha256, raw_payload = download_source_payload(config.source_url)
    source_headers = source_headers or download_headers
    payload = build_alpr_camera_feature_collection(
        raw_payload,
        bounds=config.bounds,
        source_url=config.source_url,
    )
    output_path = write_local_alpr_camera_geojson(payload, output_path=config.output_path)
    metadata = payload.get("metadata") or {}
    write_metadata(
        config,
        source_headers,
        source_sha256,
        int(metadata.get("feature_count") or 0),
        int(metadata.get("source_feature_count") or 0),
    )
    return output_path


def load_local_alpr_camera_geojson(
    artifact_path: Path | None = None,
) -> GeoJsonDict | None:
    path = artifact_path or DEFAULT_ALPR_CAMERA_OUTPUT_PATH
    if not path.exists():
        return None

    try:
        with gzip.open(path, "rb") as artifact_file:
            payload = orjson.loads(artifact_file.read())
    except OSError as exc:
        logger.warning(f"Failed reading ALPR camera artifact from {path}: {exc}")
        return None
    except orjson.JSONDecodeError as exc:
        logger.warning(f"Failed decoding ALPR camera artifact at {path}: {exc}")
        return None

    if not _is_valid_alpr_camera_geojson(payload):
        logger.warning(f"ALPR camera artifact at {path} is not a valid GeoJSON FeatureCollection.")
        return None

    return payload


def load_alpr_camera_geojson() -> GeoJsonDict:
    payload = load_local_alpr_camera_geojson()
    if payload is None:
        raise RuntimeError(
            "ALPR camera artifact is missing or invalid. "
            "Generate it with `uv run fetch-alpr-cameras`."
        )
    return payload
