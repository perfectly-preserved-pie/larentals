from .filters import *
from .components import *
from dash import html, dcc, callback
from dash_extensions.javascript import Namespace
from dash.dependencies import Input, Output, State
from datetime import date
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
  name='WhereToLive.LA - For Lease',
  title='WhereToLive.LA - For Lease',
  description='An interactive map of available rentals in Los Angeles County. Updated weekly.',
)


logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME]

# import the dataframe
df = pd.read_parquet(path='datasets/lease.parquet')
pd.set_option("display.precision", 10)

lease_filters = LeaseFilters(df)
lease_components = LeaseComponents(df)

### DASH LEAFLET AND DASH BOOTSTRAP COMPONENTS SECTION BEGINS!
# Get the means so we can center the map
lat_mean = df['Latitude'].mean()
long_mean = df['Longitude'].mean()












garage_spaces_slider =  html.Div([
    html.H5("Garage Spaces"),
    # Create a range slider for # of garage spaces
    dcc.RangeSlider(
      min=0, 
      max=df['garage_spaces'].max(), # Dynamically calculate the maximum number of garage spaces
      step=1, 
      value=[0, df['garage_spaces'].max()], 
      id='garage_spaces_slider',
      updatemode='mouseup',
      tooltip={
        "placement": "bottom",
        "always_visible": True
      },
    ),
],
style = {
  'margin-bottom' : '10px',
},
id = 'garage_div'
)

unknown_garage_radio = html.Div([
  dbc.Alert(
    [
    # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
    html.I(className="bi bi-info-circle-fill me-2"),
    ("Should we include properties with an unknown number of garage spaces?"),
    dcc.RadioItems(
      id='garage_missing_radio',
      options=[
          {'label': 'Yes', 'value': 'True'},
          {'label': 'No', 'value': 'False'}
      ],
      value='True',
      inputStyle = {
        "margin-right": "5px",
        "margin-left": "5px"
      },
      inline=True
    ),
    ],
  color="info",
  ),
],
id = 'unknown_garage_spaces_div'
)

rental_price_slider = html.Div([ 
    html.H5("Price (Monthly)"),
    # Create a range slider for rental price
    dcc.RangeSlider(
      min=df['list_price'].min(),
      max=df['list_price'].max(),
      value=[0, df['list_price'].max()],
      id='rental_price_slider',
      tooltip={
        "placement": "bottom",
        "always_visible": True
      },
      updatemode='mouseup'
    ),
],
id = 'price_div'
)

year_built_slider = html.Div([
    html.H5("Year Built"),
    # Create a range slider for year built
    dcc.RangeSlider(
      min=df['YrBuilt'].min(),
      max=df['YrBuilt'].max(),
      value=[0, df['YrBuilt'].max()],
      id='yrbuilt_slider',
      tooltip={
        "placement": "bottom",
        "always_visible": True
      },
      marks = { # Create custom tick marks
          # The left column should be floats, the right column should be strings
          f"{df['YrBuilt'].min()}": f"{df['YrBuilt'].min()}", # first mark is oldest house
          float(f"{df['YrBuilt'].min()}") + 20: str(float(f"{df['YrBuilt'].min()}") + 20), # next mark is oldest house + 20 years
          float(f"{df['YrBuilt'].min()}") + 40: str(float(f"{df['YrBuilt'].min()}") + 40),
          float(f"{df['YrBuilt'].min()}") + 60: str(float(f"{df['YrBuilt'].min()}") + 60),
          float(f"{df['YrBuilt'].min()}") + 80: str(float(f"{df['YrBuilt'].min()}") + 80),
          float(f"{df['YrBuilt'].min()}") + 100: str(float(f"{df['YrBuilt'].min()}") + 100),
          float(f"{df['YrBuilt'].min()}") + 120: str(float(f"{df['YrBuilt'].min()}") + 120),
          float(f"{df['YrBuilt'].min()}") + 140: str(float(f"{df['YrBuilt'].min()}") + 140),
          f"{df['YrBuilt'].max()}": str(f"{df['YrBuilt'].max()}") # last mark is newest house
      },
      updatemode='mouseup'
    ),
],
style = {
  'margin-bottom' : '10px',
},
id = 'yrbuilt_div'
)

