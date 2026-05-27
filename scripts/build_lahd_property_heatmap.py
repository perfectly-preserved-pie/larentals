from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from functions.lahd import (
    LAHD_DEFAULT_AGGREGATE_LIMIT,
    LAHD_GEOCODE_CACHE_PATH,
    LAHD_LOCAL_ARTIFACT_PATH,
    LAHD_MAX_HEAT_POINTS,
    LAHD_MAX_MARKER_POINTS,
    refresh_local_lahd_property_heat_geojson,
)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the LAHD heatmap artifact builder.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Build the derived LAHD property heatmap artifact from the LAHD "
            "investigation/enforcement and property violations datasets."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=LAHD_LOCAL_ARTIFACT_PATH,
        help="Path to the gzipped JSON artifact to write.",
    )
    parser.add_argument(
        "--aggregate-limit",
        type=int,
        default=LAHD_DEFAULT_AGGREGATE_LIMIT,
        help="Maximum grouped rows to fetch from each LAHD Socrata dataset.",
    )
    parser.add_argument(
        "--max-heat-points",
        type=int,
        default=LAHD_MAX_HEAT_POINTS,
        help="Maximum geocoded property points included in the heat surface.",
    )
    parser.add_argument(
        "--max-marker-points",
        type=int,
        default=LAHD_MAX_MARKER_POINTS,
        help="Maximum geocoded properties shown as zoomed-in markers.",
    )
    parser.add_argument(
        "--geocode-cache",
        type=Path,
        default=LAHD_GEOCODE_CACHE_PATH,
        help="Path to the LAHD APN coordinate cache JSON.",
    )
    parser.add_argument(
        "--print-output-path",
        action="store_true",
        help="Print the default output path and exit.",
    )
    return parser.parse_args()


def main() -> int:
    """
    Build the LAHD heatmap artifact or print its default output path.
    """
    args = parse_args()

    if args.print_output_path:
        print(LAHD_LOCAL_ARTIFACT_PATH)
        return 0

    artifact_path = refresh_local_lahd_property_heat_geojson(
        output_path=args.output,
        aggregate_limit=args.aggregate_limit,
        max_heat_points=args.max_heat_points,
        max_marker_points=args.max_marker_points,
        geocode_cache_path=args.geocode_cache,
    )
    print(artifact_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
