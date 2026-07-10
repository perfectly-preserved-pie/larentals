from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from functions.alpr_cameras import (
    DEFAULT_ALPR_CAMERA_OUTPUT_PATH,
    DEFAULT_ALPR_CAMERA_SOURCE_URL,
    SOCAL_ALPR_BOUNDS,
    AlprCameraDatasetConfig,
    refresh_local_alpr_camera_geojson,
)


def parse_args(argv: list[str] | None = None) -> AlprCameraDatasetConfig:
    """
    Parse command-line arguments for the local ALPR camera artifact builder.

    Args:
        argv: Optional argument list for tests or programmatic use. When omitted,
            argparse reads from ``sys.argv``.

    Returns:
        A typed configuration for fetching the live ALPR camera endpoint into
        the local SoCal artifact path.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Download the DeFlock/FlockHopper ALPR camera feed, filter it to "
            "Southern California, and write the local GeoJSON artifact used by "
            "the optional map layer."
        )
    )
    parser.add_argument("--output", default=str(DEFAULT_ALPR_CAMERA_OUTPUT_PATH))
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild the artifact even when source validators have not changed.",
    )
    args = parser.parse_args(argv)

    return AlprCameraDatasetConfig(
        source_url=DEFAULT_ALPR_CAMERA_SOURCE_URL,
        output_path=Path(args.output),
        bounds=dict(SOCAL_ALPR_BOUNDS),
        force=args.force,
    )


def main() -> None:
    """
    CLI entry point for ``uv run fetch-alpr-cameras``.

    Raises:
        SystemExit: Exits with status ``1`` when the artifact refresh fails.
    """

    config = parse_args()
    try:
        output_path = refresh_local_alpr_camera_geojson(config)
    except Exception as exc:
        logger.error(f"Failed to build ALPR camera artifact: {exc}")
        raise SystemExit(1) from exc

    logger.success(f"ALPR camera artifact ready at {output_path}")


if __name__ == "__main__":
    main()
