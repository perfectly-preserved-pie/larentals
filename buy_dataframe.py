from bs4 import BeautifulSoup as bs4
from dotenv import load_dotenv, find_dotenv
from functions.geocoding_utils import *
from functions.mls_image_processing_utils import *
from functions.noise_level_utils import *
from functions.webscraping_utils import *
from geopy.geocoders import GoogleV3
from imagekitio import ImageKit
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

# Using a dictionary for clearer column renaming
specific_column_map = {
  'Garage Spaces': 'garage_spaces',
  'Hfrequency': 'hoa_fee_frequency',
  'HOA Fee Frequency': 'hoa_fee_frequency',
  'HOA Fee': 'hoa_fee',
  'HOA Frequency': 'hoa_fee_frequency',
  'List Price': 'list_price',
  'Listing ID (MLS#)': 'mls_number',
  'Park Name': 'park_name',
  'PetsAllowed': 'pets_allowed',
  'Price Per Square Foot': 'ppsqft',
  'SeniorCommunity': 'senior_community',
  'SeniorCommunityYN': 'senior_community',
  'Space Rent': 'space_rent',
  'St Name': 'street_name',
  'St#': 'street_number',
  'Sub Type': 'subtype',
  'Yr Built': 'year_built',
}

# Rename columns using the specific map
renamed_sheets_corrected = {}
for sheet_name, sheet_df in xlsx.items():
  sheet_df.columns = sheet_df.columns.str.strip()
  renamed_sheets_corrected[sheet_name] = sheet_df.rename(columns=specific_column_map)

# Concatenate all sheets into a single DataFrame
df = pd.concat(renamed_sheets_corrected.values())

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

# Fetch missing city names
for row in df.loc[(df['City'].isnull()) & (df['PostalCode'].notnull())].itertuples():
  df.at[row.Index, 'City'] = fetch_missing_city(f"{row.street_number} {row.street_name} {str(row.PostalCode)}", geolocator=g)

# Cast these columns as strings so we can concatenate them
cols = ['street_number', 'street_name', 'City', 'mls_number']
for col in cols:
  df[col] = df[col].astype("string")

# Create a new column with the Street Number & Street Name
df["short_address"] = df["street_number"] + ' ' + df["street_name"].str.strip() + ',' + ' ' + df['City']

# Filter the dataframe and return only rows with a NaN postal code
# For some reason some Postal Codes are "Assessor" :| so we need to include that string in an OR operation
# Then iterate through this filtered dataframe and input the right info we get using geocoding
for row in df.loc[(df['PostalCode'].isnull()) | (df['PostalCode'] == 'Assessor')].itertuples():
  short_address = df.at[row.Index, 'short_address']
  missing_postalcode = return_postalcode(short_address, geolocator=g)
  df.at[row.Index, 'PostalCode'] = missing_postalcode

# Tag each row with the date it was processed
for row in df.itertuples():
  df.at[row.Index, 'date_processed'] = pd.Timestamp.today()

# Create a new column with the full street address
# Also strip whitespace from the St Name column
# Convert the postal code into a string so we can combine string and int
# https://stackoverflow.com/a/11858532
df["full_street_address"] = df["street_number"] + ' ' + df["street_name"].str.strip() + ',' + ' ' + df['City'] + ' ' + df["PostalCode"].map(str)

# Iterate through the dataframe and get the listed date and photo for rows 
for row in df.itertuples():
  mls_number = row[1]
  webscrape = webscrape_bhhs(f"https://www.bhhscalifornia.com/for-sale/{mls_number}-t_q;/", row.Index, row.mls_number, len(df))
  df.at[row.Index, 'listed_date'] = webscrape[0]
  df.at[row.Index, 'mls_photo'] = imagekit_transform(webscrape[1], row[1], imagekit_instance=imagekit)
  df.at[row.Index, 'listing_url'] = webscrape[2]

# Iterate through the dataframe and fetch coordinates for rows
for row in df.itertuples():
  coordinates = return_coordinates(address=row.full_street_address, row_index=row.Index, geolocator=g, total_rows=len(df))
  df.at[row.Index, 'Latitude'] = coordinates[0]
  df.at[row.Index, 'Longitude'] = coordinates[1]

#df = update_howloud_scores(df)

# Cast HowLoud columns as either nullable strings or nullable integers
#howloud_columns = [col for col in df.columns if col.startswith("howloud_")]
#for col in howloud_columns:
  # Check if the content is purely numeric
#  if df[col].dropna().astype(str).str.isnumeric().all():
#    df[col] = df[col].astype(pd.Int32Dtype())  # Cast to nullable integer
#  else:
#    df[col] = df[col].astype(pd.StringDtype())  # Cast to string
    
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
df['date_processed'] = pd.to_datetime(df['date_processed'], errors='coerce', infer_datetime_format=False, format='%Y-%m-%d')

cols = ['Full Bathrooms', 'Bedrooms', 'year_built', 'Sqft', 'list_price', 'Total Bathrooms', 'space_rent', 'ppsqft', 'hoa_fee']
# Convert columns to string type for string operations
df[cols] = df[cols].astype(str)
# Replace 'N/A' with pd.NA
df[cols] = df[cols].replace('N/A', pd.NA)
# Remove commas and other non-numeric characters
df[cols] = df[cols].replace({',': '', r'[^0-9\.]': ''}, regex=True)
# Replace empty strings with pd.NA
df[cols] = df[cols].replace('', pd.NA)
# Convert columns to numeric
df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
# Cast specified columns as nullable integers
int_cols = ['Full Bathrooms', 'Bedrooms', 'year_built', 'Sqft', 'list_price', 'Total Bathrooms']
df[int_cols] = df[int_cols].astype('Int64')

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
  elif pd.isna(space_rent) and not pd.isna(subtype) and subtype != 'MH':
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
  coordinates = return_coordinates(address=row.full_street_address, row_index=row.Index, geolocator=g, total_rows=len(df))
  df_combined.at[row.Index, 'Latitude'] = coordinates[0]
  df_combined.at[row.Index, 'Longitude'] = coordinates[1]
# Save the new combined dataframe
df_combined.to_parquet(path="datasets/buy.parquet")