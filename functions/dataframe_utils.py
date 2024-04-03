from functions.webscraping_utils import check_expired_listing
from loguru import logger
import asyncio
import pandas as pd
import sys

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

async def remove_expired_listings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Asynchronously checks each listing URL in the DataFrame to determine if it has expired,
    and removes rows with expired listings.

    Parameters:
    df (pd.DataFrame): The DataFrame containing listing URLs and MLS numbers.

    Returns:
    pd.DataFrame: The DataFrame with expired listings removed.
    """
    # Prepare coroutine list for all rows that need to be checked
    tasks = [
        check_expired_listing(row.listing_url, row.mls_number)
        for row in df[df.listing_url.notnull()].itertuples()
    ]
    
    # Execute all the coroutine tasks concurrently
    results = await asyncio.gather(*tasks)
    
    # Determine indexes of rows to drop (where listing has expired)
    indexes_to_drop = [
        row.Index for row, result in zip(df[df.listing_url.notnull()].itertuples(), results) if result
    ]
    
    # Log success messages for dropped listings
    for index in indexes_to_drop:
        row = df.loc[index]
        logger.success(f"Removed {row.mls_number} ({row.listing_url}) from the dataframe because the listing has expired.")
    
    # Drop the rows from the DataFrame and return the modified DataFrame
    df_dropped_expired = df.drop(indexes_to_drop)
    return df_dropped_expired