# Datasets

This file dictates where to get the various additional datasets in this folder.

## Farmers Markets

https://data.lacounty.gov/datasets/lacounty::farmers-markets/about

## Oil & Gas Wells

https://egis-lacounty.hub.arcgis.com/datasets/lacounty::oil-and-gas-wells/about

## Supermarkets & Grocery Stores

https://data.lacity.org/Administration-Finance/Listing-of-Active-Businesses/6rrh-rzua/about_data

Derived GeoJSON:

- `supermarkets_and_grocery_stores.geojson`
- Built from `Listing_of_Active_Businesses_20260321.csv`
- Filtered to NAICS `445100` and `445110`
- Excludes gas-station-branded businesses based on name matching
