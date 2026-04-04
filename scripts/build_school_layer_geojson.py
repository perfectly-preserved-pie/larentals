from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import requests

from functions.layers import (
    DEFAULT_SCHOOL_LAYER_GEOJSON_PATH,
    DEFAULT_SCHOOL_LAYER_GPKG_PATH,
    build_school_layer_geojson_from_gdf,
)
from functions.listing_enrichment_utils import (
    DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL,
    DEFAULT_REGION_NAME,
    is_remote_url,
    read_local_geospatial_dataset,
    resolve_region_bbox,
)

DEFAULT_USER_AGENT = "WhereToLive.LA/1.0 school layer builder"
DEFAULT_SCHOOL_COLUMNS: tuple[str, ...] = (
    "SchoolName",
    "DistrictName",
    "SchoolType",
    "SchoolLevel",
    "GradeLow",
    "GradeHigh",
    "Charter",
    "FundingType",
    "Magnet",
    "TitleIStatus",
    "Status",
    "Street",
    "City",
    "Zip",
    "State",
    "Locale",
    "Website",
    "EnrollTotal",
    "ELpct",
    "FRPMpct",
    "SEDpct",
    "SWDpct",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """
    Parse command-line arguments for the schools-layer build pipeline.

    Returns:
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Download the California Public Schools GeoPackage, clip it to Southern "
            "California, and write the slim final GeoJSON used by the optional map layer."
        )
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL,
        help=(
            "Remote GeoPackage download URL or local source file path "
            f"(default: {DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL})."
        ),
    )
    parser.add_argument(
        "--download-path",
        default=str(DEFAULT_SCHOOL_LAYER_GPKG_PATH),
        help=(
            "Local GeoPackage artifact path used when --source is remote "
            f"(default: {DEFAULT_SCHOOL_LAYER_GPKG_PATH})."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_SCHOOL_LAYER_GEOJSON_PATH),
        help=(
            "Path to the final GeoJSON layer artifact "
            f"(default: {DEFAULT_SCHOOL_LAYER_GEOJSON_PATH})."
        ),
    )
    parser.add_argument(
        "--region",
        choices=("southern-california", "all"),
        default=DEFAULT_REGION_NAME,
        help=(
            "Geographic scope to keep in the final GeoJSON "
            f"(default: {DEFAULT_REGION_NAME})."
        ),
    )
    parser.add_argument(
        "--layer",
        default=None,
        help="Optional layer name inside the GeoPackage when needed.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Redownload the GeoPackage even when the local download path already exists.",
    )
    return parser.parse_args(argv)


def download_file(url: str, destination: Path) -> Path:
    """
    Download a remote file to disk.

    Args:
        url: Remote HTTP(S) URL.
        destination: Local file path.

    Returns:
        The written destination path.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(
        url,
        stream=True,
        timeout=300,
        headers={"User-Agent": DEFAULT_USER_AGENT},
    ) as response:
        response.raise_for_status()
        with destination.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_obj.write(chunk)

    return destination


def resolve_local_source_path(args: argparse.Namespace) -> Path:
    """
    Resolve the on-disk GeoPackage path to read from.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Local path to the GeoPackage artifact.
    """
    source = str(args.source)
    if is_remote_url(source):
        download_path = Path(args.download_path).expanduser()
        if args.force_download or not download_path.exists():
            download_file(source, download_path)
        return download_path

    local_path = Path(source).expanduser()
    if not local_path.exists():
        raise FileNotFoundError(f"School source file not found: {local_path}")
    return local_path


def build_school_layer(args: argparse.Namespace) -> tuple[Path, Path, int]:
    """
    Build the final school-layer GeoJSON artifact.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Tuple of `(local_source_path, output_path, feature_count)`.
    """
    local_source_path = resolve_local_source_path(args)
    bbox = resolve_region_bbox(args.region)
    schools = read_local_geospatial_dataset(
        local_source_path,
        layer=args.layer,
        bbox=bbox,
        columns=DEFAULT_SCHOOL_COLUMNS,
    )
    payload = build_school_layer_geojson_from_gdf(schools)

    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return local_source_path, output_path, len(payload.get("features") or [])


def main() -> None:
    args = parse_args()
    source_path, output_path, feature_count = build_school_layer(args)
    print(
        f"Wrote {feature_count:,} school features to {output_path} "
        f"from GeoPackage source {source_path}."
    )


if __name__ == "__main__":
    main()
