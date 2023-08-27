from dash import html, dcc, callback
from dash_extensions.javascript import Namespace
from dash.dependencies import Input, Output
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
  path='/for-sale',
  name='WhereToLive.LA - For Sale',
  title='WhereToLive.LA - For Sale',
  description='An interactive map of available residential properties for sale in Los Angeles County. Updated weekly.',
)


logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME]

# Make the dataframe a global variable
global df

# import the dataframe 
df = pd.read_parquet(path='datasets/buy.parquet')
pd.set_option("display.precision", 10)

## FUNCTIONS ##

# Create a function to return a dataframe filter based on if the user provides a Yes/No to the "should we include properties with missing sqft?" question
def sqft_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a square footage listed"
    # Then we want nulls to be included in the final dataframe
    sqft_choice = df['Sqft'].isnull() | df.sort_values(by='Sqft')['Sqft'].between(slider_begin, slider_end)
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    sqft_choice = df.sort_values(by='Sqft')['Sqft'].between(slider_begin, slider_end)
  return (sqft_choice)

# Create a function to return a dataframe filter for missing year built
def yrbuilt_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a year built listed"
    # Then we want nulls to be included in the final dataframe
    yrbuilt_filter = df['year_built'].isnull() | df.sort_values(by='year_built')['year_built'].between(slider_begin, slider_end)
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    yrbuilt_filter = df.sort_values(by='year_built')['year_built'].between(slider_begin, slider_end)
  return (yrbuilt_filter)

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
    hoa_fee_filter = (df['hoa_fee'].isnull()) | (df.sort_values(by='hoa_fee')['hoa_fee'].between(slider_begin, slider_end))
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    hoa_fee_filter = df.sort_values(by='hoa_fee')['hoa_fee'].between(slider_begin, slider_end)
  return (hoa_fee_filter)

# Create a function to return a dataframe filter for HOA fee frequency
def hoa_fee_frequency_function(choice):
  # If the selection is "N/A" only, then we want to return a filter that contains all nulls
  if 'N/A' in choice and len(choice) == 1:
    hoa_fee_frequency_filter = df['hoa_fee_frequency'].isnull()
  # If the selection is "Monthly" only, then we want to return a filter that contains all "Monthly" values
  elif 'Monthly' in choice and len(choice) == 1:
    hoa_fee_frequency_filter = df['hoa_fee_frequency'].str.contains('Monthly')
  # If there is more than 1 selection, then we want to return a filter that contains all nulls and "Monthly" values
  elif len(choice) > 1:
    hoa_fee_frequency_filter = df['hoa_fee_frequency'].isnull() | df['hoa_fee_frequency'].str.contains('Monthly')
  return (hoa_fee_frequency_filter)

# Create a function to return a dataframe filter for space rent
def space_rent_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a HOA fee listed" (NaN)
    # Then we want nulls to be included in the final dataframe 
    space_rent_filter = df['space_rent'].isnull() | (df.sort_values(by='space_rent')['space_rent'].between(slider_begin, slider_end))
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    space_rent_filter = df.sort_values(by='space_rent')['space_rent'].between(slider_begin, slider_end)
  return (space_rent_filter)

# Create a function to return a dataframe filter for pet policy
def pet_policy_function(choice, subtype_selected):
  # If MH isn't selected, return every row where the pet policy is Yes, No, or null since it doesn't matter
  if 'MH' not in subtype_selected:
    pets_radio_choice = df['pets_allowed'].notnull() | df['pets_allowed'].isnull()
  # If MH is the only subtype selected and they want pets then we want every row where the pet policy DOES NOT contain "No"
  elif 'MH' in subtype_selected and choice == 'True' and len(subtype_selected) == 1:
    pets_radio_choice = ~df['pets_allowed'].str.contains('No')
  # If MH is the only subtype selected and they DON'T want pets then we want every row where the pet policy DOES NOT contain "No"
  elif 'MH' in subtype_selected and choice == 'False' and len(subtype_selected) == 1:
    pets_radio_choice = df['pets_allowed'].str.contains('No')
  # If the user says "I don't care, I want both kinds of properties"
  # Return every row where the pet policy is Yes or No
  elif 'MH' in subtype_selected and choice == 'Both' and len(subtype_selected) == 1: 
    pets_radio_choice = (~df['pets_allowed'].str.contains('No')) | (df['pets_allowed'].str.contains('No'))
  # If more than one subtype is selected and MH is one of them AND they want pets, return every row where the pet policy DOES contain "Yes" or is null
  elif 'MH' in subtype_selected and choice == 'True' and len(subtype_selected) > 1:
    pets_radio_choice = (~df['pets_allowed'].str.contains('No')) | df['pets_allowed'].isnull()
  # If more than one subtype is selected and MH is one of them AND they DON'T want pets, return every row where the pet policy DOES contain "No" or is null
  elif 'MH' in subtype_selected and choice == 'False' and len(subtype_selected) > 1:
    pets_radio_choice = (df['pets_allowed'].str.contains('No')) | df['pets_allowed'].isnull()
  # If more than one subtype is selected and MH is one of them AND they choose Both, return every row that is null OR non-null
  elif 'MH' in subtype_selected and choice == 'Both' and len(subtype_selected) > 1:
    pets_radio_choice = df['pets_allowed'].isnull() | df['pets_allowed'].notnull()
  return (pets_radio_choice)

