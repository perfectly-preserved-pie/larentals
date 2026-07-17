from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from functions.data_paths import CA_BROADBAND_GEOPACKAGE_PATH
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

from loguru import logger


DEFAULT_SOURCE_URL = (
    "https://www.cpuc.ca.gov/-/media/cpuc-website/divisions/communications-division/"
    "documents/broadband-mapping/fgdb_shp_data-as-of-eoy-cibm2024/"
    "fixed_consumer_deployment_eoy2024.zip"
)
DEFAULT_OUTPUT_PATH = str(CA_BROADBAND_GEOPACKAGE_PATH)
DEFAULT_LAYER_NAME = "ca_broadband_availability_aggregate"
USER_AGENT = "larentals-cpuc-broadband-fetch/1.0"


@dataclass(frozen=True)
class BroadbandGeopackageConfig:
    """
    Runtime configuration for building the CPUC broadband GeoPackage.

    The merge pipeline expects a local GeoPackage with a stable layer name. This
    config keeps the CPUC source URL, output path, and destination layer name
    together so the CLI parser and build function pass around a typed object
    instead of a loose argparse namespace.
    """

    source_url: str
    output_path: Path
    layer_name: str
    force: bool = False

    @property
    def metadata_path(self) -> Path:
        return self.output_path.with_suffix(f"{self.output_path.suffix}.metadata.json")


def parse_args(argv: list[str] | None = None) -> BroadbandGeopackageConfig:
    """
    Parse command-line arguments into a typed fetch configuration.

    Args:
        argv: Optional argument list for tests or programmatic use. When omitted,
            argparse reads from ``sys.argv``.

    Returns:
        A ``BroadbandGeopackageConfig`` containing the CPUC download URL, the
        output GeoPackage path, and the layer name to create.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Download CPUC fixed consumer broadband deployment data and convert "
            "it to the GeoPackage format expected by run-broadband-merge."
        )
    )
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--layer", default=DEFAULT_LAYER_NAME)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild the GeoPackage even when the source validators have not changed.",
    )
    args = parser.parse_args(argv)
    return BroadbandGeopackageConfig(
        source_url=args.source_url,
        output_path=Path(args.output),
        layer_name=args.layer,
        force=args.force,
    )


def require_command(command: str) -> None:
    """
    Ensure an external command is available before starting slow work.

    The download is large enough that it is better to fail immediately if GDAL
    is missing. On Ubuntu, ``ogr2ogr`` is provided by the ``gdal-bin`` package.

    Args:
        command: Executable name to find on ``PATH``.

    Raises:
        RuntimeError: If the executable cannot be found.
    """

    if shutil.which(command) is None:
        raise RuntimeError(f"{command} is required; install gdal-bin")


def _interesting_headers(headers: object) -> dict[str, str]:
    return {
        header: value
        for header in ("ETag", "Last-Modified", "Content-Length")
        if (value := headers.get(header)) is not None
    }


def probe_source(url: str) -> dict[str, str]:
    """
    Fetch lightweight source validators without downloading the full archive.

    CPUC's file is large and changes infrequently, so ETag/Last-Modified checks
    let normal pipeline runs reuse the existing GeoPackage artifact.
    """

    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return _interesting_headers(response.headers)


def load_metadata(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None

    try:
        with path.open() as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"Could not read broadband metadata {path}: {exc}")
        return None

    return payload if isinstance(payload, dict) else None


def source_matches_metadata(
    config: BroadbandGeopackageConfig,
    source_headers: dict[str, str],
) -> bool:
    metadata = load_metadata(config.metadata_path)
    if not metadata or not config.output_path.exists():
        return False

    if metadata.get("source_url") != config.source_url:
        return False

    previous_headers = metadata.get("source_headers")
    return isinstance(previous_headers, dict) and previous_headers == source_headers


def write_metadata(
    config: BroadbandGeopackageConfig,
    source_headers: dict[str, str],
    archive_sha256: str,
) -> None:
    metadata = {
        "source_url": config.source_url,
        "source_headers": source_headers,
        "archive_sha256": archive_sha256,
        "output_path": str(config.output_path),
        "layer_name": config.layer_name,
    }
    config.metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with config.metadata_path.open("w") as file:
        json.dump(metadata, file, indent=2, sort_keys=True)
        file.write("\n")


def download_file(url: str, destination: Path) -> tuple[dict[str, str], str]:
    """
    Download the CPUC broadband archive to a local file.

    CPUC serves the broadband extract as a zip attachment. A project-specific
    user agent makes the request easier to identify in server logs and avoids
    looking like a generic Python crawler.

    Args:
        url: Fully qualified CPUC archive URL.
        destination: Local path where the zip file should be written.

    Raises:
        urllib.error.URLError: If the remote server cannot be reached.
        TimeoutError: If the response stalls past the configured timeout.
        OSError: If the destination cannot be written.
    """

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as file:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                file.write(chunk)

        return _interesting_headers(response.headers), digest.hexdigest()


def extract_archive(zip_path: Path, extract_dir: Path) -> None:
    """
    Extract a CPUC zip archive into a temporary directory.

    The current CPUC fixed-consumer download is a shapefile bundle even though
    the webpage labels the link as a File Geodatabase. Older or future downloads
    may contain a ``.gdb`` directory instead. This function only unpacks the
    archive; source dataset selection is handled separately.

    Args:
        zip_path: Path to the downloaded CPUC zip archive.
        extract_dir: Existing directory that receives the extracted files.

    Raises:
        zipfile.BadZipFile: If the downloaded file is not a valid zip archive.
        OSError: If the archive contents cannot be written.
    """

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)


def find_source_dataset(extract_dir: Path) -> Path:
    """
    Locate the GIS dataset to feed into ``ogr2ogr``.

    CPUC has alternated between File Geodatabase and shapefile packaging for
    downloadable broadband layers. GDAL can read both, so the lookup prefers a
    ``.gdb`` directory when present and otherwise falls back to the first
    shapefile found in the extracted archive.

    Args:
        extract_dir: Root directory containing the extracted CPUC archive.

    Returns:
        Path to either a ``.gdb`` directory or a ``.shp`` file.

    Raises:
        FileNotFoundError: If the archive does not contain a supported vector
            dataset.
    """

    gdb_paths = sorted(extract_dir.glob("**/*.gdb"))
    if gdb_paths:
        return gdb_paths[0]

    shp_paths = sorted(extract_dir.glob("**/*.shp"))
    if shp_paths:
        return shp_paths[0]

    raise FileNotFoundError("Could not find a .gdb directory or .shp file in the CPUC zip.")


def convert_to_geopackage(source_dataset: Path, output_path: Path, layer_name: str) -> None:
    """
    Convert the CPUC vector dataset into the app's expected GeoPackage layer.

    The merge script reads a single GeoPackage layer named
    ``ca_broadband_availability_aggregate`` by default. ``PROMOTE_TO_MULTI``
    keeps the output standards-compliant when the source contains both Polygon
    and MultiPolygon geometries.

    Args:
        source_dataset: Path to the source ``.gdb`` directory or ``.shp`` file.
        output_path: Destination GeoPackage path.
        layer_name: Layer name to create inside the destination GeoPackage.

    Raises:
        subprocess.CalledProcessError: If ``ogr2ogr`` fails.
        OSError: If the output directory cannot be created.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ogr2ogr",
            "-f",
            "GPKG",
            str(output_path),
            str(source_dataset),
            "-nln",
            layer_name,
            "-t_srs",
            "EPSG:4326",
            "-nlt",
            "PROMOTE_TO_MULTI",
            "-overwrite",
        ],
        check=True,
    )


