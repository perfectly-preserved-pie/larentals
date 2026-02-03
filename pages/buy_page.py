from .components import BuyComponents
from dash import dcc, callback, MATCH, clientside_callback, ClientsideFunction
from functions.geojson_processing_utils import fetch_zip_boundary_feature, geocode_place_cached, find_zip_for_point
from functions.sql_helpers import get_earliest_listed_date
from dash.dependencies import Input, Output, State
from loguru import logger
import dash
import dash_bootstrap_components as dbc
import pandas as pd
import re
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

# Create a state for the collapsed section in the user options card
collapse_store = dcc.Store(id='collapse-store', data={'is_open': False})

# Create a store for the geojson data
geojson_store = dcc.Store(id='buy-geojson-store', storage_type='memory', data=None)
#logger.debug(f"GeoJSON data: {geojson_store.data}")
#logger.debug(f"this is the return geojson {components.return_geojson()}")

# One-shot trigger to load data after initial render
kickstart = dcc.Interval(id="buy-boot", interval=250, n_intervals=0, max_intervals=1)

# Create a Store to hold the earliest listed date
earliest_date_store = dcc.Store(id="earliest_date_store", data=get_earliest_listed_date("assets/datasets/larentals.db", table_name="buy", date_column="listed_date"))


def layout() -> dbc.Container:
  """
  Build the buy page layout on demand.

  Returns:
    The buy page layout container.
  """
  collapse_store = dcc.Store(id="collapse-store", data={"is_open": False})
  geojson_store = dcc.Store(id="buy-geojson-store", storage_type="memory", data=None)
  zip_boundary_store = dcc.Store(id="buy-zip-boundary-store", storage_type="memory", data=None)
  kickstart = dcc.Interval(id="buy-boot", interval=250, n_intervals=0, max_intervals=1)
  earliest_date_store = dcc.Store(id="earliest_date_store", data=get_earliest_listed_date("assets/datasets/larentals.db", table_name="buy", date_column="listed_date"))

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

@callback(
  Output("buy-map-spinner", "style"),
  Input("buy-geojson-store", "data"),
  Input("buy-location-input", "value"),
  Input("buy-zip-boundary-store", "data"),
  State("buy-map-spinner", "style"),
)
def toggle_map_spinner(
  geojson_data: dict | None,
  location_value: str | None,
  zip_boundary_data: dict | None,
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
  if trigger in {"buy-location-input", "buy-zip-boundary-store"}:
    text = (location_value or "").strip()
    if not text:
      base["display"] = "none"
      return base
    if zip_boundary_data and zip_boundary_data.get("error"):
      base["display"] = "none"
      return base
    base["display"] = "flex"
    return base

  has_features = geojson_data is not None and "features" in geojson_data
  base["display"] = "none" if has_features else "flex"
  return base

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
)
def update_buy_zip_boundary(location_value: str | None) -> tuple[dict, str]:
  text = (location_value or "").strip()
  if not text:
    return {"zip_code": None, "feature": None, "error": None}, ""

  if re.fullmatch(r"\d{5}", text):
    feature = fetch_zip_boundary_feature(text)
    if not feature:
      return {"zip_code": text, "feature": None, "error": "not_found"}, "No boundary found for that ZIP."
    return {"zip_code": text, "feature": feature, "error": None}, f"Filtering by ZIP {text}."

  geocoded = geocode_place_cached(text)
  if not geocoded:
    return {"zip_code": None, "feature": None, "error": "place_not_found"}, "Place not found."

  zip_code = find_zip_for_point(geocoded["lat"], geocoded["lon"])
  if not zip_code:
    return {"zip_code": None, "feature": None, "error": "place_outside"}, "Place is outside LA County ZIPs."

  feature = fetch_zip_boundary_feature(zip_code)
  if not feature:
    return {"zip_code": zip_code, "feature": None, "error": "not_found"}, "ZIP boundary not found."

  return {"zip_code": zip_code, "feature": feature, "error": None}, f"Using {text} → ZIP {zip_code}."


"""Keep subtype-dependent sections visible; dynamic hiding removed."""

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
