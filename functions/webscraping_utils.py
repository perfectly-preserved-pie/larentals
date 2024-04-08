from bs4 import BeautifulSoup
from loguru import logger
from typing import Tuple, Optional
import asyncio
import httpx
import pandas as pd
import re
import requests
import sys
import time

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

async def check_expired_listing(url: str, mls_number: str) -> bool:
    """
    Checks if a listing has expired based on the presence of a specific HTML element, asynchronously.
    
    Parameters:
    url (str): The URL of the listing to check.
    mls_number (str): The MLS number of the listing.
    
    Returns:
    bool: True if the listing has expired, False otherwise.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36 Edg/113.0.1774.35"
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            description = soup.find('div', class_='page-description').text
            cleaned_description = " ".join(description.split())
            
            return bool(cleaned_description)
            
    except httpx.TimeoutException:
        logger.warning(f"Timeout occurred while checking if the listing for {mls_number} has expired.")
    except httpx.HTTPStatusError as h:
        if h.response.status_code == 429:
            retry_after = int(h.response.headers.get("Retry-After", 60))  # Use a default retry after 60 seconds if header is missing
            logger.warning(f"Rate limit exceeded, retrying after {retry_after} seconds.")
            await asyncio.sleep(retry_after)
            return await check_expired_listing(url, mls_number)  # Retry the request
        else:
            logger.warning(f"HTTP error {h.response.status_code} occurred while checking if the listing for {mls_number} has expired. {h.response.text}")
    except AttributeError:
        # This occurs if the 'page-description' div is not found, meaning the listing hasn't expired
        return False
    except Exception as e:
        logger.warning(f"Couldn't detect if the listing for {mls_number} has expired because {e}.")

    return False

async def webscrape_bhhs(url: str, row_index: int, mls_number: str, total_rows: int) -> Tuple[Optional[pd.Timestamp], Optional[str], Optional[str]]:
    """
    Asynchronously scrapes a BHHS page to fetch the listing URL, photo, and listed date. 
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36 Edg/113.0.1774.35"
    }

    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            # Check if a redirect has occurred
            #if response.history:
            #    logger.info(f"Redirected from {url} to {response.url} for {mls_number}.")

            # Successful HTTP request
            soup = BeautifulSoup(response.text, 'html.parser')
            listed_date, photo, link = None, None, None

            # Example parsing (ensure to adjust based on actual HTML structure)
            link_tag = soup.find('a', class_='btn cab waves-effect waves-light btn-details show-listing-details')
            if link_tag and 'href' in link_tag.attrs:
                link = f"https://www.bhhscalifornia.com{link_tag['href']}"

            photo_tag = soup.find('a', class_='show-listing-details')
            if photo_tag and photo_tag.find('img'):
                photo = photo_tag.find('img')['src']

            date_tag = soup.find('p', class_='summary-mlsnumber')
            if date_tag:
                listed_date_text = date_tag.text.split()[-1]
                listed_date = pd.Timestamp(listed_date_text)

            return listed_date, photo, link

    except httpx.TimeoutException:
        logger.warning(f"Timeout occurred while scraping BHHS page for {mls_number}.")
    except httpx.HTTPStatusError as h:
        if h.response.status_code == 429:
            retry_after = int(h.response.headers.get("Retry-After", 60))  # Default to 60 seconds
            logger.warning(f"Rate limit exceeded for {mls_number}, retrying after {retry_after} seconds.")
            await asyncio.sleep(retry_after)
            return await webscrape_bhhs(url, row_index, mls_number, total_rows)  # Retry the request
        else:
            logger.warning(f"HTTP error {h.response.status_code} occurred while scraping BHHS page for {mls_number}.")
    except Exception as e:
        logger.warning(f"Error scraping BHHS page for {mls_number}: {e}.")

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
        main_response = requests.get(main_url, headers=headers)
        main_response.raise_for_status()
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