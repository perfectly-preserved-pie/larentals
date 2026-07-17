"""Build the local LAHD Rent Stabilization Ordinance property lookup."""

from __future__ import annotations

import argparse
from pathlib import Path

from functions.rso import refresh_local_rso_property_lookup


def main() -> None:
    """
    Build the local RSO lookup artifact from LAHD's public dashboard.
    """
    parser = argparse.ArgumentParser(description="Build the current LAHD RSO property lookup for listing popups.")
    parser.add_argument("--output", type=Path, default=None, help="Optional path for the generated gzip JSON lookup.")
    args = parser.parse_args()
    artifact_path = refresh_local_rso_property_lookup(args.output) if args.output else refresh_local_rso_property_lookup()
    print(artifact_path)


if __name__ == "__main__":
    main()