unknown_year_built_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),      
      ("Should we include properties with an unknown year built?"),
      dcc.RadioItems(
        id='yrbuilt_missing_radio',
        options=[
            {'label': 'Yes', 'value': 'True'},
            {'label': 'No', 'value': 'False'}
        ],
        value='True',
        inputStyle = {
          "margin-right": "5px",
          "margin-left": "5px"
        },
        inline=True
      ),
    ],
  color="info",
  ),
],
id = 'yrbuilt_missing_div'
)

furnished_checklist = html.Div([ 
      # Title this section
      html.H5("Furnished/Unfurnished"), 
      # Create a checklist of options for the user
      # https://dash.plotly.com/dash-core-components/checklist
      dcc.Checklist( 
          id = 'furnished_checklist',
          options = [
            #TODO: Dynamically populate the labels and values with a for loop
            {'label': 'Furnished Or Unfurnished', 'value': 'Furnished Or Unfurnished'},
            {'label': 'Furnished', 'value': 'Furnished'},
            {'label': 'Negotiable', 'value': 'Negotiable'},
            {'label': 'Partially', 'value': 'Partially'},
            {'label': 'Unfurnished', 'value': 'Unfurnished'},
            {'label': 'Unknown', 'value': 'Unknown'},
          ],
          value=[ # Set the default value
            'Furnished Or Unfurnished',
            'Furnished',
            'Negotiable',
            'Partially',
            'Unfurnished',
            'Unknown',
          ],
          labelStyle = {'display': 'block'},
          # add some spacing in between the checkbox and the label
          # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
          inputStyle = {
            "margin-right": "5px",
            "margin-left": "5px"
          },
      ),
],
id = 'furnished_div',
)

security_deposit_slider =  html.Div([
    html.H5("Security Deposit"),
    # Create a range slider for security deposit cost
    dcc.RangeSlider(
      min=df['DepositSecurity'].min(), # Dynamically calculate the minimum security deposit
      max=df['DepositSecurity'].max(), # Dynamically calculate the maximum security deposit
      value=[df['DepositSecurity'].min(), df['DepositSecurity'].max()], 
      id='security_deposit_slider',
      tooltip={
        "placement": "bottom",
        "always_visible": True
      },
      updatemode='mouseup'
    ),
],
style = {
  'margin-bottom' : '10px',
},
id = 'security_deposit_slider_div'
)

security_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties with an unknown security deposit?"),
      dcc.RadioItems(
        id='security_deposit_missing_radio',
        options=[
            {'label': 'Yes', 'value': 'True'},
            {'label': 'No', 'value': 'False'}
        ],
        value='True',
        # add some spacing in between the checkbox and the label
        # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
        inputStyle = {
          "margin-right": "5px",
          "margin-left": "5px"
        },
        inline=True     
        ),
    ],
  color="info",
  ),
],
id = 'unknown_security_deposit_div',
)

pet_deposit_slider =  html.Div([
    html.H5("Pet Deposit"),
    # Create a range slider for pet deposit cost
    dcc.RangeSlider(
      min=df['DepositPets'].min(), # Dynamically calculate the minimum pet deposit
      max=df['DepositPets'].max(), # Dynamically calculate the maximum pet deposit
      value=[df['DepositPets'].min(), df['DepositPets'].max()], 
      id='pet_deposit_slider',
      tooltip={
        "placement": "bottom",
        "always_visible": True
      },
      updatemode='mouseup'
    ),
],
style = {
  'margin-bottom' : '10px',
},
id = 'pet_deposit_slider_div'
)

pet_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties with an unknown pet deposit?"),
      dcc.RadioItems(
        id='pet_deposit_missing_radio',
        options=[
            {'label': 'Yes', 'value': 'True'},
            {'label': 'No', 'value': 'False'}
        ],
        value='True',
        # add some spacing in between the checkbox and the label
        # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
        inputStyle = {
          "margin-right": "5px",
          "margin-left": "5px"
        },
        inline=True      
        ),
    ],
  color="info",
  ),
],
id = 'unknown_pet_deposit_div',
)

