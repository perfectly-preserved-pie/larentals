from bs4 import BeautifulSoup as bs4
from dotenv import load_dotenv, find_dotenv
from functions.howloud import *
from geopy.geocoders import GoogleV3
from imagekitio import ImageKit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
from loguru import logger
from numpy import NaN
import glob
import os
import pandas as pd
import requests
import sys

## SETUP AND VARIABLES
load_dotenv(find_dotenv())
g = GoogleV3(api_key=os.getenv('GOOGLE_API_KEY')) # https://github.com/geopy/geopy/issues/171

logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

# ImageKit.IO
# https://docs.imagekit.io/api-reference/upload-file-api/server-side-file-upload#uploading-file-via-url
# Create keys at https://imagekit.io/dashboard/developer/api-keys
imagekit = ImageKit(
    public_key=os.getenv('IMAGEKIT_PUBLIC_KEY'),
    private_key=os.getenv('IMAGEKIT_PRIVATE_KEY'),
    url_endpoint = os.getenv('IMAGEKIT_URL_ENDPOINT')
)

# Make the dataframe a global variable
global df

### PANDAS DATAFRAME OPERATIONS
# Read all sheets from the Excel file
excel_file = glob.glob('*homes*.xlsx')[0]
xlsx = pd.read_excel(excel_file, sheet_name=None)

## Remember: N/A = Not Applicable to this home type while NaN = Unknown for some reason (missing data)
# Assuming first sheet is single-family homes, second sheet is condos/townhouses, and third sheet is mobile homes
# Set the subtype of every row in the first sheet to "SFR"
xlsx[list(xlsx.keys())[0]]["Sub Type"] = "SFR"
# Set the subtype of every row in the third sheet to "MH"
xlsx[list(xlsx.keys())[2]]["Sub Type"] = "MH"
# Set the HOA fee and HOA fee frequency of every row in the third sheet to NaN
xlsx[list(xlsx.keys())[2]]["HOA Fee"] = NaN
xlsx[list(xlsx.keys())[2]]["HOA Frequency"] = NaN
# Set the space rent and park name of every row in the first and second sheets to NaN
xlsx[list(xlsx.keys())[0]]["Space Rent"] = NaN
xlsx[list(xlsx.keys())[0]]["Park Name"] = NaN
xlsx[list(xlsx.keys())[1]]["Space Rent"] = NaN
xlsx[list(xlsx.keys())[1]]["Park Name"] = NaN
# Set the PetsAllowed of every row in the first and second sheets to NaN
xlsx[list(xlsx.keys())[0]]["PetsAllowed"] = NaN
xlsx[list(xlsx.keys())[1]]["PetsAllowed"] = NaN
# Set the SeniorCommunityYN of every row in the first and second sheets to NaN
# If "SeniorCommunity" is in the columns, set it to NaN
if "SeniorCommunity" in xlsx[list(xlsx.keys())[0]].columns:
  xlsx[list(xlsx.keys())[0]]["SeniorCommunity"] = NaN
  xlsx[list(xlsx.keys())[1]]["SeniorCommunity"] = NaN
elif "SeniorCommunityYN" in xlsx[list(xlsx.keys())[0]].columns:
  xlsx[list(xlsx.keys())[0]]["SeniorCommunityYN"] = NaN
  xlsx[list(xlsx.keys())[1]]["SeniorCommunityYN"] = NaN

# Merge all sheets into a single DataFrame
df = pd.concat(xlsx.values())

# Drop the LSqft/Ac column
df = df.drop(columns=['LSqft/Ac'])

pd.set_option("display.precision", 10)

# Strip leading and trailing whitespaces from the column names
# https://stackoverflow.com/a/36082588
df.columns = df.columns.str.strip()

