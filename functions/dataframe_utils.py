from aiolimiter import AsyncLimiter
from functions.webscraping_utils import check_expired_listing
from loguru import logger
import asyncio
import pandas as pd
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