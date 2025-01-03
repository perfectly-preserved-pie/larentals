from dotenv import load_dotenv, find_dotenv
from functions.dataframe_utils import remove_inactive_listings, update_dataframe_with_listing_data
from functions.geocoding_utils import *
from functions.mls_image_processing_utils import *
from functions.noise_level_utils import *
from functions.popup_utils import *
from geopy.geocoders import GoogleV3
from imagekitio import ImageKit
from loguru import logger
from numpy import NaN
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
# Read all sheets from the Excel file
excel_file = glob.glob('*.xlsx')[0]
xlsx = pd.read_excel(excel_file, sheet_name=None)

## Remember: N/A = Not Applicable to this home type while NaN = Unknown for some reason (missing data)
# Assuming first sheet is single-family homes, second sheet is condos/townhouses, and third sheet is mobile homes
# Set the subtype of every row in the first sheet to "Single Family Residence"
xlsx[list(xlsx.keys())[0]]["Sub type"] = "Single Family Residence"

# Merge all sheets into a single DataFrame
df = pd.concat(xlsx.values())

# Drop the LSqft/Ac column only if it exists
if 'LSqft/Ac' in df.columns:
  df = df.drop(columns=['LSqft/Ac'])

pd.set_option("display.precision", 10)

# Strip leading and trailing whitespaces from the column names and convert them to lowercase
# https://stackoverflow.com/a/36082588
df.columns = df.columns.str.strip().str.lower()

# Initialize an empty dictionary to hold renamed DataFrames
renamed_sheets_corrected = {}

# Using a dictionary for clearer column renaming
specific_column_map = {
  '# prking spaces': 'garage_spaces',
  'address': 'street_address',
  'baths(fthq)': 'bedrooms_bathrooms',
  'br': 'bedrooms',
  'city': 'city',
  'hoa fee freq.1': 'hoa_fee_frequency',
  'hoa fees': 'hoa_fee',
  'hoa': 'hoa_fee',
  'list price': 'list_price',
  'lot size': 'lot_size',
  'mls': 'mls_number',
  'price per square foot': 'ppsqft',
  'sqft': 'sqft',
  'st #': 'street_number',
  'sub type': 'subtype',
  'year built': 'year_built',
  'zip': 'zip_code',
}

# Rename columns using the specific map in a safe manner
for sheet_name, sheet_df in xlsx.items():
  original_columns = sheet_df.columns.tolist()
  sheet_df.columns = sheet_df.columns.str.strip().str.lower()
  # Identify columns that can be renamed
  existing_renames = {col: specific_column_map[col] for col in sheet_df.columns if col in specific_column_map}
  if existing_renames:
    logger.info(f"Renaming columns in sheet '{sheet_name}': {existing_renames}")
  else:
    logger.warning(f"No columns to rename in sheet '{sheet_name}'.")
  # Rename the columns
  renamed_sheet_df = sheet_df.rename(columns=existing_renames)
  # Add the renamed DataFrame to the dictionary
  renamed_sheets_corrected[sheet_name] = renamed_sheet_df

# Then proceed with concatenation
df = pd.concat(renamed_sheets_corrected.values(), ignore_index=True)

# Drop all rows with misc/irrelevant data
df.dropna(subset=['mls_number'], inplace=True)

# Define columns to remove all non-numeric characters from
cols = ['hoa_fee', 'list_price', 'ppsqft', 'sqft', 'year_built', 'lot_size']
# Loop through the columns and remove all non-numeric characters except for the string "N/A"
for col in cols:
    df[col] = df[col].apply(lambda x: ''.join(c for c in str(x) if c.isdigit() or c == '.' or str(x) == 'N/A'))

# Reindex the dataframe
df.reset_index(drop=True, inplace=True)

# Fetch missing city names
for row in df.loc[(df['city'].isnull()) & (df['zip_code'].notnull())].itertuples():
  df.at[row.Index, 'city'] = fetch_missing_city(f"{row.street_address} {str(row.city)} {str(row.zip_code)}", geolocator=g)

