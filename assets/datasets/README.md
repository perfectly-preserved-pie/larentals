# Datasets

This file dictates where to get the various additional datasets in this folder.

## Farmers Markets

https://data.lacounty.gov/datasets/lacounty::farmers-markets/about

## Schools

https://lab.data.ca.gov/dataset/california-public-schools-2024-25

Preferred local artifacts:

- `california_public_schools_2024_25.gpkg`
- `schools_socal.geojson`
- Build both with `uv run build-school-layer-geojson`
- Source of truth is the official California Open Data GeoPackage download
- Final GeoJSON is clipped to Southern California and reduced to the fields used by the map layer and popup

## Fire Hazard Severity Zones

https://osfm.fire.ca.gov/what-we-do/community-wildfire-preparedness-and-mitigation/fire-hazard-severity-zones

Preferred local derived artifact:

- `cal_fire_fhsz_southern_california.geojson`
- Built from CAL FIRE / OSFM public ArcGIS services for SRA FHSZ effective `2024-04-01` and 2025 LRA rollout phases
- Refresh listing enrichment and the optional overlay with `uv run enrich-fire-hazard`
- Stores categorical FHSZ polygons only: `Moderate`, `High`, and `Very High`
- Use the app label `Fire Hazard Severity`; explain that CAL FIRE zones describe long-term area-level hazard, not expected damage to a specific home

## Breakfast Burritos

https://labreakfastburrito.com/
https://docs.google.com/spreadsheets/d/e/2PACX-1vRtLslbRsQydGCHn7TxcPZl1682DkrpdXXRgARONtraYuxUrzII6y3Y_pviMvxjDzeryCty8WXhiQwn/pubhtml?gid=0&single=true

Derived GeoJSON:

- `breakfast_burritos.geojson`
- Built from the published LABreakfastBurrito rankings spreadsheet
- Uses spreadsheet `LatLong` values when present
- Falls back to coordinates embedded in the linked Google Maps place URLs

## Oil & Gas Wells

https://egis-lacounty.hub.arcgis.com/datasets/lacounty::oil-and-gas-wells/about

## Supermarkets & Grocery Stores

https://data.lacity.org/Administration-Finance/Listing-of-Active-Businesses/6rrh-rzua/about_data
https://data.santamonica.gov/dataset/active-business-licenses/resource/484fe63d-a388-43fa-9714-8601254afcf0

Derived GeoJSON:

- `supermarkets_and_grocery_stores.geojson`
- Built from `Listing_of_Active_Businesses_20260321.csv`
- Merged with Santa Monica active business licenses where `business_type = Grocery, Food Products`
- Santa Monica addresses are geocoded at build time with cached Nominatim lookups
- Filtered to NAICS `445100` and `445110`
- Excludes gas-station-branded businesses based on name matching

## Parking Tickets Heatmap Layer

Inspired by the LA Controller's parking citation map:
https://parkingtickets.lacontroller.app/

https://data.lacity.org/Transportation/Parking-Citations/4f5p-udkv/about_data

Preferred local derived artifact:

- `parking_tickets_heatmap_2025.json.gz`
- Built from the fixed calendar-year window `2025-01-01` through `2025-12-31`
- Stores the top `50,000` grouped ticketed spots used for the heat surface
- Also stores the top `8,000` grouped hotspot markers used for close-up popups
- Refresh locally with `uv run build-parking-tickets-heatmap`
- Preferred API: Socrata v3 query endpoint for view `4f5p-udkv`
- Set `SOCRATA_APP_TOKEN` in `.env` or the environment to enable faster offline v3 requests
- Filters out zero/out-of-bounds coordinates before grouping
- Excludes rows with missing coordinates, implausible bounds, or invalid fine amounts
- Groups citations into rounded hotspot coordinates for weighted heatmap rendering
- Keeps up to the top `50,000` 2025 hotspots, similar to the LA Controller reference map
