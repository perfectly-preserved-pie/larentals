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

load_dotenv(find_dotenv())
g = GoogleV3(api_key=os.getenv('GOOGLE_API_KEY')) # https://github.com/geopy/geopy/issues/171

#external_stylesheets=[dbc.themes.DARKLY]
external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP]

# Make the dataframe a global variable
global df

# import the csv
# Don't round the float. See https://stackoverflow.com/a/68027847
# Convert all empty strings into NaNs. See https://stackoverflow.com/a/53075732
df = pd.read_csv("larentals.csv", float_precision="round_trip", skipinitialspace=True)
pd.set_option("display.precision", 10)

# Strip leading and trailing whitespaces from the column names
# https://stackoverflow.com/a/36082588
df.columns = df.columns.str.strip()

# Drop all rows that don't have a city. Fuck this shit I'm too lazy to code around bad data input.
df = df[df['City'].notna()]

# Drop all rows that don't have a MLS Listing ID (aka misc data we don't care about)
# https://stackoverflow.com/a/13413845
df = df[df['Listing ID (MLS#)'].notna()]

# Create a new column with the Street Number & Street Name
df["Short Address"] = df["St#"] + ' ' + df["St Name"].str.strip() + ',' + ' ' + df['City']

# Create a function to get coordinates from the full street address
def return_coordinates(address):
    try:
        geocode_info = g.geocode(address)
        lat = float(geocode_info.latitude)
        lon = float(geocode_info.longitude)
        coords = f"{lat}, {lon}"
    except Exception:
        lat = "NO COORDINATES FOUND"
        lon = "NO COORDINATES FOUND"
        coords = "NO COORDINATES FOUND"
    return lat, lon, coords

# Create a function to find missing postal codes based on short address
def return_postalcode(address):
    try:
        # Forward geocoding the short address so we can get coordinates
        geocode_info = g.geocode(address)
        # Reverse geocoding the coordinates so we can get the address object components
        components = g.geocode(f"{geocode_info.latitude}, {geocode_info.longitude}").raw['address_components']
        # Create a dataframe from this list of dictionaries
        components_df = pd.DataFrame(components)
        for row in components_df.itertuples():
            # Select the row that has the postal_code list
            if row.types == ['postal_code']:
                postalcode = row.long_name
    except Exception:
        postalcode = "NO POSTAL CODE FOUND"
    return postalcode

# Webscraping Time
# Create a function to scrape the listing's BHHS page and extract the listed date
def get_listed_date_and_photo(url):
    try:
        response = requests.get(url)
        soup = bs4(response.text, 'html.parser')
        # Split the p class into strings and get the last element in the list
        # https://stackoverflow.com/a/64976919
        listed_date = soup.find('p', attrs={'class' : 'summary-mlsnumber'}).text.split()[-1]
        photo = soup.find('a', attrs={'class' : 'show-listing-details'}).contents[1]['src']
    except AttributeError:
        listed_date = "Unknown"
        photo = ""
    return listed_date, photo


# Filter the dataframe and return only rows with a NaN postal code
# For some reason some Postal Codes are "Assessor" :| so we need to include that string in an OR operation
# Then iterate through this filtered dataframe and input the right info we get using geocoding
for row in df.loc[(df['PostalCode'].isnull()) | (df['PostalCode'] == 'Assessor')].itertuples():
    missing_postalcode = return_postalcode(df.loc[(df['PostalCode'].isnull()) | (df['PostalCode'] == 'Assessor')].at[row.Index, 'Short Address'])
    df.at[row.Index, 'PostalCode'] = missing_postalcode

