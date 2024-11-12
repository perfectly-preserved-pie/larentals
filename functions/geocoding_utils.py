from geopy.geocoders import GoogleV3
from loguru import logger
from typing import Tuple, Optional, Union
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

