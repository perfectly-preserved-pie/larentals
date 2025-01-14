from dotenv import load_dotenv, find_dotenv
from functions.dataframe_utils import remove_inactive_listings, update_dataframe_with_listing_data, categorize_laundry_features, flatten_subtype_column
from functions.geocoding_utils import *
from functions.mls_image_processing_utils import *
from functions.noise_level_utils import *
from functions.popup_utils import *
from functions.webscraping_utils import *
from geopy.geocoders import GoogleV3
from imagekitio import ImageKit
from loguru import logger
import geopandas as gpd
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

# Standardize the column names by renaming them
# https://stackoverflow.com/a/65332240
# Define a renaming dictionary with exact matches
rename_dict = {
  '# prking spaces': 'parking_spaces',
  'address': 'street_name',
  'baths(fthq)': 'bathrooms',
  'br': 'bedrooms',
  'city': 'city',
  'furnished': 'furnished',
  'key deposit': 'key_deposit',
  'laundry': 'laundry',
  'lease terms': 'terms',
  'lot sz': 'lot_size',
  'lp $/sqft': 'ppsqft',
  'lp': 'list_price',
  'mls': 'mls_number',
  'other deposit': 'other_deposit',
  'pet deposit': 'pet_deposit',
  'pets': 'pet_policy',
  'prop subtype': 'subtype',
  'security deposit': 'security_deposit',
  'sqft': 'sqft',
  'st #': 'street_number',
  'yb': 'year_built',
  'zip': 'zip_code',
  "seller's agent 1 cell": 'phone_number',
}

# Rename columns based on exact matches
df = df.rename(columns=rename_dict)

# Drop the numbers in the first group of characters in the street_name column
df['street_name'] = df['street_name'].str.replace(r'^\d+\s*', '', regex=True)

# Drop all rows with misc/irrelevant data
df.dropna(subset=['street_name'], inplace=True)

# Columns to clean
cols = ['key_deposit', 'other_deposit', 'security_deposit', 'list_price', 'pet_deposit']
# Remove all non-numeric characters, convert to numeric, round to integers, fill NaNs with pd.NA, and cast to Nullable Integer Type
df[cols] = (
    df[cols]
    .replace({r'\$': '', ',': ''}, regex=True)
    .apply(pd.to_numeric, errors='coerce')
    .round(0)  # Round to ensure values are integers
    .astype(pd.UInt16Dtype())
)

# Cast 'sqft' to UInt32
df['sqft'] = df['sqft'].replace({',': ''}, regex=True).astype(pd.UInt32Dtype())

# Convert other columns to appropriate data types
df = df.astype({
  'year_built': 'UInt16',
  'parking_spaces': 'UInt8',
  'street_number': 'string'
})

# Handle lot_size column separately by removing commas, converting to numeric, and then to UInt32
df['lot_size'] = (
  df['lot_size']
  .replace({',': ''}, regex=True)
  .apply(pd.to_numeric, errors='coerce')
  .astype(pd.UInt32Dtype())
)

# Cast the following columns as a float and remove the leading $ sign
df['ppsqft'] = df['ppsqft'].replace(to_replace=r'[^\d]', value='', regex=True).astype(pd.Float32Dtype())

# Columns to be cast as strings
cols = ['mls_number', 'phone_number', 'street_name', 'zip_code', 'city']
df[cols] = df[cols].astype(pd.StringDtype())

# Columns to be cast as categories
cols = ['pet_policy', 'furnished', 'subtype', 'terms', 'laundry']
df[cols] = df[cols].astype(pd.CategoricalDtype())

# Extract total bathrooms and bathroom types (Full, Three-Quarter, Half, Quarter)
df[['total_bathrooms', 'full_bathrooms', 'three_quarter_bathrooms', 'half_bathrooms', 'quarter_bathrooms']] = df['bathrooms'].str.extract(r'(\d+\.\d+)\s\((\d+)\s(\d+)\s(\d+)\s(\d+)\)').astype(float)

# Convert bathroom columns to nullable integer type
for col in ['total_bathrooms', 'full_bathrooms', 'three_quarter_bathrooms', 'half_bathrooms', 'quarter_bathrooms']:
  df[col] = df[col].astype(pd.UInt8Dtype())

# Drop the original 'Baths(FTHQ)' column since we've extracted the data we need
df.drop(columns=['bathrooms'], inplace=True)

# Convert bedrooms to nullable integer type
df['bedrooms'] = df['bedrooms'].astype(pd.UInt8Dtype())

# Fetch missing city names
for row in df.loc[(df['city'].isnull()) & (df['zip_code'].notnull())].itertuples():
  df.at[row.Index, 'city'] = fetch_missing_city(f"{row.street_number} {row.street_name} {str(row.zip_code)}", geolocator=g)

# Create a new column with the Street Number & Street Name
df["short_address"] = (df["street_number"].astype(str) + ' ' + df["street_name"] + ', ' + df['city']).astype(pd.StringDtype())

