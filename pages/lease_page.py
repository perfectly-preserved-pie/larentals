from .components import LeaseComponents
from dash import dcc, MATCH, clientside_callback, ClientsideFunction
from dash.dependencies import Input, Output, State
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

# Create instances of the filters and components classes and log how long it takes to create them
start_time = time.time()
#lease_filters = LeaseFilters(df)
duration = time.time() - start_time
logger.info(f"Created LeaseFilters in {duration:.2f} seconds.")
start_time = time.time()
lease_components = LeaseComponents()
duration = time.time() - start_time
logger.info(f"Created LeaseComponents in {duration:.2f} seconds.")

# Create a state for the collapsed section in the user options card
collapse_store = dcc.Store(id='collapse-store', data={'is_open': False})

# Create a store for the geojson data
geojson_store = dcc.Store(id='lease-geojson-store', storage_type='memory', data=lease_components.return_geojson())
#logger.debug(f"GeoJSON data: {geojson_store.data}")
#logger.debug(f"this is the return geojson {lease_components.return_geojson()}")

layout = dbc.Container([
  collapse_store,
  geojson_store,
  dbc.Row(
    [
      dbc.Col([lease_components.title_card, lease_components.user_options_card], lg=3, md=6, sm=4),
      dbc.Col([lease_components.map_card], lg=9, md=6, sm=8),
    ],
    className="g-0",
  ),
],
fluid=True,
className="dbc"
)


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
  [
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
  ],
  State('lease-geojson-store', 'data')
)