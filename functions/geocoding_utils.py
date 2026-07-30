from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from geopy.geocoders import GoogleV3, Nominatim
from functions.listing_pipeline_checkpoint import (
    ListingCheckpointStore,
    SUCCESS_STATUSES,
    address_fingerprint,
    stable_fingerprint,
)
from functions.listing_report_utils import normalize_mls_number
from loguru import logger
from typing import Tuple, Optional
import pandas as pd
import sys

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

def return_coordinates(
    address: str,
    row_index: int,
    geolocator: GoogleV3,
    total_rows: int,
    use_nominatim: bool = False,
    nominatim_user_agent: str = "larentals-geocoder",
    nominatim_timeout: int = 10
) -> Tuple[Optional[float], Optional[float]]:
    """
    Fetches the latitude and longitude of a given address using geocoding. Uses Nominatim if flagged, otherwise defaults to GoogleV3.
    
    Parameters:
    address (str): The full street address.
    row_index (int): The row index for logging.
    geolocator (GoogleV3): An instance of a geocoding class.
    total_rows (int): Total number of rows for logging.
    
    Returns:
    Tuple[Optional[float], Optional[float]]: Latitude and Longitude as a tuple, or (None, None) if unsuccessful.
    """
    if use_nominatim:
        try:
            nomi = Nominatim(user_agent=nominatim_user_agent)
            location = nomi.geocode(
                {
                    "street": address,
                    "county": "Los Angeles",
                    "state": "California",
                    "country": "USA"
                },
                bounded=True,  # enforce the restraints above
                timeout=nominatim_timeout
            )
            if location:
                return location.latitude, location.longitude
            logger.error(f"[{row_index}/{total_rows}] Nominatim: no result for '{address}'")
        except (GeocoderTimedOut, GeocoderServiceError, Exception) as e:
            logger.error(f"[{row_index}/{total_rows}] Nominatim error: {e}")
        return None, None

    # default: GoogleV3
    try:
        loc = geolocator.geocode(address, timeout=10, components={'administrative_area': 'CA', 'country': 'US'})
        if loc:
            return loc.latitude, loc.longitude
        logger.warning(f"[{row_index}/{total_rows}] GoogleV3: no result for '{address}'")
    except (GeocoderTimedOut, GeocoderServiceError, Exception) as e:
        logger.warning(f"[{row_index}/{total_rows}] GoogleV3 error: {e}")
    return None, None

def fetch_missing_city(address: str, geolocator: GoogleV3) -> Optional[str]:
    """
    Fetches the city name for a given address using geocoding.
    
    Parameters:
    address (str): The full street address.
    geolocator (GoogleV3): An instance of a GoogleV3 geocoding class.
    
    Returns:
    Optional[str]: The city name, or None if unsuccessful.
    """
    # Initialize city variable
    city = None
    
    try:
        geocode_info = geolocator.geocode(address, components={'administrative_area': 'CA', 'country': 'US'})
        
        # Get raw geocode information
        raw = geocode_info.raw['address_components']
        
        # Find the 'locality' aka city
        city = [addr['long_name'] for addr in raw if 'locality' in addr['types']][0]
        
        logger.info(f"Fetched city ({city}) for {address}.")
    except AttributeError:
        logger.warning(f"Geocoding returned no results for {address}.")
    except Exception as e:
        logger.warning(f"Couldn't fetch city for {address} because of {e}.")
    
    return city