# Standardize the column names by renaming them
# https://stackoverflow.com/a/65332240
df = df.rename(columns=lambda c: 'mls_number' if c.startswith('Listing') and 'MLS' in c else c)
df = df.rename(columns=lambda c: 'subtype' if c.startswith('Sub Type') else c)
df = df.rename(columns=lambda c: 'street_number' if c.startswith('St#') else c)
df = df.rename(columns=lambda c: 'street_name' if c.startswith('St Name') else c)
df = df.rename(columns=lambda c: 'list_price' if c.startswith('List Price') else c)
df = df.rename(columns=lambda c: 'garage_spaces' if c.startswith('Garage Spaces') else c)
df = df.rename(columns=lambda c: 'ppsqft' if c.startswith('Price Per') else c)
df = df.rename(columns=lambda c: 'year_built' if c.startswith('Yr') else c)
df = df.rename(columns=lambda c: 'hoa_fee' if c.startswith('HOA Fee') else c)
df = df.rename(columns=lambda c: 'hoa_fee_frequency' if c.startswith('HOA Frequency') else c)
df = df.rename(columns=lambda c: 'space_rent' if c.startswith('Space') else c)
df = df.rename(columns=lambda c: 'park_name' if c.startswith('Park') else c)
df = df.rename(columns=lambda c: 'senior_community' if c.startswith('Senior') else c)
df = df.rename(columns=lambda c: 'pets_allowed' if c.startswith('Pets') else c)

# Drop all rows that don't have a MLS mls_number (aka misc data we don't care about)
# https://stackoverflow.com/a/13413845
df = df[df['mls_number'].notna()]

# Drop all duplicate rows based on MLS number
# Keep the last duplicate in case of updated listing details
df = df.drop_duplicates(subset='mls_number', keep="last")

# Define columns to remove all non-numeric characters from
cols = ['hoa_fee', 'list_price', 'space_rent', 'ppsqft', 'Sqft', 'year_built']
# Loop through the columns and remove all non-numeric characters except for the string "N/A"
for col in cols:
    df[col] = df[col].apply(lambda x: ''.join(c for c in str(x) if c.isdigit() or c == '.' or str(x) == 'N/A'))
# Fill in missing values with NaN
for col in cols:
  df[col] = df[col].replace('', pd.NA)

# Reindex the dataframe
df.reset_index(drop=True, inplace=True)

# Create a function to get coordinates from the full street address
def return_coordinates(address, row_index):
    try:
        geocode_info = g.geocode(address, components={'administrative_area': 'CA', 'country': 'US'})
        lat = float(geocode_info.latitude)
        lon = float(geocode_info.longitude)
    except Exception as e:
        lat = NaN
        lon = NaN
        logger.warning(f"Couldn't fetch geocode information for {address} (row {row_index} of {len(df)}) because of {e}.")
    logger.success(f"Fetched coordinates {lat}, {lon} for {address} (row {row_index} of {len(df)}).")
    return lat, lon

# Create a function to get a missing city
def fetch_missing_city(address):
    try:
        geocode_info = g.geocode(address, components={'administrative_area': 'CA', 'country': 'US'})
        # Get the city by using a ??? whatever method this is
        # https://gis.stackexchange.com/a/326076
        # First get the raw geocode information
        raw = geocode_info.raw['address_components']
        # Then dig down to find the 'locality' aka city
        city = [addr['long_name'] for addr in raw if 'locality' in addr['types']][0]
    except Exception as e:
        city = NaN
        logger.warning(f"Couldn't fetch city for {address} because of {e}.")
    logger.success(f"Fetched city ({city}) for {address}.")
    return  city

# Fetch missing city names
for row in df.loc[(df['City'].isnull()) & (df['PostalCode'].notnull())].itertuples():
  df.at[row.Index, 'City'] = fetch_missing_city(f"{row.street_number} {row.street_name} {str(row.PostalCode)}")

# Cast these columns as strings so we can concatenate them
cols = ['street_number', 'street_name', 'City']
for col in cols:
  df[col] = df[col].astype("string")

# Create a new column with the Street Number & Street Name
df["short_address"] = df["street_number"] + ' ' + df["street_name"].str.strip() + ',' + ' ' + df['City']

# Create a function to find missing postal codes based on short address
def return_postalcode(address):
    try:
        # Forward geocoding the short address so we can get coordinates
        geocode_info = g.geocode(address, components={'administrative_area': 'CA', 'country': 'US'})
        # Reverse geocoding the coordinates so we can get the address object components
        components = g.geocode(f"{geocode_info.latitude}, {geocode_info.longitude}").raw['address_components']
        # Create a dataframe from this list of dictionaries
        components_df = pd.DataFrame(components)
        for row in components_df.itertuples():
            # Select the row that has the postal_code list
            if row.types == ['postal_code']:
                postalcode = row.long_name
    except Exception as e:
        logger.warning(f"Couldn't fetch postal code for {address} because {e}.")
        return pd.NA
    logger.success(f"Fetched postal code {postalcode} for {address}.")
    return int(postalcode)

