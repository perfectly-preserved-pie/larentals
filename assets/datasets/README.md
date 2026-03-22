# Datasets

This file dictates where to get the various additional datasets in this folder.

## Farmers Markets

https://data.lacounty.gov/datasets/lacounty::farmers-markets/about

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