# Filter the dataframe and return only rows with a NaN postal code
# For some reason some Postal Codes are "Assessor" :| so we need to include that string in an OR operation
# Then iterate through this filtered dataframe and input the right info we get using geocoding
for row in df.loc[(df['zip_code'].isnull()) | (df['zip_code'] == 'Assessor')].itertuples():
  short_address = df.at[row.Index, 'short_address']
  missing_zip_code = return_zip_code(short_address, geolocator=g)
  df.at[row.Index, 'zip_code'] = missing_zip_code

df['zip_code'] = df['zip_code'].astype(pd.StringDtype())

# Remove the trailing .0 in the zip_code column
df['zip_code'] = df['zip_code'].str.replace(r'\.0$', '', regex=True)

# Tag each row with the date it was processed
for row in df.itertuples():
  df.at[row.Index, 'date_processed'] = pd.Timestamp.today()

# Create a new column with the full street address
df["full_street_address"] = (
    df["street_number"].astype(str) + ' ' + 
    df["street_name"].str.strip() + ', ' + 
    df['city'] + ' ' + 
    df["zip_code"].astype(str)
).astype(pd.StringDtype())

# Iterate through the dataframe and get the listed date and photo for rows
df = update_dataframe_with_listing_data(df, imagekit_instance=imagekit)

# Iterate through the dataframe and fetch coordinates for rows
for row in df.itertuples():
  coordinates = return_coordinates(address=row.full_street_address, row_index=row.Index, geolocator=g, total_rows=len(df))
  df.at[row.Index, 'latitude'] = coordinates[0]
  df.at[row.Index, 'longitude'] = coordinates[1]

# These columns should stay floats
df['latitude'] = df['latitude'].apply(pd.to_numeric, errors='raise', downcast='float')
df['longitude'] = df['longitude'].apply(pd.to_numeric, errors='raise', downcast='float')

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

# Flatten the subtype column
df = flatten_subtype_column(df)

# Convert the listed date into DateTime and use the "mixed" format to handle the different date formats
# https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.to_datetime.html
df['listed_date'] = pd.to_datetime(df['listed_date'], errors='raise', format='mixed')

# Convert date_processed into DateTime
df['date_processed'] = pd.to_datetime(df['date_processed'], errors='coerce', format='%Y-%m-%d')

# Reindex the dataframe
df.reset_index(drop=True, inplace=True)

# Do another pass to convert the date_processed column to datetime64 dtype
df['date_processed'] = pd.to_datetime(df['date_processed'], errors='coerce', format='%Y-%m-%d')

# Add pageType context using vectorized operations to each feature's properties to pass through to the onEachFeature JavaScript function
df['context'] = [{"pageType": "lease"} for _ in range(len(df))]

# Save the dataframe for later ingestion by app.py
# Read in the old dataframe
df_old = gpd.read_file(filename='https://github.com/perfectly-preserved-pie/larentals/raw/master/assets/datasets/lease.geojson')
# Combine both old and new dataframes
df_combined = pd.concat([df, df_old], ignore_index=True)
# Drop any dupes again
df_combined = df_combined.drop_duplicates(subset=['mls_number'], keep="last")
# Iterate through the dataframe and drop rows with expired listings
df_combined = remove_inactive_listings(df_combined)
# Categorize the laundry features
df_combined['laundry_category'] = df_combined['laundry'].apply(categorize_laundry_features)
# Reset the index
df_combined = df_combined.reset_index(drop=True)
# Remove trailing 0 in the street_number column and the full_street_address column
df_combined['street_number'] = df_combined['street_number'].str.replace(r'\.0$', '', regex=True)
df_combined['full_street_address'] = df_combined['full_street_address'].str.replace(r'\.0$', '', regex=True)
# Filter the dataframe for rows outside of California
outside_ca_rows = df_combined[
  (df_combined['latitude'] < 32.5) | 
  (df_combined['latitude'] > 42) | 
  (df_combined['longitude'] < -124) | 
  (df_combined['longitude'] > -114)
]
total_outside_ca = len(outside_ca_rows)
counter = 0
for row in outside_ca_rows.itertuples():
  counter += 1
  logger.warning(f"Row {counter} out of {total_outside_ca}: {row.mls_number} has coordinates {row.latitude}, {row.longitude} which is outside California. Re-geocoding {row.mls_number}...")
  # Re-geocode the row
  coordinates = return_coordinates(address=row.full_street_address, row_index=row.Index, geolocator=g, total_rows=len(df))
  df_combined.at[row.Index, 'latitude'] = coordinates[0]
  df_combined.at[row.Index, 'longitude'] = coordinates[1]
# Save the new combined dataframe
# Convert the combined DataFrame to a GeoDataFrame
gdf_combined = gpd.GeoDataFrame(
  df_combined, 
  geometry=gpd.points_from_xy(df_combined.longitude, df_combined.latitude)
)
# Save the GeoDataFrame as a GeoJSON file
try:
  gdf_combined.to_file("assets/datasets/lease.geojson", driver="GeoJSON")
  logger.info("Saved the combined GeoDataFrame to a GeoJSON file.")
except Exception as e:
  logger.error(f"Error saving the combined GeoDataFrame to a GeoJSON file: {e}")

# Reclaim space in ImageKit
reclaim_imagekit_space(geojson_path="assets/datasets/lease.geojson", imagekit_instance=imagekit)