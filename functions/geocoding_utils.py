from geopy.geocoders import GoogleV3
from loguru import logger
from shapely.geometry import Point
from typing import Tuple, Optional
import geopandas as gpd
import pandas as pd
import sys

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

def return_coordinates(address: str, row_index: int, geolocator: GoogleV3, total_rows: int) -> Tuple[Optional[float], Optional[float]]:
    """
    Fetches the latitude and longitude of a given address using geocoding.
    
    Parameters:
    address (str): The full street address.
    row_index (int): The row index for logging.
    geolocator (GoogleV3): An instance of a geocoding class.
    total_rows (int): Total number of rows for logging.
    
    Returns:
    Tuple[Optional[float], Optional[float]]: Latitude and Longitude as a tuple, or (None, None) if unsuccessful.
    """
    # Initialize variables
    lat, lon = None, None

    try:
        geocode_info = geolocator.geocode(address, components={'administrative_area': 'CA', 'country': 'US'})
        lat = float(geocode_info.latitude)
        lon = float(geocode_info.longitude)
        logger.info(f"Fetched coordinates {lat}, {lon} for {address} (row {row_index + 1} of {total_rows}).")
    except AttributeError:
        logger.warning(f"Geocoding returned no results for {address} (row {row_index + 1} of {total_rows}).")
    except Exception as e:
        logger.warning(f"Couldn't fetch geocode information for {address} (row {row_index + 1} of {total_rows}) because of {e}.")

    return lat, lon

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

def re_geocode_above_lat_threshold(gdf: gpd.GeoDataFrame, geolocator, lat_threshold: float = 35.393528) -> gpd.GeoDataFrame:
    """
    Re-geocode rows in the GeoDataFrame where the 'latitude' exceeds a given threshold and update the
    geometry property with the new coordinates.

    For each row with a latitude greater than lat_threshold, the function uses the provided geolocator
    (via the return_coordinates function) to get updated latitude and longitude, then updates the geometry 
    property accordingly.

    Args:
        gdf (gpd.GeoDataFrame): Input GeoDataFrame containing 'latitude', 'longitude', and 'full_street_address' columns,
                                 as well as a valid 'geometry' column.
        geolocator: A geolocator instance to use for re-geocoding.
        lat_threshold (float): Latitude threshold above which re-geocoding occurs.

    Returns:
        gpd.GeoDataFrame: The updated GeoDataFrame with corrected coordinates in the 'geometry' property.
    """
    filtered_gdf = gdf[gdf['latitude'] > lat_threshold]
    total_rows = len(filtered_gdf)
    counter = 0

    for row in filtered_gdf.itertuples():
        counter += 1
        logger.info(f"Re-geocoding row {counter} of {total_rows}: MLS {row.mls_number} with latitude {row.latitude} above {lat_threshold}")
        new_coords = return_coordinates(
            address=row.full_street_address,
            row_index=row.Index,
            geolocator=geolocator,
            total_rows=total_rows
        )
        # Update the geometry property for the Feature (Point expects (lng, lat))
        gdf.at[row.Index, 'geometry'] = Point(new_coords[1], new_coords[0])
    
    return gdf