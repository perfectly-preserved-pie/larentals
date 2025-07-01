from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from geopy.geocoders import GoogleV3, Nominatim
from loguru import logger
from typing import Tuple, Optional
import pandas as pd
import sys

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

def return_coordinates(
    address: str,
    row_index: int,
    geolocator: GoogleV3,
    total_rows: int,
    use_nominatim: bool = False,
    nominatim_user_agent: str = "larentals-geocoder",
    nominatim_timeout: int = 10
) -> Tuple[Optional[float], Optional[float]]:
    """
    Fetches the latitude and longitude of a given address using geocoding. Uses Nominatim if flagged, otherwise defaults to GoogleV3.
    
    Parameters:
    address (str): The full street address.
    row_index (int): The row index for logging.
    geolocator (GoogleV3): An instance of a geocoding class.
    total_rows (int): Total number of rows for logging.
    
    Returns:
    Tuple[Optional[float], Optional[float]]: Latitude and Longitude as a tuple, or (None, None) if unsuccessful.
    """
    if use_nominatim:
        try:
            nomi = Nominatim(user_agent=nominatim_user_agent)
            location = nomi.geocode(
                {
                    "street": address,
                    "county": "Los Angeles",
                    "state": "California",
                    "country": "USA"
                },
                bounded=True,  # enforce the restraints above
                timeout=nominatim_timeout
            )
            if location:
                return location.latitude, location.longitude
            logger.error(f"[{row_index}/{total_rows}] Nominatim: no result for '{address}'")
        except (GeocoderTimedOut, GeocoderServiceError, Exception) as e:
            logger.error(f"[{row_index}/{total_rows}] Nominatim error: {e}")
        return None, None

    # default: GoogleV3
    try:
        loc = geolocator.geocode(address, timeout=10, components={'administrative_area': 'CA', 'country': 'US'})
        if loc:
            return loc.latitude, loc.longitude
        logger.warning(f"[{row_index}/{total_rows}] GoogleV3: no result for '{address}'")
    except (GeocoderTimedOut, GeocoderServiceError, Exception) as e:
        logger.warning(f"[{row_index}/{total_rows}] GoogleV3 error: {e}")
    return None, None

def fetch_missing_city(address: str, geolocator: GoogleV3) -> Optional[str]:
    """
    Fetches the city name for a given address using geocoding.
    
    Parameters:
    address (str): The full street address.
    geolocator (GoogleV3): An instance of a GoogleV3 geocoding class.
    
    Returns:
    Optional[str]: The city name, or None if unsuccessful.
    """
    # Initialize city variable
    city = None
    
    try:
        geocode_info = geolocator.geocode(address, components={'administrative_area': 'CA', 'country': 'US'})
        
        # Get raw geocode information
        raw = geocode_info.raw['address_components']
        
        # Find the 'locality' aka city
        city = [addr['long_name'] for addr in raw if 'locality' in addr['types']][0]
        
        logger.info(f"Fetched city ({city}) for {address}.")
    except AttributeError:
        logger.warning(f"Geocoding returned no results for {address}.")
    except Exception as e:
        logger.warning(f"Couldn't fetch city for {address} because of {e}.")
    
    return city

def return_zip_code(address: str, geolocator: GoogleV3) -> Optional[str]:
    """
    Fetches the postal code for a given address using geocoding.

    Parameters:
    address (str): The full street address.
    geolocator (GoogleV3): An instance of the GoogleV3 geocoding class.

    Returns:
    Optional[str]: The postal code as a string, or None if unsuccessful.
    """
    postalcode = None

    try:
        geocode_info = geolocator.geocode(
            address, components={'administrative_area': 'CA', 'country': 'US'}
        )
        if geocode_info:
            raw = geocode_info.raw['address_components']
            # Find the 'postal_code'
            postalcode = next(
                (addr['long_name'] for addr in raw if 'postal_code' in addr['types']),
                None
            )
            if postalcode:
                logger.info(f"Fetched zip code ({postalcode}) for {address}.")
            else:
                logger.warning(f"No postal code found in geocoding results for {address}.")
        else:
            logger.warning(f"Geocoding returned no results for {address}.")
    except Exception as e:
        logger.warning(f"Couldn't fetch zip code for {address} because of {e}.")
        postalcode = None

    return postalcode

def fetch_missing_zip_codes(df: pd.DataFrame, geolocator) -> pd.DataFrame:
    """
    For rows where the 'zip_code' is missing or equals "Assessor",
    this function retrieves the missing postal code using the row's 'short_address'
    and updates the dataframe accordingly.

    Args:
        df (pd.DataFrame): DataFrame containing a 'zip_code' column and a 'short_address' column.
        geolocator: Geolocator instance used by the return_zip_code function.

    Returns:
        pd.DataFrame: The updated DataFrame with fixed zip codes.
    """
    missing_zip_df = df.loc[(df['zip_code'].isnull()) | (df['zip_code'] == 'Assessor')]
    total_missing = len(missing_zip_df)
    counter = 0
    for row in missing_zip_df.itertuples():
        counter += 1
        short_address = df.at[row.Index, 'short_address']
        logger.info(f"Fixing zip code for row {counter} of {total_missing}: {row.mls_number}")
        missing_zip = return_zip_code(short_address, geolocator=geolocator)
        df.at[row.Index, 'zip_code'] = missing_zip
    return df

def re_geocode_above_lat_threshold(
    df: pd.DataFrame,
    geolocator: GoogleV3,
    lat_threshold: float = 35.393528
) -> pd.DataFrame:
    """
    For rows where 'latitude' exceeds lat_threshold, re-fetch coordinates
    and overwrite the 'latitude' and 'longitude' columns in-place.
    """
    # Identify rows to re-geocode
    mask = df['latitude'] > lat_threshold
    total = mask.sum()
    if total == 0:
        return df

    counter = 0
    for idx in df[mask].index:
        counter += 1
        address = df.at[idx, 'full_street_address']
        logger.info(f"Re-geocoding row {counter} of {total}: MLS {df.at[idx,'mls_number']} "
                    f"with latitude {df.at[idx,'latitude']} above {lat_threshold}")
        new_lat, new_lon = return_coordinates(
            address=address,
            row_index=idx,
            geolocator=geolocator,
            total_rows=total
        )
        # Overwrite the numeric latitude & longitude
        df.at[idx, 'latitude']  = new_lat
        df.at[idx, 'longitude'] = new_lon

    return df