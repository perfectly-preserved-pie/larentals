from functions.mls_image_processing_utils import imagekit_transform, delete_single_mls_image
from functions.webscraping_utils import check_expired_listing_bhhs, check_expired_listing_theagency, webscrape_bhhs, fetch_the_agency_data
from loguru import logger
import geopandas as gpd
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
                delete_single_mls_image(mls_number)
        # Check if the listing is expired on The Agency
        elif 'theagencyre.com' in listing_url:
            is_sold = check_expired_listing_theagency(listing_url, mls_number)
            if is_sold:
                indexes_to_drop.append(row.Index)
                logger.success(f"Removed MLS {mls_number} (Index: {row.Index}) from the DataFrame because the listing has expired on The Agency.")
                delete_single_mls_image(mls_number)

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
                #logger.warning(f"BHHS did not return complete data for MLS {mls_number}. Trying The Agency.")
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
                    #else:
                        #logger.warning(f"No photo URL found for MLS {mls_number} from The Agency.")
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
        "Apartment": "Apartment",
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
        "Loft": "Loft",
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
        "Townhouse": "Townhouse",
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

def refresh_invalid_mls_photos(
    input_geojson_path: str, 
    output_geojson_path: str, 
    imagekit_instance
) -> None:
    """
    Loads a GeoJSON file as a GeoDataFrame, checks if the 'mls_photo' URL for each row is valid,
    regenerates data for rows with invalid photos using update_dataframe_with_listing_data, 
    and saves the updated GeoDataFrame as a GeoJSON.
    
    Args:
        input_geojson_path (str): Path to the input GeoJSON file.
        output_geojson_path (str): Path for saving the updated GeoJSON file.
        imagekit_instance: An instance of ImageKit for processing images.
    """
    try:
        gdf = gpd.read_file(input_geojson_path)
    except Exception as e:
        logger.error(f"Error loading GeoJSON from {input_geojson_path}: {e}")
        return

    for row in gdf.itertuples():
        photo_url = getattr(row, "mls_photo", None)
        if photo_url and pd.notnull(photo_url):
            try:
                response = requests.head(photo_url, timeout=5)
                if response.status_code != 200:
                    logger.info(f"Photo {photo_url} for MLS {row.mls_number} is invalid. Regenerating data.")
                    single_row_df = gdf.loc[[row.Index]].copy()
                    single_row_df = update_dataframe_with_listing_data(single_row_df, imagekit_instance)
                    gdf.loc[[row.Index]] = single_row_df
            except requests.RequestException:
                logger.info(f"Request error for photo {photo_url} for MLS {row.mls_number}. Regenerating data.")
                single_row_df = gdf.loc[[row.Index]].copy()
                single_row_df = update_dataframe_with_listing_data(single_row_df, imagekit_instance)
                gdf.loc[[row.Index]] = single_row_df

    try:
        gdf.to_file(output_geojson_path, driver="GeoJSON")
        logger.info(f"Saved the updated GeoDataFrame to {output_geojson_path}.")
    except Exception as e:
        logger.error(f"Error saving the updated GeoDataFrame to {output_geojson_path}: {e}")

def reduce_geojson_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Drops specified columns from a GeoDataFrame.

    The following columns will be dropped if they exist in the GeoDataFrame:
      - latitude
      - longitude
      - la county homes 1-13-25
      - street_name
      - Full Bathrooms
      - Half Bathrooms
      - Three Quarter Bathrooms
      - short_address
      - zip_code
      - city
      - street_number
      - street_address

    Args:
        gdf (gpd.GeoDataFrame): The input GeoDataFrame.

    Returns:
        gpd.GeoDataFrame: A new GeoDataFrame with the specified columns removed.
    """
    cols_to_drop = [
        'latitude',
        'longitude',
        'la county homes 1-13-25',
        'street_name',
        'Full Bathrooms',
        'Half Bathrooms',
        'Three Quarter Bathrooms',
        'short_address',
        'zip_code',
        'city',
        'street_number',
        'street_address'
    ]
    # Drop only the columns that exist in the GeoDataFrame
    existing_cols = [col for col in cols_to_drop if col in gdf.columns]
    reduced_gdf = gdf.drop(columns=existing_cols)
    return reduced_gdf