# Create a function to return a dataframe filter for senior community status
def senior_community_function(choice, subtype_selected):
  # If MH isn't selected, return every row where the pet policy is Yes, No, or null since it doesn't matter
  if 'MH' not in subtype_selected:
    senior_community_choice = df['senior_community'].notnull() | df['senior_community'].isnull()
  # If MH is the only subtype selected and they want a senior community then we want every row where the senior community DOES contain "Y"
  elif 'MH' in subtype_selected and choice == 'True' and len(subtype_selected) == 1:
    senior_community_choice = df['senior_community'].str.contains('Y')
  # If MH is the only subtype selected and they DON'T want a senior community then we want every row where the senior community DOES contain "N"
  elif 'MH' in subtype_selected and choice == 'False' and len(subtype_selected) == 1:
    senior_community_choice = df['senior_community'].str.contains('N')
  # If the user says "I don't care, I want both kinds of properties"
  # Return every row where the pet policy is Yes or No
  elif 'MH' in subtype_selected and choice == 'Both' and len(subtype_selected) == 1: 
    senior_community_choice = (df['senior_community'].str.contains('N')) | (df['senior_community'].str.contains('Y')) 
  # If more than one subtype is selected and MH is one of them AND they want a senior community, return every row where the senior community DOES contain "Y" or is null
  elif 'MH' in subtype_selected and choice == 'True' and len(subtype_selected) > 1:
    senior_community_choice = (df['senior_community'].str.contains('Y')) | df['pets_allowed'].isnull()
  # If more than one subtype is selected and MH is one of them AND they DON'T want a senior community, return every row where the senior community DOES contain "N" or is null
  elif 'MH' in subtype_selected and choice == 'False' and len(subtype_selected) > 1:
    senior_community_choice = (df['senior_community'].str.contains('N')) | df['pets_allowed'].isnull()
  # If more than one subtype is selected and MH is one of them AND they choose Both, return every row that is null OR non-null
  elif 'MH' in subtype_selected and choice == 'Both' and len(subtype_selected) > 1:
    senior_community_choice = df['senior_community'].isnull() | df['senior_community'].notnull()
  return (senior_community_choice)

## END FUNCTIONS ##

## BEGIN DASH BOOTSTRAP COMPONENTS ##
# Define a dictionary that maps each subtype to its corresponding meaning
subtype_meaning = {
  'CONDO': 'Condo (Unspecified)',
  'CONDO/A': 'Condo (Attached)',
  'CONDO/D': 'Condo (Detached)',
  'MH': 'Mobile Home',
  'SFR': 'Single Family Residence (Unspecified)',
  'SFR/A': 'Single Family Residence (Attached)',
  'SFR/D': 'Single Family Residence (Detached)',
  'TWNHS': 'Townhouse (Unspecified)',
  'TWNHS/A': 'Townhouse (Attached)',
  'TWNHS/D': 'Townhouse (Detached)',
  'Unknown': 'Unknown'
}
# Create a checklist for the user to select the subtypes they want to see
subtype_checklist = html.Div([ 
  # Title this section
  html.H5("Subtypes"), 
  # Create a checklist of options for the user
  # https://dash.plotly.com/dash-core-components/checklist
  dcc.Checklist( 
    id = 'subtype_checklist',
    # Loop through the list of subtypes and create a dictionary of options
    options = sorted(
    [
        {
            'label': f"{i if not pd.isna(i) else 'Unknown'} - {subtype_meaning.get(i if not pd.isna(i) else 'Unknown', 'Unknown')}", 
            'value': i if not pd.isna(i) else 'Unknown'
        }
        for i in df['subtype'].unique()
    ], 
    key=lambda x: x['label']
    ), 
    # Set the default values to all of the subtypes while handling nulls
    value = [i if not pd.isna(i) else 'Unknown' for i in df['subtype'].unique()],
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
    updatemode='mouseup',
    tooltip={
      "placement": "bottom",
      "always_visible": True
    },
  ),
],
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
    updatemode='mouseup',
    tooltip={
      "placement": "bottom",
      "always_visible": True
    },
  ),
],
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
  'margin-bottom' : '10px',
}, 
id = 'square_footage_div'
)