# Filter the dataframe and return only rows with a NaN postal code
# For some reason some Postal Codes are "Assessor" :| so we need to include that string in an OR operation
# Then iterate through this filtered dataframe and input the right info we get using geocoding
for row in df.loc[((df['PostalCode'].isnull()) | (df['PostalCode'] == 'Assessor'))].itertuples():
    missing_postalcode = return_postalcode(df.loc[(df['PostalCode'].isnull()) | (df['PostalCode'] == 'Assessor')].at[row.Index, 'short_address'])
    df.at[row.Index, 'PostalCode'] = missing_postalcode

## Webscraping Time
# Create a function to scrape the listing's Berkshire Hathaway Home Services (BHHS) page using BeautifulSoup 4 and extract some info
def webscrape_bhhs(url, row_index, mls_number):
    try:
        response = requests.get(url)
        soup = bs4(response.text, 'html.parser')
        # First find the URL to the actual listing instead of just the search result page
        try:
          link = 'https://www.bhhscalifornia.com' + soup.find('a', attrs={'class' : 'btn cab waves-effect waves-light btn-details show-listing-details'})['href']
          logger.success(f"Successfully fetched listing URL for {mls_number} (row {row_index} out of {len(df)}).")
        except AttributeError as e:
          link = None
          logger.warning(f"Couldn't fetch listing URL for {mls_number} (row {row_index} out of {len(df)}). Passing on...")
          pass
        # If the URL is available, fetch the MLS photo and listed date
        if link is not None:
          # Now find the MLS photo URL
          # https://stackoverflow.com/a/44293555
          try:
            photo = soup.find('a', attrs={'class' : 'show-listing-details'}).contents[1]['src']
            logger.success(f"Successfully fetched MLS photo for {mls_number} (row {row_index} out of {len(df)}).")
          except AttributeError as e:
            photo = None
            logger.warning(f"Couldn't fetch MLS photo for {mls_number} (row {row_index} out of {len(df)}). Passing on...")
            pass
          # For the list date, split the p class into strings and get the last element in the list
          # https://stackoverflow.com/a/64976919
          try:
            listed_date = soup.find('p', attrs={'class' : 'summary-mlsnumber'}).text.split()[-1]
            logger.success(f"Successfully fetched listed date for {mls_number} (row {row_index} out of {len(df)}).")
          except AttributeError as e:
            listed_date = pd.NaT
            logger.warning(f"Couldn't fetch listed date for {mls_number} (row {row_index} out of {len(df)}). Passing on...")
            pass
        elif link is None:
          pass
    except Exception as e:
      listed_date = pd.NaT
      photo = NaN
      link = NaN
      logger.warning(f"Couldn't scrape BHHS page for {mls_number} (row {row_index} out of {len(df)}) because of {e}. Passing on...")
      pass
    return listed_date, photo, link

# Create a function to check for expired listings based on the presence of a string
def check_expired_listing(url, mls_number):
  try:
    response = requests.get(url, timeout=5)
    soup = bs4(response.text, 'html.parser')
    # Detect if the listing has expired. Remove \t, \n, etc. and strip whitespaces
    try:
      soup.find('div', class_='page-description').text.replace("\r", "").replace("\n", "").replace("\t", "").strip()
      return True
    except AttributeError:
      return False
  except Exception as e:
    logger.warning(f"Couldn't detect if the listing for {mls_number} has expired because {e}.")
    return False

