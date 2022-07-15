from jupyter_dash import JupyterDash
import dash_core_components as dcc
from dash.dependencies import Input, Output
from dash import dcc
import dash_html_components as html
import dash_leaflet as dl
import pandas as pd
from geopy.geocoders import GoogleV3
from dotenv import load_dotenv, find_dotenv
import os
import uuid
import requests
from bs4 import BeautifulSoup as bs4
import dash_bootstrap_components as dbc
from functions import *

load_dotenv(find_dotenv())
g = GoogleV3(api_key=os.getenv('GOOGLE_API_KEY')) # https://github.com/geopy/geopy/issues/171

#external_stylesheets=[dbc.themes.DARKLY]
external_stylesheets = [dbc.themes.DARKLY]

# Make the dataframe a global variable
global df

# import the csv
# Don't round the float. See https://stackoverflow.com/a/68027847
df = pd.read_csv("larentals.csv", float_precision="round_trip")
pd.set_option("display.precision", 10)

# Drop all rows that don't have a city. Fuck this shit I'm too lazy to code around bad data input.
df = df[df['City'].notna()]

# Drop all rows that don't have a MLS Listing ID (aka misc data we don't care about)
# https://stackoverflow.com/a/13413845
df = df[df['Listing ID (MLS#)'].notna()]

# Create a new column with the Street Number & Street Name
df["Short Address"] = df["St#"] + ' ' + df["St Name"].str.strip() + ',' + ' ' + df['City']

# Filter the dataframe and return only rows with a NaN postal code
# For some reason some Postal Codes are "Assessor" :| so we need to include that string in an OR operation
# Then iterate through this filtered dataframe and input the right info we get using geocoding
for row in df.loc[(df['PostalCode'].isnull()) | (df['PostalCode'] == 'Assessor')].itertuples():
    missing_postalcode = return_postalcode(df.loc[(df['PostalCode'].isnull()) | (df['PostalCode'] == 'Assessor')].at[row.Index, 'Short Address'])
    df.at[row.Index, 'PostalCode'] = missing_postalcode

