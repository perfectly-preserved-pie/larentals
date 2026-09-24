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
from difflib import SequenceMatcher
import re
import pandas as pd
import sys

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")


def _ensure_object_columns(
    df: pd.DataFrame,
    columns: tuple[str, ...],
) -> None:
    """Prepare geocoding metadata columns to receive text values.

    An entirely empty input column is often inferred as numeric. Converting it
    to object first lets the pipeline safely store statuses, provider names,
    address hashes, and missing values under pandas 3.

    Args:
        df: Dataframe to ensure object columns.
        columns: Column names to read or process.

    Returns:
        None.
    """
    for column in columns:
        if column in df.columns:
            df[column] = df[column].astype("object")
        else:
            df[column] = pd.Series(index=df.index, dtype="object")



def _google_street_key(value: str) -> str:
    """Compare common street spellings without losing the street identity.

    Google expands directions and suffixes (for example ``S St Andrews`` to
    ``South Saint Andrews Place``). Normalize whole words so suffix removal
    cannot accidentally alter a street name such as ``East``.

    Args:
        value: Street name from the listing or geocoder response.

    Returns:
        Comparable alphanumeric street key.
    """
    words = re.findall(r"[a-z0-9]+", value.casefold())
    directions = {"n": "north", "s": "south", "e": "east", "w": "west"}
    suffixes = {
        "st": "street", "ave": "avenue", "blvd": "boulevard", "rd": "road",
        "dr": "drive", "pl": "place", "ct": "court", "ln": "lane",
        "ter": "terrace", "pkwy": "parkway", "cir": "circle",
    }
    normalized = []
    for index, word in enumerate(words):
        if word == "st" and index < len(words) - 1 and words[index + 1] not in suffixes:
            word = "saint"
        else:
            word = directions.get(word, suffixes.get(word, word))
        if word in directions.values() and normalized and normalized[-1] == word:
            continue
        normalized.append(word)
    while normalized and normalized[-1] in suffixes.values():
        normalized.pop()
    return "".join(normalized)


def _google_result_rejection_reason(address: str, raw: dict) -> Optional[str]:
    """Explain why a Google candidate cannot safely locate this listing.

    Google can return a plausible point for a nearby property. Report the first
    failed check without another API request. Fractional house numbers such as
    ``5257 1/2`` share the base building number ``5257`` for map pin purposes.
    A partial-match flag is acceptable when Google still supplies matching
    street number, route, ZIP, and usable precision.

    Args:
        address: Address sent to the geocoder.
        raw: Google's response fields for the candidate result.

    Returns:
        The first failed check, or None when the candidate matches.
    """
    location_type = raw.get("geometry", {}).get("location_type")
    if location_type not in {"ROOFTOP", "RANGE_INTERPOLATED", "GEOMETRIC_CENTER"}:
        return f"location_type={location_type!r}"
    expected_number = re.match(r"\s*(\d+)", address)
    expected_zip = re.search(r"(?<!\d)(\d{5})(?:\.0)?\s*$", address)
    actual_number = _google_address_component(raw, ("street_number",))
    actual_zip = _google_address_component(raw, ("postal_code",))
    actual_route = _google_address_component(raw, ("route",))
    if expected_number:
        actual_number_parts = re.fullmatch(r"(\d+)(?:\s+\d+/\d+)?", actual_number or "")
        if not actual_number_parts or actual_number_parts.group(1) != expected_number.group(1):
            return f"street_number mismatch (expected base {expected_number.group(1)!r}, got {actual_number!r})"
    if expected_zip and actual_zip != expected_zip.group(1):
        return f"postal_code mismatch (expected {expected_zip.group(1)!r}, got {actual_zip!r})"
    street_line = address.split(",", 1)[0]
    street_line = re.sub(r"^\s*\d+(?:\s+\d+/\d+)?\s*", "", street_line)
    street_line = re.split(r"\s+(?:#{1,2}|apt\b|unit\b|ste\b)", street_line, maxsplit=1, flags=re.I)[0]
    if street_line.strip():
        score = SequenceMatcher(
            None, _google_street_key(street_line), _google_street_key(actual_route or "")
        ).ratio()
        if score < 0.65:
            return f"route mismatch (expected {street_line.strip()!r}, got {actual_route!r}, similarity {score:.2f})"
    if raw.get("partial_match") and (not expected_number or not expected_zip):
        return "partial_match=true (street number or ZIP cannot be verified)"
    return None


