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
all_files = glob.glob(os.path.join(path, "*lacountyrentals*.csv"))
df = pd.concat((pd.read_csv(f, float_precision="round_trip", skipinitialspace=True) for f in all_files), ignore_index=True)

pd.set_option("display.precision", 10)

# Strip leading and trailing whitespaces from the column names
# https://stackoverflow.com/a/36082588
df.columns = df.columns.str.strip()

# Standardize the column names by renaminmg them
# https://stackoverflow.com/a/65332240
# Define a renaming dictionary based on patterns
rename_dict = {
  'Garage Spaces': 'garage_spaces',
  'List Office Phone': 'phone_number',
  'Listing': 'mls_number',
  'St Name': 'street_name',
  'St#': 'street_number',
  'Sub Type': 'subtype',
  'Yr': 'YrBuilt',
}

# Check if 'Price Per' column exists and add to renaming dictionary
if any(col.startswith('Price Per') for col in df.columns):
  rename_dict['Price Per'] = 'ppsqft'

# Rename columns
df = df.rename(columns=lambda c: next((v for k, v in rename_dict.items() if k in c), c))

# Special case for list price due to additional condition
df = df.rename(columns=lambda c: 'list_price' if c.startswith('List') and c.endswith('Price') else c)

# Drop all rows with misc/irrelevant data
df.dropna(subset=['street_name'], inplace=True)

# Columns to clean
cols = ['DepositKey', 'DepositOther', 'DepositPets', 'DepositSecurity', 'list_price', 'Sqft', 'YrBuilt']
if 'ppsqft' in df.columns:
  cols.append('ppsqft')

# Remove all non-numeric characters, convert to numeric, and cast to Nullable Integer Type
df[cols] = df[cols].replace(to_replace='[^\d]', value='', regex=True).apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())

# Check if 'ppsqft' column exists
if 'ppsqft' not in df.columns:
  # If it has a different name, replace 'Sqft' below with the correct column name
  df['ppsqft'] = (df['list_price'] / df['Sqft']).round(2)

# Fetch missing city names
for row in df.loc[(df['City'].isnull()) & (df['PostalCode'].notnull())].itertuples():
  df.at[row.Index, 'City'] = fetch_missing_city(f"{row.street_number} {row.street_name} {str(row.PostalCode)}", geolocator=g)

# Columns to be cast as strings
cols = ['street_number', 'street_name', 'City', 'mls_number', 'SeniorCommunityYN', 'Furnished', 'LaundryFeatures', 'subtype']

for col in cols:
  # If the column exists, replace empty strings with NaNs
  if col in df.columns:
    df[col] = df[col].replace(r'^\s*$', pd.NA, regex=True)
  # If the column does not exist, create it and fill it with NaNs
  else:
    df[col] = pd.NA
  # Cast the column as a string type (NA values will remain as NA)
  df[col] = df[col].astype(pd.StringDtype())

# Create a new column with the Street Number & Street Name
df["short_address"] = df["street_number"] + ' ' + df["street_name"] + ',' + ' ' + df['City']

# Filter the dataframe and return only rows with a NaN postal code
# For some reason some Postal Codes are "Assessor" :| so we need to include that string in an OR operation
# Then iterate through this filtered dataframe and input the right info we get using geocoding
for row in df.loc[(df['PostalCode'].isnull()) | (df['PostalCode'] == 'Assessor')].itertuples():
  short_address = df.at[row.Index, 'short_address']
  missing_postalcode = return_postalcode(short_address, geolocator=g)
  df.at[row.Index, 'PostalCode'] = missing_postalcode

df['PostalCode'] = df['PostalCode'].apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())

# Tag each row with the date it was processed
for row in df.itertuples():
  df.at[row.Index, 'date_processed'] = pd.Timestamp.today()

# Create a new column with the full street address
# Also strip whitespace from the St Name column
# Convert the postal code into a string so we can combine string and int
# https://stackoverflow.com/a/11858532
df["full_street_address"] = df["street_number"] + ' ' + df["street_name"].str.strip() + ',' + ' ' + df['City'] + ' ' + df["PostalCode"].astype(str)

