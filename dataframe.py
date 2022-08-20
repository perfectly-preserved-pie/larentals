from bs4 import BeautifulSoup as bs4
from dotenv import load_dotenv, find_dotenv
from geopy.geocoders import GoogleV3
from numpy import NaN
import os
import pandas as pd
import requests

## SETUP AND VARIABLES
load_dotenv(find_dotenv())
g = GoogleV3(api_key=os.getenv('GOOGLE_API_KEY')) # https://github.com/geopy/geopy/issues/171

# Make the dataframe a global variable
global df

### PANDAS DATAFRAME OPERATIONS
# import the csv
# Don't round the float. See https://stackoverflow.com/a/68027847
# Convert all empty strings into NaNs. See https://stackoverflow.com/a/53075732
df = pd.read_csv("larentals.csv", float_precision="round_trip", skipinitialspace=True)
pd.set_option("display.precision", 10)

# Strip leading and trailing whitespaces from the column names
# https://stackoverflow.com/a/36082588
df.columns = df.columns.str.strip()

# Drop all rows that don't have a city. # TODO: figure out a workaround
df = df[df['City'].notna()]

# Drop all rows that don't have a MLS Listing ID (aka misc data we don't care about)
# https://stackoverflow.com/a/13413845
df = df[df['Listing ID'].notna()]

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
        lat = NaN
        lon = NaN
        coords = NaN
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
        postalcode = NaN
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
        listed_date = pd.NaT
        photo = NaN
    return listed_date, photo


# Filter the dataframe and return only rows with a NaN postal code
# For some reason some Postal Codes are "Assessor" :| so we need to include that string in an OR operation
# Then iterate through this filtered dataframe and input the right info we get using geocoding
for row in df.loc[(df['PostalCode'].isnull()) | (df['PostalCode'] == 'Assessor')].itertuples():
    missing_postalcode = return_postalcode(df.loc[(df['PostalCode'].isnull()) | (df['PostalCode'] == 'Assessor')].at[row.Index, 'Short Address'])
    df.at[row.Index, 'PostalCode'] = missing_postalcode

# Now that we have street addresses and postal codes, we can put them together
# Create a new column with the full street address
# Also strip whitespace from the St Name column
df["Full Street Address"] = df["St#"] + ' ' + df["St Name"].str.strip() + ',' + ' ' + df['City'] + ' ' + df["PostalCode"]

# Iterate through the dataframe and get the listed date and photo for rows that don't have them
# If the Listed Date column is already present, iterate through the null cells
# We can use the presence of a Listed Date as a proxy for MLS Photo; generally, either both or neither exist/don't exist together
# This assumption will reduce the number of HTTP requests we send to BHHS
if 'Listed Date' in df.columns:
    for row in df.loc[df['Listed Date'].isnull()].itertuples():
        mls_number = row[1]
        webscrape = get_listed_date_and_photo(f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/")
        df.at[row.Index, 'Listed Date'] = webscrape[0]
        df.at[row.Index, 'MLS Photo'] = webscrape[1]
# if the Listed Date column doesn't exist (i.e this is a first run), create it using df.at
elif 'Listed Date' not in df.columns:
    for row in df.itertuples():
        mls_number = row[1]
        webscrape = get_listed_date_and_photo(f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/")
        df.at[row.Index, 'Listed Date'] = webscrape[0]
        df.at[row.Index, 'MLS Photo'] = webscrape[1]

# Iterate through the dataframe and fetch coordinates for rows that don't have them
# If the Coordinates column is already present, iterate through the null cells
# Similiar to above, we can use the presence of the Coordinates column as a proxy for Longitude and Latitude; all 3 should exist together or none at all
# This assumption will reduce the number of API calls to Google Maps
if 'Coordinates' in df.columns:
    for row in df['Coordinates'].isnull().itertuples():
        coordinates = return_coordinates(df.at[row.Index, 'Full Street Address'])
        df.at[row.Index, 'Latitude'] = coordinates[0]
        df.at[row.Index, 'Longitude'] = coordinates[1]
        df.at[row.Index, 'Coordinates'] = coordinates[2]
# If the Coordinates column doesn't exist (i.e this is a first run), create it using df.at
elif 'Coordinates' not in df.columns:
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

# Convert the listed date into DateTime and set missing values to be NaT
# Infer datetime format for faster parsing
# https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.to_datetime.html
df['Listed Date'] = pd.to_datetime(df['Listed Date'], errors='coerce', infer_datetime_format=True)

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

# Export the dataframe as an HDF5 file to be ingested later by the Dash app (app.py)
# https://www.numpyninja.com/post/hdf5-file-format-with-pandas
df.to_hdf("dataframe.hdf5", "/d1")