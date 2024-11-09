from aiolimiter import AsyncLimiter
from functions.mls_image_processing_utils import imagekit_transform
from functions.webscraping_utils import check_expired_listing_bhhs, webscrape_bhhs, fetch_the_agency_data
from loguru import logger
import asyncio
import pandas as pd
import re
import requests
import sys

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

async def remove_expired_listings(df: pd.DataFrame, limiter: AsyncLimiter) -> pd.DataFrame:
    """
    Asynchronously checks each listing URL in the DataFrame to determine if it has expired,
    and removes rows with expired listings, applying rate limiting. Also counts the number of expired listings removed.

    Parameters:
    df (pd.DataFrame): The DataFrame containing listing URLs and MLS numbers.
    limiter (AsyncLimiter): The rate limiter to control request frequency.

    Returns:
    pd.DataFrame: The DataFrame with expired listings removed.
    """
    async def check_and_mark_expired(row):
        async with limiter:
            expired = await check_expired_listing(row.listing_url, row.mls_number)
        return (row.Index, expired)
    
    # Gather tasks for all rows that need to be checked
    tasks = [check_and_mark_expired(row) for row in df[df.listing_url.notnull()].itertuples()]
    results = await asyncio.gather(*tasks)
    
    # Determine indexes of rows to drop (where listing has expired)
    indexes_to_drop = [index for index, expired in results if expired]
    
    # Counter for expired listings
    expired_count = len(indexes_to_drop)
    
    # Log success messages for dropped listings and the count of expired listings
    for index in indexes_to_drop:
        mls_number = df.loc[index, 'mls_number']
        logger.success(f"Removed {mls_number} (Index: {index}) from the dataframe because the listing has expired.")
    
    logger.info(f"Total expired listings removed: {expired_count}")
    
    # Drop the rows from the DataFrame and return the modified DataFrame
    df_dropped_expired = df.drop(indexes_to_drop)
    return df_dropped_expired

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
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        is_sold = data.get('IsSold', False)
        if is_sold:
            logger.debug(f"Listing {mls_number} has been sold.")
        return is_sold
    except requests.HTTPError as e:
        logger.error(f"HTTP error occurred while checking if the listing for MLS {mls_number} has been sold: {e}")
    except Exception as e:
        logger.error(f"An error occurred while checking if the listing for MLS {mls_number} has been sold: {e}")

    return False

def remove_inactive_listings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Checks each listing to determine if it has expired or been sold, and removes inactive listings.
    If 'bhhs' is in the 'listing_url', it checks for expired listings.
    If 'idcrealestate' is in the 'listing_url', it checks for sold listings.

    Parameters:
    df (pd.DataFrame): The DataFrame containing listing URLs and MLS numbers.

    Returns:
    pd.DataFrame: The DataFrame with inactive listings removed.
    """
    indexes_to_drop = []

    for row in df.itertuples():
        listing_url = getattr(row, 'listing_url', '')
        mls_number = getattr(row, 'mls_number', '')

        if 'bhhs' in listing_url:
            # Check if the listing has expired
            is_expired = check_expired_listing_bhhs(listing_url, mls_number)
            if is_expired:
                indexes_to_drop.append(row.Index)
                logger.success(f"Removed MLS {mls_number} (Index: {row.Index}) from the DataFrame because the listing has expired.")
        elif 'idcrealestate' in listing_url:
            # Check if the listing has been sold
            is_sold = check_expired_listing_theagency(listing_url, mls_number)
            if is_sold:
                indexes_to_drop.append(row.Index)
                logger.success(f"Removed MLS {mls_number} (Index: {row.Index}) from the DataFrame because the listing has been sold.")

    inactive_count = len(indexes_to_drop)
    logger.info(f"Total inactive listings removed: {inactive_count}")

    df_active = df.drop(indexes_to_drop)
    return df_active.reset_index(drop=True)

def update_dataframe_with_listing_data(
    df: pd.DataFrame, imagekit_instance
) -> pd.DataFrame:
    """
    Updates the DataFrame with listing date, MLS photo, and listing URL by scraping BHHS and using The Agency's API.

    Parameters:
    df (pd.DataFrame): The DataFrame to update.
    imagekit_instance: The ImageKit instance for image transformations.

    Returns:
    pd.DataFrame: The updated DataFrame.
    """
    for row in df.itertuples():
        mls_number = row.mls_number
        try:
            webscrape = asyncio.run(
                webscrape_bhhs(
                    url=f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/",
                    row_index=row.Index,
                    mls_number=mls_number,
                    total_rows=len(df)
                )
            )

            if not all(webscrape):
                logger.warning(f"BHHS did not return complete data for MLS {mls_number}. Trying The Agency.")
                agency_data = fetch_the_agency_data(
                    mls_number,
                    row_index=row.Index,
                    total_rows=len(df),
                    full_street_address=row.full_street_address
                )

                if agency_data and any(agency_data):
                    listed_date, listing_url, mls_photo = agency_data
                    if listed_date:
                        df.at[row.Index, 'listed_date'] = listed_date
                    if listing_url:
                        df.at[row.Index, 'listing_url'] = listing_url
                    if mls_photo:
                        df.at[row.Index, 'mls_photo'] = imagekit_transform(
                            mls_photo,
                            mls_number,
                            imagekit_instance=imagekit_instance
                        )
                    else:
                        logger.warning(f"No photo URL found for MLS {mls_number} from The Agency.")
                else:
                    pass
            else:
                df.at[row.Index, 'listed_date'] = webscrape[0]
                df.at[row.Index, 'mls_photo'] = imagekit_transform(
                    webscrape[1],
                    mls_number,
                    imagekit_instance=imagekit_instance
                )
                df.at[row.Index, 'listing_url'] = webscrape[2]
        except Exception as e:
            logger.error(f"Error processing MLS {mls_number} at index {row.Index}: {e}")
    return df