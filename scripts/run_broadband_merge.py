from __future__ import annotations
from pathlib import Path
import sys

# Add parent directory to path so 'functions' module can be found
sys.path.insert(0, str(Path(__file__).parent.parent))

from functions.broadband_spatial_merge_utils import (
    ProviderJoinConfig,
    write_provider_options_from_geopackage,
)

def main() -> None:
    jobs = [
        ProviderJoinConfig(
            larentals_db_path="assets/datasets/larentals.db",
            listing_table="lease",
            geopackage_path="/home/straying/ca_broadband_geopackage.gpkg",
            geopackage_layer="ca_broadband_availability_aggregate",
            output_table="lease_provider_options",
            buffer_meters=50.0,
            join_how="inner",
        ),
        ProviderJoinConfig(
            larentals_db_path="assets/datasets/larentals.db",
            listing_table="buy",
            geopackage_path="/home/straying/ca_broadband_geopackage.gpkg",
            geopackage_layer="ca_broadband_availability_aggregate",
            output_table="buy_provider_options",
            buffer_meters=50.0,
            join_how="inner",
        ),
    ]

    for cfg in jobs:
        rows = write_provider_options_from_geopackage(cfg)
        print(f"[{cfg.listing_table}] Wrote {rows:,} rows to {cfg.output_table}")

if __name__ == "__main__":
    main()