def return_zip_code(address: str, geolocator: GoogleV3) -> Optional[str]:
    """
    Fetches the postal code for a given address using geocoding.

    Parameters:
    address (str): The full street address.
    geolocator (GoogleV3): An instance of the GoogleV3 geocoding class.

    Returns:
    Optional[str]: The postal code as a string, or None if unsuccessful.
    """
    postalcode = None

    try:
        geocode_info = geolocator.geocode(
            address, components={'administrative_area': 'CA', 'country': 'US'}
        )
        if geocode_info:
            raw = geocode_info.raw['address_components']
            # Find the 'postal_code'
            postalcode = next(
                (addr['long_name'] for addr in raw if 'postal_code' in addr['types']),
                None
            )
            if postalcode:
                logger.info(f"Fetched zip code ({postalcode}) for {address}.")
            else:
                logger.warning(f"No postal code found in geocoding results for {address}.")
        else:
            logger.warning(f"Geocoding returned no results for {address}.")
    except Exception as e:
        logger.warning(f"Couldn't fetch zip code for {address} because of {e}.")
        postalcode = None

    return postalcode

def fetch_missing_zip_codes(df: pd.DataFrame, geolocator) -> pd.DataFrame:
    """
    For rows where the 'zip_code' is missing or equals "Assessor",
    this function retrieves the missing postal code using the row's 'short_address'
    and updates the dataframe accordingly.

    Args:
        df (pd.DataFrame): DataFrame containing a 'zip_code' column and a 'short_address' column.
        geolocator: Geolocator instance used by the return_zip_code function.

    Returns:
        pd.DataFrame: The updated DataFrame with fixed zip codes.
    """
    if "zip_code" in df.columns:
        df["zip_code"] = df["zip_code"].astype("string")
    missing_zip_df = df.loc[(df['zip_code'].isnull()) | (df['zip_code'] == 'Assessor')]
    total_missing = len(missing_zip_df)
    counter = 0
    for row in missing_zip_df.itertuples():
        counter += 1
        short_address = df.at[row.Index, 'short_address']
        logger.info(f"Fixing zip code for row {counter} of {total_missing}: {row.mls_number}")
        missing_zip = return_zip_code(short_address, geolocator=geolocator)
        df.at[row.Index, 'zip_code'] = missing_zip
    return df


def _has_text(value) -> bool:
    if value is None or value is pd.NA:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(str(value).strip()) and str(value).strip().lower() != "assessor"


def _google_address_component(raw: dict, component_types: tuple[str, ...]) -> str | None:
    components = raw.get("address_components", []) if isinstance(raw, dict) else []
    for component_type in component_types:
        for component in components:
            if component_type in component.get("types", []):
                value = component.get("long_name")
                return str(value) if value else None
    return None


