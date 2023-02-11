import dash
from dash import html, dcc, callback
from dash.dependencies import Input, Output
from datetime import date
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_leaflet.express as dlx
import logging
import pandas as pd
import uuid

dash.register_page(
  __name__,
  path='/for-sale',
  name='WhereToLive.LA - For Sale',
  title='WhereToLive.LA - For Sale',
  description='An interactive map of available residential properties for sale in Los Angeles County. Updated weekly.',
)


logging.getLogger().setLevel(logging.INFO)

external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME]

# Make the dataframe a global variable
global df

# import the dataframe pickle file
df = pd.read_pickle(filepath_or_buffer='buy.pickle')
pd.set_option("display.precision", 10)

## FUNCTIONS ##

# Create a function to return a dataframe filter based on if the user provides a Yes/No to the "should we include properties with missing sqft?" question
def sqft_radio_button(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a square footage listed"
    # Then we want nulls to be included in the final dataframe
    sqft_choice = df['Sqft'].isnull()
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    sqft_choice = df.sort_values(by='Sqft')['Sqft'].between(slider_begin, slider_end)
  return (sqft_choice)

# Create a function to return a dataframe filter for missing year built
def yrbuilt_radio_button(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a year built listed"
    # Then we want nulls to be included in the final dataframe
    yrbuilt_choice = df['YrBuilt'].isnull()
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    yrbuilt_choice = df.sort_values(by='YrBuilt')['YrBuilt'].between(slider_begin, slider_end)
  return (yrbuilt_choice)

# Create a function to return a dataframe filter for missing ppqsft
def ppsqft_radio_button(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a garage space listed"
    # Then we want nulls to be included in the final dataframe 
    ppsqft_choice = df['ppsqft'].isnull()
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    ppsqft_choice = df.sort_values(by='ppsqft')['ppsqft'].between(slider_begin, slider_end)
  return (ppsqft_choice)

# Listed Date
def listed_date_function(boolean, start_date, end_date):
  if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
    # Then we want nulls to be included in the final dataframe 
    listed_date_filter = (df['listed_date'].isnull()) | (df['listed_date'].between(start_date, end_date))
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    listed_date_filter = df['listed_date'].between(start_date, end_date)
  return (listed_date_filter)

# Create a function to return a dataframe filter for HOA fee
def hoa_fee_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a HOA fee listed" (NaN)
    # Then we want nulls to be included in the final dataframe 
    hoa_fee_filter = df['hoa_fee'].isnull() | (df.sort_values(by='hoa_fee')['hoa_fee'].between(slider_begin, slider_end))
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    hoa_fee_filter = df.sort_values(by='hoa_fee')['hoa_fee'].between(slider_begin, slider_end)
  return (hoa_fee_filter)

# Create a function to return a dataframe filter for space rent
def space_rent_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a HOA fee listed" (NaN)
    # Then we want nulls to be included in the final dataframe 
    space_rent_filter = df['space_rent'].isnull() | (df.sort_values(by='space_rent')['space_rent'].between(slider_begin, slider_end))
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    space_rent_filter = df.sort_values(by='space_rent')['space_rent'].between(slider_begin, slider_end)
  return (space_rent_filter)

# Create a function to return a dataframe filter for pet policy
def pet_policy_function(choice):
  if choice == 'Yes': # If the user says "yes, I ONLY want properties that allow pets"
    # Then we want every row where the pet policy is NOT "No" or "No, Size Limit"
    pets_radio_choice = ~df['PetsAllowed'].isin(['No', 'No, Size Limit'])
  elif choice == 'No': # If the user says "No, I don't want properties where pets are allowed"
    pets_radio_choice = df['PetsAllowed'].isin(['No', 'No, Size Limit'])
  elif choice == 'Both': # If the user says "I don't care, I want both kinds of properties"
    pets_radio_choice = df['PetsAllowed']
  return (pets_radio_choice)

# Create a function to return a dataframe filter for senior community status
def senior_community_function(choice):
  if choice == 'Yes': # If the user says "yes, I ONLY want properties that allow pets"
    # Then we want every row where the pet policy is NOT "No" or "No, Size Limit"
    senior_community_radio_choice = ~df['SeniorCommunityYN'].isin(['Y'])
  elif choice == 'No': # If the user says "No, I don't want properties where pets are allowed"
    senior_community_radio_choice = df['SeniorCommunityYN'].isin(['N'])
  elif choice == 'Both': # If the user says "I don't care, I want both kinds of properties"
    senior_community_radio_choice = df['SeniorCommunityYN']
  return (senior_community_radio_choice)

## END FUNCTIONS ##

## BEGIN DASH BOOTSTRAP COMPONENTS ##
# Create a checklist for the user to select the subtypes they want to see
subtype_checklist = html.Div([ 
  # Title this section
  html.H5("Subtypes"), 
  # Create a checklist of options for the user
  # https://dash.plotly.com/dash-core-components/checklist
  dcc.Checklist( 
    id = 'subtype_checklist',
    # Loop through the list of subtypes and create a dictionary of options
    options = [{'label': i, 'value': i} for i in df['subtype'].unique()],
    # Set the default values to all of the subtypes
    value = df['subtype'].unique(),
    labelStyle = {'display': 'block'},
    # add some spacing in between the checkbox and the label
    # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
    inputStyle = {
      "margin-right": "5px",
      "margin-left": "5px"
    },
  ),
],
id = 'subtypes_div',
)

bedrooms_slider = html.Div([
  html.H5("Bedrooms"),
  # Create a range slider for # of bedrooms
  dcc.RangeSlider(
    min=0, 
    max=df['Bedrooms'].max(), # Dynamically calculate the maximum number of bedrooms
    step=1, 
    value=[0, df['Bedrooms'].max()], 
    id='bedrooms_slider',
    updatemode='mouseup'
  ),
],
style = {'width' : '70%'},
id = 'bedrooms_div'
)

bathrooms_slider = html.Div([
  html.H5("Bathrooms"),
  # Create a range slider for # of total bathrooms
  dcc.RangeSlider(
    min=0, 
    max=df['Total Bathrooms'].max(), 
    step=1, 
    value=[0, df['Total Bathrooms'].max()], 
    id='bathrooms_slider',
    updatemode='mouseup'
  ),
],
style = {'width' : '70%'}, 
id = 'bathrooms_div'
)

# Create a range slider for square footage
square_footage_slider = html.Div([
  html.H5("Square Footage"),
  dcc.RangeSlider(
    min=df['Sqft'].min(), 
    max=df['Sqft'].max(),
    value=[df['Sqft'].min(), df['Sqft'].max()], 
    id='sqft_slider',
    tooltip={
      "placement": "bottom",
      "always_visible": True
    },
    updatemode='mouseup'
  ),
],
style = {
  'width' : '70%',
  'margin-bottom' : '10px',
}, 
id = 'square_footage_div'
)

square_footage_radio = html.Div([
  dbc.Alert(
  [
    # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
    html.I(className="bi bi-info-circle-fill me-2"),
    ("Should we include properties that don't have a square footage listed?"),
    dcc.RadioItems(
      id='sqft_missing_radio',
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
    ),
  ],
color="info",
),
],
id = 'unknown_sqft_div',
)

# Create a range slider for ppsqft
ppsqft_slider = html.Div([
  html.H5("Price Per Square Foot"),
  dcc.RangeSlider(
    min=df['ppsqft'].min(), 
    max=df['ppsqft'].max(),
    value=[df['ppsqft'].min(), df['ppsqft'].max()], 
    id='ppsqft_slider',
    tooltip={
      "placement": "bottom",
      "always_visible": True
    },
    updatemode='mouseup'
  ),
],
style = {
  'width' : '70%',
  'margin-bottom' : '10px',
},
id = 'ppsqft_div'
)
  
ppsqft_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties that don't have a price per square foot listed?"),
      dcc.RadioItems(
        id='ppsqft_missing_radio',
        options=[
          {'label': 'Yes', 'value': 'True'},
          {'label': 'No', 'value': 'False'}
        ],
        value='True',
        inputStyle = {
          "margin-right": "5px",
          "margin-left": "5px"
        },
      ),
    ],
  color="info",
  ),
],
id = 'unknown_ppsqft_div'
)

