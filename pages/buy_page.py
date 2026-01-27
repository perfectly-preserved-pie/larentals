from .components import BuyComponents
from dash import dcc, callback, MATCH, clientside_callback, ClientsideFunction
from functions.sql_helpers import get_earliest_listed_date
from dash.dependencies import Input, Output, State
from loguru import logger
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
  kickstart = dcc.Interval(id="buy-boot", interval=250, n_intervals=0, max_intervals=1)
  earliest_date_store = dcc.Store(id="earliest_date_store", data=get_earliest_listed_date("assets/datasets/larentals.db", table_name="buy", date_column="listed_date"))

  return dbc.Container(
    [
      collapse_store,
      geojson_store,
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
  Input("buy_geojson", "data"),
  State("buy-map-spinner", "style"),
)
def toggle_map_spinner(geojson_data: dict | None, current_style: dict | None) -> dict:
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

  has_data = bool(geojson_data and geojson_data.get("features"))
  base["display"] = "none" if has_data else "flex"
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