key_deposit_slider =  html.Div([
    html.H5("Key Deposit"),
    # Create a range slider for key deposit cost
    dcc.RangeSlider(
      min=df['DepositKey'].min(), # Dynamically calculate the minimum key deposit
      max=df['DepositKey'].max(), # Dynamically calculate the maximum key deposit
      value=[df['DepositKey'].min(), df['DepositKey'].max()], 
      id='key_deposit_slider',
      tooltip={
        "placement": "bottom",
        "always_visible": True
      },
      updatemode='mouseup'
    ),
],
style = {
  'margin-bottom' : '10px',
},
id = 'key_deposit_slider_div'
)

key_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties with an unknown key deposit?"),
      dcc.RadioItems(
        id='key_deposit_missing_radio',
        options=[
            {'label': 'Yes', 'value': 'True'},
            {'label': 'No', 'value': 'False'}
        ],
        value='True',
        # add some spacing in between the checkbox and the label
        # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
        inputStyle = {
          "margin-right": "5px",
          "margin-left": "5px"
        },
        inline=True       
        ),
    ],
  color="info",
  ),
],
id = 'unknown_key_deposit_div',
)

other_deposit_slider =  html.Div([
    html.H5("Other Deposit"),
    # Create a range slider for other deposit cost
    dcc.RangeSlider(
      min=df['DepositOther'].min(), # Dynamically calculate the minimum other deposit
      max=df['DepositOther'].max(), # Dynamically calculate the maximum other deposit
      value=[df['DepositOther'].min(), df['DepositOther'].max()], 
      id='other_deposit_slider',
      tooltip={
        "placement": "bottom",
        "always_visible": True
      },
      updatemode='mouseup'
    ),
],
style = {
  'margin-bottom' : '10px',
},
id = 'other_deposit_slider_div'
)

other_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties with an unknown misc/other deposit?"),
      dcc.RadioItems(
        id='other_deposit_missing_radio',
        options=[
            {'label': 'Yes', 'value': 'True'},
            {'label': 'No', 'value': 'False'}
        ],
        value='True',
        # add some spacing in between the checkbox and the label
        # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
        inputStyle = {
          "margin-right": "5px",
          "margin-left": "5px"
        },
        inline=True       
        ),
    ],
  color="info",
  ),
],
id = 'unknown_other_deposit_div',
)

laundry_categories = [
            'Dryer Hookup',
            'Dryer Included',
            'Washer Hookup',
            'Washer Included',
            'Community Laundry',
            'Other',
            'Unknown',
            'None',
        ]

laundry_checklist = html.Div([
  html.H5("Laundry Features"),
  # Create a checklist for laundry features
  dcc.Checklist(
    id='laundry_checklist',
    options=sorted([{'label': i, 'value': i} for i in laundry_categories], key=lambda x: x['label']),
    # Set the default value to all of the options
    value=laundry_categories,
    labelStyle = {'display': 'block'},
    # add some spacing in between the checkbox and the label
    # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
    inputStyle = {
      "margin-right": "5px",
      "margin-left": "5px"
    },
  ),
],
id = 'laundry_checklist_div'
)

# Get today's date and set it as the end date for the date picker
today = date.today()
# Get the earliest date and convert it to to Pythonic datetime for Dash
df['listed_date'] = pd.to_datetime(df['listed_date'], errors='coerce')
earliest_date = (df['listed_date'].min()).to_pydatetime()
listed_date_datepicker = html.Div([
    html.H5("Listed Date Range"),
    # Create a range slider for the listed date
    dcc.DatePickerRange(
      id='listed_date_datepicker',
      max_date_allowed=today,
      start_date=earliest_date,
      end_date=today
    ),
],
id = 'listed_date_datepicker_div'
)