pets_radio = html.Div([
  html.H5("Pet Policy"),
  # Create a checklist for pet policy
  dcc.RadioItems(
    id = 'pets_radio',
    options=[
      {'label': 'Pets Allowed', 'value': 'Yes'},
      {'label': 'Pets NOT Allowed', 'value': 'No'},
      {'label': 'Both', 'value': 'Both'}
    ],
    value='Both', # A value needs to be selected upon page load otherwise we error out. See https://community.plotly.com/t/how-to-convert-a-nonetype-object-i-get-from-a-checklist-to-a-list-or-int32/26256/2
    # add some spacing in between the checkbox and the label
    # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
    inputStyle = {
      "margin-right": "5px",
      "margin-left": "5px"
    },    
  ),
],
id = 'pet_policy_div'
)

# Create a slider for HOA fees
hoa_fee_slider = html.Div([
  # Title this section
  html.H5("HOA Fee"),
  # Create a slider for the user to select the range of HOA fees they want to see
  # https://dash.plotly.com/dash-core-components/slider
  dcc.RangeSlider(
    id = 'hoa_fee_slider',
    # Set the min and max values to the min and max of the HOA fee column
    min = df['hoa_fee'].min(),
    max = df['hoa_fee'].max(),
    # Set the default values to the min and max of the HOA fee column
    value = [df['hoa_fee'].min(), df['hoa_fee'].max()],
    # Set the step to 100
    step = 100,
    # Set the marks to be every 1000
    marks = {i: f'{i}' for i in range(df['hoa_fee'].min(), df['hoa_fee'].max(), 1000)},
    # Set the tooltip to be the value of the slider
    tooltip = {'always_visible': True, 'placement': 'bottom'},
  ),
  # Create a radio button for the user to select whether they want to include properties with no HOA fee listed
  # https://dash.plotly.com/dash-core-components/radioitems
  dcc.RadioItems(
    id = 'hoa_fee_radio',
    options = [
      {'label': 'Include properties without an HOA fee listed', 'value': 'True'},
      {'label': 'Exclude properties without an HOA fee listed', 'value': 'False'},
    ],
    value = 'True',
    labelStyle = {'display': 'block'},
    inputStyle = {
      "margin-right": "5px",
      "margin-left": "5px"
    },
  ),
],
id = 'hoa_fee_div',
)