# Create a function to upload the file to ImageKit and then transform it
# https://github.com/imagekit-developer/imagekit-python#file-upload
def imagekit_transform(bhhs_mls_photo_url, mls):
  # Set up options per https://github.com/imagekit-developer/imagekit-python/issues/31#issuecomment-1278883286
  options = UploadFileRequestOptions(
    is_private_file=False,
    use_unique_file_name=False,
    #folder = 'wheretolivedotla'
  )
  # if the MLS photo URL from BHHS isn't null (a photo IS available), then upload it to ImageKit
  if pd.isnull(bhhs_mls_photo_url) == False:
      try:
        uploaded_image = imagekit.upload_file(
          file = f"{bhhs_mls_photo_url}", # required
          file_name = f"{mls}", # required
          options = options
        ).url
      except Exception as e:
        uploaded_image = None
        logger.warning(f"Couldn't upload image to ImageKit because {e}. Passing on...")
  elif pd.isnull(bhhs_mls_photo_url) == True:
    uploaded_image = None
    logger.info(f"No image URL found on BHHS for {bhhs_mls_photo_url}. Not uploading anything to ImageKit. Passing on...")
    pass
  # Now transform the uploaded image
  # https://github.com/imagekit-developer/imagekit-python#url-generation
  if uploaded_image is not None:
    try:
      global transformed_image
      transformed_image = imagekit.url({
        "src": uploaded_image,
        "transformation" : [{
          "height": "300",
          "width": "400"
        }]
      })
    except Exception as e:
      transformed_image = None
      logger.warning(f"Couldn't transform image because {e}. Passing on...")
      pass
  elif uploaded_image is None:
    transformed_image = None
  return transformed_image

# Tag each row with the date it was processed
if 'date_processed' in df.columns:
  for row in df[df.date_processed.isnull()].itertuples():
    df.at[row.Index, 'date_processed'] = pd.Timestamp.today()
elif 'date_processed' not in df.columns:
    for row in df.itertuples():
      df.at[row.Index, 'date_processed'] = pd.Timestamp.today()

# Create a new column with the full street address
# Also strip whitespace from the St Name column
# Convert the postal code into a string so we can combine string and int
# https://stackoverflow.com/a/11858532
df["full_street_address"] = df["street_number"] + ' ' + df["street_name"].str.strip() + ',' + ' ' + df['City'] + ' ' + df["PostalCode"].map(str)

# Iterate through the dataframe and get the listed date and photo for rows that don't have them
# If the Listed Date column is already present, iterate through the null cells
# We can use the presence of a Listed Date as a proxy for MLS Photo; generally, either both or neither exist/don't exist together
# This assumption will reduce the number of HTTP requests we send to BHHS
if 'listed_date' in df.columns:
    for row in df.loc[(df['listed_date'].isnull()) & df['date_processed'].isnull()].itertuples():
        mls_number = row[1]
        webscrape = webscrape_bhhs(f"https://www.bhhscalifornia.com/for-sale/{mls_number}-t_q;/", {row.Index}, {row.mls_number})
        df.at[row.Index, 'listed_date'] = webscrape[0]
        df.at[row.Index, 'mls_photo'] = imagekit_transform(webscrape[1], row[1])
        df.at[row.Index, 'listing_url'] = webscrape[2]
# if the Listed Date column doesn't exist (i.e this is a first run), create it using df.at
elif 'listed_date' not in df.columns:
    for row in df.itertuples():
        mls_number = row[1]
        webscrape = webscrape_bhhs(f"https://www.bhhscalifornia.com/for-sale/{mls_number}-t_q;/", {row.Index}, {row.mls_number})
        df.at[row.Index, 'listed_date'] = webscrape[0]
        df.at[row.Index, 'mls_photo'] = imagekit_transform(webscrape[1], row[1])
        df.at[row.Index, 'listing_url'] = webscrape[2]

# Iterate through the dataframe and fetch coordinates for rows that don't have them
# If the Latitude column is already present, iterate through the null cells
# This assumption will reduce the number of API calls to Google Maps
if 'Latitude' in df.columns:
    for row in df['Latitude'].isnull().itertuples():
        coordinates = return_coordinates(row.full_street_address, row.Index)
        df.at[row.Index, 'Latitude'] = coordinates[0]
        df.at[row.Index, 'Longitude'] = coordinates[1]
# If the Coordinates column doesn't exist (i.e this is a first run), create it using df.at
elif 'Latitude' not in df.columns:
    for row in df.itertuples():
        coordinates = return_coordinates(row.full_street_address, row.Index)
        df.at[row.Index, 'Latitude'] = coordinates[0]
        df.at[row.Index, 'Longitude'] = coordinates[1]

