"""Refresh the complete LAHD records artifact used by popups and the records drawer."""

import argparse
from pathlib import Path

from functions.data_paths import LAHD_RECORDS_SNAPSHOT_PATH
from functions.lahd_snapshot import refresh_records_snapshot


def main() -> int:
    """Check both LAHD revisions and replace the artifact only after a full download.

    A failed download exits nonzero, allowing Actions to retain the prior commit.
    An unchanged source leaves the snapshot bytes untouched.

    Returns:
        Zero after a successful update or an unchanged source check.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=LAHD_RECORDS_SNAPSHOT_PATH)
    args = parser.parse_args()
    changed = refresh_records_snapshot(args.output)
    print("Updated LAHD records snapshot" if changed else "LAHD source datasets are unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
