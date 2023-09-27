import requests
import os
from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv('../.env'))

# Function to get the HowLoud score for a given location
def get_howloud_score(lat, lon):
    params = { 'lng': f'{lon}', 'lat': f'{lat}' }
    url = 'https://api.howloud.com/score'
    headers = {'x-api-key': f'{os.getenv("HOWLOUD_API_KEY")}'}
    try:
        r = requests.get(url, params=params, headers=headers)
    except requests.exceptions.RequestException as e:
        logger.error(e)
    if r.status_code == 200:
        result = r.json()['result'][0]
        return result
    else:
        logger.error(f'HowLoud API returned a {r.status_code} error.')
        return None