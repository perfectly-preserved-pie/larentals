import gzip

import orjson
import pytest

from functions.alpr_cameras import (
    DEFAULT_ALPR_CAMERA_SOURCE_URL,
    SOCAL_ALPR_BOUNDS,
    build_alpr_camera_feature_collection,
    load_local_alpr_camera_geojson,
    write_local_alpr_camera_geojson,
)
from scripts.fetch_alpr_cameras import parse_args


def test_fetch_alpr_cameras_parse_args_uses_socal_defaults() -> None:
    config = parse_args([])

    assert config.output_path.name == "alpr_cameras.geojson.gz"
    assert config.source_url == DEFAULT_ALPR_CAMERA_SOURCE_URL
    assert config.bounds == SOCAL_ALPR_BOUNDS
    assert config.force is False


def test_build_alpr_camera_feature_collection_keeps_all_alpr_brands_inside_socal() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-118.2437, 34.0522]},
                "properties": {
                    "osmId": 1,
                    "osmType": "node",
                    "brand": "Flock Safety",
                    "operator": "Los Angeles Police Department",
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-117.1611, 32.7157]},
                "properties": {
                    "osmId": 2,
                    "osmType": "node",
                    "brand": "Motorola Solutions",
                    "operator": "San Diego Police Department",
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-122.4194, 37.7749]},
                "properties": {
                    "osmId": 3,
                    "osmType": "node",
                    "brand": "Flock Safety",
                },
            },
        ],
    }

    geojson = build_alpr_camera_feature_collection(payload)

    assert geojson["metadata"]["source_feature_count"] == 3
    assert geojson["metadata"]["feature_count"] == 2
    assert [feature["properties"]["brand"] for feature in geojson["features"]] == [
        "Flock Safety",
        "Motorola Solutions",
    ]
    assert geojson["features"][0]["properties"]["osmUrl"] == "https://www.openstreetmap.org/node/1"


def test_build_alpr_camera_feature_collection_rejects_legacy_flat_array() -> None:
    payload = [
        {
            "osmId": 10,
            "osmType": "way",
            "lat": 34.0522,
            "lon": -118.2437,
            "brand": "Genetec",
        }
    ]

    with pytest.raises(ValueError, match="GeoJSON FeatureCollection"):
        build_alpr_camera_feature_collection(payload)


def test_write_and_load_local_alpr_camera_geojson_round_trips_gzip(tmp_path) -> None:
    payload = build_alpr_camera_feature_collection(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-118.2, 34.1]},
                    "properties": {
                        "osmId": 22,
                        "brand": "Rekor",
                    },
                }
            ],
        }
    )
    output_path = tmp_path / "alpr_cameras.geojson.gz"

    written_path = write_local_alpr_camera_geojson(payload, output_path=output_path)

    assert written_path == output_path.resolve()
    with gzip.open(output_path, "rb") as artifact_file:
        assert orjson.loads(artifact_file.read())["metadata"]["title"] == "ALPR Cameras"
    loaded = load_local_alpr_camera_geojson(output_path)
    assert loaded is not None
    assert loaded["features"][0]["properties"]["brand"] == "Rekor"
