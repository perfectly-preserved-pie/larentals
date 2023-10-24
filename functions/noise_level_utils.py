import requests
import os
from dotenv import load_dotenv, find_dotenv
from loguru import logger
import pandas as pd

load_dotenv(find_dotenv())

# Function to get the HowLoud score for a given location
def get_howloud_score(lat, lon):
    params = { 'lng': f'{lon}', 'lat': f'{lat}' }
    url = 'https://api.howloud.com/score'
    headers = {'x-api-key': f'{os.getenv("HOWLOUD_API_KEY")}'}
    try:
        r = requests.get(url, params=params, headers=headers)
        r.raise_for_status()  # Raises a HTTPError if the HTTP request returned an unsuccessful status code
        data = r.json()
        if 'result' in data and isinstance(data['result'], list) and len(data['result']) > 0:
            logger.debug("Successfully fetched HowLoud score for {lat}, {lon}.", lat=lat, lon=lon)
            return data['result'][0]
        else:
            logger.warning("Unexpected 'result' format or empty list for coordinates {lat}, {lon}. Response: {response}", lat=lat, lon=lon, response=data)
            return None
    except requests.exceptions.RequestException as e:
        if r.status_code == 429:  # HTTP Status Code for "Too Many Requests"
            logger.warning("Rate limit reached for the HowLoud API.")
        else:
            logger.error("Error fetching HowLoud score for {lat}, {lon}. Error: {error}. Response: {response}", lat=lat, lon=lon, error=e, response=r.text)
        return None
    
# Get the HowLoud score for each row
def get_score_for_row(row, existing_howloud_columns):
  if any(pd.isna(row[col]) for col in existing_howloud_columns):
    return get_howloud_score(row.Latitude, row.Longitude)
  return {}

# Update existing HowLoud columns
def update_existing_howloud_columns(df, existing_howloud_columns):
  df['howloud_data'] = df.apply(get_score_for_row, axis=1, existing_howloud_columns=existing_howloud_columns)
  for key in existing_howloud_columns:
    column_name = f'howloud_{key}'
    df[column_name] = df[column_name].combine_first(df['howloud_data'].apply(lambda x: x.get(key, pd.NA)))
  df.drop(columns='howloud_data', inplace=True)
  return df

# Cast HowLoud columns as either nullable strings or nullable integers
def cast_howloud_columns(df):
  howloud_columns = [col for col in df.columns if col.startswith("howloud_")]
  for col in howloud_columns:
    if df[col].dropna().astype(str).str.isnumeric().all():
      df[col] = df[col].astype(pd.Int32Dtype())
    else:
      df[col] = df[col].astype(pd.StringDtype())
  return df

# Update HowLoud scores
def update_howloud_scores(df):
  howloud_keys = ["score", "airports", "traffictext", "localtext", "airportstext", "traffic", "scoretext", "local"]
  existing_howloud_columns = [f"howloud_{key}" for key in howloud_keys if f"howloud_{key}" in df.columns]
  
  df = update_existing_howloud_columns(df, existing_howloud_columns)
  df = cast_howloud_columns(df)
  
  return df