# Cast these columns as strings so we can concatenate them
cols = ['street_number', 'street_address', 'city', 'mls_number']
for col in cols:
  df[col] = df[col].astype("string")

# Create a new column with the Street Number & Street Name
df["short_address"] = df["street_address"].str.strip() + ',' + ' ' + df['city']

# Filter the dataframe and return only rows with a NaN postal code
# For some reason some Postal Codes are "Assessor" :| so we need to include that string in an OR operation
# Then iterate through this filtered dataframe and input the right info we get using geocoding
for row in df.loc[(df['zip_code'].isnull()) | (df['zip_code'] == 'Assessor')].itertuples():
  short_address = df.at[row.Index, 'short_address']
  missing_zip_code = return_zip_code(short_address, geolocator=g)
  df.at[row.Index, 'zip_code'] = missing_zip_code

# Tag each row with the date it was processed
for row in df.itertuples():
  df.at[row.Index, 'date_processed'] = pd.Timestamp.today()

# Create a new column with the full street address
# Also strip whitespace from the St Name column
# Convert the postal code into a string so we can combine string and int
# https://stackoverflow.com/a/11858532
df["full_street_address"] = df["street_address"].str.strip() + ',' + ' ' + df['city'] + ' ' + df["zip_code"].map(str)

# Iterate through the dataframe and get the listed date and photo for rows
df = update_dataframe_with_listing_data(df, imagekit_instance=imagekit, for_sale=True)

# Iterate through the dataframe and fetch coordinates for rows
for row in df.itertuples():
  coordinates = return_coordinates(address=row.full_street_address, row_index=row.Index, geolocator=g, total_rows=len(df))
  df.at[row.Index, 'latitude'] = coordinates[0]
  df.at[row.Index, 'longitude'] = coordinates[1]

#df = update_howloud_scores(df)

# Cast HowLoud columns as either nullable strings or nullable integers
#howloud_columns = [col for col in df.columns if col.startswith("howloud_")]
#for col in howloud_columns:
  # Check if the content is purely numeric
#  if df[col].dropna().astype(str).str.isnumeric().all():
#    df[col] = df[col].astype(pd.Int32Dtype())  # Cast to nullable integer
#  else:
#    df[col] = df[col].astype(pd.StringDtype())  # Cast to string

### BATHROOMS PARSING
# Split the Bedroom/Bathrooms column to extract total and detailed bathroom counts
# Expected format: '1.00 (1 0 0 0)' where:
# - 1.00 is the total bathrooms
# - 1 is full bathrooms
# - 0 is half bathrooms
# - 0 is three-quarter bathrooms
# - 0 is extra bathrooms

# Define a regex pattern to extract total bathrooms and bathroom details inside parentheses
# Expected format: '1.00 (1 0 0 0)'
bathroom_pattern = r'^(\d+\.\d+)\s+\((\d+)\s+(\d+)\s+(\d+)\s+(\d+)\)'

# Extract the numbers: total, full, half, three_quarter, extra
bathroom_details = df['bedrooms_bathrooms'].str.extract(bathroom_pattern)

# Check if extraction was successful
if bathroom_details.isnull().values.any():
  logger.warning("Some rows in 'bedrooms_bathrooms' do not match the expected format.")

# Rename the extracted columns
bathroom_details.columns = [
  'total_bathrooms',
  'full_bathrooms',
  'half_bathrooms',
  'three_quarter_bathrooms',
  'extra_bathrooms'
]

# Convert total_bathrooms to nullable UInt8
bathroom_details['total_bathrooms'] = bathroom_details['total_bathrooms'].astype("float").astype("UInt8")

# Convert to numeric types
bathroom_details = bathroom_details.astype("UInt8")

# Assign the extracted bathrooms to the main DataFrame
df = pd.concat([df, bathroom_details], axis=1)

