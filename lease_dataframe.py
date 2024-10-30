from dotenv import load_dotenv, find_dotenv
from functions.dataframe_utils import remove_expired_listings
from functions.geocoding_utils import *
from functions.mls_image_processing_utils import *
from functions.noise_level_utils import *
from functions.popup_utils import *
from functions.webscraping_utils import *
from geopy.geocoders import GoogleV3
from imagekitio import ImageKit
from loguru import logger
import asyncio
import glob
import os
import pandas as pd
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
# Load all CSVs and concat into one dataframe
# https://stackoverflow.com/a/21232849
path = "."
all_files = glob.glob(os.path.join(path, "*Renter*.csv"))
df = pd.concat((pd.read_csv(f, float_precision="round_trip", skipinitialspace=True) for f in all_files), ignore_index=True)

pd.set_option("display.precision", 10)

# Strip leading and trailing whitespaces from the column names
# https://stackoverflow.com/a/36082588
df.columns = df.columns.str.strip()

# Convert all column names to lowercase
df.columns = df.columns.str.lower()

# Standardize the column names by renaminmg them
# https://stackoverflow.com/a/65332240
# Define a renaming dictionary based on patterns
rename_dict = {
  'agent': 'phone_number',
  'allowed': 'pet_policy',
  'baths': 'bathrooms',
  'bedrooms': 'bedrooms',
  'city': 'city',
  'furnished': 'furnished',
  'key': 'key_deposit',
  'laundry': 'laundry',
  'list': 'list_price',
  'lot': 'lot_size',
  'mls': 'mls_number',
  'name': 'street_name',
  'other': 'other_deposit',
  'pet deposit': 'pet_deposit',
  'prking': 'parking',
  'security': 'security_deposit',
  'sqft': 'sqft',
  'square': 'ppsqft',
  'st #': 'street_number',
  'sub': 'subtype',
  'terms': 'terms', 
  'yr': 'year_built',
  'zip': 'zip_code',
}

# Rename columns based on substrings in the column names
df = df.rename(columns=lambda c: next((v for k, v in rename_dict.items() if k in c), c))

# Drop the numbers in the first group of characters in the street_name column
df['street_name'] = df['street_name'].str.replace(r'^\d+\s*', '', regex=True)

# Drop all rows with misc/irrelevant data
df.dropna(subset=['street_name'], inplace=True)

# Columns to clean
cols = ['key_deposit', 'other_deposit', 'security_deposit', 'list_price', 'sqft', 'year_built', 'parking', 'lot_size']

# Remove all non-numeric characters, convert to numeric, fill NaNs with pd.NA, and cast to Nullable Integer Type
df[cols] = df[cols].replace(to_replace='[^\d]', value='', regex=True).apply(pd.to_numeric, errors='coerce').astype(pd.Int32Dtype())

# Handle pet_deposit column separately
df['pet_deposit'] = df['pet_deposit'].replace(to_replace='[^\d.]', value='', regex=True).apply(pd.to_numeric, errors='coerce').astype(pd.Int32Dtype())

# Cast the following columns as Int32Dtype
df['zip_code'] = df['zip_code'].apply(pd.to_numeric, errors='raise').astype(pd.Int32Dtype())
df['street_number'] = df['street_number'].apply(pd.to_numeric, errors='raise').astype(pd.Int32Dtype())
df['lot_size'] = df['lot_size'].apply(pd.to_numeric, errors='raise').astype(pd.Int32Dtype())

# Cast the following columns as a float and remove the leading $ sign
df['ppsqft'] = df['ppsqft'].replace(to_replace='[^\d.]', value='', regex=True).astype('float32')

# Check if 'ppsqft' column exists
if 'ppsqft' not in df.columns:
  # If it has a different name, replace 'Sqft' below with the correct column name
  df['ppsqft'] = (df['list_price'] / df['Sqft']).round(2)

# Fetch missing city names
for row in df.loc[(df['city'].isnull()) & (df['zip_code'].notnull())].itertuples():
  df.at[row.Index, 'city'] = fetch_missing_city(f"{row.street_number} {row.street_name} {str(row.zip_code)}", geolocator=g)

# Columns to be cast as strings
cols = ['mls_number', 'phone_number', 'street_name', 'zip_code', 'city', 'terms', 'pet_policy', 'furnished', 'subtype']
df[cols] = df[cols].astype(pd.StringDtype())

# Create a new column with the Street Number & Street Name
df["short_address"] = (df["street_number"].astype(str) + ' ' + df["street_name"] + ', ' + df['city']).astype(pd.StringDtype())

# Filter the dataframe and return only rows with a NaN postal code
# For some reason some Postal Codes are "Assessor" :| so we need to include that string in an OR operation
# Then iterate through this filtered dataframe and input the right info we get using geocoding
for row in df.loc[(df['zip_code'].isnull()) | (df['zip_code'] == 'Assessor')].itertuples():
  short_address = df.at[row.Index, 'short_address']
  missing_zip_code = return_zip_code(short_address, geolocator=g)
  df.at[row.Index, 'zip_code'] = (missing_zip_code).astype(pd.Int32Dtype())

# Tag each row with the date it was processed
for row in df.itertuples():
  df.at[row.Index, 'date_processed'] = pd.Timestamp.today()