# Iterate through the dataframe and get the listed date and photo
for row in df.itertuples():
    mls_number = row[1]
    webscrape = get_listed_date_and_photo(f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/")
    df.at[row.Index, 'Listed Date'] = webscrape[0]
    df.at[row.Index, 'MLS Photo'] = webscrape[1]

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

# Remove all $ and , symbols from specific columns
# https://stackoverflow.com/a/46430853
cols = ['DepositKey', 'DepositOther', 'DepositPets', 'DepositSecurity', 'List Price', 'Price Per Square Foot', 'Sqft']
# pass them to df.replace(), specifying each char and it's replacement:
df[cols] = df[cols].replace({'\$': '', ',': ''}, regex=True)

# Split the Bedroom/Bathrooms column into separate columns based on delimiters
# Based on the example given in the spreadsheet: 2 (beds) / 1 (total baths),1 (full baths) ,0 (half bath), 0 (three quarter bath)
# Realtor logic based on https://www.realtor.com/advice/sell/if-i-take-out-the-tub-does-a-bathroom-still-count-as-a-full-bath/
# TIL: A full bathroom is made up of four parts: a sink, a shower, a bathtub, and a toilet. Anything less than that, and you can???t officially consider it a full bath.
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
df['List Price'] = df['List Price'].apply(pd.to_numeric)
df['Bedrooms'] = df['Bedrooms'].apply(pd.to_numeric)
df['Total Bathrooms'] = df['Total Bathrooms'].apply(pd.to_numeric)
df['PostalCode'] = df['PostalCode'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['Sqft'] = df['Sqft'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['YrBuilt'] = df['YrBuilt'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['Price Per Square Foot'] = df['Price Per Square Foot'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['Garage Spaces'] = df['Garage Spaces'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['Latitude'] = df['Latitude'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['Longitude'] = df['Longitude'].apply(pd.to_numeric, errors='coerce') # convert non-integers into NaNs
df['DepositKey'] = df['DepositKey'].apply(pd.to_numeric, errors='coerce')
df['DepositOther'] = df['DepositOther'].apply(pd.to_numeric, errors='coerce')
df['DepositPets'] = df['DepositPets'].apply(pd.to_numeric, errors='coerce')
df['DepositSecurity'] = df['DepositSecurity'].apply(pd.to_numeric, errors='coerce')

# Per CA law, ANY type of deposit is capped at rent * 3 months
# It doesn't matter the type of deposit, they all have the same cap
# Despite that, some landlords/realtors will list the property with an absurd deposit (100k? wtf) so let's rewrite those
# Use numpy .values to rewrite anything greater than $18000 ($6000 rent * 3 months) into $18000
# https://stackoverflow.com/a/54426197
df['DepositSecurity'].values[df['DepositSecurity'] > 18000] = 18000
df['DepositPets'].values[df['DepositPets'] > 18000] = 18000
df['DepositOther'].values[df['DepositOther'] > 18000] = 18000
df['DepositKey'].values[df['DepositKey'] > 18000] = 18000

# Keep rows with less than 6 bedrooms
# 6 bedrooms and above are probably multi family investments and not actual rentals
# And skew the outliers, causing the sliders to go way up
df = df[df.Bedrooms < 6]

# Reindex the dataframe
df.reset_index(drop=True, inplace=True)

# Define HTML code for the popup so it looks pretty and nice
def popup_html(row):
    i = row.Index
    street_address=df['Full Street Address'].iloc[i] 
    mls_number=df['Listing ID (MLS#)'].iloc[i]
    mls_number_hyperlink=f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/"
    mls_photo = df['MLS Photo'].iloc[i]
    lc_price = df['List Price'].iloc[i] 
    price_per_sqft=df['Price Per Square Foot'].iloc[i]                  
    brba = df['Br/Ba'].iloc[i]
    square_ft = df['Sqft'].iloc[i]
    year = df['YrBuilt'].iloc[i]
    garage = df['Garage Spaces'].iloc[i]
    pets = df['PetsAllowed'].iloc[i]
    phone = df['List Office Phone'].iloc[i]
    terms = df['Terms'].iloc[i]
    sub_type = df['Sub Type'].iloc[i]
    listed_date = df['Listed Date'].iloc[i]
    furnished = df['Furnished'].iloc[i]
    key_deposit = df['DepositKey'].iloc[i]
    other_deposit = df['DepositOther'].iloc[i]
    pet_deposit = df['DepositPets'].iloc[i]
    security_deposit = df['DepositSecurity'].iloc[i]
    # If there's no square footage, set it to "Unknown" to display for the user
    # https://towardsdatascience.com/5-methods-to-check-for-nan-values-in-in-python-3f21ddd17eed
    if pd.isna(square_ft) == True:
        square_ft = 'Unknown'
    # If there IS a square footage, convert it into an integer (round number)
    elif pd.isna(square_ft) == False:
        square_ft = f"{int(square_ft)} sq. ft"
    # Repeat above for Year Built
    if pd.isna(year) == True:
        year = 'Unknown'
    # If there IS a square footage, convert it into an integer (round number)
    elif pd.isna(year) == False:
        year = f"{int(year)}"
    # Repeat above for garage spaces
    if pd.isna(garage) == True:
        garage = 'Unknown'
    elif pd.isna(garage) == False:
        garage = f"{int(garage)}"
    # Repeat for ppsqft
    if pd.isna(price_per_sqft) == True:
        price_per_sqft = 'Unknown'
    elif pd.isna(price_per_sqft) == False:
        price_per_sqft = f"${float(price_per_sqft)}"
    # Repeat for listed date
    if pd.isna(listed_date) == True:
        listed_date = 'Unknown'
    elif pd.isna(listed_date) == False:
        listed_date = f"{listed_date}"
    # Repeat for furnished
    if pd.isna(furnished) == True:
        furnished = 'Unknown'
    elif pd.isna(furnished) == False:
        furnished = f"{furnished}"
    # Repeat for the deposits
    if pd.isna(key_deposit) == True:
        key_deposit = 'Unknown'
    elif pd.isna(key_deposit) == False:
        key_deposit = f"${int(key_deposit)}"
    if pd.isna(pet_deposit) == True:
        pet_deposit = 'Unknown'
    elif pd.isna(pet_deposit) == False:
        pet_deposit = f"${int(pet_deposit)}"
    if pd.isna(security_deposit) == True:
        security_deposit = 'Unknown'
    elif pd.isna(security_deposit) == False:
        security_deposit = f"${int(security_deposit)}"
    if pd.isna(other_deposit) == True:
        other_deposit = 'Unknown'
    elif pd.isna(other_deposit) == False:
        other_deposit = f"${int(other_deposit)}"
    # Return the HTML snippet but NOT as a string. See https://github.com/thedirtyfew/dash-leaflet/issues/142#issuecomment-1157890463 
    return [
      html.Div([ # This is where the MLS photo will go (at the top and centered of the tooltip)
          html.Img(
              src=f'{mls_photo}',
              referrerPolicy='noreferrer',
              style={
                'display':'block',
                'width':'100%',
                'margin-left':'auto',
                'margin-right':'auto'
              },
              id='mls_photo_div'
          ),
      ]),
      html.Table([ # Create the table
        html.Tbody([ # Create the table body
          html.Tr([ # Start row #1
            html.Td("Listed Date"), html.Td(f"{listed_date}")
          ]), # end row #1
          html.Tr([ 
            html.Td("Street Address"), html.Td(f"{street_address}")
          ]),
          html.Tr([ 
            # Use a hyperlink to link to BHHS, don't use a referrer, and open the link in a new tab
            # https://www.freecodecamp.org/news/how-to-use-html-to-open-link-in-new-tab/
            html.Td("Listing ID (MLS#)"), html.Td(html.A(f"{mls_number}", href=f"{mls_number_hyperlink}", referrerPolicy='noreferrer', target='_blank'))
          ]),
          html.Tr([ 
            html.Td("List Price"), html.Td(f"${lc_price}")
          ]),
          html.Tr([
            html.Td("Price Per Square Foot"), html.Td(f"{price_per_sqft}")
          ]),
          html.Tr([
            html.Td("Bedrooms/Bathrooms"), html.Td(f"{brba}")
          ]),
          html.Tr([
            html.Td("Square Feet"), html.Td(f"{square_ft}")
          ]),
          html.Tr([
            html.Td("Year Built"), html.Td(f"{year}")
          ]),
          html.Tr([
            html.Td("Garage Spaces"), html.Td(f"{garage}"),
          ]),
          html.Tr([
            html.Td("Pets Allowed?"), html.Td(f"{pets}"),
          ]),
          html.Tr([
            html.Td("List Office Phone"), html.Td(f"{phone}"),
          ]),
          html.Tr([
            html.Td("Rental Terms"), html.Td(f"{terms}"),
          ]),
          html.Tr([
            html.Td("Furnished?"), html.Td(f"{furnished}"),
          ]),
          html.Tr([
            html.Td("Security Deposit"), html.Td(f"{security_deposit}"),
          ]),
          html.Tr([
            html.Td("Pet Deposit"), html.Td(f"{pet_deposit}"),
          ]),
          html.Tr([
            html.Td("Key Deposit"), html.Td(f"{key_deposit}"),
          ]),
          html.Tr([
            html.Td("Other Deposit"), html.Td(f"{other_deposit}"),
          ]),
          html.Tr([                                                                                            
            html.Td("Physical Sub Type"), html.Td(f"{sub_type}")                                                                                    
          ]), # end rows
        ]), # end body
      ]), # end table
    ]

# Create markers & associated popups from dataframe
markers = [dl.Marker(children=dl.Popup(popup_html(row)), position=[row.Latitude, row.Longitude]) for row in df.itertuples()]

# Get the means so we can center the map
lat_mean = df['Latitude'].mean()
long_mean = df['Longitude'].mean()

# Add them to a MarkerCluster
cluster = dl.MarkerClusterGroup(id="markers", children=markers)

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
    security_deposit_filter = df['DepositSecurity'].isnull()
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    security_deposit_filter = df['DepositSecurity'].between(slider_begin, slider_end)
  return (security_deposit_filter)

# Pets
def pet_deposit_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
    # Then we want nulls to be included in the final dataframe 
    pet_deposit_filter = df['DepositPets'].isnull()
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    pet_deposit_filter = df['DepositPets'].between(slider_begin, slider_end)
  return (pet_deposit_filter)

# Keys
def key_deposit_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
    # Then we want nulls to be included in the final dataframe 
    key_deposit_filter = df['DepositKey'].isnull()
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    key_deposit_filter = df['DepositKey'].between(slider_begin, slider_end)
  return (key_deposit_filter)

# Other
def other_deposit_function(boolean, slider_begin, slider_end):
  if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
    # Then we want nulls to be included in the final dataframe 
    other_deposit_filter = df['DepositOther'].isnull()
  elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
    other_deposit_filter = df['DepositOther'].between(slider_begin, slider_end)
  return (other_deposit_filter)

app = JupyterDash(__name__, external_stylesheets=external_stylesheets)

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
style = {
  'width' : '40%',
  'margin-bottom' : '10px',
}, 
id = 'square_footage_div'
)

square_footage_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Some properties aren't listed with a square footage for various reasons. Do you still want to include them in your search?"),
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
      updatemode='drag'
    ),
],
style = {
  'width' : '40%',
  'margin-bottom' : '10px',
},
id = 'ppsqft_div'
)
  
ppsqft_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Some properties aren't listed with a price per square foot for various reasons. Do you still want to include them in your search?"),
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
      updatemode='drag'
    ),
],
style = {'width' : '40%'}, 
id = 'garage_div'
)

