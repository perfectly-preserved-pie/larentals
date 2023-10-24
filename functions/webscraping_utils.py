from bs4 import BeautifulSoup
from loguru import logger
from typing import Tuple, Optional
import pandas as pd
import requests
import sys
import time

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

def check_expired_listing(url: str, mls_number: str) -> bool:
    """
    Checks if a listing has expired based on the presence of a specific HTML element.
    
    Parameters:
    url (str): The URL of the listing to check.
    mls_number (str): The MLS number of the listing.
    
    Returns:
    bool: True if the listing has expired, False otherwise.
    """
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # Raise HTTPError for bad responses
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try to find the 'page-description' div and clean its text
        description = soup.find('div', class_='page-description').text
        cleaned_description = " ".join(description.split())
        
        return bool(cleaned_description)
        
    except requests.Timeout:
        logger.warning(f"Timeout occurred while checking if the listing for {mls_number} has expired.")
    except requests.HTTPError as h:
        logger.warning(f"HTTP error {h} occurred while checking if the listing for {mls_number} has expired.")
    except AttributeError:
        # This occurs if the 'page-description' div is not found, meaning the listing hasn't expired
        return False
    except Exception as e:
        logger.warning(f"Couldn't detect if the listing for {mls_number} has expired because {e}.")
    
    return False

def webscrape_bhhs(url: str, row_index: int, mls_number: str, total_rows: int) -> Tuple[Optional[pd.Timestamp], Optional[str], Optional[str]]:
    """
    Scrapes a BHHS page to fetch the listing URL, photo, and listed date.
    
    Parameters:
    url (str): The URL of the BHHS listing.
    row_index (int): The row index of the listing in the DataFrame.
    mls_number (str): The MLS number of the listing.
    total_rows (int): Total number of rows in the DataFrame for logging.
    
    Returns:
    Tuple[Optional[pd.Timestamp], Optional[str], Optional[str]]: A tuple containing the listed date, photo URL, and listing link.
    """
    # Initialize variables
    listed_date, photo, link = None, None, None
    
    try:
        start_time = time.time()
        response = requests.get(url, timeout=5)
        elapsed_time = time.time() - start_time
        logger.debug(f"HTTP request for {mls_number} took {elapsed_time:.2f} seconds.")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Fetch listing URL
        link_tag = soup.find('a', attrs={'class': 'btn cab waves-effect waves-light btn-details show-listing-details'})
        if link_tag:
            link = 'https://www.bhhscalifornia.com' + link_tag['href']
            logger.success(f"Fetched listing URL for {mls_number} (row {row_index + 1} out of {total_rows}).")
        
        # Fetch MLS photo URL
        photo_tag = soup.find('a', attrs={'class': 'show-listing-details'})
        if photo_tag and photo_tag.contents[1].has_attr('src'):
            photo = photo_tag.contents[1]['src']
            logger.success(f"Fetched MLS photo {photo} for {mls_number} (row {row_index + 1} out of {total_rows}).")
        
        # Fetch list date
        date_tag = soup.find('p', attrs={'class': 'summary-mlsnumber'})
        if date_tag:
            listed_date = pd.Timestamp(date_tag.text.split()[-1])
            logger.success(f"Fetched listed date {listed_date} for {mls_number} (row {row_index + 1} out of {total_rows}).")
            
    except requests.Timeout:
        logger.warning(f"Timeout occurred while scraping BHHS page for {mls_number} (row {row_index + 1} out of {total_rows}).")
    except requests.HTTPError:
        logger.warning(f"HTTP error occurred while scraping BHHS page for {mls_number} (row {row_index + 1} out of {total_rows}).")
    except Exception as e:
        logger.warning(f"Couldn't scrape BHHS page for {mls_number} (row {row_index + 1} out of {total_rows}) because of {e}.")
    
    return listed_date, photo, link