square_footage_radio = html.Div([
  dbc.Alert(
  [
    # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
    html.I(className="bi bi-info-circle-fill me-2"),
    ("Should we include properties with an unknown square footage?"),
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
      inline=True
    ),
  ],
color="info",
),
],
id = 'unknown_sqft_div',
)

# Create a range slider for ppsqft
ppsqft_slider = html.Div([
  html.H5("Price Per Square Foot ($)"),
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
  'margin-bottom' : '10px',
},
id = 'ppsqft_div'
)
  
ppsqft_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties with an unknown price per square foot?"),
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
        inline=True
      ),
    ],
  color="info",
  ),
],
id = 'unknown_ppsqft_div'
)

pets_radio = html.Div([
  html.H5("Pet Policy"),
  html.H6([html.Em("Applies only to Mobile Homes (MH).")]),
  # Create a radio button for pet policy
  dcc.RadioItems(
    id = 'pets_radio',
    options=[
      {'label': 'Pets Allowed', 'value': 'True'},
      {'label': 'Pets NOT Allowed', 'value': 'False'},
      {'label': 'Both', 'value': 'Both'},
    ],
    value='Both', # A value needs to be selected upon page load otherwise we error out. See https://community.plotly.com/t/how-to-convert-a-nonetype-object-i-get-from-a-checklist-to-a-list-or-int32/26256/2
    # add some spacing in between the checkbox and the label
    # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
    inputStyle = {
      "margin-right": "5px",
      "margin-left": "5px"
    },
    inline=True  
  ),
],
id = 'pet_policy_div'
)

# Create a slider for HOA fees
hoa_fee_slider = html.Div([
  # Title this section
  html.H5("HOA Fee"),
  html.H6([html.Em("Applies only to SFR and CONDO/TWNHS.")]),
  # Create a slider for the user to select the range of HOA fees they want to see
  # https://dash.plotly.com/dash-core-components/slider
  dcc.RangeSlider(
    id = 'hoa_fee_slider',
    # Set the min and max values to the min and max of the HOA fee column
    min = df['hoa_fee'].min(),
    max = df['hoa_fee'].max(),
    # Set the default values to the min and max of the HOA fee column
    value = [df['hoa_fee'].min(), df['hoa_fee'].max()],
    # Set the tooltip to be the value of the slider
    tooltip = {'always_visible': True, 'placement': 'bottom'},
  ),
  # Create a radio button for the user to select whether they want to include properties with no HOA fee listed
  # https://dash.plotly.com/dash-core-components/radioitems
],
style = {
  'margin-bottom' : '10px',
},
id = 'hoa_fee_div',
)

hoa_fee_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties with an unknown HOA fee?"),
      dcc.RadioItems(
        id='hoa_fee_missing_radio',
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
id = 'unknown_hoa_fee_div'
)

