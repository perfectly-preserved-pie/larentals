from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from loguru import logger
from typing import Tuple, Optional
import asyncio
import httpx
import pandas as pd
import re
import requests
import sys
import json
import zlib
import brotli
import difflib

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="DEBUG")

# Limit to 1 request per second
limiter = AsyncLimiter(1, 1)

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
        async with limiter:
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

async def fetch_the_agency_data(mls_number: str, row_index: int, total_rows: int) -> Tuple[Optional[datetime], Optional[str], Optional[str]]:
    """
    Asynchronously fetches property data for a given MLS number from The Agency API and scrapes the detail page for the image source.

    Parameters:
    mls_number (str): The MLS number of the property to fetch.
    row_index (int): The row index for logging or debugging purposes.
    total_rows (int): Total rows being processed for progress indication.

    Returns:
    Tuple[Optional[datetime], Optional[str], Optional[str]]: The listing date (as a datetime.date object),
                                                            the detail URL of the property, and the 
                                                            first property image.
                                                            Returns (None, None, None) if no matching
                                                            property is found or if an error occurs.
    """
    url = "https://search-service.idcrealestate.com/api/property"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "X-Tenant": "AGY",
        "X-TenantMode": "Production",
        "X-TenantHost": "theagencyre.com",
        "Content-Type": "application/json",
        "Origin": "https://www.theagencyre.com",
        "Connection": "keep-alive",
        "Referer": "https://www.theagencyre.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Priority": "u=4",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache"
    }
    normalized_mls_number = mls_number.replace("-", "").replace("_", "")
    payload = {
        "urlquery": f"/rent/search-{normalized_mls_number}/rental-true",
        "countrystate": "",
        "zoom": 21
    }
    logger.debug(payload)
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.debug(response.text)

        # Check if the response content is already in JSON format
        try:
            data = response.json()
        except ValueError:
            # Decompress the response content if necessary
            content = response.content
            try:
                if response.headers.get('Content-Encoding') == 'gzip':
                    content = zlib.decompress(content, zlib.MAX_WBITS | 16)
                elif response.headers.get('Content-Encoding') == 'deflate':
                    content = zlib.decompress(content)
                elif response.headers.get('Content-Encoding') == 'br':
                    content = brotli.decompress(content)
                else:
                    content = response.content

                response.encoding = 'utf-8'  # Ensure the response is decoded as UTF-8

                # Attempt to decode the response content manually
                data = json.loads(content)
            except (zlib.error, brotli.error, ValueError) as e:
                logger.error(f"Decompression or JSON parsing error: {e}")
                logger.debug(f"Response content: {response.content}")
                return None, None, None

        # Extract MLS numbers from the response
        mls_numbers = [item.get("mlsNumber", "").replace("-", "").replace("_", "") for item in data.get("items", [])]
        idc_mls_numbers = [item.get("idcMlsNumber", "").replace("-", "").replace("_", "") for item in data.get("items", [])]
        all_mls_numbers = mls_numbers + idc_mls_numbers

        # Find the closest match to the normalized MLS number
        closest_matches = difflib.get_close_matches(normalized_mls_number, all_mls_numbers, n=1, cutoff=0.8)
        if closest_matches:
            best_match = closest_matches[0]
            logger.debug(f"Best match for MLS Number {normalized_mls_number} is {best_match} with a similarity score of {difflib.SequenceMatcher(None, normalized_mls_number, best_match).ratio()}.")

            for item in data.get("items", []):
                item_mls_number = item.get("mlsNumber", "").replace("-", "").replace("_", "")
                item_idc_mls_number = item.get("idcMlsNumber", "").replace("-", "").replace("_", "")
                if item_mls_number == best_match or item_idc_mls_number == best_match:
                    list_date_timestamp = int(item.get("listDate", 0))
                    list_date = datetime.fromtimestamp(list_date_timestamp, tz=timezone.utc).date()
                    detail_url = f"https://www.theagencyre.com{item.get('detailUrl', '')}"
                    detail_response = requests.get(detail_url, headers=headers)
                    detail_response.raise_for_status()
                    detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                    img_tag = detail_soup.find("img", {"src": lambda x: x and "_1" in x})
                    img_src = img_tag["src"] if img_tag else None
                    logger.success(f"Successfully fetched {list_date} {detail_url} {img_src} for MLS {mls_number}")
                    return list_date, detail_url, img_src
        logger.warning(f"No property found on The Agency with normalized MLS Number: {normalized_mls_number}")
        return None, None, None
    except requests.HTTPError as e:
        logger.error(f"HTTP error occurred: {e}")
        logger.debug(f"Response content: {e.response.text}")
    except requests.RequestException as e:
        logger.error(f"Request error occurred: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    return None, None, None

# Example usage in an async context
# import asyncio
# asyncio.run(fetch_property_data("24_454861"))


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