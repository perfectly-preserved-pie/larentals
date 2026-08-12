import requests
import os
from dotenv import load_dotenv, find_dotenv
from loguru import logger
import pandas as pd
from typing import Any

load_dotenv(find_dotenv())

def get_howloud_score(lat: float, lon: float) -> dict[str, Any] | None:
    """
    Fetch the HowLoud score for one latitude/longitude pair.

    Args:
        lat: Latitude of the location.
        lon: Longitude of the location.

    Returns:
        The API's score mapping, or ``None`` when the request fails or has no
        usable result.

    Side Effects:
        Makes an authenticated request to the HowLoud API and logs failures.
    """
    params = { 'lng': f'{lon}', 'lat': f'{lat}' }
    url = 'https://api.howloud.com/score'
    headers = {'x-api-key': f'{os.getenv("HOWLOUD_API_KEY")}'}
    try:
        r = requests.get(url, params=params, headers=headers)
        r.raise_for_status()  # Raises a HTTPError if the HTTP request returned an unsuccessful status code
        data = r.json()
        if 'result' in data and isinstance(data['result'], list) and len(data['result']) > 0:
            logger.debug(f"Successfully fetched HowLoud score for {lat}, {lon}.")
            return data['result'][0]
        else:
            logger.warning(f"Unexpected 'result' format or empty list for coordinates {lat}, {lon}. Response: {data}")
            return None
    except requests.exceptions.RequestException as e:
        if r.status_code == 429:  # HTTP Status Code for "Too Many Requests"
            logger.warning("Rate limit reached for the HowLoud API.")
        else:
            logger.error(f"Error fetching HowLoud score for {lat}, {lon}. Error: {e}. Response: {r.text}")
        return None
    
def get_score_for_row(row: pd.Series, existing_howloud_columns: list[str]) -> dict[str, Any]:
  """
  Fetch missing HowLoud data for a dataframe row when needed.

  Args:
    row: Listing row containing ``Latitude`` and ``Longitude`` values.
    existing_howloud_columns: Columns whose missing values trigger a refresh.

  Returns:
    A score mapping, or an empty mapping when all existing values are present.
  """
  if any(pd.isna(row[col]) for col in existing_howloud_columns):
    return get_howloud_score(row.Latitude, row.Longitude)
  return {}

def update_existing_howloud_columns(
    df: pd.DataFrame, existing_howloud_columns: list[str]
) -> pd.DataFrame:
  """
  Fill existing HowLoud columns with values returned by the API.

  Args:
    df: Listings dataframe to update.
    existing_howloud_columns: Existing HowLoud columns to backfill.

  Returns:
    The updated dataframe. The input dataframe is modified in place.

  Side Effects:
    Performs one API lookup for each row with missing HowLoud values.
  """
  df['howloud_data'] = df.apply(get_score_for_row, axis=1, existing_howloud_columns=existing_howloud_columns)
  for key in existing_howloud_columns:
    column_name = f'howloud_{key}'
    df[column_name] = df[column_name].combine_first(df['howloud_data'].apply(lambda x: x.get(key, pd.NA)))
  df.drop(columns='howloud_data', inplace=True)
  return df

def cast_howloud_columns(df: pd.DataFrame) -> pd.DataFrame:
  """
  Cast HowLoud columns to nullable integer or string dtypes.

  Args:
    df: Listings dataframe containing HowLoud columns.

  Returns:
    The dataframe with normalized nullable column dtypes.

  Side Effects:
    Modifies matching columns in the input dataframe in place.
  """
  howloud_columns = [col for col in df.columns if col.startswith("howloud_")]
  for col in howloud_columns:
    if df[col].dropna().astype(str).str.isnumeric().all():
      df[col] = df[col].astype(pd.Int32Dtype())
    else:
      df[col] = df[col].astype(pd.StringDtype())
  return df

def update_howloud_scores(df: pd.DataFrame) -> pd.DataFrame:
  """
  Refresh and normalize HowLoud score columns in a listings dataframe.

  Args:
    df: Listings dataframe to enrich.

  Returns:
    The enriched dataframe with refreshed and normalized HowLoud columns.

  Side Effects:
    May call the external HowLoud API for rows with incomplete scores.
  """
  howloud_keys = ["score", "airports", "traffictext", "localtext", "airportstext", "traffic", "scoretext", "local"]
  existing_howloud_columns = [f"howloud_{key}" for key in howloud_keys if f"howloud_{key}" in df.columns]
  
  df = update_existing_howloud_columns(df, existing_howloud_columns)
  df = cast_howloud_columns(df)
  
  return df
