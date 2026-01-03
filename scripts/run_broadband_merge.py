from functions.broadband_spatial_merge_utils import (
    ProviderJoinConfig,
    write_provider_options_from_geopackage,
)

def main() -> None:
    cfg = ProviderJoinConfig(
        larentals_db_path="assets/datasets/larentals.db",
        listing_table="lease",
        geopackage_path="/home/straying/ca_broadband_geopackage.gpkg",
        geopackage_layer="ca_broadband_availability_aggregate",
        output_table="lease_provider_options",

        buffer_meters=50.0,   # start with 50m buffer
        join_how="inner",
    )

    rows = write_provider_options_from_geopackage(cfg)
    print(f"Wrote {rows:,} provider rows to lease_provider_options")


if __name__ == "__main__":
    main()