def fill_missing_location_fields_with_checkpoint(
    df: pd.DataFrame,
    *,
    geolocator: GoogleV3,
    checkpoint_store: ListingCheckpointStore | None,
    street_column: str,
    city_column: str = "city",
    zip_column: str = "zip_code",
) -> pd.DataFrame:
    """
    Resolve missing city/ZIP fields once and checkpoint the Google response.

    Coordinates returned by the same request are carried forward so the normal
    coordinate stage does not issue a second geocode request for that listing.
    """
    # CSV/Excel inputs commonly infer location columns containing numbers and
    # missing values as float64. Geocoded city/ZIP values are text, so make the
    # columns capable of holding them before assigning individual cells.
    df[city_column] = df[city_column].astype("object")
    df[zip_column] = df[zip_column].astype("object")

    for row_index in df.index:
        city_missing = not _has_text(df.at[row_index, city_column])
        zip_missing = not _has_text(df.at[row_index, zip_column])
        if not city_missing and not zip_missing:
            continue

        mls_number = normalize_mls_number(df.at[row_index, "mls_number"])
        query_parts = [
            df.at[row_index, street_column],
            df.at[row_index, city_column],
            df.at[row_index, zip_column],
        ]
        query = " ".join(
            str(value).strip() for value in query_parts if _has_text(value)
        )
        query_hash = stable_fingerprint(query)
        record = checkpoint_store.get(mls_number) if checkpoint_store else None
        cache_hit = bool(
            query_hash
            and record
            and record.get("location_query_hash") == query_hash
            and record.get("location_status") in SUCCESS_STATUSES
        )

        location_error = None
        if cache_hit:
            resolved_city = record.get("resolved_city")
            resolved_zip = record.get("resolved_zip_code")
            latitude = record.get("latitude")
            longitude = record.get("longitude")
            status = "cached"
        else:
            try:
                location = geolocator.geocode(
                    query,
                    timeout=10,
                    components={
                        "administrative_area": "CA",
                        "country": "US",
                    },
                )
                raw = location.raw if location is not None else {}
                resolved_city = _google_address_component(
                    raw,
                    ("locality", "postal_town", "sublocality_level_1"),
                )
                resolved_zip = _google_address_component(raw, ("postal_code",))
                latitude = getattr(location, "latitude", None)
                longitude = getattr(location, "longitude", None)
                city_resolved = not city_missing or _has_text(resolved_city)
                zip_resolved = not zip_missing or _has_text(resolved_zip)
                status = "success" if city_resolved and zip_resolved else "failed"
                if status == "failed":
                    location_error = "Geocoder did not resolve all missing fields"
            except Exception as error:
                resolved_city = None
                resolved_zip = None
                latitude = None
                longitude = None
                status = "failed"
                location_error = str(error)

        if city_missing and _has_text(resolved_city):
            df.at[row_index, city_column] = resolved_city
        if zip_missing and _has_text(resolved_zip):
            df.at[row_index, zip_column] = resolved_zip
        if _usable_coordinates(latitude, longitude, max_valid_latitude=35.393528):
            df.at[row_index, "_prefetched_latitude"] = latitude
            df.at[row_index, "_prefetched_longitude"] = longitude
        df.at[row_index, "location_status"] = status

        if checkpoint_store and not cache_hit:
            checkpoint_store.checkpoint(
                mls_number,
                location_status=status,
                location_error=location_error,
                location_query_hash=query_hash,
                resolved_city=resolved_city,
                resolved_zip_code=resolved_zip,
                latitude=latitude,
                longitude=longitude,
            )

    return df


def _usable_coordinates(
    latitude,
    longitude,
    *,
    max_valid_latitude: float | None = None,
) -> bool:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return False
    if pd.isna(lat) or pd.isna(lon):
        return False
    if max_valid_latitude is not None and lat > max_valid_latitude:
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180


