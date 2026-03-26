from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from functions.parking_tickets import (
    PARKING_TICKETS_DATASET_YEAR,
    PARKING_TICKETS_LOCAL_ARTIFACT_PATH,
    refresh_local_parking_tickets_heat_geojson,
)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the parking heatmap artifact builder.

    Returns:
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Build the derived parking tickets heatmap artifact from the Los Angeles "
            f"parking citations dataset for calendar year {PARKING_TICKETS_DATASET_YEAR}."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PARKING_TICKETS_LOCAL_ARTIFACT_PATH,
        help="Path to the gzipped JSON artifact to write.",
    )
    parser.add_argument(
        "--print-output-path",
        action="store_true",
        help="Print the default output path and exit.",
    )
    return parser.parse_args()


def main() -> int:
    """
    Build the parking heatmap artifact or print its default output path.

    Returns:
        Exit status code where `0` means success.
    """
    args = parse_args()

    if args.print_output_path:
        print(PARKING_TICKETS_LOCAL_ARTIFACT_PATH)
        return 0

    artifact_path = refresh_local_parking_tickets_heat_geojson(output_path=args.output)
    print(artifact_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
