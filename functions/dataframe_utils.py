from functions.mls_image_processing_utils import imagekit_transform, delete_single_mls_image
from functions.webscraping_utils import check_expired_listing_bhhs, check_expired_listing_theagency, webscrape_bhhs, fetch_the_agency_data
from functions.listing_pipeline_checkpoint import (
    CheckpointPersistenceError,
    ListingCheckpointStore,
    SUCCESS_STATUSES,
    TERMINAL_SCRAPE_STATUSES,
    address_fingerprint,
    listing_input_fingerprint,
    photo_fingerprint,
)
from functions.listing_report_utils import normalize_mls_number
from loguru import logger
from typing import Any, Sequence, Dict, Optional, Tuple
import json
import pandas as pd
from functions.data_paths import LARENTALS_DB_PATH
import re
import requests
import sqlite3
import sys

DB = str(LARENTALS_DB_PATH)

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")


def _ensure_object_columns(
    df: pd.DataFrame,
    columns: Sequence[str],
) -> None:
    """
    Prepare columns that will receive several kinds of Python values.

    Pandas 3 rejects assignments that do not match a column's inferred dtype.
    These enrichment columns can contain strings, timestamps, and missing
    values, so they deliberately use the flexible object dtype.
    """
    for column in columns:
        if column in df.columns:
            df[column] = df[column].astype("object")
        else:
            df[column] = pd.Series(index=df.index, dtype="object")


def normalize_reported_inactive_flags(series: pd.Series) -> pd.Series:
    """
    Convert stored inactive-listing flags into nullable pandas booleans.

    SQLite and older pipeline runs may represent the same flag as an integer,
    float, string, or boolean. Missing and unrecognized values are treated as
    false.
    """
    truthy_values = {"1", "1.0", "true", "t", "yes", "y"}

    def is_reported(value: object) -> bool:
        try:
            if bool(pd.isna(value)):
                return False
        except (TypeError, ValueError):
            return False
        return str(value).strip().lower() in truthy_values

    return pd.Series(
        (is_reported(value) for value in series),
        index=series.index,
        dtype="boolean",
    )


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
    df: pd.DataFrame,
    imagekit_instance,
    *,
    listing_type: str = "lease",
    checkpoint_store: ListingCheckpointStore | None = None,
    source_file_hash: str = "ad-hoc",
) -> pd.DataFrame:
    """
    Updates the DataFrame with listing date, MLS photo, and listing URL by scraping BHHS and using The Agency's API.

    Parameters:
    df (pd.DataFrame): The DataFrame to update.
    imagekit_instance: The ImageKit instance for image transformations.

    Returns:
    pd.DataFrame: The updated DataFrame.
    """
    if listing_type not in {"buy", "lease"}:
        raise ValueError(f"Unsupported listing type: {listing_type!r}")

    _ensure_object_columns(
        df,
        (
            "listed_date",
            "listing_url",
            "source_photo_url",
            "mls_photo",
            "listing_input_hash",
            "scrape_status",
            "image_status",
            "image_source_hash",
        ),
    )

    def usable(value: Any) -> bool:
        if value is None or value is pd.NA:
            return False
        try:
            return not bool(pd.isna(value))
        except (TypeError, ValueError):
            return True

    def first_usable(*values: Any) -> Any:
        return next((value for value in values if usable(value)), None)

    for row_index in df.index:
        row = df.loc[row_index]
        mls_number = normalize_mls_number(row["mls_number"])
        input_hash = listing_input_fingerprint(
            row,
            source_file_hash=source_file_hash,
        )
        record = checkpoint_store.get(mls_number) if checkpoint_store else None

        scrape_was_cached = bool(
            record
            and record.get("listing_input_hash") == input_hash
            and record.get("scrape_status") in TERMINAL_SCRAPE_STATUSES
        )

        try:
            if scrape_was_cached:
                listed_date = record.get("listed_date")
                listing_url = record.get("listing_url")
                source_photo_url = record.get("source_photo_url")
                scrape_status = "cached"
                scrape_error = None
            else:
                listing_path = "for-sale" if listing_type == "buy" else "for-lease"
                bhhs_data = webscrape_bhhs(
                    url=f"https://www.bhhscalifornia.com/{listing_path}/{mls_number}-t_q;/",
                    row_index=row_index,
                    mls_number=mls_number,
                    total_rows=len(df),
                )
                agency_data = (None, None, None)
                if not all(usable(value) for value in bhhs_data):
                    agency_data = fetch_the_agency_data(
                        mls_number,
                        row_index=row_index,
                        total_rows=len(df),
                    )

                # BHHS tuple: date, photo, URL. Agency tuple: date, URL, photo.
                listed_date = first_usable(bhhs_data[0], agency_data[0])
                source_photo_url = first_usable(bhhs_data[1], agency_data[2])
                listing_url = first_usable(bhhs_data[2], agency_data[1])
                scrape_status = (
                    "success"
                    if any(
                        usable(value)
                        for value in (listed_date, listing_url, source_photo_url)
                    )
                    else "not_found"
                )
                scrape_error = None

            source_photo_hash = photo_fingerprint(source_photo_url)
            reusable_image = bool(
                source_photo_hash
                and record
                and record.get("image_source_hash") == source_photo_hash
                and record.get("image_status") in SUCCESS_STATUSES
                and usable(record.get("mls_photo"))
            )

            if reusable_image:
                mls_photo = record.get("mls_photo")
                image_status = "cached"
                image_error = None
            elif source_photo_hash:
                mls_photo = imagekit_transform(
                    source_photo_url,
                    mls_number,
                    imagekit_instance=imagekit_instance,
                    folder=f"/listings/{listing_type}",
                )
                image_status = "success" if usable(mls_photo) else "failed"
                image_error = None if usable(mls_photo) else "ImageKit upload failed"
            else:
                mls_photo = None
                image_status = "not_found"
                image_error = None

            df.at[row_index, "listed_date"] = listed_date
            df.at[row_index, "listing_url"] = listing_url
            df.at[row_index, "source_photo_url"] = source_photo_url
            df.at[row_index, "mls_photo"] = mls_photo
            df.at[row_index, "listing_input_hash"] = input_hash
            df.at[row_index, "scrape_status"] = scrape_status
            df.at[row_index, "image_status"] = image_status
            df.at[row_index, "image_source_hash"] = source_photo_hash

            if checkpoint_store and (
                not scrape_was_cached or not reusable_image
            ):
                checkpoint_store.checkpoint(
                    mls_number,
                    listing_input_hash=input_hash,
                    scrape_status=(
                        record.get("scrape_status")
                        if scrape_was_cached and record
                        else scrape_status
                    ),
                    scrape_error=scrape_error,
                    listed_date=listed_date,
                    listing_url=listing_url,
                    source_photo_url=source_photo_url,
                    image_status=(
                        record.get("image_status")
                        if reusable_image and record
                        else image_status
                    ),
                    image_error=image_error,
                    image_source_hash=source_photo_hash,
                    mls_photo=mls_photo,
                )
        except CheckpointPersistenceError:
            raise
        except Exception as error:
            logger.error(
                f"Error processing MLS {mls_number} at index {row_index}: {error}"
            )
            df.at[row_index, "listing_input_hash"] = input_hash
            df.at[row_index, "scrape_status"] = "failed"
            df.at[row_index, "image_status"] = "failed"
            if checkpoint_store:
                checkpoint_store.checkpoint(
                    mls_number,
                    listing_input_hash=input_hash,
                    scrape_status="failed",
                    scrape_error=str(error),
                    image_status="failed",
                    image_error=str(error),
                )
    return df