def update_dataframe_with_geocoding(
    df: pd.DataFrame,
    *,
    geolocator: GoogleV3,
    checkpoint_store: ListingCheckpointStore | None = None,
    existing_df: pd.DataFrame | None = None,
    use_nominatim: bool = False,
    max_valid_latitude: float | None = 35.393528,
) -> pd.DataFrame:
    """
    Geocode listings with address-keyed checkpoint reuse.

    A checkpoint hit avoids another paid lookup. Legacy coordinates are reused
    only when their normalized address still matches the incoming address.
    """
    existing_by_mls: dict[str, pd.Series] = {}
    if existing_df is not None and not existing_df.empty:
        existing = existing_df.copy()
        existing["_normalized_mls"] = existing["mls_number"].apply(
            normalize_mls_number
        )
        existing = existing.drop_duplicates("_normalized_mls", keep="last")
        existing_by_mls = {
            str(row["_normalized_mls"]): row
            for _, row in existing.iterrows()
        }

    provider = "nominatim" if use_nominatim else "google"
    for row_index in df.index:
        mls_number = normalize_mls_number(df.at[row_index, "mls_number"])
        address = df.at[row_index, "full_street_address"]
        address_hash = address_fingerprint(address)
        record = checkpoint_store.get(mls_number) if checkpoint_store else None

        checkpoint_hit = bool(
            address_hash
            and record
            and record.get("geocode_address_hash") == address_hash
            and record.get("geocode_status") in SUCCESS_STATUSES
            and _usable_coordinates(
                record.get("latitude"),
                record.get("longitude"),
                max_valid_latitude=max_valid_latitude,
            )
        )

        should_sync = False
        geocode_error = None
        if checkpoint_hit:
            latitude = record.get("latitude")
            longitude = record.get("longitude")
            status = "cached"
        else:
            existing_row = existing_by_mls.get(mls_number)
            prefetched_hit = (
                "_prefetched_latitude" in df.columns
                and "_prefetched_longitude" in df.columns
                and _usable_coordinates(
                    df.at[row_index, "_prefetched_latitude"],
                    df.at[row_index, "_prefetched_longitude"],
                    max_valid_latitude=max_valid_latitude,
                )
            )
            legacy_hit = bool(
                address_hash
                and existing_row is not None
                and address_fingerprint(existing_row.get("full_street_address"))
                == address_hash
                and _usable_coordinates(
                    existing_row.get("latitude"),
                    existing_row.get("longitude"),
                    max_valid_latitude=max_valid_latitude,
                )
            )
            if prefetched_hit:
                latitude = df.at[row_index, "_prefetched_latitude"]
                longitude = df.at[row_index, "_prefetched_longitude"]
                status = "success"
            elif legacy_hit:
                latitude = existing_row.get("latitude")
                longitude = existing_row.get("longitude")
                status = "reused"
            else:
                latitude, longitude = return_coordinates(
                    address=address,
                    row_index=row_index,
                    geolocator=geolocator,
                    total_rows=len(df),
                    use_nominatim=use_nominatim,
                )
                if _usable_coordinates(
                    latitude,
                    longitude,
                    max_valid_latitude=max_valid_latitude,
                ):
                    status = "success"
                else:
                    status = "failed"
                    geocode_error = "Geocoder returned no usable coordinates"
            should_sync = True

        df.at[row_index, "latitude"] = latitude
        df.at[row_index, "longitude"] = longitude
        df.at[row_index, "geocode_status"] = status
        df.at[row_index, "geocode_provider"] = provider
        df.at[row_index, "geocode_address_hash"] = address_hash

        if checkpoint_store and should_sync:
            checkpoint_store.checkpoint(
                mls_number,
                geocode_status=status,
                geocode_error=geocode_error,
                geocode_provider=provider,
                geocode_address_hash=address_hash,
                latitude=latitude,
                longitude=longitude,
            )

    df.drop(
        columns=["_prefetched_latitude", "_prefetched_longitude"],
        errors="ignore",
        inplace=True,
    )
    return df

def re_geocode_above_lat_threshold(
    df: pd.DataFrame,
    geolocator: GoogleV3,
    lat_threshold: float = 35.393528,
    *,
    checkpoint_store: ListingCheckpointStore | None = None,
    use_nominatim: bool = False,
) -> pd.DataFrame:
    """
    For rows where 'latitude' exceeds lat_threshold, re-fetch coordinates
    and overwrite the 'latitude' and 'longitude' columns in-place.
    """
    if "latitude" not in df.columns:
        return df

    # Coerce coords to numeric so comparisons and downstream logic don't break
    lat_num = pd.to_numeric(df["latitude"], errors="coerce")
    df["latitude"] = lat_num
    lon_num = pd.to_numeric(df["longitude"], errors="coerce")
    df["longitude"] = lon_num

    # Identify rows to re-geocode
    mask = lat_num > lat_threshold
    total = int(mask.sum())
    if total == 0:
        return df

    invalid_rows = df.loc[mask].copy()
    for counter, idx in enumerate(invalid_rows.index, start=1):
        logger.info(
            f"Re-geocoding row {counter} of {total}: MLS {df.at[idx,'mls_number']} "
            f"with latitude {df.at[idx,'latitude']} above {lat_threshold}"
        )

    invalid_rows = update_dataframe_with_geocoding(
        invalid_rows,
        geolocator=geolocator,
        checkpoint_store=checkpoint_store,
        use_nominatim=use_nominatim,
        max_valid_latitude=lat_threshold,
    )
    for column in (
        "latitude",
        "longitude",
        "geocode_status",
        "geocode_provider",
        "geocode_address_hash",
    ):
        df.loc[invalid_rows.index, column] = invalid_rows[column]

    return df
