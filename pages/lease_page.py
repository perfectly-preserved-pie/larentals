from .components import *
from .filters import *
from dash import dcc, callback, MATCH
from dash_extensions.javascript import Namespace
from dash.dependencies import Input, Output, State
from flask import request
from loguru import logger
from user_agents import parse
import dash
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_leaflet.express as dlx
import pandas as pd
import sys
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

# import the dataframe
df = pd.read_parquet(path='datasets/lease.parquet')
pd.set_option("display.precision", 10)

lease_filters = LeaseFilters(df)
lease_components = LeaseComponents(df)

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

@callback(
  Output(component_id='lease_geojson', component_property='children'),
  [
    Input(component_id='subtype_checklist', component_property='value'),
    Input(component_id='pets_radio', component_property='value'),
    Input(component_id='terms_checklist', component_property='value'),
    Input(component_id='garage_spaces_slider', component_property='value'),
    Input(component_id='rental_price_slider', component_property='value'),
    Input(component_id='bedrooms_slider', component_property='value'),
    Input(component_id='bathrooms_slider', component_property='value'),
    Input(component_id='sqft_slider', component_property='value'),
    Input(component_id='yrbuilt_slider', component_property='value'),
    Input(component_id='sqft_missing_radio', component_property='value'),
    Input(component_id='yrbuilt_missing_radio', component_property='value'),
    Input(component_id='garage_missing_radio', component_property='value'),
    Input(component_id='ppsqft_slider', component_property='value'),
    Input(component_id='ppsqft_missing_radio', component_property='value'),
    Input(component_id='furnished_checklist', component_property='value'),
    Input(component_id='security_deposit_slider', component_property='value'),
    Input(component_id='security_deposit_missing_radio', component_property='value'),
    Input(component_id='pet_deposit_slider', component_property='value'),
    Input(component_id='pet_deposit_missing_radio', component_property='value'),
    Input(component_id='key_deposit_slider', component_property='value'),
    Input(component_id='key_deposit_missing_radio', component_property='value'),
    Input(component_id='other_deposit_slider', component_property='value'),
    Input(component_id='other_deposit_missing_radio', component_property='value'),
    Input(component_id='listed_date_datepicker', component_property='start_date'),
    Input(component_id='listed_date_datepicker', component_property='end_date'),
    Input(component_id='listed_date_missing_radio', component_property='value'),
    Input(component_id='laundry_checklist', component_property='value'),
  ]
)
# The following function arguments are positional related to the Inputs in the callback above
# Their order must match
def update_map(subtypes_chosen, pets_chosen, terms_chosen, garage_spaces, rental_price, bedrooms_chosen, bathrooms_chosen, sqft_chosen, years_chosen, sqft_missing_radio_choice, yrbuilt_missing_radio_choice, garage_missing_radio_choice, ppsqft_chosen, ppsqft_missing_radio_choice, furnished_choice, security_deposit_chosen, security_deposit_radio_choice, pet_deposit_chosen, pet_deposit_radio_choice, key_deposit_chosen, key_deposit_radio_choice, other_deposit_chosen, other_deposit_radio_choice, listed_date_datepicker_start, listed_date_datepicker_end, listed_date_radio, laundry_chosen):
  # Pre-sort our various lists of strings for faster performance
  subtypes_chosen.sort()
  df_filtered = df[
    lease_filters.subtype_checklist_function(subtypes_chosen) &
    lease_filters.pets_radio_button(pets_chosen) &
    lease_filters.terms_function(terms_chosen) &
    # For the slider, we need to filter the dataframe by an integer range this time and not a string like the ones aboves
    # To do this, we can use the Pandas .between function
    # See https://stackoverflow.com/a/40442778
    ((df.sort_values(by='garage_spaces')['garage_spaces'].between(garage_spaces[0], garage_spaces[1])) | lease_filters.garage_radio_button(garage_missing_radio_choice, garage_spaces[0], garage_spaces[1])) &
    # Repeat but for rental price
    # Also pre-sort our lists of values to improve the performance of .between()
    (df.sort_values(by='list_price')['list_price'].between(rental_price[0], rental_price[1])) &
    (df.sort_values(by='Bedrooms')['Bedrooms'].between(bedrooms_chosen[0], bedrooms_chosen[1])) &
    (df.sort_values(by='Total Bathrooms')['Total Bathrooms'].between(bathrooms_chosen[0], bathrooms_chosen[1])) &
    ((df.sort_values(by='Sqft')['Sqft'].between(sqft_chosen[0], sqft_chosen[1])) | lease_filters.sqft_radio_button(sqft_missing_radio_choice, sqft_chosen[0], sqft_chosen[1])) &
    ((df.sort_values(by='YrBuilt')['YrBuilt'].between(years_chosen[0], years_chosen[1])) | lease_filters.yrbuilt_radio_button(yrbuilt_missing_radio_choice, years_chosen[0], years_chosen[1])) &
    ((df.sort_values(by='ppsqft')['ppsqft'].between(ppsqft_chosen[0], ppsqft_chosen[1])) | lease_filters.ppsqft_radio_button(ppsqft_missing_radio_choice, ppsqft_chosen[0], ppsqft_chosen[1])) &
    lease_filters.furnished_checklist_function(furnished_choice) &
    lease_filters.security_deposit_function(security_deposit_radio_choice, security_deposit_chosen[0], security_deposit_chosen[1]) &
    lease_filters.pet_deposit_function(pet_deposit_radio_choice, pet_deposit_chosen[0], pet_deposit_chosen[1]) &
    lease_filters.key_deposit_function(key_deposit_radio_choice, key_deposit_chosen[0], key_deposit_chosen[1]) &
    lease_filters.other_deposit_function(other_deposit_radio_choice, other_deposit_chosen[0], other_deposit_chosen[1]) &
    lease_filters.listed_date_function(listed_date_radio, listed_date_datepicker_start, listed_date_datepicker_end) &
    lease_filters.laundry_checklist_function(laundry_chosen)
  ]

  # Create an empty list for the markers
  markers = []
  # Iterate through the dataframe, create a marker for each row, and append it to the list
  for row in df_filtered.itertuples():
    markers.append(
      dict(
        lat=row.Latitude,
        lon=row.Longitude,
        popup=row.popup_html
        )
    )
  # Generate geojson with a marker for each listing
  geojson = dlx.dicts_to_geojson([{**m} for m in markers])

  # Logging
  user_agent_string = request.headers.get('User-Agent')
  user_agent = parse(user_agent_string)
  ip_address = request.remote_addr
  logger.info(f"""User {ip_address} is using {user_agent.browser.family} on {user_agent.get_device()}. 
  They have chosen the following filters: 
    Subtypes: {subtypes_chosen}.
    Pet policy: {pets_chosen}.
    List price: {rental_price}.
    Bedrooms: {bedrooms_chosen}.
    Bbathrooms: {bathrooms_chosen}.
    Square footage: {sqft_chosen}.
    Year built: {years_chosen}.
    Price per square foot: {ppsqft_chosen}.
    Listed date range: {listed_date_datepicker_start} to {listed_date_datepicker_end}.
  
  The resulting filtered dataframe has {len(df_filtered.index)} rows and {len(markers)} markers out of {len(df.index)} total rows.""")

  # Now check for missing rows
  #if len(df) != len(df_filtered):
    # Merge the two dataframes to find rows that are not common in both dataframes
  #  missing_df = pd.concat([df, df_filtered]).drop_duplicates(keep=False)
  #  logger.warning(f"""{len(missing_df)} missing rows have been found. A CSV has been generated and saved in the working directory.""")
  #  missing_df.to_csv('missing_rows.csv', index=False)

  ns = Namespace("dash_props", "module")
  # Generate the map
  return dl.GeoJSON(
    id=str(uuid.uuid4()),
    #children=[dl.Popup(id='2popup')],
    data=geojson,
    cluster=True,
    zoomToBoundsOnClick=True,
    superClusterOptions={ # https://github.com/mapbox/supercluster#options
      'radius': 160,
      'minZoom': 3,
    },
    options=dict(onEachFeature=ns("on_each_feature"))
  )

