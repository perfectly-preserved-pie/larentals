from .components import BuyComponents
from .filters import BuyFilters
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
geojson_store = dcc.Store(id='buy-geojson-store', storage_type='memory', data=components.return_geojson())
#logger.debug(f"GeoJSON data: {geojson_store.data}")
#logger.debug(f"this is the return geojson {lease_components.return_geojson()}")

layout = dbc.Container([
  collapse_store,
  geojson_store,
  dbc.Row( # First row: title card
    [
      dbc.Col([components.title_card, components.user_options_card], lg=3, md=6, sm=4),
      dbc.Col([components.map_card], lg=9, md=6, sm=8),
    ],
    className="g-0",
  ),
  # Create a hidden Store to store the selected subtype value
  dcc.Store(id='selected_subtype', data='SFR'),
],
fluid = True,
className = "dbc"
),

## BEGIN CALLBACKS ##
# First, we want to hide the pet policy and senior community options if the user selects a property type that doesn't have those options (anything other than a mobile home)
# Define callback to update selected_subtype store with the value of the subtype radio button
@callback(Output('selected_subtype', 'data'), Input('subtype_checklist', 'value'))
def update_selected_subtype(value):
    return value

# Define callback to update the style property of the senior community div based on the selected subtype value
clientside_callback(
  ClientsideFunction(namespace='clientside', function_name='toggleVisibilityBasedOnSubtype'),
  Output('senior_community_div_buy', 'style'),
  [Input('selected_subtype', 'data')]
)
    
# Define callback to update the style property of the pet policy div based on the selected subtype value
clientside_callback(
  ClientsideFunction(namespace='clientside', function_name='toggleVisibilityBasedOnSubtype'),
  Output('pet_policy_div_buy', 'style'),
  [Input('selected_subtype', 'data')]
)
  
# Define callback to update the style property of the space rent div based on the selected subtype value
clientside_callback(
  ClientsideFunction(namespace='clientside', function_name='toggleVisibilityBasedOnSubtype'),
  Output('space_rent_div_buy', 'style'),
  [Input('selected_subtype', 'data')]
)

# Define callback to update the style property of the missing HOA Fee div based on the selected subtype value
clientside_callback(
  ClientsideFunction(namespace='clientside', function_name='toggleHOAVisibility'),
  Output('hoa_fee_div_buy', 'style'),
  [Input('selected_subtype', 'data')]
)
  
# Define callback to update the style property of the HOA Fee frequency div based on the selected subtype value
clientside_callback(
  ClientsideFunction(namespace='clientside', function_name='toggleHOAVisibility'),
  Output('hoa_fee_frequency_div_buy', 'style'),
  [Input('selected_subtype', 'data')]
)

# Create a callback to manage the collapsing behavior
clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='toggleCollapse'
  ),
  [
    Output('more-options-collapse-buy', 'is_open'),
    Output('more-options-button-buy', 'children')
  ],
  [Input('more-options-button-buy', 'n_clicks')],
  [State('more-options-collapse-buy', 'is_open')]
)

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
    Input('pets_radio', 'value'),
    Input('sqft_slider', 'value'),
    Input('sqft_missing_radio', 'value'),
    Input('ppsqft_slider', 'value'),
    Input('ppsqft_missing_radio', 'value'),
    #Input('garage_spaces_slider', 'value'),
    #Input('garage_missing_radio', 'value'),
    Input('yrbuilt_slider', 'value'),
    Input('yrbuilt_missing_radio', 'value'),
    Input('senior_community_radio', 'value'),
    Input('subtype_checklist', 'value'),
    Input('listed_date_datepicker', 'start_date'),
    Input('listed_date_datepicker', 'end_date'),
    Input('listed_date_missing_radio', 'value'),
  ],
  State('buy-geojson-store', 'data')
)

# Callback to toggle the visibility of dynamic components
# When the toggle button with a specific index is clicked, this function toggles the visibility of the corresponding dynamic_output_div with the same index
# If the toggle button is clicked an even number of times, the dynamic_output_div is shown and the button label is set to "Hide"
# If the toggle button is clicked an odd number of times, the dynamic_output_div is hidden and the button label is set to "Show"
clientside_callback(
  ClientsideFunction(namespace='clientside', function_name='toggleVisibility'),
  [
    Output({'type': 'dynamic_output_div_buy', 'index': MATCH}, 'style'),
    Output({'type': 'dynamic_toggle_button_buy', 'index': MATCH}, 'children')
  ],
  [Input({'type': 'dynamic_toggle_button_buy', 'index': MATCH}, 'n_clicks')]
)