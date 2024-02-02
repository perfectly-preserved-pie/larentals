from typing import Dict, List, Any
import json
import requests
import uuid

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

def fetch_json_data(url: str) -> Any:
    """
    Fetches JSON data from a URL.

    Args:
        url (str): The URL to fetch the JSON data from.

    Returns:
        Any: The fetched JSON data.
    """
    response = requests.get(url)
    response.raise_for_status() # Raise an exception if the request was unsuccessful
    return response.json()

def convert_to_geojson(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Converts a list of dictionaries to GeoJSON format.

    Args:
        data (List[Dict[str, Any]]): The data to convert.

    Returns:
        Dict[str, Any]: The data in GeoJSON format.
    """
    return {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'id': str(uuid.uuid4()),  # Assign a unique id to each feature
                'geometry': {
                    'type': 'Point',
                    'coordinates': [float(item['lon']), float(item['lat'])]
                },
                'properties': item,
            }
            for item in data
        ],
    }