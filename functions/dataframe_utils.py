from functions.mls_image_processing_utils import imagekit_transform
from functions.webscraping_utils import check_expired_listing_bhhs, check_expired_listing_theagency, webscrape_bhhs, fetch_the_agency_data
from loguru import logger
import asyncio
import pandas as pd
import sys

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

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
        listing_url = str(getattr(row, 'listing_url', ''))
        mls_number = str(getattr(row, 'mls_number', ''))

        if 'bhhscalifornia.com' in listing_url:
            # Check if the listing has expired
            is_expired = check_expired_listing_bhhs(listing_url, mls_number)
            if is_expired:
                indexes_to_drop.append(row.Index)
                logger.success(f"Removed MLS {mls_number} (Index: {row.Index}) from the DataFrame because the listing has expired on BHHS.")
        elif 'theagencyre.com' in listing_url:
            # Check if the listing has been sold
            is_sold = check_expired_listing_theagency(listing_url, mls_number)
            if is_sold:
                indexes_to_drop.append(row.Index)
                logger.success(f"Removed MLS {mls_number} (Index: {row.Index}) from the DataFrame because the listing has expired on The Agency.")

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