unknown_sqft_radio = html.Div([
  dbc.Alert(
    [
    # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
    html.I(className="bi bi-info-circle-fill me-2"),
    ("Some properties aren't listed with garage spaces for various reasons. Do you still want to include them in your search?"),
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
style = {
  'width' : '40%',
  'margin-bottom' : '10px',
},
id = 'yrbuilt_div'
)

unknown_year_built_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),      
      ("Some properties aren't listed with a year built for various reasons. Do you still want to include them in your search?"),
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
      updatemode='drag'
    ),
],
style = {'width' : '40%'}, 
id = 'security_deposit_slider_div'
)

security_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Some properties aren't listed with a security deposit for various reasons. Do you still want to include them in your search?"),
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
      updatemode='drag'
    ),
],
style = {'width' : '40%'}, 
id = 'pet_deposit_slider_div'
)

pet_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Some properties aren't listed with a pet deposit for various reasons. Do you still want to include them in your search?"),
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
      updatemode='drag'
    ),
],
style = {'width' : '40%'}, 
id = 'key_deposit_slider_div'
)

key_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Some properties aren't listed with a key deposit for various reasons. Do you still want to include them in your search?"),
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
      updatemode='drag'
    ),
],
style = {'width' : '40%'}, 
id = 'other_deposit_slider_div'
)