def _google_result_matches_address(address: str, raw: dict) -> bool:
    """Keep the boolean address check used by existing callers and tests.

    The rejection helper owns the checks so logging and acceptance always use
    the same decision.

    Args:
        address: Address sent to the geocoder.
        raw: Google's response fields for the candidate result.

    Returns:
        Whether the candidate passes every address check.
    """
    return _google_result_rejection_reason(address, raw) is None



def _google_verified_zip_correction(address: str, raw: dict, reason: Optional[str]) -> Optional[str]:
    """Trust Google's ZIP only for a precise match to the listed building.

    A wrong source ZIP can make Google's constrained request return nothing.
    An unrestricted rooftop result may correct it only when the number, route,
    and city still identify the same property; a nearby road is insufficient.

    Args:
        address: Listing address used for this geocoding attempt.
        raw: Google's response fields for the candidate result.
        reason: Failed strict check for the candidate.

    Returns:
        Google's five-digit ZIP when the other address fields verify, or None.
    """
    if not reason or not reason.startswith("postal_code mismatch"):
        return None
    if raw.get("partial_match") or raw.get("geometry", {}).get("location_type") != "ROOFTOP":
        return None
    google_zip = _google_address_component(raw, ("postal_code",))
    google_route = _google_address_component(raw, ("route",))
    if not google_zip or not re.fullmatch(r"\d{5}", google_zip) or not google_route:
        return None
    street_line, separator, locality = address.partition(",")
    if not separator:
        return None
    listed_route = re.sub(r"^\s*\d+(?:\s+\d+/\d+)?\s*", "", street_line)
    listed_route = re.split(
        r"\s+(?:#{1,2}|apt\b|unit\b|ste\b)", listed_route, maxsplit=1, flags=re.I
    )[0]
    if not listed_route or _google_street_key(listed_route) != _google_street_key(google_route):
        return None
    listed_city = re.sub(r"\s+\d{5}(?:\.0)?\s*$", "", locality).strip().casefold()
    formatted_address = str(raw.get("formatted_address") or "").casefold()
    if not listed_city or listed_city not in formatted_address:
        return None
    return google_zip


def _address_with_zip(address: str, zip_code: str) -> str:
    """Replace the trailing listing ZIP while preserving its street and city.

    The full address and geocode fingerprint must refer to the same corrected
    ZIP, or a later pipeline run would repeat the paid lookup.

    Args:
        address: Full listing address ending in a five-digit ZIP.
        zip_code: Verified replacement ZIP from Google.

    Returns:
        Full address with the verified ZIP.
    """
    return re.sub(r"(?<!\d)\d{5}(?:\.0)?\s*$", zip_code, address)


def _set_google_zip_on_row(
    df: pd.DataFrame, row_index: int, address: str, zip_code: str
) -> str:
    """Keep the displayed ZIP and full address aligned after a correction.

    The source report remains untouched. Only this working listing row changes,
    and its address fingerprint is recomputed by the caller for checkpoint use.

    Args:
        df: Listing dataframe being geocoded.
        row_index: Row whose verified ZIP differs from the report.
        address: Full source address on that row.
        zip_code: ZIP verified by the Google rooftop result.

    Returns:
        Full address with the corrected ZIP.
    """
    corrected_address = _address_with_zip(address, zip_code)
    if "zip_code" in df.columns:
        df["zip_code"] = df["zip_code"].astype("object")
    df.at[row_index, "zip_code"] = zip_code
    df.at[row_index, "full_street_address"] = corrected_address
    return corrected_address


