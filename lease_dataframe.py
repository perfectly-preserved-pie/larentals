from bs4 import BeautifulSoup as bs4
from dotenv import load_dotenv, find_dotenv
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
df = df.rename(columns=lambda c: 'mls_number' if c.startswith('Listing') else c)
df = df.rename(columns=lambda c: 'subtype' if c.startswith('Sub Type') else c)
df = df.rename(columns=lambda c: 'street_number' if c.startswith('St#') else c)
df = df.rename(columns=lambda c: 'street_name' if c.startswith('St Name') else c)
df = df.rename(columns=lambda c: 'list_price' if c.startswith('List') and c.endswith('Price') else c)
df = df.rename(columns=lambda c: 'garage_spaces' if c.startswith('Garage Spaces') else c)
df = df.rename(columns=lambda c: 'phone_number' if c.startswith('List Office Phone') else c)
df = df.rename(columns=lambda c: 'ppsqft' if c.startswith('Price Per') else c)
df = df.rename(columns=lambda c: 'YrBuilt' if c.startswith('Yr') else c)

# Drop all rows that don't have a MLS mls_number (aka misc data we don't care about)
# https://stackoverflow.com/a/13413845
df = df[df['mls_number'].notna()]

# Drop all duplicate rows based on MLS number
# Keep the last duplicate in case of updated listing details
df = df.drop_duplicates(subset='mls_number', keep="last")

# Remove all $ and , symbols from specific columns
# https://stackoverflow.com/a/46430853
if 'ppsqft' in df.columns:
  cols = ['DepositKey', 'DepositOther', 'DepositPets', 'DepositSecurity', 'list_price', 'ppsqft', 'Sqft']
elif 'ppsqft' not in df.columns:
  cols = ['DepositKey', 'DepositOther', 'DepositPets', 'DepositSecurity', 'list_price', 'Sqft']
# pass them to df.replace(), specifying each char and it's replacement:
df[cols] = df[cols].replace({'\$': '', ',': ''}, regex=True)

# Remove the square footage & YrBuilt abbreviations and cast as nullable Integer type
df['Sqft'] = df['Sqft'].str.split('/').str[0].apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())
df['YrBuilt'] = df['YrBuilt'].str.split('/').str[0].apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())

# Cast the list price column as integers
df['list_price'] = df['list_price'].apply(pd.to_numeric, errors='coerce', downcast='integer')

# Create a function to get coordinates from the full street address
def return_coordinates(address, row_index):
    try:
        geocode_info = g.geocode(address, components={'administrative_area': 'CA', 'country': 'US'})
        lat = float(geocode_info.latitude)
        lon = float(geocode_info.longitude)
    except Exception as e:
        lat = NaN
        lon = NaN
        logger.warning(f"Couldn't fetch geocode information for {address} (row {row.Index} of {len(df)}) because of {e}.")
    logger.success(f"Fetched coordinates {lat}, {lon} for {address} (row {row.Index} of {len(df)}).")
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
        webscrape = webscrape_bhhs(f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/", {row.Index}, {row.mls_number})
        df.at[row.Index, 'listed_date'] = webscrape[0]
        df.at[row.Index, 'mls_photo'] = imagekit_transform(webscrape[1], row[1])
        df.at[row.Index, 'listing_url'] = webscrape[2]
# if the Listed Date column doesn't exist (i.e this is a first run), create it using df.at
elif 'listed_date' not in df.columns:
    for row in df.itertuples():
        mls_number = row[1]
        webscrape = webscrape_bhhs(f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/", {row.Index}, {row.mls_number})
        df.at[row.Index, 'listed_date'] = webscrape[0]
        df.at[row.Index, 'mls_photo'] = imagekit_transform(webscrape[1], row[1])
        df.at[row.Index, 'listing_url'] = webscrape[2]

# Iterate through the dataframe and fetch coordinates for rows that don't have them
# If the Latitude column is already present, iterate through the null cells
# This assumption will reduce the number of API calls to Google Maps
if 'Latitude' in df.columns:
    for row in df['Latitude'].isnull().itertuples():
        coordinates = return_coordinates(df.at[row.Index, 'full_street_address'], row.Index)
        df.at[row.Index, 'Latitude'] = coordinates[0]
        df.at[row.Index, 'Longitude'] = coordinates[1]
# If the Coordinates column doesn't exist (i.e this is a first run), create it using df.at
elif 'Latitude' not in df.columns:
    for row in df.itertuples():
        coordinates = return_coordinates(df.at[row.Index, 'full_street_address'], row.Index)
        df.at[row.Index, 'Latitude'] = coordinates[0]
        df.at[row.Index, 'Longitude'] = coordinates[1]

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
df['ppsqft'] = df['ppsqft'].apply(pd.to_numeric, errors='coerce')
df['Latitude'] = df['Latitude'].apply(pd.to_numeric, errors='coerce')
df['Longitude'] = df['Longitude'].apply(pd.to_numeric, errors='coerce')
df['garage_spaces'] = df['garage_spaces'].apply(pd.to_numeric, errors='coerce')
# Convert the rest into nullable integer data types
# We should do this because these fields will often have missing data, forcing a conversion to float64 
# https://pandas.pydata.org/docs/user_guide/integer_na.html
# https://medium.com/when-i-work-data/nullable-integers-4060089f92ec
# We don't really have a need for floats here, just ints
# And this will prevent weird TypeError shit like TypeError: '>=' not supported between instances of 'str' and 'int'
# And this will also convert non-integers into NaNs
df['PostalCode'] = df['PostalCode'].apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())
df['Sqft'] = df['Sqft'].apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())
df['YrBuilt'] = df['YrBuilt'].apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())
df['DepositKey'] = df['DepositKey'].apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())
df['DepositOther'] = df['DepositOther'].apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())
df['DepositPets'] = df['DepositPets'].apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())
df['DepositSecurity'] = df['DepositSecurity'].apply(pd.to_numeric, errors='coerce').astype(pd.Int64Dtype())