# Get the HowLoud score for each row
# A set to keep track of columns we've already populated, so we don't fetch data redundantly.
populated_columns = set()
# Step 1: Populate existing HowLoud related columns if they exist
howloud_keys = ["score", "airports", "traffictext", "localtext", "airportstext", "traffic", "scoretext", "local"]
existing_howloud_columns = [f"HowLoud_{key}" for key in howloud_keys if f"HowLoud_{key}" in df.columns]

if existing_howloud_columns:
  for row in df.itertuples():
    if any(pd.isna(getattr(row, col)) for col in existing_howloud_columns):  # check if any value is NaN
      score_dict = get_howloud_score(row.Latitude, row.Longitude)
      if score_dict:
        for key, value in score_dict.items():
          column_name = f'HowLoud_{key}'
          if column_name in existing_howloud_columns:
            df.at[row.Index, column_name] = value
            populated_columns.add(column_name)
  
# Step 2: Create and populate new columns based on HowLoud scores
for row in df.itertuples():
  # If we've already populated this row's HowLoud values, skip fetching again.
  if all(column in populated_columns for column in existing_howloud_columns):
    continue
      
  score_dict = get_howloud_score(row.Latitude, row.Longitude)
  
  if score_dict:
    for key, value in score_dict.items():
      column_name = f'howloud_{key}'
      if column_name not in df.columns:
        df[column_name] = NaN  # Initialize the column with NaNs  
      df.at[row.Index, column_name] = value
      
# Cast HowLoud columns as either nullable strings or nullable integers
howloud_columns = [col for col in df.columns if col.startswith("HowLoud_")]
for col in howloud_columns:
  # Check if the content is purely numeric
  if df[col].dropna().astype(str).str.isnumeric().all():
    df[col] = df[col].astype(pd.Int32Dtype())  # Cast to nullable integer
  else:
    df[col] = df[col].astype(pd.StringDtype())  # Cast to string
    
# Split the Bedroom/Bathrooms column into separate columns based on delimiters
# Based on the example given in the spreadsheet: 2 (beds) / 1 (total baths),1 (full baths) ,0 (half bath), 0 (three quarter bath)
# Realtor logic based on https://www.realtor.com/advice/sell/if-i-take-out-the-tub-does-a-bathroom-still-count-as-a-full-bath/
# TIL: A full bathroom is made up of four parts: a sink, a shower, a bathtub, and a toilet. Anything less than thpdat, and you can’t officially consider it a full bath.
df['Bedrooms'] = df['Br/Ba'].str.split('/', expand=True)[0]
df['Total Bathrooms'] = (df['Br/Ba'].str.split('/', expand=True)[1]).str.split(',', expand=True)[0]
df['Full Bathrooms'] = (df['Br/Ba'].str.split('/', expand=True)[1]).str.split(',', expand=True)[1]
df['Half Bathrooms'] = (df['Br/Ba'].str.split('/', expand=True)[1]).str.split(',', expand=True)[2]
df['Three Quarter Bathrooms'] = (df['Br/Ba'].str.split('/', expand=True)[1]).str.split(',', expand=True)[3]

# Convert a few columns into int64
# pd.to_numeric will convert into int64 or float64 automatically, which is cool
# These columns are assumed to have NO MISSING DATA, so we can cast them as int64 instead of floats (ints can't handle NaNs)
df['Bedrooms'] = df['Bedrooms'].apply(pd.to_numeric, errors='coerce')
df['Total Bathrooms'] = df['Total Bathrooms'].apply(pd.to_numeric, errors='coerce')
# These columns should stay floats
df['Latitude'] = df['Latitude'].apply(pd.to_numeric, errors='coerce')
df['Longitude'] = df['Longitude'].apply(pd.to_numeric, errors='coerce')
# Convert PostalCode into nullable integer dtype
df['PostalCode'] = df['PostalCode'].apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())

# Convert the listed date into DateTime and set missing values to be NaT
# Infer datetime format for faster parsing
# https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.to_datetime.html
df['listed_date'] = pd.to_datetime(df['listed_date'], errors='coerce', infer_datetime_format=True)

# Convert date_processed into DateTime
df['date_processed'] = pd.to_datetime(df['date_processed'], errors='coerce', infer_datetime_format=True, format='%Y-%m-%d')

# Cast these columns as nullable integers
cols = ['Full Bathrooms', 'Bedrooms', 'year_built', 'Sqft', 'list_price', 'Total Bathrooms']
for col in cols:
  df[col] = df[col].astype('Int64')
