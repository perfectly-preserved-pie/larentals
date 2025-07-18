from functions.aws_functions import load_ssm_parameters
from functions.dataframe_utils import *
from functions.geocoding_utils import *
from functions.mls_image_processing_utils import *
from functions.noise_level_utils import *
from functions.popup_utils import *
from geopy.geocoders import GoogleV3
from imagekitio import ImageKit
from loguru import logger
import glob
import os
import pandas as pd
import sys
import sqlite3
import argparse
import json

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("-n","--sample",  type=int, default=None,
    help="If set, run on a sample and exit before write")
  parser.add_argument("-l","--logfile", type=str, default=None,
    help="Path to log file (default ~/larentals/buy_dataframe.log)")
  parser.add_argument("--use-env",   action="store_true",           
    help="Load from .env instead of SSM")
  parser.add_argument("--use-nominatim", action="store_true",
    help="If set, use Nominatim instead of Google for geocoding"
  )
  args = parser.parse_args()
  SAMPLE_N = args.sample
  USE_NOMINATIM  = args.use_nominatim
  LOGFILE  = args.logfile or "~/larentals/buy_dataframe.log"

  # — Setup logging — remove defaults, add stderr + chosen file only
  logger.remove()
  logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")
  logger.add(
    LOGFILE,
    level="INFO",
    rotation="10 MB",
    retention="7 days",
    backtrace=True,
    diagnose=True,
  )

  ## SETUP AND VARIABLES
  # load env
  if args.use_env:
    load_dotenv(find_dotenv())
    logger.info("Loaded local .env")
  else:
    ssm_vals = load_ssm_parameters("/wheretolivedotla/")
    os.environ.update(ssm_vals)
    logger.info("Loaded from SSM")
  g = GoogleV3(api_key=os.getenv('GOOGLE_API_KEY')) # https://github.com/geopy/geopy/issues/171

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
  TABLE_NAME = "buy"

  try:
    ### PANDAS DATAFRAME OPERATIONS
    # find the one .xlsx in this pipelines/ folder
    script_dir = os.path.dirname(__file__)
    excel_files = glob.glob(os.path.join(script_dir, '*.xlsx'))
    if not excel_files:
      raise FileNotFoundError("Expected one .xlsx in pipelines/, found none")
    excel_path = os.path.join(script_dir, excel_files[0])
    xlsx = pd.read_excel(excel_path, sheet_name=None)

    # Merge all sheets into a single DataFrame
    df = pd.concat(xlsx.values(), ignore_index=True)

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
      'hod': 'hoa_fee',
      'list price': 'list_price',
      'lot size': 'lot_size',
      'lot sz': 'lot_size',
      'lp $/sqft': 'ppsqft',
      'lp': 'list_price',
      'mls': 'mls_number',
      'price per sqft': 'ppsqft',
      'price per square foot': 'ppsqft',
      'prop subtype': 'subtype',
      'sqft': 'sqft',
      'st #': 'street_number',
      'sub type': 'subtype',
      'yb': 'year_built',
      'year built': 'year_built',
      'yr built': 'year_built',
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

    ## Remember: N/A = Not Applicable to this home type while NaN = Unknown for some reason (missing data)
    # Assuming first sheet is single-family homes, second sheet is condos/townhouses, and third sheet is mobile homes
    # Set the subtype of every row in the first sheet to "Single Family Residence"
    xlsx[list(xlsx.keys())[0]]["subtype"] = "Single Family Residence"

    # Then proceed with concatenation
    df = pd.concat(renamed_sheets_corrected.values(), ignore_index=True)

    # Drop all rows with misc/irrelevant data
    df.dropna(subset=['mls_number'], inplace=True)

    # Remove all cells in mls_number that have more than 20 characters
    # To get rid of garbage data
    df = df[df['mls_number'].astype(str).str.len() <= 20]

    if SAMPLE_N:
      df = df.sample(SAMPLE_N, random_state=1)
      logger.info(f"[buy] TEST MODE: sampled {SAMPLE_N} new rows")

    # Define columns to remove all non-numeric characters from
    cols = ['hoa_fee', 'list_price', 'ppsqft', 'sqft', 'year_built', 'lot_size']
    # Loop through the columns and remove all non-numeric characters except for the string "N/A"
    for col in cols:
      if col not in df.columns:
        logger.warning(f"Column '{col}' is missing. Available columns: {list(df.columns)}")
        continue
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

    # Fetch missing zip codes
    df = fetch_missing_zip_codes(df, geolocator=g)

    # Tag each row with the date it was processed
    for row in df.itertuples():
      df.at[row.Index, 'date_processed'] = pd.Timestamp.today()

    # Create a new column with the full street address
    # Also strip whitespace from the St Name column
    # Convert the postal code into a string so we can combine string and int
    # https://stackoverflow.com/a/11858532
    df["full_street_address"] = df["street_address"].str.strip() + ',' + ' ' + df['city'] + ' ' + df["zip_code"].map(str)

    # Iterate through the dataframe and get the listed date and photo for rows
    df = update_dataframe_with_listing_data(df, imagekit_instance=imagekit)

    # Iterate through the dataframe and fetch coordinates for rows
    for row in df.itertuples():
      coordinates = return_coordinates(address=row.full_street_address, row_index=row.Index, geolocator=g, total_rows=len(df), use_nominatim=USE_NOMINATIM)
      df.at[row.Index, 'latitude'] = coordinates[0]
      df.at[row.Index, 'longitude'] = coordinates[1]

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

    # Assign the extracted bathrooms to the main DataFrame
    df = pd.concat([df, bathroom_details], axis=1)

    # If total_bathrooms is missing, fill it with the sum of the detailed bathrooms
    df['total_bathrooms'] = df['total_bathrooms'].fillna(df['full_bathrooms'] + df['half_bathrooms'] + df['three_quarter_bathrooms'] + df['extra_bathrooms'])

    logger.info("Bathroom columns extracted and total_bathrooms updated.")
    logger.debug(df[['bedrooms_bathrooms', 'total_bathrooms', 'full_bathrooms', 'half_bathrooms', 'three_quarter_bathrooms']].sample(n=10))

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

    # Reindex the dataframe
    df.reset_index(drop=True, inplace=True)

    # Add pageType context using vectorized operations to each feature's properties to pass through to the onEachFeature JavaScript function
    df['context'] = [{"pageType": "buy"} for _ in range(len(df))]

    ### MERGE WITH EXISTING DATA ###
    df_old = pd.DataFrame()
    if os.path.exists(DB_PATH):
      conn = sqlite3.connect(DB_PATH)
      try:
        # if SAMPLE_N is set, sample historical rows too
        if SAMPLE_N:
          df_old = pd.read_sql_query(
            f"SELECT * FROM {TABLE_NAME} ORDER BY RANDOM() LIMIT {SAMPLE_N}",
            conn
          )
        else:
          df_old = pd.read_sql_query(f"SELECT * FROM {TABLE_NAME}", conn)
      except Exception as e:
        logger.warning(f"No existing table {TABLE_NAME} or error reading it: {e}")
        df_old = pd.DataFrame()
      finally:
        conn.close()

    if not df_old.empty:
      df_old["listed_date"] = pd.to_datetime(df_old["listed_date"], errors="coerce")
      df_old["date_processed"] = pd.to_datetime(df_old["date_processed"], errors="coerce")
      df_combined = pd.concat([df, df_old], ignore_index=True, sort=False)
    else:
      df_combined = df.copy()
    df_combined = df_combined.drop_duplicates(subset=["mls_number"], keep="last")

    df_combined = flatten_subtype_column(df_combined) 
    df_combined = remove_inactive_listings(df_combined, table_name="buy")
    df_combined.reset_index(drop=True, inplace=True)
    
    # Attempt to reconstruct missing base address components from full_street_address
    required_base_fields = ['street_address', 'city', 'zip_code', 'street_number']
    for col in required_base_fields:
      if col not in df_combined.columns:
        df_combined[col] = None

    mask_missing = df_combined['street_address'].isna() & df_combined['full_street_address'].notna()

    # Extract street_number from start of street_address, city, zip from the full address
    reconstructed = df_combined.loc[mask_missing, 'full_street_address'].str.extract(
      r'^(?P<street_address>.*?), (?P<city>.*?) (?P<zip_code>\d{5})$'
    )

    # Attempt to extract street_number from reconstructed street_address
    reconstructed["street_number"] = reconstructed["street_address"].str.extract(r'^(?P<street_number>\d+)')

    # Apply reconstructed values back to df_combined
    for col in ['street_address', 'city', 'zip_code', 'street_number']:
      df_combined.loc[mask_missing & reconstructed[col].notna(), col] = reconstructed[col]

    # Clean up address fields
    df_combined['city']     = df_combined['city'].fillna('').astype(str)
    df_combined['zip_code'] = df_combined['zip_code'].fillna('').astype(str)
    df_combined["street_number"] = df_combined["street_number"].astype(str).str.replace(r"\.0$", "", regex=True)

    # Rebuild short_address and full_street_address for all rows with valid components
    valid_address_rows = df_combined["street_address"].notna()

    df_combined.loc[valid_address_rows, "short_address"] = (
      df_combined.loc[valid_address_rows, "street_address"].str.strip()
      + ", " + df_combined.loc[valid_address_rows, "city"].str.strip()
    )

    df_combined.loc[valid_address_rows, "full_street_address"] = (
      df_combined.loc[valid_address_rows, "street_address"].str.strip()
      + ", " + df_combined.loc[valid_address_rows, "city"].str.strip()
      + " " + df_combined.loc[valid_address_rows, "zip_code"].str.strip()
    )

    df_combined = re_geocode_above_lat_threshold(df_combined, geolocator=g)
    #df_combined = reduce_geojson_columns(df_combined)
    # Prepare final DataFrame
    df_combined.reset_index(drop=True, inplace=True)
    df_final = pd.DataFrame(df_combined)
    if "reported_as_inactive" not in df_final.columns:
      df_final["reported_as_inactive"] = False
    else:
      df_final["reported_as_inactive"] = df_final["reported_as_inactive"].fillna(False)
    if not df_old.empty:
      previously_flagged = set(df_old[df_old["reported_as_inactive"] == True]["mls_number"])
      df_final.loc[df_final["mls_number"].isin(previously_flagged), "reported_as_inactive"] = True

    # serialize any dict‐valued columns (e.g. context) to JSON text
    if "context" in df_combined.columns:
      df_combined["context"] = df_combined["context"].apply(json.dumps)

    # decide where to write
    if SAMPLE_N:
      target_table = f"{TABLE_NAME}_sample"
      logger.info(f"[buy] TEST MODE: writing {len(df_combined)} rows into table '{target_table}'")
    else:
      target_table = TABLE_NAME
      logger.info(f"[buy] FULL MODE: writing {len(df_combined)} rows into table '{target_table}'")

    # Save into SQLite
    try:
      conn = sqlite3.connect(DB_PATH)
      df_combined.to_sql(target_table, conn, if_exists="replace", index=False)
      conn.commit()
      conn.close()

      if SAMPLE_N:
        logger.success(f"[buy] Sample insert into '{target_table}' succeeded—exiting without overwriting '{TABLE_NAME}'.")
        sys.exit(0)

      logger.success(f"[buy] Full insert into '{TABLE_NAME}' succeeded.")
    except Exception as e:
      logger.error(f"Error updating SQLite table '{target_table}': {e}")
      sys.exit(1)
    
  except Exception as e:
    logger.exception(f"Error in buy pipeline: {e}")
    sys.exit(1)

    # Reclaim space in ImageKit
    #reclaim_imagekit_space(geojson_path="assets/datasets/buy.geojson", imagekit_instance=imagekit)