# Replace all empty values in the following columns with NaN and cast the column as dtype string
# https://stackoverflow.com/a/47810911
df.Terms = df.Terms.astype("string").replace(r'^\s*$', pd.NA, regex=True)
if 'Furnished' in df.columns:
    df['Furnished'] = df['Furnished'].replace(r'^\s*$', pd.NA, regex=True).astype(pd.StringDtype())
else:
    df['Furnished'] = pd.NA
    df['Furnished'] = df['Furnished'].astype(pd.StringDtype())
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

# Convert the listed date into DateTime and set missing values to be NaT
# Infer datetime format for faster parsing
# https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.to_datetime.html
df['listed_date'] = pd.to_datetime(df['listed_date'], errors='coerce', infer_datetime_format=True)

# Convert date_processed into DateTime
df['date_processed'] = pd.to_datetime(df['date_processed'], errors='coerce', infer_datetime_format=True, format='%Y-%m-%d')

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
  year = df['YrBuilt'].at[i]
  garage = df['garage_spaces'].at[i]
  pets = df['PetsAllowed'].at[i]
  phone = df['phone_number'].at[i]
  terms = df['Terms'].at[i]
  sub_type = df['subtype'].at[i]
  listed_date = pd.to_datetime(df['listed_date'].at[i]).date() # Convert the full datetime into date only. See https://stackoverflow.com/a/47388569
  furnished = df['Furnished'].at[i]
  key_deposit = df['DepositKey'].at[i]
  other_deposit = df['DepositOther'].at[i]
  pet_deposit = df['DepositPets'].at[i]
  security_deposit = df['DepositSecurity'].at[i]
  laundry = df['LaundryFeatures'].at[i]
  # If there's no square footage, set it to "Unknown" to display for the user
  # https://towardsdatascience.com/5-methods-to-check-for-nan-values-in-in-python-3f21ddd17eed
  if pd.isna(square_ft) == True:
      square_ft = 'Unknown'
  # If there IS a square footage, convert it into an integer (round number)
  elif pd.isna(square_ft) == False:
      square_ft = f"{square_ft:,.0f} sq. ft"
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
      garage = f"{garage}"
  # Repeat for ppsqft
  if pd.isna(price_per_sqft) == True:
      price_per_sqft = 'Unknown'
  elif pd.isna(price_per_sqft) == False:
      price_per_sqft = f"${price_per_sqft:,.2f}"
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
      key_deposit = f"${key_deposit:,.0f}"
  if pd.isna(pet_deposit) == True:
      pet_deposit = 'Unknown'
  elif pd.isna(pet_deposit) == False:
      pet_deposit = f"${pet_deposit:,.0f}"
  if pd.isna(security_deposit) == True:
      security_deposit = 'Unknown'
  elif pd.isna(security_deposit) == False:
      security_deposit = f"${security_deposit:,.0f}"
  if pd.isna(other_deposit) == True:
      other_deposit = 'Unknown'
  elif pd.isna(other_deposit) == False:
      other_deposit = f"${other_deposit:,.0f}"
  if pd.isna(laundry) == True:
      laundry = 'Unknown'
  elif pd.isna(laundry) == False:
      laundry = f"{laundry}"
  if pd.isna(terms) == True:
      terms = 'Unknown'
  elif pd.isna(terms) == False:
      terms = f"{terms}"
  # If there's no MLS photo, set it to an empty string so it doesn't display on the tooltip
  # Basically, the HTML block should just be an empty Img tag
  if pd.isna(mls_photo) == True:
      mls_photo_html_block = "<img src='' referrerPolicy='noreferrer' style='display:block;width:100%;margin-left:auto;margin-right:auto' id='mls_photo_div'>"
  # If there IS an MLS photo, just set it to itself
  # The HTML block should be an Img tag wrapped inside a parent <a href> tag so the image will be clickable
  elif pd.isna(mls_photo) == False:
      mls_photo_html_block = f"""
        <a href="{mls_number_hyperlink}" referrerPolicy="noreferrer" target="_blank">
        <img src="{mls_photo}" referrerPolicy="noreferrer" style="display:block;width:100%;margin-left:auto;margin-right:auto" id="mls_photo_div">
        </a>
      """
  # If the MLS hyperlink is empty, that means there isn't a BHHS webpage to redirect to. Do not hyperlink to it.
  if pd.isna(mls_number_hyperlink) == True:
    listing_url_block = f"""
      <tr>
        <td><a href="https://github.com/perfectly-preserved-pie/larentals/wiki#listing-id" target="_blank">Listing ID (MLS#)</a></td>
        <td>{mls_number}</td>
      </tr>
    """
  # If the hyperlink exists, hyperlink it
  # Use a hyperlink to link to BHHS, don't use a referrer, and open the link in a new tab
  # https://www.freecodecamp.org/news/how-to-use-html-to-open-link-in-new-tab/
  elif pd.isna(mls_number_hyperlink) == False:
    listing_url_block = f"""
      <tr>
        <td><a href="https://github.com/perfectly-preserved-pie/larentals/wiki#listing-id" target="_blank">Listing ID (MLS#)</a></td>
        <td><a href="{mls_number_hyperlink}" referrerPolicy="noreferrer" target="_blank">{mls_number}</a></td>
      </tr>
    """
  # Return the HTML snippet as a string
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
        {listing_url_block}
        <tr id='list_office_phone'>
          <td>List Office Phone</td>
          <td><a href="tel:{phone}">{phone}</a></td>
        </tr>
        <tr id='rental_price'>
          <td>Rental Price</td>
          <td>${lc_price:,.0f}</td>
        </tr>
        <tr id='security_deposit'>
          <td>Security Deposit</td>
          <td>{security_deposit}</td>
        </tr>
        <tr id='pet_deposit'>
          <td>Pet Deposit</td>
          <td>{pet_deposit}</td>
        </tr>
        <tr id='key_deposit'>
          <td>Key Deposit</td>
          <td>{key_deposit}</td>
        </tr>
        <tr id='other_deposit'>
          <td>Other Deposit</td>
          <td>{other_deposit}</td>
        </tr>
        <tr id='square_feet'>
          <td>Square Feet</td>
          <td>{square_ft}</td>
        </tr>
        <tr id='price_per_sqft'>
          <td>Price Per Square Foot</td>
          <td>{price_per_sqft}</td>
        </tr>
        <tr id='bedrooms_bathrooms'>
          <td><a href="https://github.com/perfectly-preserved-pie/larentals/wiki#bedroomsbathrooms" target="_blank">Bedrooms/Bathrooms</a></td>
          <td>{brba}</td>
        </tr>
        <tr id='garage_spaces'>
          <td>Garage Spaces</td>
          <td>{garage}</td>
        </tr>
        <tr id='pets_allowed'>
          <td>Pets Allowed?</td>
          <td>{pets}</td>
        </tr>
        <tr id='furnished'>
          <td>Furnished?</td>
          <td>{furnished}</td>
        </tr>
        <tr id='laundry_features'>
          <td>Laundry Features</td>
          <td>{laundry}</td>
        </tr>
        <tr id='year_built'>
          <td>Year Built</td>
          <td>{year}</td>
        </tr>
        <tr id='rental_terms'>
          <td><a href="https://github.com/perfectly-preserved-pie/larentals/wiki#rental-terms" target="_blank">Rental Terms</a></td>
          <td>{terms}</td>
        </tr>
        <tr id='subtype'>
          <td><a href="https://github.com/perfectly-preserved-pie/larentals/wiki#physical-sub-type" target="_blank">Physical Sub Type</a></td>
          <td>{sub_type}</td>
        </tr>
      </tbody>
    </table>
    """

# Define a lambda function to replace the <table> tag
#replace_table_tag = lambda html: html.replace("<table>", "<table height='200' width='20%'>", 1)

# Apply the lambda function to create the popup_html_mobile column
#df['popup_html_mobile'] = df['popup_html'].apply(replace_table_tag)

# Do another pass to convert the date_processed column to datetime64 dtype
df['date_processed'] = pd.to_datetime(df['date_processed'], errors='coerce', infer_datetime_format=True, format='%Y-%m-%d')

# Save the dataframe for later ingestion by app.py
# Read the old dataframe in depending if it's a pickle (old) or parquet (new)
# If the pickle URL returns a 200 OK, read it in
if requests.get('https://github.com/perfectly-preserved-pie/larentals/raw/master/datasets/lease.pickle').status_code == 200:
  df_old = pd.read_pickle(filepath_or_buffer='https://github.com/perfectly-preserved-pie/larentals/raw/master/datasets/lease.pickle')
# If the pickle URL returns a 404 Not Found, read in the parquet file instead
elif requests.get('https://github.com/perfectly-preserved-pie/larentals/raw/master/datasets/lease.pickle').status_code == 404:
  df_old = pd.read_parquet(path='https://github.com/perfectly-preserved-pie/larentals/raw/master/datasets/lease.parquet')
# Combine both old and new dataframes
df_combined = pd.concat([df, df_old], ignore_index=True)
# Drop any dupes again
df_combined = df_combined.drop_duplicates(subset=['mls_number'], keep="last")
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
# Save the new dataframe
df_combined.to_parquet(path="datasets/lease.parquet")