from bs4 import BeautifulSoup
from loguru import logger
import json
import re
import requests

def get_pin_and_street_details_zimas(house_number: str, street_name: str) -> dict:
    """Query ZIMAS to get PIN, street direction, and street suffix."""
    
    # Base URL and endpoint
    base_url = "https://zimas.lacity.org"
    endpoint = "/ajaxSearchResults.aspx"
    
    # Define the query parameters
    params = {
        "search": "address",
        "HouseNumber": house_number,
        "StreetName": street_name
    }
    
    # Send the GET request
    response = requests.get(base_url + endpoint, params=params)
    
    # Check if the request was successful
    if response.status_code == 200:
        # Extract data using regular expressions
        text = response.text
        
        # Regular expression to find the PIN, street direction, and suffix
        match = re.search(r"ZimasData\.navigateDataToPin\('([^']+)', '\d+\s+([NSEW])\s+\w+\s+([A-Z]+)'\)", text)
        
        if match:
            pin = match.group(1)
            street_direction = match.group(2)
            street_suffix = match.group(3)
            
            logger.info(f"PIN: {pin}, Street Direction: {street_direction}, Street Suffix: {street_suffix}")
            return {
                "PIN": pin,
                "StreetDirection": street_direction,
                "StreetSuffix": street_suffix
            }
        else:
            logger.error("Could not extract PIN, Street Direction, or Street Suffix from the response.")
            return {}
    else:
        logger.error(f"Failed to retrieve data from ZIMAS. Status code: {response.status_code}")
        return {}

def fetch_permits(house_number: str, street_name: str, zip_code: str) -> list[dict]:
    """Fetches permit data from the specified URL and parses it into a list of dictionaries."""
    
    # Get PIN, Street Direction, and Street Suffix from ZIMAS
    zimas_data = get_pin_and_street_details_zimas(house_number, street_name)
    
    if not zimas_data:
        logger.error("Could not retrieve PIN, Street Direction, or Street Suffix from ZIMAS.")
        return []

    street_direction = zimas_data.get('StreetDirection')
    street_suffix = zimas_data.get('StreetSuffix')
    logger.debug(f"Street Direction: {street_direction}, Street Suffix: {street_suffix}")
    
    if not street_direction or not street_suffix:
        logger.error("Street direction or suffix not found in ZIMAS response.")
        return []
    
    # Define the base URL and the endpoint path
    base_url = "https://www.ladbsservices2.lacity.org"
    endpoint = "/OnlineServices/PermitReport/_IparPcisAddressDrillDownPartial"
    
    # Define the query parameters
    params = {
        "Range_Str": house_number,
        "Frac_Str": "",
        "Range_End": house_number,
        "Frac_End": "",
        "Str_Dir": street_direction,
        "Str_Name": street_name.upper(),  # Ensure street name is uppercase
        "Str_Suff": street_suffix,  # Use the dynamically determined suffix
        "Suff_Dir": "",
        "Unit_Str": "",
        "Unit_End": "",
        "Zip": zip_code
    }
    
    # Send the GET request
    response = requests.get(base_url + endpoint, params=params)

    logger.debug(f"Request URL: {response.url}")
    
    # Check if the request was successful
    if response.status_code == 200:
        logger.info("Successfully retrieved permit data.")

        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the table and rows within it
        table = soup.find('table', {'class': 'table table-nested'})
        if not table:
            logger.error("Could not find the expected table in the HTML response.")
            return []

        rows = table.find_all('tr')[1:]  # Skipping the header row
        
        # Initialize a list to store the data
        permit_data = []
        
        # Extract data from each row
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5:
                logger.error("Unexpected number of columns in row.")
                continue
            
            record = {
                "Application/Permit #": cols[0].text.strip(),
                "PC/Job #": cols[1].text.strip(),
                "Type": cols[2].text.strip(),
                "Status": cols[3].text.strip(),
                "Work Description": cols[4].text.strip()
            }
            permit_data.append(record)
        
        return permit_data
    
    else:
        logger.error(f"Failed to retrieve permit data. Status code: {response.status_code}")
        return []

# Example usage
house_number = "1452"
street_name = "96th"
zip_code = "90002"

# Fetch and parse the permit data
permit_data = fetch_permits(house_number, street_name, zip_code)

# If data was retrieved successfully, print it or save it
if permit_data:
    logger.debug("Permit data retrieved:", permit_data)  # Debug print
    # Print the data
    for entry in permit_data:
        print(entry)
    
    # Optionally, save to JSON
    with open('permit_data.json', 'w') as json_file:
        json.dump(permit_data, json_file, indent=4)

else:
    logger.info("No permit data found.")