# Cast these columns as nullable floats
cols = ['ppsqft', 'Latitude', 'Longitude', 'hoa_fee', 'space_rent']
for col in cols:
  df[col] = df[col].astype(str).replace('N/A', pd.NA)
  df[col] = df[col].str.replace(',', '')  # remove commas
  df[col] = df[col].str.replace(r'[^0-9\.]', '', regex=True)  # remove any other non-numeric characters
  df[col] = df[col].replace('', pd.NA)  # replace empty strings with np.nan
  df[col] = pd.to_numeric(df[col], errors='coerce')
# Cast these columns as nullable strings
cols = ['short_address', 'full_street_address', 'mls_number', 'mls_photo', 'listing_url', 'subtype', 'Br/Ba', 'pets_allowed', 'senior_community', 'hoa_fee_frequency']
for col in cols:
  df[col] = df[col].astype('string')


# Reindex the dataframe
df.reset_index(drop=True, inplace=True)

# Define HTML code for the popup so it looks pretty and nice
def popup_html(dataframe, row):
  df = dataframe
  i = row.Index
  short_address = df['short_address'].at[i]
  postalcode = df['PostalCode'].at[i]
  full_address = f"{short_address} {postalcode}"
  mls_number=df['mls_number'].at[i]
  mls_number_hyperlink=df['listing_url'].at[i]
  mls_photo = df['mls_photo'].at[i]
  lc_price = df['list_price'].at[i] 
  price_per_sqft=df['ppsqft'].at[i]                  
  brba = df['Br/Ba'].at[i]
  square_ft = df['Sqft'].at[i]
  year = df['year_built'].at[i]
  park_name = df['park_name'].at[i]
  hoa_fee = df['hoa_fee'].at[i]
  hoa_fee_frequency = df['hoa_fee_frequency'].at[i]
  space_rent = df['space_rent'].at[i]
  senior_community = df['senior_community'].at[i]
  subtype = df['subtype'].at[i]
  pets = df['pets_allowed'].at[i]
  airport_description = df['HowLoud'].at[i]['airporttext']
  airport_score = df['HowLoud'].at[i]['airports']
  local_description = df['HowLoud'].at[i]['localtext']
  noise_score = df['HowLoud'].at[i]['score']
  score_description = df['HowLoud'].at[i]['scoretext']
  traffic_description = df['HowLoud'].at[i]['traffictext']
  traffic_score = df['HowLoud'].at[i]['traffic']
  listed_date = pd.to_datetime(df['listed_date'].at[i]).date() # Convert the full datetime into date only
  if pd.isna(square_ft):
      square_ft = 'Unknown'
  else:
      square_ft = f"{int(square_ft):,d} sq. ft"
  if pd.isna(year):
      year = 'Unknown'
  else:
      year = f"{int(year)}"
  if pd.isna(price_per_sqft):
      price_per_sqft = 'Unknown'
  else:
      price_per_sqft = f"${price_per_sqft:,.2f}"
  if pd.isna(listed_date):
      listed_date = 'Unknown'
  else:
      listed_date = f"{listed_date}"
  if pd.isna(pets) and not pd.isna(subtype) and subtype == 'MH':
      pets = 'Unknown'
  elif not pd.isna(pets) and not pd.isna(subtype) and subtype == 'MH':
      pets = f"{pets}"
  elif pd.isna(pets) and not pd.isna(subtype) and subtype != 'MH':
      pets = "N/A"
  if pd.isna(senior_community) and not pd.isna(subtype) and subtype == 'MH':
      senior_community = 'Unknown'
  elif not pd.isna(senior_community) and not pd.isna(subtype) and subtype == 'MH':
      senior_community = senior_community
  elif pd.isna(senior_community) and not pd.isna(subtype) and subtype != 'MH':
      senior_community = "N/A"
  if pd.isna(hoa_fee) == True and not pd.isna(subtype) and (subtype == 'SFR' or 'CONDO' in subtype):
      hoa_fee = 'Unknown'
  elif pd.isna(hoa_fee) == False and not pd.isna(subtype) and (subtype == 'SFR' or 'CONDO' in subtype):
      hoa_fee = f"${hoa_fee:,.2f}"
  elif pd.isna(hoa_fee) == True and not pd.isna(subtype) and subtype == 'MH':
      hoa_fee = "N/A"
  if pd.isna(hoa_fee_frequency) == True and not pd.isna(subtype) and (subtype == 'SFR' or 'CONDO' in subtype):
      hoa_fee_frequency = 'Unknown'
  elif pd.isna(hoa_fee_frequency) == False and not pd.isna(subtype) and (subtype == 'SFR' or 'CONDO' in subtype):
      hoa_fee_frequency = f"{hoa_fee_frequency}"
  elif pd.isna(hoa_fee_frequency) == True and not pd.isna(subtype) and subtype == 'MH':
      hoa_fee_frequency = "N/A"
  if pd.isna(space_rent) and not pd.isna(subtype) and subtype == 'MH':
      space_rent = 'Unknown'
  elif not pd.isna(space_rent) and not pd.isna(subtype) and subtype == 'MH':
      space_rent = f"${space_rent:,.2f}"
  elif not pd.isna(space_rent) and not pd.isna(subtype) and subtype != 'MH':
      space_rent = "N/A"
  if pd.isna(park_name) == True and not pd.isna(subtype) and subtype == 'MH':
      park_name = 'Unknown'
  elif pd.isna(park_name) == False and not pd.isna(subtype) and subtype == 'MH':
      park_name = f"{park_name}"
  elif pd.isna(park_name) == True and not pd.isna(subtype) and subtype != 'MH':
      park_name = "N/A"
  if pd.isna(mls_photo):
      mls_photo_html_block = "<img src='' referrerPolicy='noreferrer' style='display:block;width:100%;margin-left:auto;margin-right:auto' id='mls_photo_div'>"
  else:
      mls_photo_html_block = f"""
      <a href="{mls_number_hyperlink}" referrerPolicy="noreferrer" target="_blank">
      <img src="{mls_photo}" referrerPolicy="noreferrer" style="display:block;width:100%;margin-left:auto;margin-right:auto" id="mls_photo_div">
      </a>
      """
  if pd.isna(mls_number_hyperlink):
      listing_url_block = f"""
      <tr>
          <td><a href="https://github.com/perfectly-preserved-pie/larentals/wiki#listing-id" target="_blank">Listing ID (MLS#)</a></td>
          <td>{mls_number}</td>
      </tr>
      """
  else:
      listing_url_block = f"""
      <tr>
          <td><a href="https://github.com/perfectly-preserved-pie/larentals/wiki#listing-id" target="_blank">Listing ID (MLS#)</a></td>
          <td><a href="{mls_number_hyperlink}" referrerPolicy="noreferrer" target="_blank">{mls_number}</a></td>
      </tr>
      """
  return f"""<div>{mls_photo_html_block}</div>
  <table id='popup_html_table'>
    <tbody id='popup_html_table_body'>
      <tr id='listed_date'>
          <td>Listed Date</td>
          <td>{listed_date}</td>
      </tr>
      <tr id='street_address'>
          <td>Street Address</td>
          <td>{full_address}</td>
      </tr>
      <tr id='park_name'>
          <td>Park Name</td>
          <td>{park_name}</td>
      </tr>
      {listing_url_block}
      <tr id='list_price'>
          <td>List Price</td>
          <td>${lc_price:,.0f}</td>
      </tr>
      <tr id='hoa_fee'>
          <td>HOA Fee</td>
          <td>{hoa_fee}</td>
      </tr>
      <tr id='hoa_fee_frequency'>
          <td>HOA Fee Frequency</td>
          <td>{hoa_fee_frequency}</td>
      </tr>
      <tr id='square_feet'>
          <td>Square Feet</td>
          <td>{square_ft}</td>
      </tr>
      <tr id='space_rent'>
          <td>Space Rent</td>
          <td>{space_rent}</td>
      </tr>
      <tr id='price_per_sqft'>
          <td>Price Per Square Foot</td>
          <td>{price_per_sqft}</td>
      </tr>
      <tr id='bedrooms_bathrooms'>
          <td><a href="https://github.com/perfectly-preserved-pie/larentals/wiki#bedroomsbathrooms" target="_blank">Bedrooms/Bathrooms</a></td>
          <td>{brba}</td>
      </tr>
      <tr id='year_built'>
          <td>Year Built</td>
          <td>{year}</td>
      </tr>
      <tr id='pets_allowed'>
          <td>Pets Allowed?</td>
          <td>{pets}</td>
      </tr>
      <tr id='senior_community'>
          <td>Senior Community</td>
          <td>{senior_community}</td>
      </tr>
      <tr id='subtype'>
          <td>Sub Type</td>
          <td>{subtype}</td>
      </tr>
      <tr id='more_info_trigger'>
        <td colspan='2'>More Info...</td>
      </tr>
      <tbody id='extra_info' style='display: none;'>
          <tr id='noise_score'>
              <td>Noise Score</td>
              <td>{noise_score}</td>
          </tr>
          <tr id='airport_noise_level'>
              <td>Airport Noise Level</td>
              <td>{airport_description}</td>
          </tr>
          <tr id='traffic_score'>
              <td>Traffic Score</td>
              <td>{traffic_score}</td>
          </tr>
          </tbody>
  </table>
  """

