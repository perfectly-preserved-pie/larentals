from dash import Dash, html, dcc
from dash.dependencies import Input, Output
from datetime import date
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import pandas as pd
import uuid

external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME]

# Make the dataframe a global variable
global df

# import the dataframe HDF5 file
df = pd.read_csv("dataframe.csv")
pd.set_option("display.precision", 10)

### DASH LEAFLET AND DASH BOOTSTRAP COMPONENTS SECTION BEGINS!
# Create markers & associated popups from dataframe
markers = [dl.Marker(children=dl.Popup(row.popup_html, closeButton=True, maxHeight=100, maxWidth=5), position=[row.Latitude, row.Longitude]) for row in df.itertuples()]
# Add them to a MarkerCluster
cluster = dl.MarkerClusterGroup(id="markers", children=markers)

# Get the means so we can center the map
lat_mean = df['Latitude'].mean()
long_mean = df['Longitude'].mean()

# Create a function to return a dataframe filter based on if the user provides a Yes/No to the "should we include properties with missing sqft?" question
def sqft_radio_button(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a square footage listed"
    # Then we want nulls to be included in the final dataframe
    sqft_choice = df['Sqft'].isnull()
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    sqft_choice = df['Sqft'].between(slider_begin, slider_end)
  return (sqft_choice)

# Create a function to return a dataframe filter for missing year built
def yrbuilt_radio_button(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a year built listed"
    # Then we want nulls to be included in the final dataframe
    yrbuilt_choice = df['YrBuilt'].isnull()
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    yrbuilt_choice = df['YrBuilt'].between(slider_begin, slider_end)
  return (yrbuilt_choice)

# Create a function to return a dataframe filter for missing garage spaces
def garage_radio_button(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a garage space listed"
    # Then we want nulls to be included in the final dataframe 
    garage_choice = df['Garage Spaces'].isnull()
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    garage_choice = df['Garage Spaces'].between(slider_begin, slider_end)
  return (garage_choice)

# Create a function to return a dataframe filter for missing ppqsft
def ppsqft_radio_button(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a garage space listed"
    # Then we want nulls to be included in the final dataframe 
    ppsqft_choice = df['Price Per Square Foot'].isnull()
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    ppsqft_choice = df['Price Per Square Foot'].between(slider_begin, slider_end)
  return (ppsqft_choice)

# Create a function to return a dataframe filter for pet policy
def pets_radio_button(choice):
  if choice == 'Yes': # If the user says "yes, I ONLY want properties that allow pets"
    # Then we want every row where the pet policy is NOT "No" or "No, Size Limit"
    pets_radio_choice = ~df['PetsAllowed'].isin(['No', 'No, Size Limit'])
  elif choice == 'No': # If the user says "No, I don't want properties where pets are allowed"
    pets_radio_choice = df['PetsAllowed'].isin(['No', 'No, Size Limit'])
  elif choice == 'Both': # If the user says "I don't care, I want both kinds of properties"
    pets_radio_choice = df['PetsAllowed']
  return (pets_radio_choice)

# Create a function to return a dataframe filter for furnished dwellings
def furnished_checklist_function(choice):
  if 'Unknown' in choice: # If Unknown is selected, return all rows with NaN OR the selected choices
    furnished_checklist_filter = (df['Furnished'].isnull()) | (df['Furnished'].isin(choice))
  elif 'Unknown' not in choice: # If Unknown is NOT selected, return the selected choices only, which implies .notnull()
    furnished_checklist_filter = df['Furnished'].isin(choice)
  return (furnished_checklist_filter)

## Create functions to return a dataframe filter for the various types of deposits
# Security
def security_deposit_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
    # Then we want nulls to be included in the final dataframe 
    security_deposit_filter = df['DepositSecurity'].isnull() | (df['DepositSecurity'].between(slider_begin, slider_end))
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    security_deposit_filter = df['DepositSecurity'].between(slider_begin, slider_end)
  return (security_deposit_filter)

# Pets
def pet_deposit_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
    # Then we want nulls to be included in the final dataframe 
    pet_deposit_filter = df['DepositPets'].isnull() | (df['DepositPets'].between(slider_begin, slider_end))
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    pet_deposit_filter = df['DepositPets'].between(slider_begin, slider_end)
  return (pet_deposit_filter)

# Keys
def key_deposit_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
    # Then we want nulls to be included in the final dataframe 
    key_deposit_filter = df['DepositKey'].isnull() | (df['DepositKey'].between(slider_begin, slider_end))
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    key_deposit_filter = df['DepositKey'].between(slider_begin, slider_end)
  return (key_deposit_filter)

# Other
def other_deposit_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
    # Then we want nulls to be included in the final dataframe 
    other_deposit_filter = df['DepositOther'].isnull() | (df['DepositOther'].between(slider_begin, slider_end))
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    other_deposit_filter = df['DepositOther'].between(slider_begin, slider_end)
  return (other_deposit_filter)

# Listed Date
def listed_date_function(boolean, start_date, end_date):
  if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
    # Then we want nulls to be included in the final dataframe 
    listed_date_filter = (df['Listed Date'].isnull()) | (df['Listed Date'].between(start_date, end_date))
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    listed_date_filter = df['Listed Date'].between(start_date, end_date)
  return (listed_date_filter)

app = Dash(
  __name__, 
  external_stylesheets=external_stylesheets,
  # Add meta tags for mobile devices
  # https://community.plotly.com/t/reorder-website-for-mobile-view/33669/5?
  meta_tags = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1"}
  ],
)

server = app.server


# TODO: implement a Select All checkbox: https://dash.plotly.com/advanced-callbacks#synchronizing-two-checklists
subtype_checklist = html.Div([ 
      # Title this section
      html.H5("Subtypes"), 
      # Create a checklist of options for the user
      # https://dash.plotly.com/dash-core-components/checklist
      dcc.Checklist( 
          id = 'subtype_checklist',
          options = [
            {'label': 'Apartment (Attached)', 'value': 'APT/A'},
            {'label': 'Apartment (Unspecified)', 'value': 'APT'},
            {'label': 'Condo (Attached)', 'value': 'CONDO/A'},
            {'label': 'Condo (Detached)', 'value': 'CONDO/D'},
            {'label': 'Condo (Unspecified)', 'value': 'CONDO'},
            {'label': 'Duplex (Attached)', 'value': 'DPLX/A'},
            {'label': 'Duplex (Detached)', 'value': 'DPLX/D'},
            {'label': 'Quadplex (Attached)', 'value': 'QUAD/A'},
            {'label': 'Quadplex (Detached)', 'value': 'QUAD/D'},
            {'label': 'Ranch House (Detached)', 'value': 'RMRT/D'},
            {'label': 'Single Family Residence (Attached)', 'value': 'SFR/A'},
            {'label': 'Single Family Residence (Detached)', 'value': 'SFR/D'},
            {'label': 'Single Family Residence (Unspecified)', 'value': 'SFR'},
            {'label': 'Studio (Attached)', 'value': 'STUD/A'},
            {'label': 'Townhouse (Attached)', 'value': 'TWNHS/A'},
            {'label': 'Townhouse (Detached)', 'value': 'TWNHS/D'},
            {'label': 'Triplex (Attached)', 'value': 'TPLX/A'}
          ],
          value=[
            'APT/A',
            'APT',
            'CONDO/A',
            'CONDO/D',
            'CONDO',
            'DPLX/A',
            'DPLX/D',
            'QUAD/A',
            'QUAD/D',
            'RMRT/D',
            'SFR/A',
            'SFR/D',
            'SFR',
            'STUD/A',
            'TWNHS/A',
            'TWNHS/D',
            'TPLX/A',
          ], # Set the default values
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
      min=df['Price Per Square Foot'].min(), 
      max=df['Price Per Square Foot'].max(),
      value=[df['Price Per Square Foot'].min(), df['Price Per Square Foot'].max()], 
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

rental_terms_checklist = html.Div([
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
      value=['MO', '12M', '24M', 'NG'],
      # add some spacing in between the checkbox and the label
      # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
      inputStyle = {
        "margin-right": "5px",
        "margin-left": "5px"
      },
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
      updatemode='mouseup'
    ),
],
style = {'width' : '70%'}, 
id = 'garage_div'
)

unknown_sqft_radio = html.Div([
  dbc.Alert(
    [
    # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
    html.I(className="bi bi-info-circle-fill me-2"),
    ("Should we include properties that don't have a square footage listed?"),
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
      min=df['List Price'].min(),
      max=df['List Price'].max(),
      value=[0, df['List Price'].max()],
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
  'width' : '70%',
  'margin-bottom' : '10px',
},
id = 'security_deposit_slider_div'
)

security_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties that don't have a security deposit listed?"),
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
  'width' : '70%',
  'margin-bottom' : '10px',
},
id = 'pet_deposit_slider_div'
)

pet_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties that don't have a pet deposit listed?"),
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
  'width' : '70%',
  'margin-bottom' : '10px',
},
id = 'key_deposit_slider_div'
)

key_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties that don't have a key deposit listed?"),
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
  'width' : '70%',
  'margin-bottom' : '10px',
},
id = 'other_deposit_slider_div'
)

other_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Should we include properties that don't have a miscellaneous/other deposit listed?"),
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
        ),
    ],
  color="info",
  ),
],
id = 'unknown_other_deposit_div',
)

