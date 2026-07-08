from pathlib import Path

from scripts.fetch_cpuc_broadband_geopackage import (
    BroadbandGeopackageConfig,
    source_matches_metadata,
    write_metadata,
)


def test_source_matches_metadata_when_output_and_headers_match(tmp_path: Path) -> None:
    output_path = tmp_path / "ca_broadband_geopackage.gpkg"
    output_path.write_text("stub", encoding="utf-8")
    config = BroadbandGeopackageConfig(
        source_url="https://example.test/broadband.zip",
        output_path=output_path,
        layer_name="ca_broadband_availability_aggregate",
    )
    headers = {
        "ETag": '"abc123"',
        "Last-Modified": "Wed, 01 Jul 2026 00:00:00 GMT",
        "Content-Length": "12345",
    }

    write_metadata(config, headers, archive_sha256="abc123")

    assert source_matches_metadata(config, headers) is True


def test_source_metadata_mismatch_forces_rebuild(tmp_path: Path) -> None:
    output_path = tmp_path / "ca_broadband_geopackage.gpkg"
    output_path.write_text("stub", encoding="utf-8")
    config = BroadbandGeopackageConfig(
        source_url="https://example.test/broadband.zip",
        output_path=output_path,
        layer_name="ca_broadband_availability_aggregate",
    )

    write_metadata(config, {"ETag": '"old"'}, archive_sha256="old")

    assert source_matches_metadata(config, {"ETag": '"new"'}) is False
