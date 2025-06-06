from functions.aws_functions import load_ssm_parameters, upload_file_to_s3
from functions.dataframe_utils import *
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
import sqlite3
import argparse


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument(
      "--sample", "-n", type=int, default=None,
      help="If set, sample N rows from both CSVs and existing DB and run pipeline without saving"
  )
  args = parser.parse_args()
  SAMPLE_N = args.sample

  ## SETUP AND VARIABLES
  # Load everything from AWS SSM into os.environ ─
  ssm_values = load_ssm_parameters("/wheretolivedotla/")
  os.environ.update(ssm_values)

  g = GoogleV3(api_key=os.getenv('GOOGLE_API_KEY')) # https://github.com/geopy/geopy/issues/171

  logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")
  # Log to a file
  logger.add(
    "/var/log/lease_dataframe.log",
    level="INFO",
    rotation="10 MB",        # optional
    retention="7 days",      # optional
    backtrace=True,
    diagnose=True
  )

  # ImageKit.IO
  # https://docs.imagekit.io/api-reference/upload-file-api/server-side-file-upload#uploading-file-via-url
  # Create keys at https://imagekit.io/dashboard/developer/api-keys
  imagekit = ImageKit(
      public_key=os.getenv('IMAGEKIT_PUBLIC_KEY'),
      private_key=os.getenv('IMAGEKIT_PRIVATE_KEY'),
      url_endpoint = os.getenv('IMAGEKIT_URL_ENDPOINT')
  )

  # Database path and table name
  DB_PATH = "assets/datasets/larentals.db"
  TABLE_NAME = "lease"

  # Make the dataframe a global variable
  global df

  try:
    ### PANDAS DATAFRAME OPERATIONS
    # Load all CSVs and concat into one dataframe
    # https://stackoverflow.com/a/21232849
    path = "."
    all_files = glob.glob(os.path.join(path, "*Renter*.csv"))
    df = pd.concat((pd.read_csv(f, float_precision="round_trip", skipinitialspace=True) for f in all_files), ignore_index=True)

    pd.set_option("display.precision", 10)

    # sample new rows if in test mode
    if SAMPLE_N:
      df = df.sample(SAMPLE_N, random_state=1)

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
    cols = ['key_deposit', 'other_deposit', 'security_deposit', 'list_price', 'pet_deposit', 'lot_size', 'sqft', 'year_built']
    # Remove all non-numeric characters, convert to numeric, and round to integers
    numeric_cleaned = (
      df[cols]
      .replace({r'\$': '', ',': ''}, regex=True)
      .apply(pd.to_numeric, errors='coerce')
      .round(0)
    )
    
    # Assign cleaned columns back to the dataframe
    df[cols] = numeric_cleaned

    # Clean ppsqft column separately to shaving off the decimal places
    df['ppsqft'] = df['ppsqft'].replace({r'\$': '', ',': ''}, regex=True)

    # Extract total bathrooms and bathroom types (Full, Three-Quarter, Half, Quarter)
    df[['total_bathrooms', 'full_bathrooms', 'three_quarter_bathrooms', 'half_bathrooms', 'quarter_bathrooms']] = df['bathrooms'].str.extract(r'(\d+\.\d+)\s\((\d+)\s(\d+)\s(\d+)\s(\d+)\)')

    # Drop the original 'Baths(FTHQ)' column since we've extracted the data we need
    df.drop(columns=['bathrooms'], inplace=True)

    # Fetch missing city names
    for row in df.loc[(df['city'].isnull()) & (df['zip_code'].notnull())].itertuples():
      df.at[row.Index, 'city'] = fetch_missing_city(f"{row.street_number} {row.street_name} {str(row.zip_code)}", geolocator=g)

    # Create a new column with the Street Number & Street Name
    df["short_address"] = (df["street_number"].astype(str) + ' ' + df["street_name"] + ', ' + df['city'])

    # Fetch missing zip codes
    df = fetch_missing_zip_codes(df, geolocator=g)
    df['zip_code'] = df['zip_code']

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
    )

    # Iterate through the dataframe and get the listed date and photo for rows
    df = update_dataframe_with_listing_data(df, imagekit_instance=imagekit)

    # Iterate through the dataframe and fetch coordinates for rows
    for row in df.itertuples():
      coordinates = return_coordinates(address=row.full_street_address, row_index=row.Index, geolocator=g, total_rows=len(df))
      df.at[row.Index, 'latitude'] = coordinates[0]
      df.at[row.Index, 'longitude'] = coordinates[1]

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

    ### MERGE WITH EXISTING DATA ###
    # Read existing lease data from SQLite to preserve historical listings and flags
    df_old = pd.DataFrame()
    if os.path.exists(DB_PATH):
      conn = sqlite3.connect(DB_PATH)
      try:
        df_old = pd.read_sql_query(f"SELECT * FROM {TABLE_NAME}", conn)
      except Exception as e:
        logger.warning(f"No existing table {TABLE_NAME} or error reading it: {e}")
        df_old = pd.DataFrame()
      finally:
        conn.close()

    # sample old rows too if in test mode
    if SAMPLE_N and not df_old.empty:
      df_old = df_old.sample(min(SAMPLE_N, len(df_old)), random_state=1)

    # Combine new and old data
    if not df_old.empty:
      # Ensure datetime columns in old data are proper dtypes
      df_old["listed_date"] = pd.to_datetime(df_old["listed_date"], errors="coerce")
      df_old["date_processed"] = pd.to_datetime(df_old["date_processed"], errors="coerce")
      df_combined = pd.concat([df, df_old], ignore_index=True, sort=False)
      # Drop any dupes again
      df_combined = df_combined.drop_duplicates(subset=['mls_number'], keep="last")
      # Iterate through the dataframe and drop rows with expired listings
      df_combined = remove_inactive_listings(df_combined, table_name="lease")
      # Categorize the laundry features
      df_combined['laundry_category'] = df_combined['laundry'].apply(categorize_laundry_features)
      # Reset the index
      df_combined = df_combined.reset_index(drop=True)
      for col in ['street_number','full_street_address','short_address']:
        df_combined[col] = (
            df_combined[col]
              .fillna('')           # no more NaNs
              .astype(str)          # ensure string dtype
              .str.replace(r'\.0$', '', regex=True)
        )
      # Remove trailing 0 in the street_number column and the full_street_address column and the short_address column
      df_combined['street_number'] = df_combined['street_number'].str.replace(r'\.0', '', regex=True)
      df_combined['full_street_address'] = df_combined['full_street_address'].str.replace(r'\.0', '', regex=True)
      df_combined['short_address'] = df_combined['short_address'].str.replace(r'\.0', '', regex=True)
      # Compute geometry from lon/lat where available
      computed_geometry = gpd.points_from_xy(df_combined.longitude, df_combined.latitude)
      # Convert to a Series with the same index as the original DataFrame
      computed_geometry_series = pd.Series(computed_geometry, index=df_combined.index)
      # Combine the existing geometry with computed_geometry_series
      df_combined["geometry"] = df_combined.get("geometry", computed_geometry_series).combine_first(computed_geometry_series)
      # Create the GeoDataFrame using the updated geometry column
      gdf_combined = gpd.GeoDataFrame(df_combined, geometry="geometry")
      # Re-geocode rows where latitude is above a certain threshold
      gdf_combined = re_geocode_above_lat_threshold(gdf_combined, geolocator=g)
      # Drop some columns that are no longer needed
      gdf_combined = reduce_geojson_columns(gdf=gdf_combined)
      # Clean up outliers
      gdf_combined = drop_high_outliers(gdf=gdf_combined, absolute_caps={"total_bathrooms": 7, "bedrooms": 7, "parking_spaces": 5, "sqft": 10000})
    else:
      df_combined = df.copy()

    if "reported_as_inactive" not in gdf_combined.columns:
      gdf_combined["reported_as_inactive"] = False
    else:
      gdf_combined["reported_as_inactive"] = gdf_combined["reported_as_inactive"].fillna(False)
    if not df_old.empty:
      previously_flagged = set(df_old[df_old["reported_as_inactive"] == True]["mls_number"])
      gdf_combined.loc[gdf_combined["mls_number"].isin(previously_flagged), "reported_as_inactive"] = True

    # before saving, if in test mode exit here
    if SAMPLE_N:
      logger.success(f"[lease] Test run succeeded on {SAMPLE_N} rows – exiting before write.")
      sys.exit(0)

    # Save the GeoDataFrame to the SQLite database
    try:
      conn = sqlite3.connect(DB_PATH)
      # overwrite the existing 'lease' table
      gdf_combined.drop(columns=["geometry"]).to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
      conn.commit()
      conn.close()
      logger.info(f"Updated SQLite table '{TABLE_NAME}' in '{DB_PATH}'.")
    except Exception as e:
      logger.error(f"Error updating SQLite table '{TABLE_NAME}': {e}")

    # Reclaim space in ImageKit
    #reclaim_imagekit_space(geojson_path="assets/datasets/lease.geojson", imagekit_instance=imagekit)
  except Exception as e:
    logger.exception(f"Error in lease pipeline: {e}")
    sys.exit(1)