# Create a checklist for HOA fee frequency
hoa_fee_frequency_checklist = html.Div([
  # Title this section
  html.H5("HOA Fee Frequency"),
  # Create a checklist for the user to select the frequency of HOA fees they want to see
  dcc.Checklist(
    id = 'hoa_fee_frequency_checklist',
    # Loop through the list of HOA fee frequencies and create a dictionary of options
    options = [{'label': i, 'value': i} for i in df['hoa_fee_frequency'].unique()],
    # Set the default values to all of the HOA fee frequencies
    value = df['hoa_fee_frequency'].unique(),
    labelStyle = {'display': 'block'},
    inputStyle = {
      "margin-right": "5px",
      "margin-left": "5px"
    },
  ),
],
id = 'hoa_fee_frequency_div',
)

# Create a slider for space rent
space_rent_slider = html.Div([
  # Title this section
  html.H5("Space Rent"),
  # Create a slider for the user to select the range of space rent they want to see
  # https://dash.plotly.com/dash-core-components/slider
  dcc.RangeSlider(
    id = 'space_rent_slider',
    # Set the min and max values to the min and max of the space rent column
    min = df['space_rent'].min(),
    max = df['space_rent'].max(),
    # Set the default values to the min and max of the space rent column
    value = [df['space_rent'].min(), df['space_rent'].max()],
    # Set the step to 100
    step = 100,
    # Set the marks to be every 1000
    marks = {i: f'{i}' for i in range(df['space_rent'].min(), df['space_rent'].max(), 1000)},
    # Set the tooltip to be the value of the slider
    tooltip = {'always_visible': True, 'placement': 'bottom'},
  ),
  # Create a radio button for the user to select whether they want to include properties with no space rent listed
  # https://dash.plotly.com/dash-core-components/radioitems
  dcc.RadioItems(
    id = 'space_rent_radio',
    options = [
      {'label': 'Include properties without a space rent listed', 'value': 'True'},
      {'label': 'Exclude properties without a space rent listed', 'value': 'False'},
    ],
    value = 'True',
    labelStyle = {'display': 'block'},
    inputStyle = {
      "margin-right": "5px",
      "margin-left": "5px"
    },
  ),
],
id = 'space_rent_div',
)

