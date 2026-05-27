from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from functions.lahd import (
    LAHD_DEFAULT_LOOKUP_LIMIT,
    LAHD_GEOCODE_CACHE_PATH,
    LAHD_LOCAL_LOOKUP_ARTIFACT_PATH,
    refresh_local_lahd_property_lookup,
)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the LAHD listing lookup artifact builder.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Build the derived LAHD property lookup artifact used by listing popups."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=LAHD_LOCAL_LOOKUP_ARTIFACT_PATH,
        help="Path to the gzipped JSON lookup artifact to write.",
    )
    parser.add_argument(
        "--aggregate-limit",
        type=int,
        default=LAHD_DEFAULT_LOOKUP_LIMIT,
        help="Maximum grouped rows to fetch from each LAHD Socrata dataset.",
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
    Build the LAHD lookup artifact or print its default output path.
    """
    args = parse_args()

    if args.print_output_path:
        print(LAHD_LOCAL_LOOKUP_ARTIFACT_PATH)
        return 0

    artifact_path = refresh_local_lahd_property_lookup(
        output_path=args.output,
        aggregate_limit=args.aggregate_limit,
        geocode_cache_path=args.geocode_cache,
    )
    print(artifact_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