# Create a callback to manage the collapsing behavior
@callback(
  [Output('more-options-collapse-lease', 'is_open'),
    Output('more-options-button-lease', 'children')],
  [Input('more-options-button-lease', 'n_clicks')],
  [State('more-options-collapse-lease', 'is_open')]
)
def toggle_collapse(n, is_open):
  if not n:
    return False, "More Options"

  if is_open:
    return False, "More Options"
  else:
    return True, "Less Options"

# Callback to toggle the visibility of dynamic components
# When the toggle button with a specific index is clicked, this function toggles the visibility of the corresponding dynamic_output_div with the same index
# If the toggle button is clicked an even number of times, the dynamic_output_div is shown and the button label is set to "Hide"
# If the toggle button is clicked an odd number of times, the dynamic_output_div is hidden and the button label is set to "Show"
@callback(
  [Output({'type': 'dynamic_output_div_lease', 'index': MATCH}, 'style'),
    Output({'type': 'dynamic_toggle_button_lease', 'index': MATCH}, 'children')],
  [Input({'type': 'dynamic_toggle_button_lease', 'index': MATCH}, 'n_clicks')],
  [State({'type': 'dynamic_output_div_lease', 'index': MATCH}, 'style')]
)
def toggle_lease_components(n, current_style):
  if n is None:
    raise dash.exceptions.PreventUpdate

  if n % 2 == 0:
    return {'display': 'block'}, "Hide"
  else:
    return {'display': 'none'}, "Show"