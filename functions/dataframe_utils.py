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

def convert_to_int8(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    Convert the specified column in the DataFrame to Int8Dtype, logging errors without changing the original value.

    Args:
        df (pd.DataFrame): The DataFrame containing the column to convert.
        column_name (str): The name of the column to convert.

    Returns:
        pd.DataFrame: The DataFrame with the specified column converted to Int8Dtype.
    """
    try:
        df[column_name] = df[column_name].astype('Int8')
    except Exception as e:
        logger.error(f"Error converting column '{column_name}' to Int8: {e}")
    return df

def convert_to_int16(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    Convert the specified column in the DataFrame to Int16Dtype, logging errors without changing the original value.

    Args:
        df (pd.DataFrame): The DataFrame containing the column to convert.
        column_name (str): The name of the column to convert.

    Returns:
        pd.DataFrame: The DataFrame with the specified column converted to Int16Dtype.
    """
    try:
        df[column_name] = df[column_name].astype('Int16')
    except Exception as e:
        logger.error(f"Error converting column '{column_name}' to Int16: {e}")
    return df

def convert_to_int64(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    Convert the specified column in the DataFrame to Int64Dtype, logging errors without changing the original value.

    Args:
        df (pd.DataFrame): The DataFrame containing the column to convert.
        column_name (str): The name of the column to convert.

    Returns:
        pd.DataFrame: The DataFrame with the specified column converted to Int64Dtype.
    """
    try:
        df[column_name] = df[column_name].astype('Int64')
    except Exception as e:
        logger.error(f"Error converting column '{column_name}' to Int64: {e}")
    return df

def convert_to_float32(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    Convert the specified column in the DataFrame to Float32Dtype, logging errors without changing the original value.

    Args:
        df (pd.DataFrame): The DataFrame containing the column to convert.
        column_name (str): The name of the column to convert.

    Returns:
        pd.DataFrame: The DataFrame with the specified column converted to Float32Dtype.
    """
    try:
        df[column_name] = df[column_name].astype('Float32')
    except Exception as e:
        logger.error(f"Error converting column '{column_name}' to Float32: {e}")
    return df

def convert_to_nullable_string(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    Convert the specified column in the DataFrame to nullable string dtype, logging errors without changing the original value.

    Args:
        df (pd.DataFrame): The DataFrame containing the column to convert.
        column_name (str): The name of the column to convert.

    Returns:
        pd.DataFrame: The DataFrame with the specified column converted to nullable string dtype.
    """
    try:
        df[column_name] = df[column_name].astype(pd.StringDtype())
    except Exception as e:
        logger.error(f"Error converting column '{column_name}' to nullable string: {e}")
    return df

def convert_to_category(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    Convert the specified column in the DataFrame to category dtype, logging errors without changing the original value.

    Args:
        df (pd.DataFrame): The DataFrame containing the column to convert.
        column_name (str): The name of the column to convert.

    Returns:
        pd.DataFrame: The DataFrame with the specified column converted to category dtype.
    """
    try:
        df[column_name] = df[column_name].astype('category')
    except Exception as e:
        logger.error(f"Error converting column '{column_name}' to category: {e}")
    return df

def convert_to_datetime64(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    Convert the specified column in the DataFrame to datetime64[ns] dtype, logging errors without changing the original value.

    Args:
        df (pd.DataFrame): The DataFrame containing the column to convert.
        column_name (str): The name of the column to convert.

    Returns:
        pd.DataFrame: The DataFrame with the specified column converted to datetime64[ns] dtype.
    """
    try:
        df[column_name] = pd.to_datetime(df[column_name], format='mixed', errors='raise')
    except Exception as e:
        logger.error(f"Error converting column '{column_name}' to datetime64[ns]: {e}")
    return df