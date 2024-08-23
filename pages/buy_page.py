from .components import BuyComponents
from .filters import BuyFilters
from dash import dcc, callback, MATCH, clientside_callback, ClientsideFunction
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
from loguru import logger
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

# import the dataframe and log how long it takes to load
start_time = time.time()
df = pd.read_parquet(path='assets/datasets/buy.parquet')
duration = time.time() - start_time
logger.info(f"Loaded 'buy' dataset in {duration:.2f} seconds.")

pd.set_option("display.precision", 10)

# Create the filters and components objects and log how long it takes to create them
start_time = time.time()
filters = BuyFilters(df)
duration = time.time() - start_time
logger.info(f"Created BuyFilters object in {duration:.2f} seconds.")
start_time = time.time()
components = BuyComponents(df)
duration = time.time() - start_time
logger.info(f"Created BuyComponents object in {duration:.2f} seconds.")

# Create a state for the collapsed section in the user options card
collapse_store = dcc.Store(id='collapse-store', data={'is_open': False})


layout = dbc.Container([
  collapse_store,
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
  
@callback(
  Output(component_id='buy_geojson', component_property='children'),
  [
    Input(component_id='subtype_checklist', component_property='value'),
    Input(component_id='pets_radio', component_property='value'),
    Input(component_id='list_price_slider', component_property='value'),
    Input(component_id='bedrooms_slider', component_property='value'),
    Input(component_id='bathrooms_slider', component_property='value'),
    Input(component_id='sqft_missing_radio', component_property='value'),
    Input(component_id='sqft_slider', component_property='value'),
    Input(component_id='yrbuilt_slider', component_property='value'),
    Input(component_id='yrbuilt_missing_radio', component_property='value'),
    Input(component_id='ppsqft_slider', component_property='value'),
    Input(component_id='ppsqft_missing_radio', component_property='value'),
    Input(component_id='listed_date_datepicker', component_property='start_date'),
    Input(component_id='listed_date_datepicker', component_property='end_date'),
    Input(component_id='listed_date_missing_radio', component_property='value'),
    Input(component_id='hoa_fee_slider', component_property='value'),
    Input(component_id='hoa_fee_missing_radio', component_property='value'),
    Input(component_id='hoa_fee_frequency_checklist', component_property='value'),
    Input(component_id='space_rent_slider', component_property='value'),
    Input(component_id='space_rent_missing_radio', component_property='value'),
    Input(component_id='senior_community_radio', component_property='value'),
  ]
)
# The following function arguments are positional related to the Inputs in the callback above
# Their order must match
def update_map(
  subtypes_chosen,
  pets_chosen,
  rental_price,
  bedrooms_chosen,
  bathrooms_chosen,
  sqft_missing_radio_choice,
  sqft_chosen,
  years_chosen,
  yrbuilt_missing_radio_choice,
  ppsqft_chosen,
  ppsqft_missing_radio_choice,
  listed_date_datepicker_start,
  listed_date_datepicker_end,
  listed_date_radio,
  hoa_fee,
  hoa_fee_radio,
  hoa_fee_frequency_chosen,
  space_rent,
  space_rent_radio,
  senior_community_radio_choice
):
  df_filtered = df[
    filters.subtype_checklist_function(subtypes_chosen) &
    filters.pet_policy_function(pets_chosen, subtypes_chosen) &
    # For the slider, we need to filter the dataframe by an integer range this time and not a string like the ones aboves
    # To do this, we can use the Pandas .between function
    # See https://stackoverflow.com/a/40442778
    # Repeat but for rental price
    (df['list_price'].between(rental_price[0], rental_price[1])) &
    (df['Bedrooms'].between(bedrooms_chosen[0], bedrooms_chosen[1])) &
    (df['Total Bathrooms'].between(bathrooms_chosen[0], bathrooms_chosen[1])) &
    filters.sqft_function(sqft_missing_radio_choice, sqft_chosen[0], sqft_chosen[1]) &
    filters.year_built_function(yrbuilt_missing_radio_choice, years_chosen[0], years_chosen[1]) &
    ((df['ppsqft'].between(ppsqft_chosen[0], ppsqft_chosen[1])) | filters.ppsqft_function(ppsqft_missing_radio_choice, ppsqft_chosen[0], ppsqft_chosen[1])) &
    filters.listed_date_function(listed_date_radio, listed_date_datepicker_start, listed_date_datepicker_end) &
    filters.hoa_fee_function(hoa_fee_radio, hoa_fee[0], hoa_fee[1]) &
    filters.hoa_fee_frequency_function(hoa_fee_frequency_chosen) &
    filters.space_rent_function(space_rent_radio, space_rent[0], space_rent[1]) &
    filters.senior_community_function(senior_community_radio_choice, subtypes_chosen)
  ]

  # Create an empty list for the markers
  markers = []
  # Iterate through the dataframe, create a marker for each row, and append it to the list
  for row in df_filtered.itertuples():
    markers.append(
      dict(
        lat=row.Latitude,
        lon=row.Longitude,
        data=dict(
          #bedrooms_bathrooms=row['Br/Ba'],
          city=row.City,
          date_processed=row.date_processed,
          #full_bathrooms=row['Full Bathrooms'],
          full_street_address=row.full_street_address,
          #half_bathrooms=row['Half Bathrooms'],
          hoa_fee_frequency=row.hoa_fee_frequency,
          hoa_fee=row.hoa_fee,
          image_url=row.mls_photo,
          list_price=row.list_price,
          listed_date=row.listed_date,
          listing_url=row.listing_url,
          mls_number=row.mls_number,
          park_name=row.park_name,
          pets_allowed=row.pets_allowed,
          popup_html=row.popup_html,
          postal_code=row.PostalCode,
          ppsqft=row.ppsqft,
          senior_community=row.senior_community,
          short_address=row.short_address,
          space_rent=row.space_rent,
          sqft=row.Sqft,
          street_name=row.street_name,
          street_number=row.street_number,
          subtype=row.subtype,
          #three_quarter_bathrooms=row['Three Quarter Bathrooms'],
          #total_bathrooms=row['Total Bathrooms'],
          year_built=row.year_built,
        ),
      )
    )
  # Generate geojson with a marker for each listing
  geojson = dlx.dicts_to_geojson([{**m} for m in markers])

  # Add context to each feature's properties to pass through to the onEachFeature JavaScript function
  for feature in geojson['features']:
    feature['properties']['context'] = {"pageType": "buy"}

  # Logging
  user_agent_string = request.headers.get('User-Agent')
  user_agent = parse(user_agent_string)
  ip_address = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
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
    HOA fee range: {hoa_fee}.
    HOA fee frequency: {hoa_fee_frequency_chosen}.
    Space rent: {space_rent}.
    Senior community: {senior_community_radio_choice}.
  
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
    data=geojson,
    cluster=True,
    zoomToBoundsOnClick=True,
    superClusterOptions={ # https://github.com/mapbox/supercluster#options
      'radius': 160,
      'minZoom': 3,
    },
    options=dict(onEachFeature=ns("on_each_feature"))
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