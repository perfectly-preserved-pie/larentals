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
    crime_data: ClassVar[Optional[Any]] = None

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
        Creates a Dash Leaflet GeoJSON layer with crime data.

        Returns:
            dl.GeoJSON: A Dash Leaflet GeoJSON component.
        """
        ns = Namespace("myNamespace", "mySubNamespace")
        return dl.GeoJSON(
            id=str(uuid.uuid4()),
            url='/assets/datasets/crime.geojson',
            cluster=True,
            zoomToBoundsOnClick=True,
            superClusterOptions={
                'radius': 160,
                'maxClusterRadius': 40,
                'minZoom': 3,
            },
            options=dict(
                pointToLayer=ns("drawCrimeIcon")
            )
    )