def merge_listing_dataframes(
    new_df: pd.DataFrame,
    old_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge listing refreshes per column while preserving trusted old enrichment.

    Source columns prefer non-null incoming values. Enrichment values only win
    when their stage succeeded; otherwise legacy values fill the gaps. Changed
    addresses invalidate legacy coordinates, and a changed upstream photo
    invalidates the legacy ImageKit URL when its replacement failed.
    """
    if old_df.empty:
        return new_df.drop_duplicates(subset=["mls_number"], keep="last").copy()
    if new_df.empty:
        return old_df.drop_duplicates(subset=["mls_number"], keep="last").copy()

    new = new_df.copy()
    old = old_df.copy()
    new["_merge_mls"] = new["mls_number"].apply(normalize_mls_number)
    old["_merge_mls"] = old["mls_number"].apply(normalize_mls_number)
    new = new.drop_duplicates("_merge_mls", keep="last").set_index("_merge_mls")
    old = old.drop_duplicates("_merge_mls", keep="last").set_index("_merge_mls")

    enrichment_policies = {
        "scrape_status": ("listed_date", "listing_url", "source_photo_url"),
        "image_status": ("mls_photo",),
        "geocode_status": ("latitude", "longitude"),
    }
    for status_column, protected_columns in enrichment_policies.items():
        if status_column not in new.columns:
            continue
        failed_or_incomplete = (
            new[status_column].notna()
            & ~new[status_column].isin(SUCCESS_STATUSES)
        )
        for column in protected_columns:
            if column in new.columns:
                new.loc[failed_or_incomplete, column] = pd.NA

    combined = new.combine_first(old)
    overlap = new.index.intersection(old.index)

    if len(overlap) > 0 and "geocode_status" in new.columns:
        new_derived_address_hash = new.get(
            "full_street_address",
            pd.Series(index=new.index, dtype="str"),
        ).apply(address_fingerprint)
        new_address_hash = (
            new["geocode_address_hash"].combine_first(new_derived_address_hash)
            if "geocode_address_hash" in new.columns
            else new_derived_address_hash
        )
        old_derived_address_hash = old.get(
            "full_street_address",
            pd.Series(index=old.index, dtype="str"),
        ).apply(address_fingerprint)
        old_address_hash = (
            old["geocode_address_hash"].combine_first(old_derived_address_hash)
            if "geocode_address_hash" in old.columns
            else old_derived_address_hash
        )
        address_changed = (
            new_address_hash.loc[overlap].notna()
            & old_address_hash.loc[overlap].notna()
            & (new_address_hash.loc[overlap] != old_address_hash.loc[overlap])
        )
        geocode_succeeded = new.loc[overlap, "geocode_status"].isin(
            SUCCESS_STATUSES
        )
        old_latitude = pd.to_numeric(
            old.get(
                "latitude",
                pd.Series(index=old.index, dtype="float64"),
            ).loc[overlap],
            errors="coerce",
        )
        old_longitude = pd.to_numeric(
            old.get(
                "longitude",
                pd.Series(index=old.index, dtype="float64"),
            ).loc[overlap],
            errors="coerce",
        )
        old_coordinates_usable = (
            old_latitude.between(-90, 35.393528, inclusive="both")
            & old_longitude.between(-180, 180, inclusive="both")
        )
        invalidate_coordinates = (
            address_changed | ~old_coordinates_usable
        ) & ~geocode_succeeded
        invalid_coordinate_indexes = invalidate_coordinates[
            invalidate_coordinates
        ].index
        for column in ("latitude", "longitude"):
            if column in combined.columns:
                combined.loc[invalid_coordinate_indexes, column] = pd.NA

    if (
        len(overlap) > 0
        and "image_status" in new.columns
        and "image_source_hash" in new.columns
        and "image_source_hash" in old.columns
    ):
        new_photo_hash = new.loc[overlap, "image_source_hash"]
        old_photo_hash = old.loc[overlap, "image_source_hash"]
        photo_changed = (
            new_photo_hash.notna()
            & old_photo_hash.notna()
            & (new_photo_hash != old_photo_hash)
        )
        image_succeeded = new.loc[overlap, "image_status"].isin(SUCCESS_STATUSES)
        invalidate_image = photo_changed & ~image_succeeded
        invalid_image_indexes = invalidate_image[invalidate_image].index
        if "mls_photo" in combined.columns:
            combined.loc[invalid_image_indexes, "mls_photo"] = pd.NA

    return combined.reset_index(drop=True)


def reconstruct_missing_address_components(df: pd.DataFrame) -> pd.DataFrame:
    """
    Restore address components from ``full_street_address`` when possible.

    Merging current listings with SQLite data can leave ZIP and street-number
    columns with a numeric dtype. Cast the destination columns to object before
    assigning extracted text so pandas does not reject valid string values.
    """
    result = df.copy()
    required_columns = ("street_address", "city", "zip_code", "street_number")
    for column in required_columns:
        if column not in result.columns:
            result[column] = pd.NA

    missing_street = (
        result["street_address"].isna()
        & result["full_street_address"].notna()
    )
    if not missing_street.any():
        return result

    reconstructed = result.loc[
        missing_street, "full_street_address"
    ].astype("string").str.extract(
        r"^(?P<street_address>.*?), (?P<city>.*?) (?P<zip_code>\d{5})$"
    )
    reconstructed["street_number"] = reconstructed[
        "street_address"
    ].str.extract(r"^(?P<street_number>\d+)")

    for column in required_columns:
        valid_indexes = reconstructed.index[reconstructed[column].notna()]
        if valid_indexes.empty:
            continue
        result[column] = result[column].astype("object")
        result.loc[valid_indexes, column] = reconstructed.loc[
            valid_indexes, column
        ].astype("object")

    return result


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
    cols: Sequence[str] = ("sqft", "total_bathrooms", "bedrooms", "parking_spaces"),
    iqr_multiplier: float = 1.5,
    absolute_caps: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """
    Remove rows from a DataFrame where values in specified numeric columns exceed an
    upper outlier bound and optionally exceed domain-specific hard caps.

    Outlier rule (per column):
        - Coerce the column to numeric (best-effort).
        - Compute Q1, Q3, and IQR on non-null numeric values.
        - Upper cutoff = Q3 + iqr_multiplier * IQR.
        - Drop rows where the value is NOT null AND value > cutoff.

    Absolute cap rule (per column):
        - Coerce the column to numeric (best-effort).
        - Drop rows where the value is NOT null AND value > cap.

    Important:
        - NULL/NaN values are preserved (never dropped solely due to being null).

    Args:
        df: Input DataFrame.
        cols: Column names to apply IQR-based high-outlier removal to.
        iqr_multiplier: Multiplier applied to IQR when computing the upper cutoff.
        absolute_caps: Optional mapping of column -> maximum allowed value.

    Returns:
        A filtered DataFrame with high outliers removed, index reset.
    """
    df_clean = df.copy()

    def _coerce_numeric_inplace(frame: pd.DataFrame, col: str) -> None:
        """
        Best-effort numeric coercion for columns that often arrive as strings:
        strips $, commas, and whitespace; maps common placeholders to NA.
        """
        s = frame[col]

        # If it's already numeric (includes pandas nullable Int64/Float64), do nothing.
        if pd.api.types.is_numeric_dtype(s):
            return

        s2 = s.astype("string").str.strip()
        s2 = s2.replace(
            {"": pd.NA, "Unknown": pd.NA, "None": pd.NA, "N/A": pd.NA, "nan": pd.NA, "NaN": pd.NA}
        )
        s2 = s2.str.replace(r"[\$,]", "", regex=True)

        frame[col] = pd.to_numeric(s2, errors="coerce")

    def _apply_upper_bound_keep_nulls(frame: pd.DataFrame, col: str, upper: float) -> Tuple[pd.DataFrame, int]:
        """
        Keep rows where col is null OR col <= upper. Drops only non-null values above upper.

        Returns:
            (filtered_frame, dropped_count)
        """
        before = len(frame)
        mask = frame[col].isna() | (frame[col] <= upper)
        out = frame[mask]
        return out, before - len(out)

    # 1) Compute IQR thresholds once on original (after coercion)
    thresholds: Dict[str, float] = {}
    stats: Dict[str, Dict[str, float]] = {}

    for col in cols:
        if col not in df_clean.columns:
            logger.warning(f"Column '{col}' not found; skipping IQR removal.")
            continue

        _coerce_numeric_inplace(df_clean, col)

        if not pd.api.types.is_numeric_dtype(df_clean[col]):
            logger.warning(f"Column '{col}' is not numeric after coercion; skipping.")
            continue

        numeric_non_null = df_clean[col].dropna()
        if numeric_non_null.empty:
            logger.warning(f"Column '{col}' has no numeric values after coercion; skipping.")
            continue

        q1 = float(numeric_non_null.quantile(0.25))
        q3 = float(numeric_non_null.quantile(0.75))
        iqr = q3 - q1

        if iqr == 0:
            logger.warning(f"IQR for '{col}' is zero; skipping.")
            continue

        cutoff = q3 + iqr_multiplier * iqr
        thresholds[col] = cutoff
        stats[col] = {"q1": q1, "q3": q3, "iqr": iqr, "cutoff": cutoff}

    # 2) Drop using IQR thresholds (KEEP NULLS)
    total_dropped = 0
    for col, cutoff in thresholds.items():
        df_clean, dropped = _apply_upper_bound_keep_nulls(df_clean, col, cutoff)
        total_dropped += dropped

        st = stats.get(col, {})
        if st:
            logger.info(
                f"Dropped {dropped} rows where '{col}' > {cutoff:.2f} "
                f"(Q1={st['q1']:.2f}, Q3={st['q3']:.2f}, IQR={st['iqr']:.2f}, k={iqr_multiplier})."
            )
        else:
            logger.info(f"Dropped {dropped} rows where '{col}' > {cutoff:.2f}.")

    # 3) Drop using absolute caps if provided (KEEP NULLS)
    if absolute_caps:
        for col, cap in absolute_caps.items():
            if col not in df_clean.columns:
                continue

            _coerce_numeric_inplace(df_clean, col)

            if pd.api.types.is_numeric_dtype(df_clean[col]):
                df_clean, dropped = _apply_upper_bound_keep_nulls(df_clean, col, cap)
                total_dropped += dropped
                logger.info(f"Dropped {dropped} rows where '{col}' > absolute cap {cap}.")

    logger.info(f"Total rows dropped: {total_dropped}")
    return df_clean.reset_index(drop=True)

def remove_trailing_zero(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove trailing '.0' from all columns except hoa_fee and space_rent in the given DataFrame. Convert to string if necessary.
    """
    for col in df.columns:
        if col not in ['hoa_fee', 'space_rent']:
            if pd.api.types.is_object_dtype(df[col].dtype):
                df[col] = df[col].apply(
                    lambda x: re.sub(r"\.0$", "", x) if isinstance(x, str) else x
                )
            elif pd.api.types.is_string_dtype(df[col].dtype):
                df[col] = df[col].str.replace(r"\.0$", "", regex=True)
            elif pd.api.types.is_numeric_dtype(df[col]):
                df[col] = (
                    df[col]
                    .astype("string")
                    .str.replace(r"\.0$", "", regex=True)
                )
    return df
