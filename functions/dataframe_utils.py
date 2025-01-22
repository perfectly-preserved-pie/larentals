from functions.mls_image_processing_utils import imagekit_transform
from functions.webscraping_utils import check_expired_listing_bhhs, check_expired_listing_theagency, webscrape_bhhs, fetch_the_agency_data
from loguru import logger
import pandas as pd
import requests
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

        # Check if the listing is expired on BHHS
        if 'bhhscalifornia.com' in listing_url:
            is_expired = check_expired_listing_bhhs(listing_url, mls_number)
            if is_expired:
                indexes_to_drop.append(row.Index)
                logger.success(f"Removed MLS {mls_number} (Index: {row.Index}) from the DataFrame because the listing has expired on BHHS.")
        # Check if the listing is expired on The Agency
        elif 'theagencyre.com' in listing_url:
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
            webscrape = webscrape_bhhs(
                url=f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/",
                row_index=row.Index,
                mls_number=mls_number,
                total_rows=len(df)
            )
        
            if not all(webscrape):
                logger.warning(f"BHHS did not return complete data for MLS {mls_number}. Trying The Agency.")
                agency_data = fetch_the_agency_data(
                    mls_number,
                    row_index=row.Index,
                    total_rows=len(df),
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

def categorize_laundry_features(feature) -> str:
    # If it's NaN, treat as unknown
    if pd.isna(feature):
        return 'Unknown'

    # Convert to string, lowercase, and strip whitespace
    feature_str = str(feature).lower().strip()

    # If it's empty or literally 'unknown', just call it 'Unknown'
    if feature_str in ['', 'unknown']:
        return 'Unknown'

    # Split on commas
    tokens = [token.strip() for token in feature_str.split(',')]

    has_any = lambda keywords: any(any_kw in t for t in tokens for any_kw in keywords)

    if has_any(['in closet', 'in kitchen', 'in garage', 'inside', 'individual room']):
        return 'In Unit'
    elif has_any(['community laundry', 'common area', 'shared']):
        return 'Shared'
    elif has_any(['hookup', 'electric dryer hookup', 'gas dryer hookup', 'washer hookup']):
        return 'Hookups'
    elif has_any(['dryer included', 'dryer', 'washer included', 'washer']):
        return 'Included Appliances'
    elif has_any(['outside', 'upper level', 'in carport']):
        return 'Location Specific'
    elif feature_str == 'none':
        return 'None'
    else:
        return 'Other'
    
def flatten_subtype_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flatten the 'subtype' column in-place by mapping attached/detached abbreviations
    (e.g. 'SFR/A', 'SFR/D', 'CONDO/A', etc.) to a simplified label 
    (e.g. 'Single Family', 'Condominium', etc.).
    
    :param df: A pandas DataFrame with a column named 'subtype'.
    :return: The same DataFrame (df) with its 'subtype' column flattened.
    """

    # Create a mapping from various raw subtype strings → flattened label
    subtype_map = {
        "APT": "Apartment",
        "APT/A": "Apartment",
        "APT/D": "Apartment",
        "Co-Ownership": "Co-Ownership",
        "CONDO": "Condominium",
        "CONDO/A": "Condominium",
        "CONDO/D": "Condominium",
        "Condominium": "Condominium",
        "DPLX": "Duplex",
        "DPLX/A": "Duplex",
        "DPLX/D": "Duplex",
        "MH": "Manufactured Home",
        "Own Your Own": "Own Your Own",
        "OwnYourOwn": "Own Your Own",
        "OYO": "Own Your Own",
        "OYO/A": "Own Your Own",
        "OYO/D": "Own Your Own",
        "QUAD": "Quadruplex",
        "QUAD/A": "Quadruplex",
        "QUAD/D": "Quadruplex",
        "SFR": "Single Family Residence",
        "SFR/A": "Single Family Residence",
        "SFR/D": "Single Family Residence",
        "Single Family Residence": "Single Family Residence",
        "Stock Cooperative": "Stock Cooperative",
        "TPLX": "Triplex",
        "TPLX/A": "Triplex",
        "TPLX/D": "Triplex",
        "TWNHS": "Townhouse",
        "TWNHS/A": "Townhouse",
        "TWNHS/D": "Townhouse",
    }

    # Apply the subtype_map only to known subtypes
    df['subtype'] = df['subtype'].apply(lambda x: subtype_map.get(x, x) if pd.notnull(x) and x != '' else 'Unknown')

    return df

def refresh_invalid_mls_photos(df: pd.DataFrame, imagekit_instance) -> pd.DataFrame:
    """
    Checks if each mls_photo URL returns HTTP 200. 
    If not, regenerates data for that row using update_dataframe_with_listing_data.
    """
    for row in df.itertuples():
        photo_url = getattr(row, 'mls_photo', None)
        if photo_url and pd.notnull(photo_url):
            try:
                response = requests.head(photo_url, timeout=5)
                if response.status_code != 200:
                    single_row_df = df.loc[[row.Index]].copy()
                    single_row_df = update_dataframe_with_listing_data(single_row_df, imagekit_instance)
                    df.loc[[row.Index]] = single_row_df
            except requests.RequestException:
                # If the photo fails to load, we try to update it
                single_row_df = df.loc[[row.Index]].copy()
                single_row_df = update_dataframe_with_listing_data(single_row_df, imagekit_instance)
                df.loc[[row.Index]] = single_row_df
    return df