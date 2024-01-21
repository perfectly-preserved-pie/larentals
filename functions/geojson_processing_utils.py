from typing import Dict, List

def optimize_geojson(data: Dict, fields_to_keep: List[str]) -> Dict:
    """
    Optimizes a GeoJSON data by retaining only specified fields in the properties of each feature.

    Args:
        data (Dict): The GeoJSON data to optimize.
        fields_to_keep (List[str]): A list of strings specifying the fields to retain in the properties.

    Returns:
        Dict: The optimized GeoJSON data.
    """
    # Process each feature in the GeoJSON
    for feature in data['features']:
        properties: Dict = feature['properties']
        # Keep only the required fields
        feature['properties'] = {key: properties[key] for key in fields_to_keep if key in properties}

    return data