# Iterate through the dataframe and get the listed date and photo for rows 
for row in df.itertuples():
  mls_number = row[1]
  webscrape = asyncio.run(webscrape_bhhs(url=f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/", row_index=row.Index, mls_number=mls_number, total_rows=len(df)))
  df.at[row.Index, 'listed_date'] = webscrape[0]
  df.at[row.Index, 'mls_photo'] = imagekit_transform(webscrape[1], row[1], imagekit_instance=imagekit)
  df.at[row.Index, 'listing_url'] = webscrape[2]

# Iterate through the dataframe and fetch coordinates for rows
for row in df.itertuples():
  coordinates = return_coordinates(address=row.full_street_address, row_index=row.Index, geolocator=g, total_rows=len(df))
  df.at[row.Index, 'Latitude'] = coordinates[0]
  df.at[row.Index, 'Longitude'] = coordinates[1]

#df = update_howloud_scores(df)

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
df['Total Bathrooms'] = df['Total Bathrooms'].apply(pd.to_numeric)
# These columns should stay floats
df['Latitude'] = df['Latitude'].apply(pd.to_numeric, errors='coerce')
df['Longitude'] = df['Longitude'].apply(pd.to_numeric, errors='coerce')
df['garage_spaces'] = df['garage_spaces'].astype('Float64')

# Replace all empty values in the following columns with NaN and cast the column as dtype string
# https://stackoverflow.com/a/47810911
df.Terms = df.Terms.astype("string").replace(r'^\s*$', pd.NA, regex=True)

## Laundry Features ##
# Replace all empty values in the following column with "Unknown" and cast the column as dtype string
df.LaundryFeatures = df.LaundryFeatures.astype("string").replace(r'^\s*$', "Unknown", regex=True)
# Fill in any NaNs in the Laundry column with "Unknown"
df.LaundryFeatures = df.LaundryFeatures.fillna(value="Unknown")
# Any string containing "Community" in the Laundry column should be replaced with "Community Laundry"
df['LaundryFeatures'] = df['LaundryFeatures'].str.replace("Community", "Community Laundry")
# Any string containing "Common" in the Laundry column should be replaced with "Community Laundry"
df['LaundryFeatures'] = df['LaundryFeatures'].str.replace("Common", "Community Laundry")
# Replace "Community Laundry Area" with "Community Laundry"
df['LaundryFeatures'] = df['LaundryFeatures'].str.replace("Community Laundry Area", "Community Laundry")

# Convert the listed date into DateTime and use the "mixed" format to handle the different date formats
# https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.to_datetime.html
df['listed_date'] = pd.to_datetime(df['listed_date'], errors='raise', format='mixed')

# Convert date_processed into DateTime
df['date_processed'] = pd.to_datetime(df['date_processed'], errors='coerce', format='%Y-%m-%d')

# Per CA law, ANY type of deposit is capped at rent * 3 months
# It doesn't matter the type of deposit, they all have the same cap
# Despite that, some landlords/realtors will list the property with an absurd deposit (100k? wtf) so let's rewrite those
# Use numpy .values to rewrite anything greater than $18000 ($6000 rent * 3 months) into $18000
# https://stackoverflow.com/a/54426197
df['DepositSecurity'].values[df['DepositSecurity'] > 18000] = 18000
df['DepositPets'].values[df['DepositPets'] > 18000] = 18000
df['DepositOther'].values[df['DepositOther'] > 18000] = 18000
df['DepositKey'].values[df['DepositKey'] > 18000] = 18000

# Rewrite anything greater than 5000 square feet as NaN
# Because there's no fucking way there's a RENTAL PROPERTY that is 5000+ sqft in this city
# It clearly must be some kind of clerical error so a NaN (unknown) is more appropriate
# All that being said, I should peruse new spreadsheets to make sure there isn't actually a valid property exceeds 5000 sqft
df['Sqft'].values[df['Sqft'] > 5000] = pd.NA

# Rewrite anything with >5 garage spaces as None
df['garage_spaces'].values[df['garage_spaces'] > 5] = None

# Keep rows with less than 6 bedrooms
# 6 bedrooms and above are probably multi family investments and not actual rentals
# They also skew the outliers, causing the sliders to go way up
df = df[df.Bedrooms < 6]

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