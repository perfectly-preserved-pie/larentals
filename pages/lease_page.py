from .components import LeaseComponents
from .filters import LeaseFilters
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

  # Sort the DataFrame once at the beginning
  df_sorted = df.sort_values(by=['parking_spaces', 'list_price', 'bedrooms', 'total_bathrooms', 'sqft', 'year_built', 'ppsqft'])

  filters = [
    lease_filters.subtype_checklist_function(subtypes_chosen),
    lease_filters.pets_radio_button(pets_chosen),
    lease_filters.terms_function(terms_chosen),
    ((df_sorted['parking_spaces'].between(garage_spaces[0], garage_spaces[1])) | lease_filters.garage_radio_button(garage_missing_radio_choice, garage_spaces[0], garage_spaces[1])),
    (df_sorted['list_price'].between(rental_price[0], rental_price[1])),
    (df_sorted['bedrooms'].between(bedrooms_chosen[0], bedrooms_chosen[1])),
    (df_sorted['total_bathrooms'].between(bathrooms_chosen[0], bathrooms_chosen[1])),
    ((df_sorted['sqft'].between(sqft_chosen[0], sqft_chosen[1])) | lease_filters.sqft_radio_button(sqft_missing_radio_choice, sqft_chosen[0], sqft_chosen[1])),
    ((df_sorted['year_built'].between(years_chosen[0], years_chosen[1])) | lease_filters.yrbuilt_radio_button(yrbuilt_missing_radio_choice, years_chosen[0], years_chosen[1])),
    ((df_sorted['ppsqft'].between(ppsqft_chosen[0], ppsqft_chosen[1])) | lease_filters.ppsqft_radio_button(ppsqft_missing_radio_choice, ppsqft_chosen[0], ppsqft_chosen[1])),
    lease_filters.furnished_checklist_function(furnished_choice),
    lease_filters.security_deposit_function(security_deposit_radio_choice, security_deposit_chosen[0], security_deposit_chosen[1]),
    lease_filters.pet_deposit_function(pet_deposit_radio_choice, pet_deposit_chosen[0], pet_deposit_chosen[1]),
    lease_filters.key_deposit_function(key_deposit_radio_choice, key_deposit_chosen[0], key_deposit_chosen[1]),
    lease_filters.other_deposit_function(other_deposit_radio_choice, other_deposit_chosen[0], other_deposit_chosen[1]),
    lease_filters.listed_date_function(listed_date_radio, listed_date_datepicker_start, listed_date_datepicker_end),
    lease_filters.laundry_checklist_function(laundry_chosen)
  ]

  # Align filters with the DataFrame
  aligned_filters = [df_sorted.index.isin(df_sorted[f].index) for f in filters]\
  
  # Combine all filters
  combined_filter = filters[0]
  for f in filters[1:]:
    combined_filter &= f

  # Apply the combined filter
  df_filtered = df_sorted[combined_filter]

  # Debugging: Print the row if it is excluded
  if 'GD24178910' not in df_filtered['mls_number'].values:
      logger.debug("Row GD24178910 is excluded. Intermediate filter results:")
      for i, f in enumerate(aligned_filters):
          if not f[df_sorted['mls_number'] == 'GD24178910'].any():
              logger.debug(f"Filter {i} excluded the row.")
  else:
      logger.debug("Row GD24178910 is included.")

  # Fill NA/NaN values with None
  df_filtered = df_filtered.applymap(lambda x: None if pd.isna(x) else x)

  # Create an empty list for the markers
  markers = []
  # Iterate through the dataframe, create a marker for each row, and append it to the list
  for row in df_filtered.itertuples():
    markers.append(
      dict(
        lat=row.latitude,
        lon=row.longitude,
        data=dict(
          #bedrooms_bathrooms=row.total_bathrooms,
          bedrooms=row.bedrooms,
          city=row.city,
          date_processed=row.date_processed,
          full_bathrooms=row.full_bathrooms,
          full_street_address=row.full_street_address,
          furnished=row.furnished,
          half_bathrooms=row.half_bathrooms,
          key_deposit=row.key_deposit,
          laundry=row.laundry,
          list_price=row.list_price,
          listed_date=row.listed_date,
          listing_url=row.listing_url,
          mls_number=row.mls_number,
          mls_photo=row.mls_photo,
          other_deposit=row.other_deposit,
          parking_spaces=row.parking_spaces,
          pet_deposit=row.pet_deposit,
          pet_policy=row.pet_policy,
          phone_number=row.phone_number,
          ppsqft=row.ppsqft,
          security_deposit=row.security_deposit,
          senior_community=row.senior_community,
          short_address=row.short_address,
          sqft=row.sqft,
          street_name=row.street_name,
          street_number=row.street_number,
          subtype=row.subtype,
          terms=row.terms,
          three_quarter_bathrooms=row.three_quarter_bathrooms,
          total_bathrooms=row.total_bathrooms,
          year_built=row.year_built,
          zip_code=row.zip_code,
        ),
      )
    )
  # Generate geojson with a marker for each listing
  geojson = dlx.dicts_to_geojson([{**m} for m in markers])

  # Add context to each feature's properties to pass through to the onEachFeature JavaScript function
  for feature in geojson['features']:
    feature['properties']['context'] = {"pageType": "lease"}

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
  
  The resulting filtered dataframe has {len(df_filtered.index)} rows and {len(markers)} markers out of {len(df.index)} total rows.""")

  # Now check for missing rows
  #if len(df) != len(df_filtered):
      # Merge the two dataframes to find rows that are not common in both dataframes
 #     missing_df = pd.concat([df, df_filtered]).drop_duplicates(keep=False)
 #     logger.warning(f"""{len(missing_df)} missing rows have been found. A CSV has been generated and saved in the working directory.""")
 #     missing_df.to_csv('missing_rows.csv', index=False)

      # Align the DataFrames before comparison
 #     df_aligned, missing_df_aligned = df.align(missing_df, join='outer', axis=1, fill_value=None)
      
      # Ensure the indices are aligned
  #    df_aligned, missing_df_aligned = df_aligned.align(missing_df_aligned, join='outer', axis=0, fill_value=None)
      
      # Compare the missing rows with the original dataframe
   #   comparison_df = df_aligned.compare(missing_df_aligned, align_axis=0)
    #  comparison_df.to_csv('missing_rows_comparison.csv', index=False)
     # logger.info(f"Comparison of missing rows has been saved to 'missing_rows_comparison.csv'")

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