# Define a lambda function to replace the <table> tag
#replace_table_tag = lambda html: html.replace("<table>", "<table id='popup_table'>", 1)

# Apply the lambda function to create the popup_html_mobile column
#df['popup_html_mobile'] = df['popup_html'].apply(replace_table_tag)

# Do another pass to convert the date_processed column to datetime64 dtype
df['date_processed'] = pd.to_datetime(df['date_processed'], errors='coerce', infer_datetime_format=True, format='%Y-%m-%d')

# Save the dataframe for later ingestion by app.py
# Read the old dataframe in depending if it's a pickle (old) or parquet (new)
# If the pickle URL returns a 200 OK, read it in
if requests.get('https://github.com/perfectly-preserved-pie/larentals/raw/master/datasets/buy.pickle').status_code == 200:
  df_old = pd.read_pickle(filepath_or_buffer='https://github.com/perfectly-preserved-pie/larentals/raw/master/datasets/buy.pickle')
# If the pickle URL returns a 404 Not Found, read in the parquet file instead
elif requests.get('https://github.com/perfectly-preserved-pie/larentals/raw/master/datasets/buy.pickle').status_code == 404:
  df_old = pd.read_parquet(path='https://github.com/perfectly-preserved-pie/larentals/raw/master/datasets/buy.parquet')