# Create a checklist for HOA fee frequency
hoa_fee_frequency_checklist = html.Div([
  # Title this section
  html.H5("HOA Fee Frequency"),
  html.H6([html.Em("Applies only to SFR and CONDO/TWNHS.")]),
  # Create a checklist for the user to select the frequency of HOA fees they want to see
  dcc.Checklist(
    id = 'hoa_fee_frequency_checklist',
    options=[
      {'label': 'N/A', 'value': 'N/A'},
      {'label': 'Monthly', 'value': 'Monthly'}
    ],
    # Set the value to all of the values in options
    value = ['N/A', 'Monthly'],
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
  html.H6([html.Em("Applies only to Mobile Homes (MH).")]),
  # Create a slider for the user to select the range of space rent they want to see
  # https://dash.plotly.com/dash-core-components/slider
  dcc.RangeSlider(
    id = 'space_rent_slider',
    # Set the min and max values to the min and max of the space rent column
    min = df['space_rent'].min(),
    max = df['space_rent'].max(),
    # Set the default values to the min and max of the space rent column
    value = [df['space_rent'].min(), df['space_rent'].max()],
    # Set the tooltip to be the value of the slider
    tooltip = {'always_visible': True, 'placement': 'bottom'},
  ),
],
style = {
  'margin-bottom' : '10px',
},
id = 'space_rent_div',
)

# Create a radio button for the user to select whether they want to include properties with no space rent listed
# https://dash.plotly.com/dash-core-components/radioitems
space_rent_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties with an unknown space rent?"),
      dcc.RadioItems(
        id='space_rent_missing_radio',
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
id = 'unknown_space_rent_div'
)

# Create a radio button for the user to select whether they want to see properties in Senior Communities
# https://dash.plotly.com/dash-core-components/radioitems
senior_community_radio = html.Div([
  html.H5("Senior Community"),
  html.H6([html.Em("Applies only to Mobile Homes (MH).")]),
  dcc.RadioItems(
    id = 'senior_community_radio',
    options=[
      {'label': 'Yes', 'value': 'True'},
      {'label': 'No', 'value': 'False'},
      {'label': 'Both', 'value': 'Both'},
    ],
    value='Both',
    # add some spacing in between the checkbox and the label
    # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
    inputStyle = {
      "margin-right": "5px",
      "margin-left": "5px"
    },
    inline=True   
  ),
],
id = 'senior_community_div'
)

rental_price_slider = html.Div([ 
    html.H5("List Price"),
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
style = {
  'margin-bottom' : '10px',
},
id = 'price_div'
)

year_built_slider = html.Div([
    html.H5("Year Built"),
    # Create a range slider for year built
    dcc.RangeSlider(
      min=df['year_built'].min(),
      max=df['year_built'].max(),
      value=[0, df['year_built'].max()],
      id='yrbuilt_slider',
      tooltip={
        "placement": "bottom",
        "always_visible": True
      },
      marks = { # Create custom tick marks
          # The left column should be floats, the right column should be strings
          f"{df['year_built'].min()}": f"{df['year_built'].min()}", # first mark is oldest house
          float(f"{df['year_built'].min()}") + 20: str(float(f"{df['year_built'].min()}") + 20), # next mark is oldest house + 20 years
          float(f"{df['year_built'].min()}") + 40: str(float(f"{df['year_built'].min()}") + 40),
          float(f"{df['year_built'].min()}") + 60: str(float(f"{df['year_built'].min()}") + 60),
          float(f"{df['year_built'].min()}") + 80: str(float(f"{df['year_built'].min()}") + 80),
          float(f"{df['year_built'].min()}") + 100: str(float(f"{df['year_built'].min()}") + 100),
          float(f"{df['year_built'].min()}") + 120: str(float(f"{df['year_built'].min()}") + 120),
          float(f"{df['year_built'].min()}") + 140: str(float(f"{df['year_built'].min()}") + 140),
          f"{df['year_built'].max()}": str(f"{df['year_built'].max()}") # last mark is newest house
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
# Get the means so we can center the map
lat_mean = df['Latitude'].mean()
long_mean = df['Longitude'].mean()
map = dl.Map(
  [dl.TileLayer(), dl.LayerGroup(id="buy_geojson"), dl.FullScreenControl()],
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
    hoa_fee_radio,
    hoa_fee_frequency_checklist,
    space_rent_slider,
    space_rent_radio,
    bedrooms_slider,
    bathrooms_slider,
    square_footage_slider,
    square_footage_radio,
    ppsqft_slider,
    ppsqft_radio,
    year_built_slider,
    unknown_year_built_radio,
    pets_radio,
    senior_community_radio,
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
      " Looking to rent a property instead?",
      href="/",
      color="primary",
      external_link=True,
      className="bi bi-building-fill w-100 mt-2",
    ),
  ],
  body = True
)

layout = dbc.Container([
  dbc.Row( # First row: title card
    [
      dbc.Col([title_card, user_options_card], lg=3, md=6, sm=4),
      dbc.Col([map_card], lg=9, md=6, sm=8),
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
@callback(Output('senior_community_div', 'style'), Input('selected_subtype', 'data'))
def update_senior_community_div(selected_subtype):
  if 'MH' in selected_subtype:
    return {'display': 'block'}
  else:
    return {'display': 'none'}
    
# Define callback to update the style property of the pet policy div based on the selected subtype value
@callback(Output('pet_policy_div', 'style'), Input('selected_subtype', 'data'))
def update_pet_policy_div(selected_subtype):
  if 'MH' in selected_subtype:
    return {'display': 'block'}
  else:
    return {'display': 'none'}
  
# Define callback to update the style property of the space rent div based on the selected subtype value
@callback(Output('space_rent_div', 'style'), Input('selected_subtype', 'data'))
def update_space_rent_div(selected_subtype):
  if 'MH' in selected_subtype:
    return {
      'display': 'block',
      'margin-bottom' : '10px',
    }
  else:
    return {'display': 'none'}
  
# Define callback to update the style property of the unknown space rent div based on the selected subtype value
@callback(Output('unknown_space_rent_div', 'style'), Input('selected_subtype', 'data'))
def update_unknown_space_rent_div(selected_subtype):
  if 'MH' in selected_subtype:
    return {'display': 'block'}
  else:
    return {'display': 'none'}
  
# Define callback to update the style property of the HOA Fee div based on the selected subtype value
@callback(Output('hoa_fee_div', 'style'), Input('selected_subtype', 'data'))
def update_hoa_fee_div(selected_subtype):
  if 'MH' in selected_subtype and len(selected_subtype) == 1:
    return {
      'display': 'none',
    }
  else:
    return {
      'display': 'block',
      'margin-bottom' : '10px',
    }

# Define callback to update the style property of the missing HOA Fee div based on the selected subtype value
@callback(Output('unknown_hoa_fee_div', 'style'), Input('selected_subtype', 'data'))
def update_unknown_hoa_fee_div(selected_subtype):
  if 'MH' in selected_subtype and len(selected_subtype) == 1:
    return {
      'display': 'none',
    }
  else:
    return {
      'display': 'block',
      'margin-bottom' : '10px',
    }
  
# Define callback to update the style property of the HOA Fee frequency div based on the selected subtype value
@callback(Output('hoa_fee_frequency_div', 'style'), Input('selected_subtype', 'data'))
def update_hoa_fee_frequency_div(selected_subtype):
  if 'MH' in selected_subtype and len(selected_subtype) == 1:
    return {
      'display': 'none',
    }
  else:
    return {
      'display': 'block',
      'margin-bottom' : '10px',
    }
  
@callback(
  Output(component_id='buy_geojson', component_property='children'),
  [
    Input(component_id='subtype_checklist', component_property='value'),
    Input(component_id='pets_radio', component_property='value'),
    Input(component_id='rental_price_slider', component_property='value'),
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
    Input(component_id='listed_date_radio', component_property='value'),
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
    (df['subtype'].isin(subtypes_chosen)) &
    pet_policy_function(pets_chosen, subtypes_chosen) &
    # For the slider, we need to filter the dataframe by an integer range this time and not a string like the ones aboves
    # To do this, we can use the Pandas .between function
    # See https://stackoverflow.com/a/40442778
    # Repeat but for rental price
    # Also pre-sort our lists of values to improve the performance of .between()
    (df.sort_values(by='list_price')['list_price'].between(rental_price[0], rental_price[1])) &
    (df.sort_values(by='Bedrooms')['Bedrooms'].between(bedrooms_chosen[0], bedrooms_chosen[1])) &
    (df.sort_values(by='Total Bathrooms')['Total Bathrooms'].between(bathrooms_chosen[0], bathrooms_chosen[1])) &
    sqft_function(sqft_missing_radio_choice, sqft_chosen[0], sqft_chosen[1]) &
    yrbuilt_function(yrbuilt_missing_radio_choice, years_chosen[0], years_chosen[1]) &
    ((df.sort_values(by='ppsqft')['ppsqft'].between(ppsqft_chosen[0], ppsqft_chosen[1])) | ppsqft_radio_button(ppsqft_missing_radio_choice, ppsqft_chosen[0], ppsqft_chosen[1])) &
    listed_date_function(listed_date_radio, listed_date_datepicker_start, listed_date_datepicker_end) &
    hoa_fee_function(hoa_fee_radio, hoa_fee[0], hoa_fee[1]) &
    hoa_fee_frequency_function(hoa_fee_frequency_chosen) &
    space_rent_function(space_rent_radio, space_rent[0], space_rent[1]) &
    senior_community_function(senior_community_radio_choice, subtypes_chosen)
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
    #options=dict(onEachFeature=ns("on_each_feature"))
  )