from __future__ import annotations
import argparse
from pathlib import Path
import sys

# Add parent directory to path so 'functions' module can be found
sys.path.insert(0, str(Path(__file__).parent.parent))

from functions.broadband_spatial_merge_utils import (
    ProviderJoinConfig,
    write_provider_options_from_geopackage,
)

DEFAULT_DB_PATH = "assets/datasets/larentals.db"
DEFAULT_GEOPACKAGE_PATH = "/home/straying/ca_broadband_geopackage.gpkg"
DEFAULT_GEOPACKAGE_LAYER = "ca_broadband_availability_aggregate"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Join listing points to CPUC broadband provider polygons."
    )
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--geopackage-path", default=DEFAULT_GEOPACKAGE_PATH)
    parser.add_argument("--geopackage-layer", default=DEFAULT_GEOPACKAGE_LAYER)
    parser.add_argument(
        "--buffer-meters",
        type=float,
        default=0.0,
        help=(
            "Tolerance around listing coordinates. Use 0 for the fast exact "
            "point-in-polygon join; the old 50m buffered join is much slower."
        ),
    )
    parser.add_argument(
        "--predicate",
        choices=("intersects", "within", "contains"),
        default=None,
        help=(
            "Spatial predicate to use. Defaults to 'within' for exact joins "
            "and 'intersects' when a buffer is requested."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    predicate = args.predicate or ("intersects" if args.buffer_meters > 0 else "within")
    jobs = [
        ProviderJoinConfig(
            larentals_db_path=args.db_path,
            listing_table="lease",
            geopackage_path=args.geopackage_path,
            geopackage_layer=args.geopackage_layer,
            output_table="lease_provider_options",
            buffer_meters=args.buffer_meters,
            predicate=predicate,
            join_how="inner",
        ),
        ProviderJoinConfig(
            larentals_db_path=args.db_path,
            listing_table="buy",
            geopackage_path=args.geopackage_path,
            geopackage_layer=args.geopackage_layer,
            output_table="buy_provider_options",
            buffer_meters=args.buffer_meters,
            predicate=predicate,
            join_how="inner",
        ),
    ]

    for cfg in jobs:
        rows = write_provider_options_from_geopackage(cfg)
        print(f"[{cfg.listing_table}] Wrote {rows:,} rows to {cfg.output_table}")

if __name__ == "__main__":
    main()