def _return_coordinates_with_zip(
    address: str,
    row_index: int,
    geolocator: GoogleV3,
    total_rows: int,
    use_nominatim: bool = False,
    nominatim_user_agent: str = "larentals-geocoder",
    nominatim_timeout: int = 10,
    allow_zip_correction: bool = False,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Geocode a listing and carry a verified Google ZIP correction.

    Numeric source columns can turn a street number into ``800.0``. Normalize
    it before querying Google. For a unit address with no usable candidate,
    retry the building address and apply the same address checks before moving
    a listing pin. A query without the ZIP filter diagnoses source ZIP errors,
    but its candidate must still match the listing ZIP unless the dataframe
    caller allows a verified correction. Failures return empty coordinates.
    The third return field is set only when a
    rooftop result verifies the building but contradicts the source ZIP.

    Parameters:
    address (str): The full street address.
    row_index (int): The row index for logging.
    geolocator (GoogleV3): An instance of a geocoding class.
    total_rows (int): Total number of rows for logging.
    use_nominatim (bool): Whether to use Nominatim instead of GoogleV3.
    nominatim_user_agent (str): User-agent sent to Nominatim.
    nominatim_timeout (int): Nominatim request timeout in seconds.
    allow_zip_correction (bool): Whether a verified rooftop result may replace the source ZIP.

    Returns:
    Tuple[Optional[float], Optional[float], Optional[str]]: Latitude, longitude,
    and an optional corrected ZIP. Coordinates are None when no candidate passes.
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
                return location.latitude, location.longitude, None
            logger.error(f"[{row_index}/{total_rows}] Nominatim: no result for '{address}'")
        except (GeocoderTimedOut, GeocoderServiceError, Exception) as e:
            logger.error(f"[{row_index}/{total_rows}] Nominatim error: {e}")
        return None, None, None

    # default: GoogleV3
    try:
        zip_match = re.search(r"(?<!\d)(\d{5})(?:\.0)?\s*$", address)
        components = {'administrative_area': 'CA', 'country': 'US'}
        if zip_match:
            components['postal_code'] = zip_match.group(1)
        normalized_address = re.sub(r"^(\s*\d+)\.0(?=\s)", r"\1", address)
        normalized_address = re.sub(r"(\d{5})\.0\s*$", r"\1", normalized_address)
        street_line, separator, locality = normalized_address.partition(",")
        building_street = re.sub(
            r"\s+(?:#{1,2}|apt\b|unit\b|ste\b).*$",
            "",
            street_line,
            flags=re.I,
        )
        queries = [normalized_address]
        if building_street != street_line:
            queries.append(building_street + separator + locality)
        attempts = [("ZIP constrained", components)]
        if zip_match:
            attempts.append(("without ZIP filter", {'administrative_area': 'CA', 'country': 'US'}))
        failures = []
        for query in queries:
            for label, request_components in attempts:
                loc = geolocator.geocode(query, timeout=10, components=request_components)
                if loc:
                    rejection_reason = _google_result_rejection_reason(query, loc.raw)
                    if rejection_reason is None:
                        return loc.latitude, loc.longitude, None
                    corrected_zip = (
                        _google_verified_zip_correction(query, loc.raw, rejection_reason)
                        if allow_zip_correction else None
                    )
                    if corrected_zip:
                        logger.info(
                            f"[{row_index}/{total_rows}] GoogleV3: corrected ZIP for "
                            f"'{address}' to {corrected_zip} from a matching rooftop result"
                        )
                        return loc.latitude, loc.longitude, corrected_zip
                    failures.append(
                        f"{query!r} [{label}]: {rejection_reason}; "
                        f"Google returned {loc.raw.get('formatted_address')!r}"
                    )
                else:
                    failures.append(f"{query!r} [{label}]: no result")
        logger.warning(
            f"[{row_index}/{total_rows}] GoogleV3: no usable result for "
            f"'{address}'; attempts: {'; '.join(failures)}"
        )
    except (GeocoderTimedOut, GeocoderServiceError, Exception) as e:
        logger.warning(f"[{row_index}/{total_rows}] GoogleV3 error: {e}")
    return None, None, None


def return_coordinates(
    address: str,
    row_index: int,
    geolocator: GoogleV3,
    total_rows: int,
    use_nominatim: bool = False,
    nominatim_user_agent: str = "larentals-geocoder",
    nominatim_timeout: int = 10,
) -> Tuple[Optional[float], Optional[float]]:
    """Return coordinates for callers that do not store ZIP corrections.

    The dataframe pipeline uses the detailed result so it can update the ZIP
    and address hash together. Coordinate-only callers keep rejecting ZIP
    mismatches because they have no place to store a correction.

    Args:
        address: Full listing address.
        row_index: Row index for logging.
        geolocator: Configured geocoding provider.
        total_rows: Total rows for logging.
        use_nominatim: Whether to use Nominatim instead of Google.
        nominatim_user_agent: User agent sent to Nominatim.
        nominatim_timeout: Nominatim timeout in seconds.

    Returns:
        Latitude and longitude, or two None values when no result passes.
    """
    latitude, longitude, _ = _return_coordinates_with_zip(
        address, row_index, geolocator, total_rows,
        use_nominatim, nominatim_user_agent, nominatim_timeout,
    )
    return latitude, longitude


def fetch_missing_city(address: str, geolocator: GoogleV3) -> Optional[str]:
    """Fetches the city name for a given address using geocoding.

The lookup is needed only when the source address lacks a usable city value.

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
    """Fetches the postal code for a given address using geocoding.

Postal components are taken from the geocoder response rather than inferred from partial address text.

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

def fetch_missing_zip_codes(df: pd.DataFrame, geolocator: GoogleV3) -> pd.DataFrame:
    """For rows where the 'zip_code' is missing or equals "Assessor",
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


def _has_text(value: object) -> bool:
    """Handle has text.

    Null-like values are treated as absent before address component selection.

    Args:
        value: Candidate city, ZIP, or address field to validate.

    Returns:
        Whether the value contains usable, non-placeholder text.
    """
    if value is None or value is pd.NA:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(str(value).strip()) and str(value).strip().lower() != "assessor"


def _google_address_component(raw: dict, component_types: tuple[str, ...]) -> str | None:
    """Handle google address component.

    Address components are selected by Google’s type labels because their array order is not stable.

    Args:
        raw: Raw Google geocoder response containing address components.
        component_types: Google address-component types to search in priority order.

    Returns:
        The google address component text, or ``None`` when unavailable.
    """
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
    """Resolve missing city/ZIP fields once and checkpoint the Google response.

    Coordinates returned by the same request are carried forward so the normal
    coordinate stage does not issue a second geocode request for that listing.

    Args:
        df: Dataframe to fill missing location fields with checkpoint.
        geolocator: Configured geocoder used to resolve the address.
        checkpoint_store: Optional checkpoint store used to resume prior processing.
        street_column: Dataframe column containing street addresses.
        city_column: Dataframe column containing city names.
        zip_column: Dataframe column containing ZIP codes.

    Returns:
        The fill missing location fields with checkpoint dataframe.
    """
    # CSV/Excel inputs commonly infer location columns containing numbers and
    # missing values as float64. Geocoded city/ZIP values are text, so make the
    # columns capable of holding them before assigning individual cells.
    df[city_column] = df[city_column].astype("object")
    df[zip_column] = df[zip_column].astype("object")
    _ensure_object_columns(df, ("location_status",))
    for coordinate_column in ("_prefetched_latitude", "_prefetched_longitude"):
        if coordinate_column in df.columns:
            df[coordinate_column] = pd.to_numeric(
                df[coordinate_column],
                errors="coerce",
            )

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
    latitude: object,
    longitude: object,
    *,
    max_valid_latitude: float | None = None,
) -> bool:
    """Handle usable coordinates.

    Only finite coordinates inside the configured region are safe to attach to a listing.

    Args:
        latitude: Property latitude in decimal degrees.
        longitude: Property longitude in decimal degrees.
        max_valid_latitude: Optional upper latitude bound used to reject bad coordinates.

    Returns:
        Whether both coordinates are present and numeric.
    """
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
    """Geocode listings with address-keyed checkpoint reuse.

    A checkpoint hit avoids another paid lookup. A verified Google ZIP change
    updates the row's displayed address and fingerprint together, and the
    checkpoint can restore that correction on the next run.

    Args:
        df: Dataframe to update dataframe with geocoding.
        geolocator: Configured geocoder used to resolve the address.
        checkpoint_store: Optional checkpoint store used to resume prior processing.
        existing_df: Previously published listings to merge with the new dataframe.
        use_nominatim: Whether to use Nominatim instead of the Google geocoder.
        max_valid_latitude: Optional upper latitude bound used to reject bad coordinates.

    Returns:
        The updated dataframe with geocoding dataframe.
    """
    for coordinate_column in ("latitude", "longitude"):
        if coordinate_column in df.columns:
            df[coordinate_column] = pd.to_numeric(
                df[coordinate_column],
                errors="coerce",
            )
        else:
            df[coordinate_column] = pd.Series(index=df.index, dtype="float64")
    _ensure_object_columns(
        df,
        ("geocode_status", "geocode_provider", "geocode_address_hash"),
    )

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
        cached_zip = record.get("resolved_zip_code") if record else None
        if (
            not use_nominatim
            and isinstance(cached_zip, str)
            and re.fullmatch(r"\d{5}", cached_zip)
            and record.get("geocode_status") in SUCCESS_STATUSES
            and record.get("geocode_address_hash")
            == address_fingerprint(_address_with_zip(address, cached_zip))
        ):
            address = _set_google_zip_on_row(df, row_index, address, cached_zip)
            address_hash = address_fingerprint(address)

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
        corrected_zip = None
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
                latitude, longitude, corrected_zip = _return_coordinates_with_zip(
                    address=address,
                    row_index=row_index,
                    geolocator=geolocator,
                    total_rows=len(df),
                    use_nominatim=use_nominatim,
                    allow_zip_correction=True,
                )
                if _usable_coordinates(
                    latitude,
                    longitude,
                    max_valid_latitude=max_valid_latitude,
                ):
                    if corrected_zip:
                        address = _set_google_zip_on_row(df, row_index, address, corrected_zip)
                        address_hash = address_fingerprint(address)
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
            checkpoint_fields = {
                "geocode_status": status,
                "geocode_error": geocode_error,
                "geocode_provider": provider,
                "geocode_address_hash": address_hash,
                "latitude": latitude,
                "longitude": longitude,
            }
            if corrected_zip and status == "success":
                checkpoint_fields["resolved_zip_code"] = corrected_zip
            checkpoint_store.checkpoint(mls_number, **checkpoint_fields)

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
    """For rows where 'latitude' exceeds lat_threshold, re-fetch coordinates
    and overwrite the 'latitude' and 'longitude' columns in-place.

    Args:
        df: Dataframe to re geocode above lat threshold.
        geolocator: Configured geocoder used to resolve the address.
        lat_threshold: Latitude above which coordinates are considered erroneous.
        checkpoint_store: Optional checkpoint store used to resume prior processing.
        use_nominatim: Whether to use Nominatim instead of the Google geocoder.

    Returns:
        The re geocode above lat threshold dataframe.
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
    _ensure_object_columns(
        df,
        ("geocode_status", "geocode_provider", "geocode_address_hash"),
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