# Create a new column with the full street address
df["full_street_address"] = (
    df["street_number"].astype(str) + ' ' + 
    df["street_name"].str.strip() + ', ' + 
    df['city'] + ' ' + 
    df["zip_code"].astype(str)
)

# Iterate through the dataframe and get the listed date and photo for rows
for row in df.itertuples():
  mls_number = row[1]
  # Try fetching data from BHHS
  webscrape = asyncio.run(
    webscrape_bhhs(
      url=f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/",
      row_index=row.Index,
      mls_number=mls_number,
      total_rows=len(df)
    )
  )

  if not all(webscrape):
    # If BHHS didn't return data, try fetching from The Agency
    agency_data = asyncio.run(
      fetch_the_agency_data(
        mls_number, row_index=row.Index, total_rows=len(df)
      )
    )
    if agency_data[0]:
      df.at[row.Index, 'listed_date'] = agency_data[0]
    if agency_data[1]:
      df.at[row.Index, 'listing_url'] = agency_data[1]
  else:
    # BHHS returned data, proceed as before
    df.at[row.Index, 'listed_date'] = webscrape[0]
    df.at[row.Index, 'mls_photo'] = imagekit_transform(
      webscrape[1], mls_number, imagekit_instance=imagekit
    )
    df.at[row.Index, 'listing_url'] = webscrape[2]

# Iterate through the dataframe and fetch coordinates for rows
for row in df.itertuples():
  coordinates = return_coordinates(address=row.full_street_address, row_index=row.Index, geolocator=g, total_rows=len(df))
  df.at[row.Index, 'latitude'] = coordinates[0]
  df.at[row.Index, 'longitude'] = coordinates[1]

# Extract total bathrooms and bathroom types (Full, Three-Quarter, Half, Quarter)
df[['total_bathrooms', 'full_bathrooms', 'three_quarter_bathrooms', 'half_bathrooms', 'quarter_bathrooms']] = df['bathrooms'].str.extract(r'(\d+\.\d+)\s\((\d+)\s(\d+)\s(\d+)\s(\d+)\)').astype(float)

# Convert columns to nullable integer type
for col in ['total_bathrooms', 'full_bathrooms', 'three_quarter_bathrooms', 'half_bathrooms', 'quarter_bathrooms']:
  df[col] = df[col].astype(pd.Int8Dtype())

# Drop the original 'Baths(FTHQ)' column since we've extracted the data we need
df.drop(columns=['bathrooms'], inplace=True)

# Convert bedrooms to nullable integer type
df['bedrooms'] = df['bedrooms'].astype(pd.Int8Dtype())
# These columns should stay floats
df['latitude'] = df['latitude'].apply(pd.to_numeric, errors='raise')
df['longitude'] = df['longitude'].apply(pd.to_numeric, errors='raise')

## Laundry Features ##
# Replace all empty values in the following column with "Unknown" and cast the column as dtype string
df.laundry = df.laundry.astype("string").replace(r'^\s*$', "Unknown", regex=True)
# Fill in any NaNs in the Laundry column with "Unknown"
df.laundry = df.laundry.fillna(value="Unknown")
# Replace various patterns in the Laundry column with "Community Laundry"
df.laundry = df.laundry.str.replace(
  r'Community Laundry Area|Laundry Area|Community|Common', 
  'Community Laundry', 
  regex=True
)

# Convert the listed date into DateTime and use the "mixed" format to handle the different date formats
# https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.to_datetime.html
df['listed_date'] = pd.to_datetime(df['listed_date'], errors='raise', format='mixed')

# Convert date_processed into DateTime
df['date_processed'] = pd.to_datetime(df['date_processed'], errors='coerce', format='%Y-%m-%d')

# Reindex the dataframe
df.reset_index(drop=True, inplace=True)

# Do another pass to convert the date_processed column to datetime64 dtype
df['date_processed'] = pd.to_datetime(df['date_processed'], errors='coerce', format='%Y-%m-%d')

# Save the dataframe for later ingestion by app.py
# Read in the old dataframe
df_old = pd.read_parquet(path='https://github.com/perfectly-preserved-pie/larentals/raw/master/assets/datasets/lease.parquet')
# Combine both old and new dataframes
df_combined = pd.concat([df, df_old], ignore_index=True)
# Drop any dupes again
df_combined = df_combined.drop_duplicates(subset=['mls_number'], keep="last")
# Iterate through the dataframe and drop rows with expired listings
df_combined = asyncio.run(remove_expired_listings(df_combined, limiter))
# Reset the index
df_combined = df_combined.reset_index(drop=True)
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
try:
  df_combined.to_parquet(path="assets/datasets/lease.parquet")
except Exception as e:
  logger.warning(f"Error saving the combined dataframe as a parquet file: {e}. Falling back to CSV...")
  # Save the new combined dataframe to a CSV file
  try:
    df_combined.to_csv(path_or_buf="assets/datasets/lease.csv", index=False)
    logger.info("Saved the combined dataframe to a CSV file")
  except Exception as e:
    logger.error(f"Error saving the combined dataframe to a CSV file: {e}")

# Reclaim space in ImageKit
reclaim_imagekit_space(df_path="assets/datasets/lease.parquet", imagekit_instance=imagekit)