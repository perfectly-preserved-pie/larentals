from .components import LeaseComponents
from dash import dcc, clientside_callback, ClientsideFunction, callback
from dash.dependencies import Input, Output, State
from functions.geojson_processing_utils import (
  geocode_place_cached,
  get_zip_feature_for_point,
  intersect_bbox_with_zip_polygons,
  load_zip_polygons,
)
from functions.sql_helpers import get_earliest_listed_date
from loguru import logger
import re
import dash
import dash_bootstrap_components as dbc
import sys
import time

dash.register_page(
  __name__,
  path='/',
  name='LA County Homes for Rent',
  title='Where to Rent in LA',
  description='An interactive map of available rentals in Los Angeles County. Updated weekly.',
)


logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME]

# Create instances of the components classes and log how long it takes to create them
start_time = time.time()
duration = time.time() - start_time
logger.info(f"Created LeaseComponents in {duration:.2f} seconds.")

# Load the ZIP polygons once at module load time
ZIP_POLYGONS = load_zip_polygons("assets/datasets/la_county_zip_codes.geojson")

# Create a state for the collapsed section in the user options card
collapse_store = dcc.Store(id='collapse-store', data={'is_open': False})

# Create a store for the geojson data
geojson_store = dcc.Store(id='lease-geojson-store', storage_type='memory', data=None)
#logger.debug(f"GeoJSON data: {geojson_store.data}")
#logger.debug(f"this is the return geojson {lease_components.return_geojson()}")

# One-shot trigger to load data after initial render
kickstart = dcc.Interval(id="lease-boot", interval=250, n_intervals=0, max_intervals=1)

def layout() -> dbc.Container:
  """
  Build the lease page layout on demand.

  Returns:
    The lease page layout container.
  """
  lease_components = LeaseComponents()

  collapse_store = dcc.Store(id="collapse-store", data={"is_open": False})
  geojson_store = dcc.Store(id="lease-geojson-store", storage_type="memory", data=None)
  zip_boundary_store = dcc.Store(id="lease-zip-boundary-store", storage_type="memory", data=None)
  kickstart = dcc.Interval(id="lease-boot", interval=250, n_intervals=0, max_intervals=1)
  # Create a Store to hold the earliest listed date
  earliest_date_store = dcc.Store(id="earliest_date_store", data=get_earliest_listed_date("assets/datasets/larentals.db", table_name="lease", date_column="listed_date"))

  return dbc.Container(
    [
      collapse_store,
      geojson_store,
      zip_boundary_store,
      kickstart,
      earliest_date_store,
      dbc.Row(
        [
          dbc.Col(
            [lease_components.title_card, lease_components.user_options_card], 
            lg=3, md=12, sm=12, xs=12,
            className="options-col d-lg-block",  # Always visible on desktop
            # style={"height": "100vh", "overflowY": "auto"}  # moved to CSS for desktop only
          ),
          dbc.Col(
            [lease_components.map_card], 
            lg=9, md=12, sm=12, xs=12,
            className="map-col position-lg-relative"
            # style={"height": "100vh"},  # moved to CSS for desktop only
          ),
        ],
        className="g-0",
        style={"minHeight": "100vh"}
      ),
    ],
    fluid=True,
    className="dbc p-0",
    style={"overflowX": "hidden"}  # Prevent horizontal scroll
  )

# Server-side callbacks
@callback(
  Output("lease-geojson-store", "data"),
  Input("lease-boot", "n_intervals"),
  prevent_initial_call=True,
)
def load_lease_geojson(_: int) -> dict:
  """
  Load the full lease GeoJSON into the browser store once, after the page renders.

  Returns:
    A GeoJSON dict suitable for dl.GeoJSON(data=...).
  """
  components = LeaseComponents()
  return components.return_geojson()


