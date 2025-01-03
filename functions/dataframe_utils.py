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
        # Single Family
        "SFR": "Single Family",
        "SFR/A": "Single Family",
        "SFR/D": "Single Family",
        
        # Condominium
        "CONDO": "Condominium",
        "CONDO/A": "Condominium",
        "CONDO/D": "Condominium",
        
        # Apartment
        "APT": "Apartment",
        "APT/A": "Apartment",
        "APT/D": "Apartment",
        
        # Townhouse
        "TWNHS": "Townhouse",
        "TWNHS/A": "Townhouse",
        "TWNHS/D": "Townhouse",
        
        # Duplex
        "DPLX": "Duplex",
        "DPLX/A": "Duplex",
        "DPLX/D": "Duplex",
        
        # Triplex
        "TPLX": "Triplex",
        "TPLX/A": "Triplex",
        "TPLX/D": "Triplex",
        
        # Quadplex
        "QUAD": "Quadplex",
        "QUAD/A": "Quadplex",
        "QUAD/D": "Quadplex",
        
        # Lofts
        "LOFT": "Loft",
        "LOFT/A": "Loft",
        
        # Studios
        "STUD": "Studio",
        "STUD/A": "Studio",
        "STUD/D": "Studio",
        
        # Room for Rent
        "RMRT/A": "Room For Rent",
        "RMRT/D": "Room For Rent",
        
        # Cabin
        "CABIN": "Cabin",
        "CABIN/A": "Cabin",
        "CABIN/D": "Cabin",
        
        # Commercial Residential
        "COMRES/A": "Commercial Residential",
        "COMRES/D": "Commercial Residential",
        "Combo - Res &amp; Com": "Commercial Residential",
    }

    # Apply the mapping: where a key is found, replace with its value; otherwise leave as is
    df["subtype"] = df["subtype"].map(subtype_map).fillna(df["subtype"])

    return df