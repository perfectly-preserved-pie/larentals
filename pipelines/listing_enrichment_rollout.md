# Listing Enrichment Rollout

This project already enriches listings with ISP speeds at load time in
`pages/component_base.py`. The same pattern now supports generic
`buy_enrichment` and `lease_enrichment` tables keyed by `mls_number`.

## Why this shape

- Keep raw MLS tables (`buy`, `lease`) close to the source feed.
- Store derived spatial/context fields separately so we can rebuild them without
  touching the source pipelines.
- Let pages opt into enrichment columns by adding them to page config column
  lists when they are ready for filters, popups, or overlays.

## Bootstrap

Run the schema bootstrap once before building any enrichment jobs:

```bash
uv run init-listing-enrichment-tables
```

This creates or evolves:

- `buy_enrichment`
- `lease_enrichment`

Each table uses `mls_number` as the primary key and includes starter columns for:

- schools and school district
- zoning and nearby permit activity
- calls for service and crime rollups
- transit access
- CalEnviroScreen and traffic
- amenities and EV charging
- LAHD / DBS code and housing cases

The bootstrap also ensures lightweight indexes on:

- `school_district_name`
- `has_open_housing_or_code_case`

These are mostly for ad hoc SQL and future server-side filtering. The current
app still loads listings into pandas and filters client-side.

## Current hook points

- Shared enrichment attach logic: `pages/component_base.py`
- Optional overlays registry: `functions/layers.py`
- School layer builder: `scripts/build_school_layer_geojson.py`
- Buy filter config: `pages/buy_components.py`
- Lease filter config: `pages/lease_components.py`

The loader now:

1. Reads base-table columns that actually exist on `buy` or `lease`
2. Joins ISP speed data
3. Joins `<table_name>_enrichment` on `mls_number`
4. Preserves requested enrichment columns when page configs opt in

This means future page configs can safely request enrichment columns such as
`school_district_name` or `dist_rail_station_mi` without causing the base SQL
query to fail.

## Rollout order

### Phase 1: Schools

Goal:
Add the highest-signal family-focused fields first and keep the rollout narrow.

Datasets:

- California Public Schools 2024-25
- California School District Areas 2024-25

Script names to add:

- `scripts/enrich_schools.py`

Columns to populate first:

- `school_district_name`
- `school_district_type`
- `nearest_elem_school_name`
- `nearest_elem_school_mi`
- `nearest_mid_school_name`
- `nearest_mid_school_mi`
- `nearest_high_school_name`
- `nearest_high_school_mi`

Expose next:

- Add district and distance fields to `BUY_COLUMNS` / `LEASE_COLUMNS` style lists
- Add buyer and renter filters for school district and school distance
- Add optional overlays for school points
- Build school points as a local artifact pipeline:
  - download the official California Public Schools GeoPackage
  - export a slim `assets/datasets/schools_socal.geojson` for the Dash map layer
  - use the same local schools GeoPackage plus a local districts GeoJSON as the
    default `enrich-schools` inputs, auto-downloading the official artifacts
    when those defaults are missing

### Phase 2: Transit, zoning, and neighborhood change

Goal:
Make the search feel predictive, not just descriptive.

Datasets:

- Metro API / GTFS
- Los Angeles zoning polygons
- Los Angeles building permits

Script names to add:

- `scripts/enrich_transit_access.py`
- `scripts/enrich_permits_and_zoning.py`

Columns:

- `nearest_rail_station`
- `dist_rail_station_mi`
- `dist_frequent_transit_stop_mi`
- `frequent_stops_0_5mi`
- `transit_access_score`
- `zoning_code`
- `permits_500ft_12mo`
- `major_permits_0_5mi_12mo`
- `new_res_permits_0_5mi_36mo`
- `demo_permits_0_5mi_36mo`

Expose next:

- Buyer filter for `dist_rail_station_mi`
- Buyer and renter filter for `transit_access_score`
- Popup fields for zoning and nearby permit activity

