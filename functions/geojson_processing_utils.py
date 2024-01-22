from typing import Dict, List, Any
import json
import requests

def optimize_geojson(input_filepath: str, output_filepath: str, fields_to_keep: List[str]) -> None:
    """
    Optimizes a GeoJSON data by retaining only specified fields in the properties of each feature,
    and saves the optimized data to a file.

    Args:
        input_filepath (str): Path to the input GeoJSON file.
        output_filepath (str): Path to the optimized output GeoJSON file.
        fields_to_keep (List[str]): A list of strings specifying the fields to retain in the properties.
    """
    # Load the GeoJSON data from the input file
    with open(input_filepath, 'r') as f:
        data = json.load(f)

    # Keep only the features in Los Angeles County
    data['features'] = [feature for feature in data['features'] if feature['properties'].get('CountyName') == 'Los Angeles']

    # Now process each remaining feature in the GeoJSON
    for feature in data['features']:
        properties: Dict = feature['properties']
        # Keep only the required fields
        feature['properties'] = {key: properties[key] for key in fields_to_keep if key in properties}

    # Save the optimized GeoJSON data to the output file
    with open(output_filepath, 'w') as f:
        json.dump(data, f)

def fetch_geojson_data(url: str) -> Any:
    """
    Fetches GeoJSON data from a URL.

    Args:
        url (str): The URL to fetch the GeoJSON data from.

    Returns:
        Any: The fetched GeoJSON data.
    """
    response = requests.get(url)
    response.raise_for_status() # Raise an exception if the request was unsuccessful
    return response.json()