@callback(
  Output("lease-zip-boundary-store", "data"),
  Output("lease-location-status", "children"),
  Input("lease-location-input", "value"),
  Input("lease-nearby-zip-switch", "checked"),
)
def update_lease_zip_boundary(
  location: str | None,
  include_nearby: bool | None,
) -> tuple[dict, str]:
  """
  Update the ZIP boundary store based on the user-entered location.

  Returns:
    A tuple of (GeoJSON feature dict or None, status message).
  """
  # Do some validation checks
  if not location or location.strip() == "":
    return {"zip_codes": [], "features": [], "error": None}, ""

  geocoded = geocode_place_cached(location)
  if not geocoded:
    return {"zip_codes": [], "features": [], "error": "place_not_found"}, f"Could not geocode location: '{location}'."

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
    for feature in nearby_features:
      # Skip if already included
      if feature not in zip_features:
        zip_features.append(feature)

  if not zip_features:
    return {"zip_codes": [], "features": [], "error": "place_outside"}, "No ZIP code boundaries found for the specified location."

  # Extract ZIP codes from the features
  zip_codes = [feature.get("properties", {}).get("ZIPCODE") for feature in zip_features]
  # Filter out any None values
  zip_codes = [zip for zip in zip_codes if zip]
  logger.debug(f"Found ZIP codes for location '{location}': {zip_codes}")

  # Generate a label for the status message based on the number of ZIPs found (up to 5)
  label = ", ".join(zip_codes[:5])
  if len(zip_codes) > 5:
    label = f"{label} +{len(zip_codes) - 5} more"

  return {"zip_codes": zip_codes, "features": zip_features, "error": None}, f"Filtering by ZIP codes: {label}."

@callback(
  Output("lease-map-spinner", "style"),
  Input("lease-geojson-store", "data"),
  Input("lease_geojson", "data"),
  State("lease-map-spinner", "style"),
)
def toggle_map_spinner(
  geojson_data: dict | None,
  layer_data: dict | None,
  current_style: dict | None,
) -> dict:
  """
  Show the spinner overlay until the GeoJSON layer has data.

  This works even when the heavy work is clientside, because we’re reacting to the
  data prop being populated.
  """
  base = {
    "position": "absolute",
    "inset": "0",
    "alignItems": "center",
    "justifyContent": "center",
    "backgroundColor": "rgba(0, 0, 0, 0.25)",
    "zIndex": "10000",
  }

  trigger = dash.ctx.triggered_id
  # Hide once the map layer actually updates
  if trigger == "lease_geojson":
    has_features = layer_data is not None and "features" in layer_data
    base["display"] = "none" if has_features else "flex"
    return base

  # Initial load fallback
  has_features = geojson_data is not None and "features" in geojson_data
  base["display"] = "none" if has_features else "flex"
  return base

# Clientside callback to filter the full data in memory, then update the map
clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='filterAndCluster'
  ),
  Output('lease_geojson', 'data'),
  [ # The order of these inputs must match the order of the arguments in the filterAndCluster function
    Input('rental_price_slider', 'value'),
    Input('bedrooms_slider', 'value'),
    Input('bathrooms_slider', 'value'),
    Input('pets_radio', 'value'),
    Input('sqft_slider', 'value'),
    Input('sqft_missing_switch', 'checked'),
    Input('ppsqft_slider', 'value'),
    Input('ppsqft_missing_switch', 'checked'),
    Input('garage_spaces_slider', 'value'),
    Input('garage_missing_switch', 'checked'),
    Input('yrbuilt_slider', 'value'),
    Input('yrbuilt_missing_switch', 'checked'),
    Input('terms_checklist', 'value'),
    Input('terms_missing_switch', 'checked'),
    Input('furnished_checklist', 'value'),
    Input('security_deposit_slider', 'value'),
    Input('security_deposit_missing_switch', 'checked'),
    Input('pet_deposit_slider', 'value'),
    Input('pet_deposit_missing_switch', 'checked'),
    Input('key_deposit_slider', 'value'),
    Input('key_deposit_missing_switch', 'checked'),
    Input('other_deposit_slider', 'value'),
    Input('other_deposit_missing_switch', 'checked'),
    Input('laundry_checklist', 'value'),
    Input('subtype_checklist', 'value'),
    Input('listed_date_datepicker_lease', 'start_date'),
    Input('listed_date_datepicker_lease', 'end_date'),
    Input('listed_date_missing_switch', 'checked'),
    Input('isp_download_speed_slider', 'value'),
    Input('isp_upload_speed_slider', 'value'),
    Input('isp_speed_missing_switch', 'checked'),
    Input('lease-zip-boundary-store', 'data'),
    Input('lease-geojson-store', "data"),
  ],
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='updateDatePicker'
  ),
  Output('listed_date_datepicker_lease', 'start_date'),
  Input('listed_time_range_radio', 'value'),
  State('earliest_date_store', 'data'),
  
)
