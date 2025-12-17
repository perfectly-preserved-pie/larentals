from functions.mls_image_processing_utils import imagekit_transform, delete_single_mls_image
from functions.webscraping_utils import check_expired_listing_bhhs, check_expired_listing_theagency, webscrape_bhhs, fetch_the_agency_data
from loguru import logger
from typing import Sequence, Dict, Optional
import json
import pandas as pd
import re
import requests
import sqlite3
import sys

DB = "assets/datasets/larentals.db"

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

def remove_inactive_listings(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    """
    Removes listings that have expired or been sold both in memory and in the SQLite table.
    """
    to_delete = []

    for row in df.itertuples():
        raw = getattr(row, 'listing_url', '')
        # guard against NaN, floats, etc.
        if pd.isna(raw) or not isinstance(raw, str):
            url = ""
        else:
            url = raw
        mls = getattr(row, 'mls_number', '')

        if 'bhhscalifornia.com' in url and check_expired_listing_bhhs(url, mls):
            to_delete.append(mls)
            delete_single_mls_image(mls)
        elif 'theagencyre.com' in url and check_expired_listing_theagency(url, mls):
            to_delete.append(mls)
            delete_single_mls_image(mls)

    if to_delete:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        for mls_number in to_delete:
            cur.execute(
                f"DELETE FROM {table_name} WHERE mls_number = ?",
                (mls_number,)
            )
        conn.commit()
        conn.close()

    df_clean = df[~df['mls_number'].isin(to_delete)].reset_index(drop=True)
    logger.info(f"Removed {len(to_delete)} inactive listings")
    return df_clean

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
    Loads a GeoJSON file as JSON, checks if the 'mls_photo' URL for each feature is valid,
    regenerates data for features with invalid photos using update_dataframe_with_listing_data,
    and writes out the updated GeoJSON.
    """
    try:
        with open(input_geojson_path, 'r') as f:
            geojson = json.load(f)
    except Exception as e:
        logger.error(f"Error loading GeoJSON from {input_geojson_path}: {e}")
        return

    features = geojson.get('features', [])
    if not features:
        logger.warning(f"No features found in {input_geojson_path}")
    # build a DataFrame of properties so we can call the existing update logic
    props_df = pd.json_normalize([feat.get('properties', {}) for feat in features])
    # retain the original indices so we can map back
    props_df.index = range(len(features))

    for idx, row in props_df.iterrows():
        photo_url = row.get('mls_photo')
        if not photo_url or pd.isna(photo_url):
            continue
        try:
            resp = requests.head(photo_url, timeout=5)
            if resp.status_code != 200:
                logger.info(f"Photo invalid for feature {idx}, regenerating.")
                single = row.to_frame().T.copy()
                updated = update_dataframe_with_listing_data(single, imagekit_instance)
                props_df.loc[idx, updated.columns] = updated.iloc[0].to_dict()
        except requests.RequestException:
            logger.info(f"Request error on photo for feature {idx}, regenerating.")
            single = row.to_frame().T.copy()
            updated = update_dataframe_with_listing_data(single, imagekit_instance)
            props_df.loc[idx, updated.columns] = updated.iloc[0].to_dict()

    # write properties back into geojson structure
    for i, feat in enumerate(features):
        feat['properties'] = props_df.iloc[i].to_dict()

    try:
        with open(output_geojson_path, 'w') as f:
            json.dump(geojson, f)
        logger.info(f"Saved the updated GeoJSON to {output_geojson_path}.")
    except Exception as e:
        logger.error(f"Error saving updated GeoJSON to {output_geojson_path}: {e}")

def reduce_geojson_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drops specified columns from a DataFrame.

    The following columns will be dropped if they exist in the DataFrame:
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
        df (pd.DataFrame): The input DataFrame.

    Returns:
        pd.DataFrame: A new DataFrame with the specified columns removed.
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
    existing_cols = [col for col in cols_to_drop if col in df.columns]
    reduced_gdf = df.drop(columns=existing_cols)
    return reduced_gdf

def drop_high_outliers(
    df: pd.DataFrame,
    cols: Optional[Sequence[str]] = None,
    iqr_multiplier: float = 1.5,
    absolute_caps: Optional[Dict[str, float]] = None
) -> pd.DataFrame:
    """
     Remove rows from a DataFrame where values in numeric or numeric-looking columns
     exceed the upper bound defined by Q3 + iqr_multiplier * IQR, and optionally
     also any domain-specific hard caps. Logs each dropped row with the reason.
     """
    df_clean = df.copy()

    def _numeric_series(series: pd.Series) -> pd.Series:
        return pd.to_numeric(series, errors="coerce")

    # 1) Decide which columns to inspect
    candidate_cols = cols if cols is not None else df_clean.columns
    thresholds: Dict[str, Dict[str, float]] = {}
    for col in candidate_cols:
        if col not in df_clean.columns:
            logger.warning(f"Column '{col}' not found; skipping IQR removal.")
            continue

        num_series = _numeric_series(df_clean[col])
        if num_series.notna().sum() == 0:
            logger.warning(f"Column '{col}' has no numeric values; skipping.")
            continue

        q1 = num_series.quantile(0.25)
        q3 = num_series.quantile(0.75)
        iqr = q3 - q1

        if pd.isna(iqr) or iqr == 0:
            logger.warning(f"IQR for '{col}' is zero; skipping.")
            continue

        thresholds[col] = {"cutoff": q3 + iqr_multiplier * iqr, "q1": q1, "q3": q3, "iqr": iqr}

    # 2) Drop using IQR thresholds
    total_dropped = 0
    for col, info in thresholds.items():
        num_series = _numeric_series(df_clean[col])
        cutoff = info["cutoff"]
        mask = num_series > cutoff
        if mask.any():
            dropped_rows = df_clean.loc[mask]
            for idx in dropped_rows.index:
                identifier = (
                    dropped_rows.loc[idx, "mls_number"]
                    if "mls_number" in dropped_rows.columns
                    else idx
                )
                logger.info(
                    f"Dropping row '{identifier}' because '{col}'={num_series.loc[idx]} exceeds IQR threshold {cutoff:.2f} "
                    f"(Q1={info['q1']:.2f}, Q3={info['q3']:.2f}, IQR={info['iqr']:.2f})."
                )
            total_dropped += mask.sum()
            df_clean = df_clean.loc[~mask]

    # 3) Drop using absolute caps if provided
    if absolute_caps:
        for col, cap in absolute_caps.items():
            if col in df_clean.columns:
                num_series = _numeric_series(df_clean[col])
                mask = num_series > cap
                if mask.any():
                    dropped_rows = df_clean.loc[mask]
                    for idx in dropped_rows.index:
                        identifier = (
                            dropped_rows.loc[idx, "mls_number"]
                            if "mls_number" in dropped_rows.columns
                            else idx
                        )
                        logger.info(
                            f"Dropping row '{identifier}' because '{col}'={num_series.loc[idx]} exceeds absolute cap {cap}."
                        )
                    total_dropped += mask.sum()
                    df_clean = df_clean.loc[~mask]

    logger.info(f"Total rows dropped: {total_dropped}")
    return df_clean.reset_index(drop=True)

def remove_trailing_zero(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove trailing '.0' from all columns except hoa_fee and space_rent in the given DataFrame. Convert to string if necessary.
    """
    for col in df.columns:
        if col not in ['hoa_fee', 'space_rent']:
            if df[col].dtype == object:
                df[col] = df[col].apply(
                    lambda x: re.sub(r"\.0$", "", x) if isinstance(x, str) else x
                )
            elif pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].astype(str).str.replace(r"\.0$", "", regex=True)
    return df