# Combine both old and new dataframes
df_combined = pd.concat([df, df_old], ignore_index=True)
# Drop any dupes again
df_combined = df_combined.drop_duplicates(subset=['mls_number'], keep="last")
# Drop the LSqft/Ac column if it exists
if 'LSqft/Ac' in df_combined.columns:
  df_combined = df_combined.drop(columns=['LSqft/Ac'])
# Iterate through the dataframe and drop rows with expired listings
for row in df_combined[df_combined.listing_url.notnull()].itertuples():
  if check_expired_listing(row.listing_url, row.mls_number) == True:
    df_combined = df_combined.drop(row.Index)
    logger.success(f"Removed {row.mls_number} ({row.listing_url}) from the dataframe because the listing has expired.")
# Reset the index
df_combined = df_combined.reset_index(drop=True)
# Iterate through the combined dataframe and (re)generate the popup_html column
for row in df_combined.itertuples():
  df_combined.at[row.Index, 'popup_html'] = popup_html(df_combined, row)
# Filter the dataframe for rows outside of California
outside_ca_rows = df_combined[
  (df_combined['Latitude'] < 32.5) | 
  (df_combined['Latitude'] > 42) | 
  (df_combined['Longitude'] < -124) | 
  (df_combined['Longitude'] > -114)
]
total_outside_ca = len(outside_ca_rows)
counter = 0
for row in outside_ca_rows.itertuples():
  counter += 1
  logger.warning(f"Row {counter} out of {total_outside_ca}: {row.mls_number} has coordinates {row.Latitude}, {row.Longitude} which is outside California. Re-geocoding {row.mls_number}...")
  # Re-geocode the row
  coordinates = return_coordinates(row.full_street_address, row.Index)
  df_combined.at[row.Index, 'Latitude'] = coordinates[0]
  df_combined.at[row.Index, 'Longitude'] = coordinates[1]
# Save the new combined dataframe
df_combined.to_parquet(path="datasets/buy.parquet")