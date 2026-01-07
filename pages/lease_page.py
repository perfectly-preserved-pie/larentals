from .components import LeaseComponents
from dash import dcc, MATCH, clientside_callback, ClientsideFunction, callback
from dash.dependencies import Input, Output, State
from functions.sql_helpers import get_earliest_listed_date
from loguru import logger
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
  kickstart = dcc.Interval(id="lease-boot", interval=250, n_intervals=0, max_intervals=1)
  # Create a Store to hold the earliest listed date
  earliest_date_store = dcc.Store(id="earliest_date_store", data=get_earliest_listed_date("assets/datasets/larentals.db", table_name="lease", date_column="listed_date"))

  return dbc.Container(
    [
      collapse_store,
      geojson_store,
      kickstart,
      earliest_date_store,
      dbc.Row(
        [
          dbc.Col([lease_components.title_card, lease_components.user_options_card], lg=3, md=6, sm=4),
          dbc.Col([lease_components.map_card], lg=9, md=6, sm=8),
        ],
        className="g-0",
      ),
    ],
    fluid=True,
    className="dbc p-0",
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
  Output("lease-map-spinner", "style"),
  Input("lease_geojson", "data"),
  State("lease-map-spinner", "style"),
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

# Create a callback to manage the collapsing behavior
clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='toggleCollapse'
  ),
  [
    Output('more-options-collapse-lease', 'is_open'),
    Output('more-options-button-lease', 'children')
  ],
  [Input('more-options-button-lease', 'n_clicks')],
  [State('more-options-collapse-lease', 'is_open')]
)

# Callback to toggle the visibility of dynamic components
# When the toggle button with a specific index is clicked, this function toggles the visibility of the corresponding dynamic_output_div with the same index
# If the toggle button is clicked an even number of times, the dynamic_output_div is shown and the button label is set to "Hide"
# If the toggle button is clicked an odd number of times, the dynamic_output_div is hidden and the button label is set to "Show"
clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='toggleVisibility'
  ),
  [
    Output({'type': 'dynamic_output_div_lease', 'index': MATCH}, 'style'),
    Output({'type': 'dynamic_toggle_button_lease', 'index': MATCH}, 'children')
  ],
  [Input({'type': 'dynamic_toggle_button_lease', 'index': MATCH}, 'n_clicks')],
  [State({'type': 'dynamic_output_div_lease', 'index': MATCH}, 'style')]
)

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
    Input('sqft_missing_radio', 'value'),
    Input('ppsqft_slider', 'value'),
    Input('ppsqft_missing_radio', 'value'),
    Input('garage_spaces_slider', 'value'),
    Input('garage_missing_radio', 'value'),
    Input('yrbuilt_slider', 'value'),
    Input('yrbuilt_missing_radio', 'value'),
    Input('terms_checklist', 'value'),
    Input('furnished_checklist', 'value'),
    Input('security_deposit_slider', 'value'),
    Input('security_deposit_missing_radio', 'value'),
    Input('pet_deposit_slider', 'value'),
    Input('pet_deposit_missing_radio', 'value'),
    Input('key_deposit_slider', 'value'),
    Input('key_deposit_missing_radio', 'value'),
    Input('other_deposit_slider', 'value'),
    Input('other_deposit_missing_radio', 'value'),
    Input('laundry_checklist', 'value'),
    Input('subtype_checklist', 'value'),
    Input('listed_date_datepicker_lease', 'start_date'),
    Input('listed_date_datepicker_lease', 'end_date'),
    Input('listed_date_missing_radio', 'value'),
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