def build_geopackage(config: BroadbandGeopackageConfig) -> None:
    """
    Download, extract, and convert CPUC broadband data into a GeoPackage.

    Temporary download and extraction files are removed automatically after the
    conversion finishes. The resulting GeoPackage is suitable for
    ``uv run run-broadband-merge`` without manual QGIS export steps.

    Args:
        config: Fetch and conversion settings.

    Raises:
        RuntimeError: If required GDAL tooling is missing.
        urllib.error.URLError: If the CPUC download fails.
        zipfile.BadZipFile: If the downloaded archive is invalid.
        subprocess.CalledProcessError: If GDAL cannot convert the dataset.
    """

    source_headers: dict[str, str] = {}
    if not config.force:
        try:
            source_headers = probe_source(config.source_url)
        except Exception as exc:
            logger.warning(f"Could not probe CPUC broadband source; rebuilding: {exc}")
        else:
            if source_headers and source_matches_metadata(config, source_headers):
                logger.success(
                    f"CPUC broadband source is unchanged; reusing {config.output_path}"
                )
                return

    require_command("ogr2ogr")

    with tempfile.TemporaryDirectory() as work_dir_str:
        work_dir = Path(work_dir_str)
        zip_path = work_dir / "cpuc_broadband.zip"
        extract_dir = work_dir / "extracted"
        extract_dir.mkdir()

        logger.info(f"Downloading CPUC broadband data from {config.source_url}")
        download_headers, archive_sha256 = download_file(config.source_url, zip_path)
        source_headers = source_headers or download_headers

        logger.info(f"Extracting CPUC broadband data to {extract_dir}")
        extract_archive(zip_path, extract_dir)

        source_dataset = find_source_dataset(extract_dir)
        logger.info(f"Converting {source_dataset} to {config.output_path}")
        convert_to_geopackage(source_dataset, config.output_path, config.layer_name)
        write_metadata(config, source_headers, archive_sha256)

    logger.success(f"Wrote {config.output_path} with layer {config.layer_name}")


def main() -> None:
    """
    CLI entry point for ``uv run fetch-cpuc-broadband-geopackage``.

    Exceptions are converted to a concise stderr message and exit code ``1`` so
    failures are obvious in EC2 user-data logs.
    """

    config = parse_args()
    try:
        build_geopackage(config)
    except Exception as exc:
        logger.error(f"Failed to build CPUC broadband GeoPackage: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