# Validate the 'total_bathrooms' against the detailed counts
df['calculated_total_bathrooms'] = (
  df['full_bathrooms'] +
  0.5 * df['half_bathrooms'] +
  0.75 * df['three_quarter_bathrooms']
)

# Drop the 'calculated_total_bathrooms' column
df = df.drop(columns=['calculated_total_bathrooms'])

logger.info("Bathroom columns extracted and total_bathrooms updated.")
logger.debug(df[['bedrooms_bathrooms', 'total_bathrooms', 'full_bathrooms', 'half_bathrooms', 'three_quarter_bathrooms']].sample(n=10))

# Convert a few columns into int64
# pd.to_numeric will convert into int64 or float64 automatically, which is cool
# These columns are assumed to have NO MISSING DATA, so we can cast them as int64 instead of floats (ints can't handle NaNs)
# These columns should stay floats
df['latitude'] = df['latitude'].apply(pd.to_numeric, errors='coerce')
df['longitude'] = df['longitude'].apply(pd.to_numeric, errors='coerce')
# Convert zip_code into string
df['zip_code'] = df['zip_code'].apply(pd.to_numeric, errors='coerce').astype("string")

# Convert the listed date into DateTime and use the "mixed" format to handle the different date formats
# https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.to_datetime.html
df['listed_date'] = pd.to_datetime(df['listed_date'], errors='raise', format='mixed')

# Convert date_processed into DateTime
df['date_processed'] = pd.to_datetime(df['date_processed'], errors='raise', format='mixed')

cols = ['full_bathrooms', 'bedrooms', 'year_built', 'sqft', 'list_price', 'total_bathrooms', 'ppsqft', 'hoa_fee', 'bedrooms_bathrooms']
# Convert columns to string type for string operations
df[cols] = df[cols].astype(str)
# Remove commas and other non-numeric characters
df[cols] = df[cols].replace({',': '', r'[^0-9\.]': ''}, regex=True)
# Replace empty strings with Unknown
df[cols] = df[cols].replace('', 'Unknown')
# Convert columns to numeric
df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
# Cast specified columns as nullable integers
int_cols = ['full_bathrooms', 'bedrooms', 'year_built', 'sqft', 'list_price', 'total_bathrooms']
df[int_cols] = df[int_cols].astype('Int64')

# Cast these columns as nullable strings
cols = ['short_address', 'full_street_address', 'mls_number', 'mls_photo', 'listing_url', 'subtype', 'bedrooms_bathrooms', 'hoa_fee_frequency']
for col in cols:
  df[col] = df[col].astype('string')


# Reindex the dataframe
df.reset_index(drop=True, inplace=True)

# Add pageType context using vectorized operations to each feature's properties to pass through to the onEachFeature JavaScript function
df['context'] = [{"pageType": "buy"} for _ in range(len(df))]

# Save the dataframe for later ingestion by app.py
# Read in the old dataframe
df_old = gpd.read_file(filename='https://github.com/perfectly-preserved-pie/larentals/raw/master/assets/datasets/buy.geojson')
# Combine both old and new dataframes
df_combined = pd.concat([df, df_old], ignore_index=True)
# Drop any dupes again
df_combined = df_combined.drop_duplicates(subset=['mls_number'], keep="last")
# Iterate through the dataframe and drop rows with expired listings
df_combined = remove_inactive_listings(df_combined)
# Reset the index
df_combined = df_combined.reset_index(drop=True)
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
  gdf_combined.to_file("assets/datasets/buy.geojson", driver="GeoJSON")
  logger.info("Saved the combined GeoDataFrame to a GeoJSON file.")
except Exception as e:
  logger.error(f"Error saving the combined GeoDataFrame to a GeoJSON file: {e}")

# Reclaim space in ImageKit
reclaim_imagekit_space(geojson_path="assets/datasets/buy.geojson", imagekit_instance=imagekit)