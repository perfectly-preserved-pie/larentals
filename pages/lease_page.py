from .components import LeaseComponents
from .filters import LeaseFilters
from dash import dcc, callback, MATCH, clientside_callback, ClientsideFunction
from dash_extensions.javascript import Namespace
from dash.dependencies import Input, Output, State
from flask import request
from functions.convex_hull import generate_convex_hulls
from loguru import logger
from user_agents import parse
import dash
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_leaflet.express as dlx
import pandas as pd
import sys
import time
import uuid

dash.register_page(
  __name__,
  path='/',
  name='LA County Homes for Rent',
  title='Where to Rent in LA',
  description='An interactive map of available rentals in Los Angeles County. Updated weekly.',
)


logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME]

# import the dataframe and log how long it takes to load
start_time = time.time()
df = pd.read_parquet(path='assets/datasets/lease.parquet')
duration = time.time() - start_time
logger.info(f"Loaded 'lease' dataset in {duration:.2f} seconds.")
pd.set_option("display.precision", 10)

# Create instances of the filters and components classes and log how long it takes to create them
start_time = time.time()
lease_filters = LeaseFilters(df)
duration = time.time() - start_time
logger.info(f"Created LeaseFilters in {duration:.2f} seconds.")
start_time = time.time()
lease_components = LeaseComponents(df)
duration = time.time() - start_time
logger.info(f"Created LeaseComponents in {duration:.2f} seconds.")

# Create a state for the collapsed section in the user options card
collapse_store = dcc.Store(id='collapse-store', data={'is_open': False})

layout = dbc.Container([
  collapse_store,
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