# Get today's date and set it as the end date for the date picker
today = date.today()
# Get the earliest date and convert it to to Pythonic datetime for Dash
earliest_date = (df['Listed Date'].min()).to_pydatetime()
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
map = dl.Map(
  [dl.TileLayer(), dl.LayerGroup(id="cluster"), dl.FullscreenControl()],
  id='map',
  zoom=9,
  minZoom=9,
  center=(lat_mean, long_mean),
  style={'width': '100%', 'height': '90vh', 'margin': "auto", "display": "inline-block"}
)

user_options_card = dbc.Card(
  [
    listed_date_datepicker,
    listed_date_radio,
    subtype_checklist,
    rental_price_slider,
    bedrooms_slider,
    bathrooms_slider,
    square_footage_slider,
    square_footage_radio,
    ppsqft_slider,
    ppsqft_radio,
    garage_spaces_slider,
    unknown_sqft_radio,
    year_built_slider,
    unknown_year_built_radio,
    pets_radio,
    rental_terms_checklist,
    furnished_checklist,
    security_deposit_slider,
    security_deposit_radio,
    pet_deposit_slider,
    pet_deposit_radio,
    key_deposit_slider,
    key_deposit_radio,
    other_deposit_slider,
    other_deposit_radio
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

title_card = dbc.Card(
  [
    html.H3("WhereToLive.LA", className="card-title"),
    html.P("An interactive map of rental properties in Los Angeles County."),
    html.I( # use a GitHub icon for my repo
      className="bi bi-github",
      style = {
        "margin-right": "5px",
        "margin-left": "5px"
      },
    ),
    html.A("GitHub", href='https://github.com/perfectly-preserved-pie/larentals', target='_blank'),
    html.I( # Add an icon for my blog
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

app.layout = dbc.Container([
  dbc.Row( # First row: title card
    [
      dbc.Col([title_card]),
    ]
  ),
  dbc.Row( # Second row: the rest
    [
      # Use column width properties to dynamically resize the cards based on screen size
      # https://community.plotly.com/t/layout-changes-with-screen-size-and-resolution/27530/6
      dbc.Col([map_card], lg = 9, md = 6, sm = 8),
      dbc.Col([user_options_card], lg = 3, md = 6, sm = 4),
    ]
  ),
],
fluid = True,
className = "dbc"
)

@app.callback(
  Output(component_id='cluster', component_property='children'),
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
  ]
)
# The following function arguments are positional related to the Inputs in the callback above
# Their order must match
def update_map(subtypes_chosen, pets_chosen, terms_chosen, garage_spaces, rental_price, bedrooms_chosen, bathrooms_chosen, sqft_chosen, years_chosen, sqft_missing_radio_choice, yrbuilt_missing_radio_choice, garage_missing_radio_choice, ppsqft_chosen, ppsqft_missing_radio_choice, furnished_choice, security_deposit_chosen, security_deposit_radio_choice, pet_deposit_chosen, pet_deposit_radio_choice, key_deposit_chosen, key_deposit_radio_choice, other_deposit_chosen, other_deposit_radio_choice, listed_date_datepicker_start, listed_date_datepicker_end, listed_date_radio):
  df_filtered = df[
    (df['Sub Type'].isin(subtypes_chosen)) &
    pets_radio_button(pets_chosen) &
    (df['Terms'].isin(terms_chosen)) &
    # For the slider, we need to filter the dataframe by an integer range this time and not a string like the ones aboves
    # To do this, we can use the Pandas .between function
    # See https://stackoverflow.com/a/40442778
    (((df['Garage Spaces'].between(garage_spaces[0], garage_spaces[1])) | garage_radio_button(garage_missing_radio_choice, garage_spaces[0], garage_spaces[1]))) & # for this one, combine a dataframe of both the slider inputs and the radio button input
    # Repeat but for rental price
    (df['List Price'].between(rental_price[0], rental_price[1])) &
    (df['Bedrooms'].between(bedrooms_chosen[0], bedrooms_chosen[1])) &
    (df['Total Bathrooms'].between(bathrooms_chosen[0], bathrooms_chosen[1])) &
    (((df['Sqft'].between(sqft_chosen[0], sqft_chosen[1])) | sqft_radio_button(sqft_missing_radio_choice, sqft_chosen[0], sqft_chosen[1]))) &
    (((df['YrBuilt'].between(years_chosen[0], years_chosen[1])) | yrbuilt_radio_button(yrbuilt_missing_radio_choice, years_chosen[0], years_chosen[1]))) &
    (((df['Price Per Square Foot'].between(ppsqft_chosen[0], ppsqft_chosen[1])) | ppsqft_radio_button(ppsqft_missing_radio_choice, ppsqft_chosen[0], ppsqft_chosen[1]))) &
    furnished_checklist_function(furnished_choice) &
    security_deposit_function(security_deposit_radio_choice, security_deposit_chosen[0], security_deposit_chosen[1]) &
    pet_deposit_function(pet_deposit_radio_choice, pet_deposit_chosen[0], pet_deposit_chosen[1]) &
    key_deposit_function(key_deposit_radio_choice, key_deposit_chosen[0], key_deposit_chosen[1]) &
    other_deposit_function(other_deposit_radio_choice, other_deposit_chosen[0], other_deposit_chosen[1]) &
    listed_date_function(listed_date_radio, listed_date_datepicker_start, listed_date_datepicker_end)
  ]

  # Create markers & associated popups from dataframe
  markers = [dl.Marker(children=dl.Popup(row.popup_html, closeButton=True, maxHeight=100, maxWidth=5), position=[row.Latitude, row.Longitude]) for row in df_filtered.itertuples()]

  # Debug print a statement to check if we have all markers in the dataframe displayed
  print(f"The original dataframe has {len(df.index)} rows. There are {len(df_filtered.index)} rows in the filtered dataframe. There are {len(markers)} markers on the map.")

  # Generate the map
  return dl.MarkerClusterGroup(id=str(uuid.uuid4()), children=markers)

# Launch the Flask app
if __name__ == '__main__':
  app.run_server(debug=True)