# Create a radio button for Senior Community
senior_community_radio = html.Div([
  # Title this section
  html.H5("Senior Community"),
  # Create a radio button for the user to select whether they want to see properties in Senior Communities
  # https://dash.plotly.com/dash-core-components/radioitems
  dcc.RadioItems(
    id = 'senior_community_radio',
    options = [
      {'label': 'Include properties in Senior Communities', 'value': 'True'},
      {'label': 'Exclude properties in Senior Communities', 'value': 'False'},
    ],
    value = 'True',
    labelStyle = {'display': 'block'},
    inputStyle = {
      "margin-right": "5px",
      "margin-left": "5px"
    },
  ),
],
id = 'senior_community_div',
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
style = {'width' : '70%'}, 
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
  'width' : '70%',
  'margin-bottom' : '10px',
},
id = 'yrbuilt_div'
)

unknown_year_built_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),      
      ("Should we include properties that don't have the year built listed?"),
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
      ),
    ],
  color="info",
  ),
],
id = 'yrbuilt_missing_div'
)

# Get today's date and set it as the end date for the date picker
today = date.today()
# Get the earliest date and convert it to to Pythonic datetime for Dash
df['listed_date'] = pd.to_datetime(df['listed_date'], errors='coerce', infer_datetime_format=True)
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
      ("Should we include properties that don't have a listed date?"),
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
        ),
    ],
  color="info",
  ),
],
id = 'listed_date_radio_div',
)

# Generate the map
# Get the means so we can center the map
lat_mean = df['Latitude'].mean()
long_mean = df['Longitude'].mean()
map = dl.Map(
  [dl.TileLayer(), dl.LayerGroup(id="geojson"), dl.FullscreenControl()],
  id='map',
  zoom=9,
  minZoom=9,
  center=(lat_mean, long_mean),
  preferCanvas=True,
  closePopupOnClick=True,
  style={'width': '100%', 'height': '90vh', 'margin': "auto", "display": "inline-block"}
)

