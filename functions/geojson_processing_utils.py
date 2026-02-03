from typing import Dict, List, Any
from functools import lru_cache
from pathlib import Path
import json
import logging
import re
import uuid

logger = logging.getLogger(__name__)

_ZIP_RE = re.compile(r"^\d{5}$")
_DEFAULT_ZIP_GEOJSON_PATH = Path("assets/datasets/la_county_zip_codes.geojson")

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


@lru_cache(maxsize=4)
def _load_zip_boundaries(file_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Load LA County ZIP boundaries from a local GeoJSON file.

    Returns:
        Dict mapping ZIP code strings to GeoJSON Features.
    """
    path = Path(file_path)
    if not path.exists():
        logger.warning("ZIP boundary file not found: %s", path)
        return {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        logger.warning("Failed reading ZIP boundary file %s: %s", path, exc)
        return {}

    features = data.get("features", [])
    lookup: Dict[str, Dict[str, Any]] = {}
    for feature in features:
        props = feature.get("properties") or {}
        raw_zip = props.get("ZIPCODE")
        if raw_zip is None:
            continue
        zip_code = str(raw_zip).strip().zfill(5)
        if not _ZIP_RE.fullmatch(zip_code):
            continue
        geometry = feature.get("geometry")
        if not geometry:
            continue
        lookup[zip_code] = {
            "type": "Feature",
            "properties": {"zip_code": zip_code},
            "geometry": geometry,
        }

    return lookup


@lru_cache(maxsize=512)
def fetch_zip_boundary_feature(zip_code: str, file_path: str | None = None) -> Dict[str, Any] | None:
    """
    Fetch a LA County ZIP polygon from a local GeoJSON file.

    Args:
        zip_code: 5-digit ZIP code.
        file_path: Optional file path to the local ZIP GeoJSON.

    Returns:
        GeoJSON Feature dict or None when not found/invalid.
    """
    if not zip_code:
        return None

    zip_code = str(zip_code).strip()
    if not _ZIP_RE.fullmatch(zip_code):
        return None

    path = file_path or str(_DEFAULT_ZIP_GEOJSON_PATH)
    lookup = _load_zip_boundaries(path)
    return lookup.get(zip_code)