other_deposit_radio = html.Div([
  dbc.Alert(
    [
      # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
      html.I(className="bi bi-info-circle-fill me-2"),
      ("Some properties aren't listed with an 'other' deposit for various reasons. Do you still want to include them in your search?"),
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


# Generate the map
map = dl.Map(
  [dl.TileLayer(), dl.LayerGroup(id="cluster")],
  id='map',
  zoom=9,
  minZoom=9,
  center=(lat_mean, long_mean),
  style={'width': '100%', 'height': '90vh', 'margin': "auto", "display": "inline-block"}
)

user_options_card = dbc.Card(
  [
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
    html.P("An interactive map of rental properties in Los Angeles County.")
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
      dbc.Col([user_options_card], width = 4),
      dbc.Col([map_card], width = 8)
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
  ]
)
# The following function arguments are positional related to the Inputs in the callback above
# Their order must match
def update_map(subtypes_chosen, pets_chosen, terms_chosen, garage_spaces, rental_price, bedrooms_chosen, bathrooms_chosen, sqft_chosen, years_chosen, sqft_missing_radio_choice, yrbuilt_missing_radio_choice, garage_missing_radio_choice, ppsqft_chosen, ppsqft_missing_radio_choice, furnished_choice, security_deposit_chosen, security_deposit_radio_choice, pet_deposit_chosen, pet_deposit_radio_choice, key_deposit_chosen, key_deposit_radio_choice, other_deposit_chosen, other_deposit_radio_choice):
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
    (((df['DepositSecurity'].between(security_deposit_chosen[0], security_deposit_chosen[1])) | security_deposit_function(security_deposit_radio_choice, security_deposit_chosen[0], security_deposit_chosen[1]))) &
    (((df['DepositPets'].between(pet_deposit_chosen[0], pet_deposit_chosen[1])) | pet_deposit_function(pet_deposit_radio_choice, pet_deposit_chosen[0], pet_deposit_chosen[1]))) &
    (((df['DepositKey'].between(key_deposit_chosen[0], key_deposit_chosen[1])) | key_deposit_function(key_deposit_radio_choice, key_deposit_chosen[0], key_deposit_chosen[1]))) &
    (((df['DepositOther'].between(other_deposit_chosen[0], other_deposit_chosen[1])) | other_deposit_function(other_deposit_radio_choice, other_deposit_chosen[0], other_deposit_chosen[1])))
  ]

  # Create markers & associated popups from dataframe
  markers = [dl.Marker(children=dl.Popup(popup_html(row)), position=[row.Latitude, row.Longitude]) for row in df_filtered.itertuples()]

  # Debug print a statement to check if we have all markers in the dataframe displayed
  print(f"The original dataframe has {len(df.index)} rows. There are {len(df_filtered.index)} rows in the filtered dataframe. There are {len(markers)} markers on the map.")

  # Generate the map
  return dl.MarkerClusterGroup(id=str(uuid.uuid4()), children=markers)



# Launch the Flask app
if __name__ == '__main__':
    app.run_server(mode='external', host='192.168.4.196', port='9208', debug='false')