listed_date_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties with an unknown listed date?"),
      dcc.RadioItems(
        id='listed_date_radio',
        options=[
            {'label': 'Yes', 'value': 'True'},
            {'label': 'No', 'value': 'False'}
        ],
        value='True',
        # add some spacing in between the checkbox and the label
        # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
        inputStyle = {
          "margin-right": "5px",
          "margin-left": "5px"
        },
        inline=True     
        ),
    ],
  color="info",
  ),
],
id = 'listed_date_radio_div',
)

# Generate the map
map = dl.Map(
  [dl.TileLayer(), dl.LayerGroup(id="lease_geojson"), dl.FullScreenControl()],
  id='map',
  zoom=9,
  minZoom=9,
  center=(lat_mean, long_mean),
  preferCanvas=True,
  closePopupOnClick=True,
  style={'width': '100%', 'height': '90vh', 'margin': "auto", "display": "inline-block"}
)

# Create a state for the collapsed section in the user options card
collapse_store = dcc.Store(id='collapse-store', data={'is_open': False})

# Create a button to toggle the collapsed section in the user options card
# https://dash-bootstrap-components.opensource.faculty.ai/docs/components/collapse/
more_options = dbc.Collapse(
  [
    lease_components.square_footage_slider,
    lease_components.square_footage_radio,
    lease_components.ppsqft_slider,
    lease_components.ppsqft_radio,
    garage_spaces_slider,
    unknown_garage_radio, 
    year_built_slider,
    unknown_year_built_radio,
    lease_components.rental_terms_checklist,
    furnished_checklist,
    laundry_checklist,
    security_deposit_slider,
    security_deposit_radio,
    pet_deposit_slider,
    pet_deposit_radio,
    key_deposit_slider,
    key_deposit_radio,
    other_deposit_slider,
    other_deposit_radio,
  ],
  id='more-options-collapse-lease'
)

# Create a card for the user options
user_options_card = dbc.Card(
  [
    html.P(
      "Use the options below to filter the map "
      "according to your needs.",
      className="card-text",
    ),
    listed_date_datepicker,
    listed_date_radio,
    lease_components.subtype_checklist,
    rental_price_slider,
    lease_components.bedrooms_slider,
    lease_components.bathrooms_slider,
    lease_components.pets_radio,
    dbc.Button("More Options", id='more-options-button-lease', className='mt-2'),
    more_options,
  ],
  body=True
)

map_card = dbc.Card(
    [map], 
    body = True,
    # Make the graph stay in view as the page is scrolled down
    # https://getbootstrap.com/docs/4.0/utilities/position/
    className = 'sticky-top'
)

# Get the latest date of a rental property and then convert it to American date format
# https://pandas.pydata.org/docs/reference/api/pandas.Timestamp.strftime.html
last_updated = df['date_processed'].max().strftime('%m/%d/%Y')

title_card = dbc.Card(
  [
    html.H3("WhereToLive.LA", className="card-title"),
    html.P("An interactive map of available rentals in Los Angeles County. Updated weekly."),
    html.P(f"Last updated: {last_updated}", style={'margin-bottom': '5px'}),
    # Use a GitHub icon for my repo
    html.I(
      className="bi bi-github",
      style = {
        "margin-right": "5px",
      },
    ),
    html.A("GitHub", href='https://github.com/perfectly-preserved-pie/larentals', target='_blank'),
    # Add an icon for my blog
    html.I(
      className="fa-solid fa-blog",
      style = {
        "margin-right": "5px",
        "margin-left": "15px"
      },
    ),
    html.A("About This Project", href='https://automateordie.io/wheretolivedotla/', target='_blank'),
    dbc.Button(
      " Looking to buy a property instead?",
      href="/for-sale",
      color="primary",
      external_link=True,
      className="bi bi-house-door-fill w-100 mt-2",
    ),
  ],
  body = True
)

layout = dbc.Container([
  collapse_store,
  dbc.Row(
    [
      dbc.Col([title_card, user_options_card], lg=3, md=6, sm=4),
      dbc.Col([map_card], lg=9, md=6, sm=8),
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
    Input(component_id='listed_date_radio', component_property='value'),
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