# Iterate through the dataframe and get the listed date
for row in df.itertuples():
    mls_number = row[1]
    df.at[row.Index, 'Listed Date'] = get_listed_date(f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/")

# Now that we have street addresses and postal codes, we can put them together
# Create a new column with the full street address
# Also strip whitespace from the St Name column
df["Full Street Address"] = df["St#"] + ' ' + df["St Name"].str.strip() + ',' + ' ' + df['City'] + ' ' + df["PostalCode"]

# Fetch coordinates for every row
for row in df.itertuples():
    coordinates = return_coordinates(df.at[row.Index, 'Full Street Address'])
    df.at[row.Index, 'Latitude'] = coordinates[0]
    df.at[row.Index, 'Longitude'] = coordinates[1]
    df.at[row.Index, 'Coordinates'] = coordinates[2]

# Add an extra column for simply saying either Yes or No if pets are allowed
# We need this because there are many ways of saying "Yes":
# i.e "Call", "Small Dogs OK", "Breed Restrictions", "Cats Only", etc.
# To be used later in the Dash callback function
for row in df.itertuples():
    if row.PetsAllowed != 'No':
        df.at[row.Index, "PetsAllowedSimple"] = 'True'
    elif row.PetsAllowed == 'No' or row.PetsAllowed == 'No, Size Limit':
        df.at[row.Index, "PetsAllowedSimple"] = 'False'

# Remove the leading $ symbol and comma in the cost field
df['L/C Price'] = df['L/C Price'].str.replace("$","").str.replace(",","")
# Remove the leading $ symbol in the ppsqft field
df['Price Per Square Foot'] = df['Price Per Square Foot'].str.replace("$","")

# Split the Bedroom/Bathrooms column into separate columns based on delimiters
# Based on the example given in the spreadsheet: 2 (beds) / 1 (total baths),1 (full baths) ,0 (half bath), 0 (three quarter bath)
# Realtor logic based on https://www.realtor.com/advice/sell/if-i-take-out-the-tub-does-a-bathroom-still-count-as-a-full-bath/
# TIL: A full bathroom is made up of four parts: a sink, a shower, a bathtub, and a toilet. Anything less than that, and you can’t officially consider it a full bath.
df['Bedrooms'] = df['Br/Ba'].str.split('/', expand=True)[0]
df['Total Bathrooms'] = (df['Br/Ba'].str.split('/', expand=True)[1]).str.split(',', expand=True)[0]
df['Full Bathrooms'] = (df['Br/Ba'].str.split('/', expand=True)[1]).str.split(',', expand=True)[1]
df['Half Bathrooms'] = (df['Br/Ba'].str.split('/', expand=True)[1]).str.split(',', expand=True)[2]
df['Three Quarter Bathrooms'] = (df['Br/Ba'].str.split('/', expand=True)[1]).str.split(',', expand=True)[3]

# Remove the square footage & YrBuilt abbreviations
df['Sqft'] = df['Sqft'].str.split('/').str[0]
df['YrBuilt'] = df['YrBuilt'].str.split('/').str[0]

# Convert a few columns into integers 
# To prevent weird TypeError shit like TypeError: '>=' not supported between instances of 'str' and 'int'
df['L/C Price'] = df['L/C Price'].apply(pd.to_numeric)
df['Bedrooms'] = df['Bedrooms'].apply(pd.to_numeric)
df['Total Bathrooms'] = df['Total Bathrooms'].apply(pd.to_numeric)
df['PostalCode'] = df['PostalCode'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['Sqft'] = df['Sqft'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['YrBuilt'] = df['YrBuilt'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['Price Per Square Foot'] = df['Price Per Square Foot'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['Garage Spaces'] = df['Garage Spaces'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['Latitude'] = df['Latitude'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['Longitude'] = df['Longitude'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
# Keep rows with less than 6 bedrooms
# 6 bedrooms and above are probably multi family investments and not actual rentals
# And skew the outliers, causing the sliders to go way up
df = df[df.Bedrooms < 6]

# Reindex the dataframe
df.reset_index(drop=True, inplace=True)

# Create markers & associated popups from dataframe
markers = [dl.Marker(children=dl.Popup(popup_html(row)), position=[row.Latitude, row.Longitude]) for row in df.itertuples()]

# Get the means so we can center the map
lat_mean = df['Latitude'].mean()
long_mean = df['Longitude'].mean()

# Add them to a MarkerCluster
cluster = dl.MarkerClusterGroup(id="markers", children=markers)

app = JupyterDash(__name__, external_stylesheets=external_stylesheets)

subtype_checklist = html.Div([ 
      # Title this section
      html.H5("Subtypes"), 
      # Create a checklist of options for the user
      # https://dash.plotly.com/dash-core-components/checklist
      dcc.Checklist( 
          id = 'subtype_checklist',
          options=[
            {'label': 'Apartment (Unspecified)', 'value': 'APT'},
            {'label': 'Apartment (Attached)', 'value': 'APT/A'},
            {'label': 'Studio (Attached)', 'value': 'STUD/A'},
            {'label': 'Single Family Residence (Unspecified)', 'value': 'SFR'},
            {'label': 'Single Family Residence (Attached)', 'value': 'SFR/A'},
            {'label': 'Single Family Residence (Detached)', 'value': 'SFR/D'},
            {'label': 'Condo (Unspecified)', 'value': 'CONDO'},
            {'label': 'Condo (Attached)', 'value': 'CONDO/A)'},
            {'label': 'Condo (Detached)', 'value': 'CONDO/D'},
            {'label': 'Quadplex (Attached)', 'value': 'QUAD/A'},
            {'label': 'Quadplex (Detached)', 'value': 'QUAD/D'},
            {'label': 'Triplex (Attached)', 'value': 'TPLX/A'},
            {'label': 'Townhouse (Attached)', 'value': 'TWNHS/A'},
            {'label': 'Townhouse (Detached)', 'value': 'TWNHS/D'},
            {'label': 'Duplex (Attached)', 'value': 'DPLX/A'},
            {'label': 'Duplex (Detached)', 'value': 'DPLX/D'},
            {'label': 'Ranch House (Detached)', 'value': 'RMRT/D'}
          ],
          value=['APT/A'], # Set the default value
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
      updatemode='drag'
    ),
  ],
  style = {'width' : '40%'},
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
      updatemode='drag'
    ),
  ],
  style = {'width' : '40%'}, 
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
      updatemode='drag'
    ),
  ],
  style = {'width' : '40%'}, 
  id = 'square_footage_div'
  )

square_footage_radio = html.Div([
    html.H6("Include properties with an unknown square footage?"),
    html.P("⚠ Some properties aren't listed with a square footage for various reasons. Do you want to include them in your search?"),
    dcc.RadioItems(
      id='sqft_missing_radio',
      options=[
          {'label': 'Yes', 'value': 'True'},
          {'label': 'No', 'value': 'False'}
      ],
      value='True'
    ),
  ],
  id = 'unknown_sqft_div'
  )

# Create a range slider for ppsqft
ppsqft_slider = html.Div([
    html.H5("Price Per Square Foot"),
    dcc.RangeSlider(
      min=df['Price Per Square Foot'].min(), 
      max=df['Price Per Square Foot'].max(),
      value=[df['Price Per Square Foot'].min(), df['Price Per Square Foot'].max()], 
      id='ppsqft_slider',
      tooltip={
        "placement": "bottom",
        "always_visible": True
      },
      updatemode='drag'
    ),
  ],
  style = {'width' : '40%'}, 
  id = 'ppsqft_div'
  )
  
ppsqft_radio = html.Div([
    html.H6("Include properties with an unknown price per square footage?"),
    html.P("⚠ Some properties aren't listed with a price square footage for various reasons. Do you want to include them in your search?"),
    dcc.RadioItems(
      id='ppsqft_missing_radio',
      options=[
          {'label': 'Yes', 'value': 'True'},
          {'label': 'No', 'value': 'False'}
      ],
      value='True'
    ),
  ],
  id = 'unknown_ppsqft_div'
  )

pets_slider = html.Div([
    html.H5("Pet Policy"),
    # Create a checklist for pet policy
    dcc.Checklist(
      id = 'pets_checklist',
      options=[
        {'label': 'Pets Allowed', 'value': 'True'},
        {'label': 'Pets NOT Allowed', 'value': 'False'}
      ],
        value=['True', 'False'] # A value needs to be selected upon page load otherwise we error out. See https://community.plotly.com/t/how-to-convert-a-nonetype-object-i-get-from-a-checklist-to-a-list-or-int32/26256/2
    ),
  ],
  id = 'pet_policy_div'
  )

rental_terms_slider = html.Div([
    html.H5("Lease Length"),
    # Create a checklist for rental terms
    dcc.Checklist(
      id = 'terms_checklist',
      options = [
        {'label': 'Monthly', 'value': 'MO'},
        {'label': '12 Months', 'value': '12M'},
        {'label': '24 Months', 'value': '24M'},
        {'label': 'Negotiable', 'value': 'NG'}
      ],
        value=['MO', '12M', '24M', 'NG']
    ),
  ],
  id = 'rental_terms_div'
  )

garage_spaces_slider =  html.Div([
    html.H5("Garage Spaces"),
    # Create a range slider for # of garage spaces
    dcc.RangeSlider(
      min=0, 
      max=df['Garage Spaces'].max(), # Dynamically calculate the maximum number of garage spaces
      step=1, 
      value=[0, df['Garage Spaces'].max()], 
      id='garage_spaces_slider',
      updatemode='drag'
    ),
  ],
  style = {'width' : '40%'}, 
  id = 'garage_div'
  )

unknown_sqft_radio = html.Div([
    html.H6("Include properties with unknown garage spaces?"),
    html.P("⚠ Some properties aren't listed with garage spaces for various reasons. Do you want to include them in your search?"),
    dcc.RadioItems(
      id='garage_missing_radio',
      options=[
          {'label': 'Yes', 'value': 'True'},
          {'label': 'No', 'value': 'False'}
      ],
      value='True'
    ),
  ],
  id = 'unknown_garage_spaces_div'
  )

rental_price_slider = html.Div([ 
    html.H5("Price (Monthly)"),
    # Create a range slider for rental price
    dcc.RangeSlider(
      min=df['L/C Price'].min(),
      max=df['L/C Price'].max(),
      value=[0, df['L/C Price'].max()],
      id='rental_price_slider',
      tooltip={
        "placement": "bottom",
        "always_visible": True
      },
      updatemode='drag'
    ),
  ],
  style = {'width' : '40%'}, 
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
      updatemode='drag'
    ),
  ],
  style = {'width' : '40%'}, 
  id = 'yrbuilt_div'
  )

unknown_year_built_radio = html.Div([
    html.H6("Include properties with an unknown year built?"),
    html.P("⚠ Some properties aren't listed with a year built for various reasons. Do you want to include them in your search?"),
    dcc.RadioItems(
      id='yrbuilt_missing_radio',
      options=[
          {'label': 'Yes', 'value': 'True'},
          {'label': 'No', 'value': 'False'}
      ],
      value='True'
    ),
  ],
  id = 'yrbuilt_missing_div'
  )

# Generate the map
map = dl.Map(
  [dl.TileLayer(), dl.LayerGroup(id="cluster")],
  id='map',
  zoom=9,
  minZoom=9,
  center=(lat_mean, long_mean),
  style={'width': '100%', 'height': '50vh', 'margin': "auto", "display": "inline-block"}
)


user_options_card = dbc.Card(
  [
    subtype_checklist,
    bedrooms_slider,
    bathrooms_slider,
    square_footage_slider,
    square_footage_radio,
    ppsqft_slider,
    ppsqft_radio,
    pets_slider,
    rental_terms_slider,
    garage_spaces_slider,
    unknown_sqft_radio,
    rental_price_slider,
    year_built_slider,
    unknown_year_built_radio
  ],
  body=True
)

map_card = dbc.Card([map], body = True)

app.layout = dbc.Container([
  dbc.Row(
    [dbc.Col([user_options_card], width = 4),
    dbc.Col([map_card], width = 8)]
  ),
  ],
  fluid = True,
  className = "dbc"
)

@app.callback(
  Output(component_id='cluster', component_property='children'),
  [
    Input(component_id='subtype_checklist', component_property='value'),
    Input(component_id='pets_checklist', component_property='value'),
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
    Input(component_id='ppsqft_missing_radio', component_property='value')
  ]
)
# The following function arguments are positional related to the Inputs in the callback above
# Their order must match
def update_map(subtypes_chosen, pets_chosen, terms_chosen, garage_spaces, rental_price, bedrooms_chosen, bathrooms_chosen, sqft_chosen, years_chosen, sqft_missing_radio_choice, yrbuilt_missing_radio_choice, garage_missing_radio_choice, ppsqft_chosen, ppsqft_missing_radio_choice):
  df_filtered = df[
    (df['Sub Type'].isin(subtypes_chosen)) &
    (df['PetsAllowedSimple'].isin(pets_chosen)) &
    (df['Terms'].isin(terms_chosen)) &
    # For the slider, we need to filter the dataframe by an integer range this time and not a string like the ones aboves
    # To do this, we can use the Pandas .between function
    # See https://stackoverflow.com/a/40442778
    (((df['Garage Spaces'].between(garage_spaces[0], garage_spaces[1])) | garage_radio_button(garage_missing_radio_choice, garage_spaces[0], garage_spaces[1]))) & # for this one, combine a dataframe of both the slider inputs and the radio button input
    # Repeat but for rental price
    (df['L/C Price'].between(rental_price[0], rental_price[1])) &
    (df['Bedrooms'].between(bedrooms_chosen[0], bedrooms_chosen[1])) &
    (df['Total Bathrooms'].between(bathrooms_chosen[0], bathrooms_chosen[1])) &
    (((df['Sqft'].between(sqft_chosen[0], sqft_chosen[1])) | sqft_radio_button(sqft_missing_radio_choice, sqft_chosen[0], sqft_chosen[1]))) &
    (((df['YrBuilt'].between(years_chosen[0], years_chosen[1])) | yrbuilt_radio_button(yrbuilt_missing_radio_choice, years_chosen[0], years_chosen[1]))) &
    (((df['Price Per Square Foot'].between(ppsqft_chosen[0], ppsqft_chosen[1])) | ppsqft_radio_button(ppsqft_missing_radio_choice, ppsqft_chosen[0], ppsqft_chosen[1])))
  ]

  # Create markers & associated popups from dataframe
  markers = [dl.Marker(children=dl.Popup(popup_html(row)), position=[row.Latitude, row.Longitude]) for row in df_filtered.itertuples()]

  # Generate the map
  return dl.MarkerClusterGroup(id=str(uuid.uuid4()), children=markers)



# Launch the Flask app
if __name__ == '__main__':
    app.run_server(mode='external', host='192.168.4.196', port='9208', debug='false')