### Phase 3: Safety, environment, and amenities

Goal:
Add the neighborhood decision layer people ask about most often.

Datasets:

- LAPD Calls for Service 2024 to Present
- LAPD NIBRS Offenses
- CalEnviroScreen 4.0
- LADOT Traffic Counts Summary
- Listing of Active Businesses
- NREL Alternative Fuel Stations
- LAHD property lookup datasets
- Building and Safety open code enforcement cases

Script names to add:

- `scripts/enrich_public_safety.py`
- `scripts/enrich_environment_and_traffic.py`
- `scripts/enrich_amenities.py`
- `scripts/enrich_housing_and_code_cases.py`

Columns:

- `calls_for_service_0_5mi_6mo`
- `violent_crimes_0_5mi_12mo`
- `property_crimes_0_5mi_12mo`
- `quality_of_life_calls_0_5mi_6mo`
- `ces_percentile`
- `pm25_percentile`
- `diesel_pm_percentile`
- `traffic_percentile`
- `nearest_traffic_count`
- `max_traffic_count_0_25mi`
- `grocery_count_1mi`
- `pharmacy_count_1mi`
- `childcare_count_1mi`
- `fitness_count_1mi`
- `dist_grocery_mi`
- `dist_public_ev_charger_mi`
- `public_ev_count_2mi`
- `dc_fast_count_5mi`
- `lahd_violation_case_count`
- `lahd_enforcement_case_count`
- `lahd_ccris_case_count`
- `dbs_open_code_case_count`
- `has_open_housing_or_code_case`

## Implementation notes

- Keep all spatial joins and buffer counts in scripts, not inside Dash page load.
- Write one row per `mls_number` into the matching enrichment table.
- Stamp each row with `source_version` and `enriched_at` so rebuilds are auditable.
- Use `coverage_city_only_flag = 1` when a field depends on LA City-only datasets.
- Prefer countywide/statewide coverage for default filters. Use city-only data as
  an extra layer, not as the only truth.

## First UI fields to expose

Buy page:

- `school_district_name`
- `nearest_high_school_mi`
- `dist_rail_station_mi`
- `major_permits_0_5mi_12mo`

Lease page:

- `transit_access_score`
- `dist_frequent_transit_stop_mi`
- `grocery_count_1mi`
- `lahd_violation_case_count`
- `dbs_open_code_case_count`
- `has_open_housing_or_code_case`

## Data sources

- California Public Schools 2024-25: https://sandbox.data.ca.gov/dataset/california-public-schools-2024-25
- California School District Areas 2024-25: https://sandbox.data.ca.gov/dataset/california-school-district-areas-2024-25
- Los Angeles Zoning: https://data.lacity.org/d/jjxn-vhan
- Los Angeles Building Permits Issued from 2020 to Present: https://catalog.data.gov/dataset/building-and-safety-building-permits-issued-from-2020-to-present-n
- LAPD Calls for Service 2024 to Present: https://data.lacity.org/d/xjgu-z4ju
- LAPD NIBRS Offenses: https://data.lacity.org/d/y8y3-fqfu
- CalEnviroScreen 4.0: https://sandbox.data.ca.gov/dataset/calenviroscreen-4-0
- Listing of Active Businesses: https://data.lacity.org/api/views/6rrh-rzua/rows
- Metro API: https://api.metro.net/
- NREL Alt Fuel Stations API: https://developer.nrel.gov/docs/transportation/alt-fuel-stations-v1/all/
- LAHD Violations: https://data.lacity.org/d/cr8f-uc4j
- LAHD Investigation and Enforcement Cases: https://data.lacity.org/d/eagk-wq48
- LAHD CCRIS Cases: https://data.lacity.org/d/ds2y-sb5t
- Building and Safety Open Code Cases: https://catalog.data.gov/dataset/building-and-safety-code-enforcement-case-open-n
