from .components import BuyComponents
from dash import dcc, callback, clientside_callback, ClientsideFunction
from functions.zip_geocoding_utils import (
  geocode_place_cached,
  get_zip_feature_for_point,
  intersect_bbox_with_zip_polygons,
  get_zip_features_for_place,
  load_zip_place_crosswalk,
  load_zip_polygons,
)
from functions.sql_helpers import get_earliest_listed_date
from dash.dependencies import Input, Output, State
from loguru import logger
import bleach
import dash
import dash_bootstrap_components as dbc
import pandas as pd
import sys
import time

dash.register_page(
  __name__,
  path='/buy',
  name='LA County Homes for Sale',
  title='Where to Buy in LA',
  description='An interactive map of available residential properties for sale in Los Angeles County. Updated weekly.',
)

logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME]

pd.set_option("display.precision", 10)

# Create the components objects and log how long it takes to create them
start_time = time.time()
components = BuyComponents()
duration = time.time() - start_time
logger.info(f"Created BuyComponents object in {duration:.2f} seconds.")

# Load the ZIP polygons once at module load time
ZIP_POLYGONS = load_zip_polygons("assets/datasets/la_county_zip_codes.geojson")

# Load the HUD ZIP-to-city crosswalk once at module load time
ZIP_PLACE_CROSSWALK = load_zip_place_crosswalk("assets/datasets/ZIP_COUNTY_092025.csv")

def layout() -> dbc.Container:
  """
  Build the buy page layout on demand.

  Returns:
    The buy page layout container.
  """
  collapse_store = dcc.Store(id="collapse-store", data={"is_open": False})
  geojson_store = dcc.Store(id="buy-geojson-store", storage_type="memory", data=None)
  zip_boundary_store = dcc.Store(id="buy-zip-boundary-store", storage_type="memory", data={"zip_codes": [], "features": [], "error": None})
  kickstart = dcc.Interval(id="buy-boot", interval=250, n_intervals=0, max_intervals=1)
  earliest_date_store = dcc.Store(id="earliest_date_store", data=get_earliest_listed_date("assets/datasets/larentals.db", table_name="buy", date_column="listed_date"))
  theme_store = dcc.Store(id="theme-switch-store", data=None)

  return dbc.Container(
    [
      collapse_store,
      geojson_store,
      zip_boundary_store,
      kickstart,
      earliest_date_store,
      theme_store,
      dbc.Row(
        [
          dbc.Col(
          [components.title_card, components.user_options_card], 
            lg=3, md=12, sm=12, xs=12,
            style={"height": "100vh", "overflowY": "auto"},  # Full height with scroll on desktop
            className="d-lg-block"  # Always visible on desktop
        ),
          dbc.Col(
          [components.map_card], 
            lg=9, md=12, sm=12, xs=12,
            style={"height": "100vh"},  # Full viewport height
            className="position-lg-relative"
          ),
        ],
        className="g-0",
        style={"minHeight": "100vh"}
      ),
      # Create a hidden Store to store the selected subtype value
      dcc.Store(id='selected_subtype', data='Single Family Residence')
    ],
    fluid=True,
    className="dbc p-0",
    style={"overflowX": "hidden"}  # Prevent horizontal scroll
  )

## BEGIN CALLBACKS ##
# Keep subtype selection in sync with the store
@callback(Output('selected_subtype', 'data'), Input('subtype_checklist', 'value'))
def update_selected_subtype(value):
    return value

clientside_callback(
  ClientsideFunction(namespace='clientside', function_name='loadingMapSpinner'),
  Output("buy-map-spinner", "style"),
  Input("buy-geojson-store", "data"),
  Input("buy_geojson", "data"),
  State("buy-map-spinner", "style"),
)

# Server-side callbacks
@callback(
  Output("buy-geojson-store", "data"),
  Input("buy-boot", "n_intervals"),
  prevent_initial_call=True,
)
def load_buy_geojson(_: int) -> dict:
  """
  Load the full buy GeoJSON into the browser store once, after the page renders.

  Returns:
    A GeoJSON dict suitable for dl.GeoJSON(data=...).
  """
  components = BuyComponents()
  return components.return_geojson()

