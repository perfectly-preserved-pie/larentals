from dash_extensions.javascript import Namespace
from datetime import datetime, timedelta
from dotenv import load_dotenv
from functions.geojson_processing_utils import fetch_json_data, convert_to_geojson
from sodapy import Socrata
from typing import Any, ClassVar, Optional
from urllib.parse import urlparse
import dash_leaflet as dl
import json
import os
import uuid

load_dotenv()

# Create a base class for the additional layers
# The additional layers are used in both the Lease and Sale pages, so we can use inheritance to avoid code duplication
class BaseClass:
    oil_well_data: ClassVar[Optional[Any]] = None

    @classmethod
    def load_geojson_data(cls, filepath: str = 'assets/datasets/oil_well_optimized.geojson') -> Any:
        """
        Loads GeoJSON data from a file, implementing lazy loading to avoid reloading 
        if the data is already loaded.

        Args:
            filepath (str): Path to the GeoJSON file. Defaults to 'assets/datasets/oil_well_optimized.geojson'.

        Returns:
            Any: The loaded GeoJSON data.
        """
        if cls.oil_well_data is None:
            with open(filepath, 'r') as f:
                cls.oil_well_data = json.load(f)
        return cls.oil_well_data

    @classmethod
    def create_oil_well_geojson_layer(cls) -> dl.GeoJSON:
        """
        Creates a Dash Leaflet GeoJSON layer with oil well data.

        Returns:
            dl.GeoJSON: A Dash Leaflet GeoJSON component.
        """
        ns = Namespace("myNamespace", "mySubNamespace")
        return dl.GeoJSON(
            id=str(uuid.uuid4()),
            url='assets/datasets/oil_well_optimized.geojson',
            cluster=True,
            zoomToBoundsOnClick=True,
            superClusterOptions={
                'radius': 160,
                'maxClusterRadius': 40,
                'minZoom': 3,
            },
            options=dict(
                pointToLayer=ns("drawOilIcon")
            )
        )

    def create_crime_layer(cls) -> dl.GeoJSON:
        """
        Creates a new Dash Leaflet GeoJSON layer with crime data from the past year.

        Returns:
            dl.GeoJSON: A Dash Leaflet GeoJSON component.
        """
        base_url = "https://data.lacity.org/resource/2nrs-mtv8.geojson"
        # Parse the base_url to get the domain and dataset identifier
        parsed_url = urlparse(base_url)
        domain = parsed_url.netloc
        dataset_id = parsed_url.path.split('/')[-1].split('.')[0]
        print(domain, dataset_id)

        # Create a Socrata client
        client = Socrata(domain, os.getenv('SOCRATA_APP_TOKEN'))

        # Calculate the date range for the past year
        today = datetime.now()
        one_year_ago = today - timedelta(days=365)

        # Format the dates in the required format
        today_str = today.strftime('%Y-%m-%dT%H:%M:%S')
        one_year_ago_str = one_year_ago.strftime('%Y-%m-%dT%H:%M:%S')

        # Construct the query
        query = (
            f"date_occ between '{one_year_ago_str}' and '{today_str}'"
        )

        # Fetch the data
        data = client.get(
            dataset_id, 
            where=query, 
            limit=75000, 
            select="dr_no, date_occ, time_occ, crm_cd_desc, vict_age, vict_sex, premis_desc, weapon_desc, status_desc, lat, lon"
        )

        # Check if the data is already in GeoJSON format
        if not ('type' in data and 'features' in data):
            data = convert_to_geojson(data)
        
        return dl.GeoJSON(
            data=data,
            id=str(uuid.uuid4()),
            cluster=True,
            zoomToBoundsOnClick=True,
            superClusterOptions={
                'radius': 160,
                'maxClusterRadius': 40,
                'minZoom': 3,
            },
            options=dict(
                pointToLayer=Namespace("myNamespace", "mySubNamespace")("drawCrimeIcon")
            )
        )