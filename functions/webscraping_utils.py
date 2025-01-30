from bs4 import BeautifulSoup
from datetime import datetime
from loguru import logger
from typing import Tuple, Optional, List, Union
import pandas as pd
import re
import requests
import sys
import time

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="DEBUG")

def check_expired_listing_bhhs(url: str, mls_number: str) -> bool:
    """
    Checks if a BHHS listing has expired by looking for a specific message on the page.

    Parameters:
    url (str): The URL of the listing to check.
    mls_number: The MLS number of the listing.

    Returns:
    bool: True if the listing has expired, False otherwise.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()

        time.sleep(5)

        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for the message indicating the listing is no longer active
        description_div = soup.find('div', class_='page-description')
        if description_div:
            description_text = " ".join(description_div.text.split())
            if "We're sorry, the listing you are looking for is no longer active." in description_text:
                return True
        return False

    except requests.Timeout:
        logger.warning(f"Timeout occurred while checking if the listing for {mls_number} has expired.")
    except requests.HTTPError as e:
        logger.error(f"HTTP error occurred for MLS {mls_number}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred for MLS {mls_number}: {e}")

    return False

def check_expired_listing_theagency(listing_url: str, mls_number: str, board_code: str = 'clr') -> bool:
    """
    Checks if a listing has been sold based on the 'IsSold' key from The Agency API.

    Parameters:
    listing_url (str): The URL of the listing to check.
    mls_number (str): The MLS number of the listing.
    board_code (str, optional): The board code extracted from the listing URL or a default value.

    Returns:
    bool: True if the listing has been sold, False otherwise.
    """
    # Try to extract the board code from the listing_url if it varies
    try:
        pattern = r'https://.*?idcrealestate\.com/.*?/(?P<board_code>\w+)/'
        match = re.search(pattern, listing_url)
        if match:
            board_code = match.group('board_code')
        else:
            # Use the default board_code provided in the function parameter
            pass  # board_code remains as provided
    except Exception as e:
        logger.warning(f"Could not extract board code from listing URL: {listing_url}. Error: {e}")

    api_url = f'https://search-service.idcrealestate.com/api/property/en_US/d4/sold-detail/{board_code}/{mls_number}'
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/json",
        "Referer": "https://www.theagencyre.com/",
        "X-Tenant": "QUdZfFBST0R8Q09NUEFOWXwx",
        "Origin": "https://www.theagencyre.com",
        "Connection": "keep-alive",
    }

    try:
        response = requests.get(api_url, headers=headers, timeout=5)
        response.raise_for_status()
        time.sleep(5)
        data = response.json()
        is_sold = data.get('IsSold', False)
        if is_sold:
            logger.info(f"Listing {mls_number} has been sold.")
        return is_sold
    except requests.HTTPError as e:
        logger.error(f"HTTP error occurred while checking if the listing for MLS {mls_number} has been sold: {e}")
    except Exception as e:
        logger.error(f"An error occurred while checking if the listing for MLS {mls_number} has been sold: {e}")

    return False

def webscrape_bhhs(url: str, row_index: int, mls_number: str, total_rows: int) -> Tuple[Optional[pd.Timestamp], Optional[str], Optional[str]]:
    """
    Scrapes the BHHS website for listing details.

    Parameters:
    url (str): The URL of the listing to scrape.
    row_index (int): The current row index being processed.
    mls_number (str): The MLS number of the listing.
    total_rows (int): The total number of rows to process.

    Returns:
    Tuple[Optional[pd.Timestamp], Optional[str], Optional[str]]:
        - listed_date (pd.Timestamp): The listing date if found.
        - photo (str): The URL of the listing photo if found.
        - link (str): The detailed listing URL if found.
        Returns (None, None, None) if data is not found or an error occurs.
    """
    logger.info(f"Scraping BHHS page for {mls_number} (row {row_index + 1} of {total_rows}).")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        time.sleep(5)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Initialize variables
        listed_date = None
        photo = None
        link = None

        # Extract the detailed listing URL
        link_tag = soup.find('a', class_='btn cab waves-effect waves-light btn-details show-listing-details')
        if link_tag and 'href' in link_tag.attrs:
            link = f"https://www.bhhscalifornia.com{link_tag['href']}"

        # Extract the photo URL
        photo_tag = soup.find('a', class_='show-listing-details')
        if photo_tag and photo_tag.find('img'):
            photo = photo_tag.find('img')['src']

        # Extract the listed date
        date_tag = soup.find('p', class_='summary-mlsnumber')
        if date_tag:
            listed_date_text = date_tag.text.split()[-1]
            listed_date = pd.Timestamp(listed_date_text)

        return listed_date, photo, link

    except requests.HTTPError as e:
        logger.warning(f"HTTP error occurred while scraping BHHS page for {mls_number}: {e}")
    except Exception as e:
        logger.warning(f"Error scraping BHHS page for {mls_number}: {e}")

    return None, None, None

def extract_street_name(full_street_address: str) -> Optional[str]:
    """
    Extracts the street name from a full street address.

    This function handles addresses with or without unit numbers and directional indicators.
    It splits the address to isolate the street name component.

    Args:
        full_street_address (str): The full street address (e.g., "118 S Cordova ST #B, ALHAMBRA 91801")

    Returns:
        Optional[str]: The extracted street name in lowercase if successful; otherwise, None.
    """
    # Split the address at the comma
    address_first_part = full_street_address.split(',')[0].strip()
    # Remove unit numbers (e.g., #A, #1/2)
    address_first_part = re.sub(r'#\S+', '', address_first_part)
    # Split the first part by spaces
    tokens = address_first_part.split()
    # Check if tokens are sufficient
    if len(tokens) >= 2:
        possible_direction = tokens[1].upper()
        if possible_direction in ['N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW']:
            # Direction present
            if len(tokens) >= 3:
                street_name = tokens[2]
            else:
                return None
        else:
            # No direction
            street_name = tokens[1]
        return street_name.lower()
    else:
        # Can't extract street name
        return None

def extract_zip_code(full_street_address: str) -> Optional[str]:
    """
    Extracts the ZIP code from a full street address.

    Uses regular expressions to find a 5-digit ZIP code, optionally handling ZIP+4 formats.

    Args:
        full_street_address (str): The full street address (e.g., "118 S Cordova ST #B, ALHAMBRA 91801")

    Returns:
        Optional[str]: The extracted ZIP code if successful; otherwise, None.
    """
    match = re.search(r'\b\d{5}(?:-\d{4})?\b', full_street_address)
    if match:
        return match.group()
    else:
        return None

def fetch_the_agency_data(
    mls_number: str,
    row_index: int,
    total_rows: int,
) -> Tuple[Optional[datetime.date], Optional[str], Optional[str]]:
    """
    Fetches property data for a given MLS number from The Agency API.

    Parameters:
    mls_number (str): The MLS number of the property to fetch.
    row_index (int): The row index for logging or debugging purposes.
    total_rows (int): Total rows being processed for progress indication.

    Returns:
    Tuple[Optional[datetime.date], Optional[str], Optional[str]]: 
        - The listing date (as a datetime.date object) if found; otherwise, None.
        - The detail URL of the property if found; otherwise, None.
        - The first property image URL if found; otherwise, None.
    Returns (None, None, None) if no matching property is found or if an error occurs.
    """
    url = f"https://search-service.idcrealestate.com/api/property/en_US/d4/detail/clr/{mls_number}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://www.theagencyre.com",
        "Connection": "keep-alive",
        #"Sec-Fetch-Dest": "empty",
        #"Sec-Fetch-Mode": "no-cors",
        #"Sec-Fetch-Site": "cross-site",
        "Content-Type": "application/json",
        "X-Tenant": "QUdZfFBST0R8Q09NUEFOWXwx",
        "Priority": "u=4",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "Referer": "https://www.theagencyre.com/"
    }

    logger.debug(f"Processing MLS {mls_number} ({row_index}/{total_rows})")

    try:
        response = requests.get(url, headers=headers, timeout=5)
        #logger.debug(f"Request URL: {url}")
        #logger.debug(f"Response Status Code: {response.status_code}")
        response.raise_for_status()

        time.sleep(5)

        # Parse JSON response
        data = response.json()
        logger.debug(f"Response JSON for MLS {mls_number}: {data}")

        # Extract listing date
        list_date_str = data.get("ListDate", "")
        if list_date_str:
            try:
                list_date = datetime.fromisoformat(list_date_str).date()
            except ValueError as ve:
                logger.error(f"Date parsing error for MLS {mls_number}: {ve}")
                list_date = None
        else:
            list_date = None
        logger.debug(f"Listing Date for MLS {mls_number}: {list_date}")

        # Extract detail URL
        detail_url_path = data.get("DetailUrl", "")
        detail_url = f"https://www.theagencyre.com{detail_url_path}" if detail_url_path else None
        logger.debug(f"Detail URL for MLS {mls_number}: {detail_url}")

        # Extract image source from PhotosXml
        photos = data.get("PhotosXml", {}).get("Urls", {}).get("URL", [])
        # Ensure photos is always a list
        if isinstance(photos, str):
            photos = [photos]
        img_src = photos[0] if photos else None  # Get the first image URL
        if img_src:
            logger.debug(f"Image Source for MLS {mls_number}: {img_src}")
        else:
            logger.debug(f"No images found for MLS {mls_number}.")
        
        logger.info(f"Successfully fetched data for MLS {mls_number}")
        return list_date, detail_url, img_src

    except requests.HTTPError as e:
        logger.error(f"HTTP error occurred while fetching MLS {mls_number}: {e}")
        if e.response is not None:
            logger.debug(f"Response content: {e.response.text}")
    except requests.RequestException as e:
        logger.error(f"Request error occurred while fetching MLS {mls_number}: {e}")
    except ValueError as e:
        logger.error(f"JSON decoding failed for MLS {mls_number}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching MLS {mls_number}: {e}")

    return None, None, None

def update_hoa_fee(df: pd.DataFrame, mls_number: str) -> None:
    """
    Updates the HOA fee value for a given MLS number by scraping the HOA fee from the detailed listing webpage.
    Logs a message only when the HOA fee value changes.
    
    Parameters:
    df (pd.DataFrame): The DataFrame containing the listings.
    mls_number (str): The MLS number of the listing to update the HOA fee for.
    """
    # Define headers to mimic a browser request
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }
    # Base URL for the main listing page
    base_url = 'https://www.bhhscalifornia.com/for-sale/{}-t_q;/'
    main_url = base_url.format(mls_number)  
    try:
        # Fetch the main listing page
        main_response = requests.get(main_url, headers=headers, timeout=5)
        main_response.raise_for_status()
        time.sleep(5)
        main_soup = BeautifulSoup(main_response.text, 'html.parser')     
        # Find the link to the details page
        link_tag = main_soup.find('a', attrs={'class': 'btn cab waves-effect waves-light btn-details show-listing-details'})
        if link_tag:
            # Construct the URL to the details page
            details_url = 'https://www.bhhscalifornia.com' + link_tag['href']
            # Fetch the details page
            details_response = requests.get(details_url, headers=headers)
            details_response.raise_for_status()
            details_soup = BeautifulSoup(details_response.text, 'html.parser')
            # Look for the HOA fee within the details page
            hoa_fee_text = details_soup.find(string=re.compile(r'HOA Fee is \$[\d,]+\.?\d*'))
            if hoa_fee_text:
                # Extract and convert the HOA fee value
                hoa_fee_value = float(re.search(r'\$\s*([\d,]+\.?\d*)', hoa_fee_text).group(1).replace(',', ''))
                # Check if the 'hoa_fee' column exists and if the mls_number is in the DataFrame
                if 'hoa_fee' in df.columns and not df[df['mls_number'] == mls_number].empty:
                    old_hoa_fee = df.loc[df['mls_number'] == mls_number, 'hoa_fee'].iloc[0]
                    # Update the HOA fee in the DataFrame if the value has changed
                    if old_hoa_fee != hoa_fee_value:
                        df.loc[df['mls_number'] == mls_number, 'hoa_fee'] = hoa_fee_value
                        logger.success(f"HOA fee updated from {old_hoa_fee} to {hoa_fee_value} for MLS number {mls_number}.")
                    else:
                        logger.info(f"No update required. HOA fee for MLS number {mls_number} remains {old_hoa_fee}.")
                else:
                    # If the 'hoa_fee' column doesn't exist or the mls_number is not found, log the new value
                    df.loc[df['mls_number'] == mls_number, 'hoa_fee'] = hoa_fee_value
                    logger.success(f"HOA fee set to {hoa_fee_value} for MLS number {mls_number}.")
            else:
                logger.warning(f"HOA fee information not found in the details page for MLS number {mls_number}.")
        else:
            logger.warning(f"Details link not found on the main listing page for MLS number {mls_number}.")
    except requests.HTTPError as e:
        logger.error(f"HTTP error {e} occurred while trying to fetch data for MLS number {mls_number}.")
    except requests.ConnectionError as e:
        logger.error(f"Connection error {e} occurred while trying to fetch data for MLS number {mls_number}.")
    except requests.Timeout:
        logger.error(f"Timeout occurred while trying to fetch data for MLS number {mls_number}.")
    except requests.RequestException as e:
        logger.error(f"Request exception {e} occurred while trying to fetch data for MLS number {mls_number}.")
    except Exception as e:
        logger.error(f"An error occurred while trying to update HOA fee for MLS number {mls_number}: {e}.")

# Iterate over each MLS number in the DataFrame
#for mls_number in df['mls_number'].unique():
#    update_hoa_fee(df, mls_number)