@callback(
  Output("buy-zip-boundary-store", "data"),
  Output("buy-location-status", "children"),
  Input("buy-location-input", "value"),
  Input("buy-nearby-zip-switch", "checked"),
)
def update_buy_zip_boundary(
  location: str | None,
  include_nearby: bool | None,
) -> tuple[dict, str]:
  """
  Update the ZIP boundary store based on the user-entered location.

  Uses the HUD crosswalk to find ALL ZIPs belonging to the place first.
  Falls back to point-in-polygon + optional bbox intersection if the
  crosswalk has no match.

  Returns:
    A tuple of (boundary payload dict, status message string).
  """
  # Do some validation checks
  if not location or location.strip() == "":
    return {"zip_codes": [], "features": [], "error": None}, ""
  
  sanitized_location = bleach.clean(location or "", tags=[], attributes={}, strip=True)

  # Try the crosswalk first
  crosswalk_features = get_zip_features_for_place(sanitized_location, ZIP_PLACE_CROSSWALK, ZIP_POLYGONS)

  # Get the geocode bbox in case the "include nearby" switch is on
  geocoded = geocode_place_cached(sanitized_location)

  if crosswalk_features:
    # Start with crosswalk results
    zip_features = list(crosswalk_features)  

    # Optionally expand with nearby ZIPs from the geocoded bbox
    if include_nearby and geocoded:
      bbox = geocoded["bbox"]
      nearby_features = intersect_bbox_with_zip_polygons(bbox, ZIP_POLYGONS)
      existing_zips = {
        f.get("properties", {}).get("ZIPCODE") for f in zip_features
      }
      for feature in nearby_features:
        fzip = feature.get("properties", {}).get("ZIPCODE")
        if fzip and fzip not in existing_zips:
          zip_features.append(feature)
          existing_zips.add(fzip)

    # Extract ZIP codes from the features
    zip_codes = [
      f.get("properties", {}).get("ZIPCODE")
      for f in zip_features
    ]
    # Filter out any None values
    zip_codes = [z for z in zip_codes if z]
    logger.debug(f"Crosswalk matched '{sanitized_location}' → {zip_codes}")

    # Generate the label
    label = ", ".join(sorted(zip_codes)[:5])
    if len(zip_codes) > 5:
      label = f"{label} +{len(zip_codes) - 5} more"

    return (
      {"zip_codes": zip_codes, "features": zip_features, "error": None},
      f"Filtering by ZIP codes: {label}.",
    )
  
  # Fallback to geocoding + point-in-polygon if no crosswalk match
  if not geocoded:
    return (
      {"zip_codes": [], "features": [], "error": "place_not_found"},
      f"Could not geocode location: '{sanitized_location}'.",
    )

  lat = geocoded["lat"]
  lon = geocoded["lon"]
  bbox = geocoded["bbox"]

  zip_features = []

  # Always include the ZIP containing the point
  zip_feature = get_zip_feature_for_point(lat, lon, ZIP_POLYGONS)
  if zip_feature:
    zip_features.append(zip_feature)

  # Optionally include nearby ZIPs intersecting the bounding box
  if include_nearby:
    nearby_features = intersect_bbox_with_zip_polygons(bbox, ZIP_POLYGONS)
    # First get the existing ZIPs to avoid duplicates
    existing_zips = {
      f.get("properties", {}).get("ZIPCODE") for f in zip_features
    }
    # Then add any nearby features that aren't already included
    for feature in nearby_features:
      fzip = feature.get("properties", {}).get("ZIPCODE")
      # If the feature has a ZIP code and it's not already in our list, add it
      if fzip and fzip not in existing_zips:
        zip_features.append(feature)
        existing_zips.add(fzip)

  if not zip_features:
    return (
      {"zip_codes": [], "features": [], "error": "place_outside"},
      "No ZIP code boundaries found for the specified location.",
    )

  # Extract ZIP codes from the features
  zip_codes = [feature.get("properties", {}).get("ZIPCODE") for feature in zip_features]
  # Filter out any None values
  zip_codes = [zip for zip in zip_codes if zip]
  logger.debug(f"Spatial fallback for '{sanitized_location}': {zip_codes}")

  # Generate a label for the status message based on the number of ZIPs found (up to 5)
  label = ", ".join(zip_codes[:5])
  if len(zip_codes) > 5:
    label = f"{label} +{len(zip_codes) - 5} more"

  return {"zip_codes": zip_codes, "features": zip_features, "error": None}, f"Filtering by ZIP codes: {label}."

# Clientside callback to filter the full data in memory, then update the map
clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='filterAndClusterBuy'
  ),
  Output('buy_geojson', 'data'),
  [
    Input('list_price_slider', 'value'),
    Input('bedrooms_slider', 'value'),
    Input('bathrooms_slider', 'value'),
    Input('sqft_slider', 'value'),
    Input('sqft_missing_switch', 'checked'),
    Input('ppsqft_slider', 'value'),
    Input('ppsqft_missing_switch', 'checked'),
    Input('lot_size_slider', 'value'),
    Input('lot_size_missing_switch', 'checked'),
    Input('yrbuilt_slider', 'value'),
    Input('yrbuilt_missing_switch', 'checked'),
    Input('subtype_checklist', 'value'),
    Input('listed_date_datepicker_buy', 'start_date'),
    Input('listed_date_datepicker_buy', 'end_date'),
    Input('listed_date_missing_switch', 'checked'),
    Input('hoa_fee_slider', 'value'),
    Input('hoa_fee_missing_switch', 'checked'),
    Input('hoa_fee_frequency_checklist', 'value'),
    Input('isp_download_speed_slider', 'value'),
    Input('isp_upload_speed_slider', 'value'),
    Input('isp_speed_missing_switch', 'checked'),
    Input('buy-zip-boundary-store', 'data'),
    Input('buy-geojson-store', "data")
  ],
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='updateDatePicker'
  ),
  Output('listed_date_datepicker_buy', 'start_date'),
  Input('listed_time_range_radio', 'value'),
  State('earliest_date_store', 'data'),
)

clientside_callback(
  """
  (switchOn) => {
      document.documentElement.setAttribute('data-mantine-color-scheme', switchOn ? 'dark' : 'light');
      document.documentElement.setAttribute('data-bs-theme', switchOn ? 'dark' : 'light');
      return window.dash_clientside.no_update;
  }
  """,
  Output("theme-switch-store", "data"),
  Input("color-scheme-switch", "checked"),
)