user_options_card = dbc.Card(
  [
    html.P(
      "Use the options below to filter the map "
      "according to your needs.",
      className="card-text",
    ),
    listed_date_datepicker,
    listed_date_radio,
    subtype_checklist,
    rental_price_slider,
    hoa_fee_slider,
    hoa_fee_frequency_checklist,
    space_rent_slider,
    senior_community_radio,
    bedrooms_slider,
    bathrooms_slider,
    square_footage_slider,
    square_footage_radio,
    ppsqft_slider,
    ppsqft_radio,
    year_built_slider,
    unknown_year_built_radio,
    pets_radio,
    pet_deposit_slider,
    pet_deposit_radio,
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


## END OF DASH BOOTSTRAP COMPONENTS ##

title_card = dbc.Card(
  [
    html.H3("WhereToLive.LA", className="card-title"),
    html.P("An interactive map of available residential properties for sale in Los Angeles County. Updated weekly."),
    html.P(f"Last updated: yeah uhhhh lol what"),
    # Add an icon for the for-sale page
    html.I(
        className="fa-building fa",
        style = {
            "margin-right": "5px",
        },
    ),
    html.A("Looking to rent a property instead?", href='/'),
    # Use a GitHub icon for my repo
    html.I(
      className="bi bi-github",
      style = {
        "margin-right": "5px",
        "margin-left": "15px"
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
  ],
  body = True
)

layout = dbc.Container([
  dbc.Row( # First row: title card
    [
      dbc.Col([title_card]),
    ]
  ),
  dbc.Row( # Second row: the rest
    [
      # Use column width properties to dynamically resize the cards based on screen size
      # https://community.plotly.com/t/layout-changes-with-screen-size-and-resolution/27530/6
      dbc.Col([user_options_card], lg = 3, md = 6, sm = 4),
      dbc.Col([map_card], lg = 9, md = 6, sm = 8),
    ],
    # Remove the whitespace/padding between the two cards (aka the gutters)
    # https://stackoverflow.com/a/70495385
    className="g-0",
  ),
],
fluid = True,
className = "dbc"
)

## BEGIN CALLBACKS ##
@callback(
  Output(component_id='geojson', component_property='children'),
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
    Input(component_id='listed_date_datepicker', component_property='start_date'),
    Input(component_id='listed_date_datepicker', component_property='end_date'),
    Input(component_id='listed_date_radio', component_property='value'),
    Input(component_id='laundry_checklist', component_property='value'),
    Input(component_id='hoa_fee_slider', component_property='value'),
    Input(component_id='hoa_fee_frequency_checklist', component_property='value'),
    Input(component_id='space_rent_slider', component_property='value'),
    Input(component_id='senior_community_radio', component_property='value'),
  ]
)
# The following function arguments are positional related to the Inputs in the callback above
# Their order must match
def update_map(subtypes_chosen, pets_chosen, terms_chosen, rental_price, bedrooms_chosen, bathrooms_chosen, sqft_chosen, years_chosen, sqft_missing_radio_choice, yrbuilt_missing_radio_choice, ppsqft_chosen, ppsqft_missing_radio_choice, listed_date_datepicker_start, listed_date_datepicker_end, listed_date_radio, hoa_fee, space_rent, senior_community_radio_choice):
  # Pre-sort our various lists of strings for faster performance
  subtypes_chosen.sort()
  terms_chosen.sort()
  df_filtered = df[
    (df['subtype'].isin(subtypes_chosen)) &
    pet_policy_function(pets_chosen) &
    (df['Terms'].isin(terms_chosen)) &
    # For the slider, we need to filter the dataframe by an integer range this time and not a string like the ones aboves
    # To do this, we can use the Pandas .between function
    # See https://stackoverflow.com/a/40442778
    # Repeat but for rental price
    # Also pre-sort our lists of values to improve the performance of .between()
    (df.sort_values(by='list_price')['list_price'].between(rental_price[0], rental_price[1])) &
    (df.sort_values(by='Bedrooms')['Bedrooms'].between(bedrooms_chosen[0], bedrooms_chosen[1])) &
    (df.sort_values(by='Total Bathrooms')['Total Bathrooms'].between(bathrooms_chosen[0], bathrooms_chosen[1])) &
    ((df.sort_values(by='Sqft')['Sqft'].between(sqft_chosen[0], sqft_chosen[1])) | sqft_radio_button(sqft_missing_radio_choice, sqft_chosen[0], sqft_chosen[1])) &
    ((df.sort_values(by='YrBuilt')['YrBuilt'].between(years_chosen[0], years_chosen[1])) | yrbuilt_radio_button(yrbuilt_missing_radio_choice, years_chosen[0], years_chosen[1])) &
    ((df.sort_values(by='ppsqft')['ppsqft'].between(ppsqft_chosen[0], ppsqft_chosen[1])) | ppsqft_radio_button(ppsqft_missing_radio_choice, ppsqft_chosen[0], ppsqft_chosen[1])) &
    listed_date_function(listed_date_radio, listed_date_datepicker_start, listed_date_datepicker_end) &
    hoa_fee_function(hoa_fee[0], hoa_fee[1]) &
    space_rent_function(space_rent[0], space_rent[1]) &
    senior_community_function(senior_community_radio_choice)
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

  # Log statements to check if we have all markers in the dataframe displayed
  logging.info(f"The original dataframe has {len(df.index)} rows. There are {len(df_filtered.index)} rows in the filtered dataframe. There are {len(markers)} markers on the map.")
  logging.info(f"IMPORTANT! The original dataframe has {df.Latitude.isnull().sum()} rows with a missing Latitude. There are {df_filtered.Latitude.isnull().sum()} rows with a missing Latitude in the filtered dataframe.")
  # Generate the map
  return dl.GeoJSON(
    id=str(uuid.uuid4()),
    data=geojson,
    cluster=True,
    zoomToBoundsOnClick=True,
    superClusterOptions={ # https://github.com/mapbox/supercluster#options
      'radius': 160,
      'minZoom': 3,
    }
  )