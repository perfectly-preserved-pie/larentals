import requests
import os
from dotenv import load_dotenv, find_dotenv
from loguru import logger

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