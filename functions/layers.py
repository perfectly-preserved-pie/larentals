from dash_extensions.javascript import Namespace
from dotenv import load_dotenv
from loguru import logger
from typing import Any, ClassVar, Optional
import dash_leaflet as dl
import json
import time
import uuid
import traceback

load_dotenv()

# Create a base class for the additional layers
# The additional layers are used in both the Lease and Sale pages, so we can use inheritance to avoid code duplication
class BaseClass:
    oil_well_data: ClassVar[Optional[Any]] = None
    crime_data: ClassVar[Optional[Any]] = None

    @classmethod
    def load_geojson_data(cls, filepath: str, dataset: str) -> Any:
        """
        Loads GeoJSON data from a file, implementing lazy loading to avoid reloading 
        if the data is already loaded. Logs the duration of the loading process.

        Args:
            filepath (str): Path to the GeoJSON file.
            dataset (str): The dataset to load ('oil_well' or 'crime').

        Returns:
            Any: The loaded GeoJSON data.
        """
        logger.debug(f"load_geojson_data called from:\n{traceback.format_stack()}")

        start_time = time.time()  # Start timing
        if dataset == 'oil_well' and cls.oil_well_data is None:
            with open(filepath, 'r') as f:
                cls.oil_well_data = json.load(f)
                duration = time.time() - start_time  # Calculate duration
                logger.info(f"Loaded 'oil_well' dataset in {duration:.2f} seconds.")
            return cls.oil_well_data
        elif dataset == 'crime' and cls.crime_data is None:
            with open(filepath, 'r') as f:
                cls.crime_data = json.load(f)
                duration = time.time() - start_time  # Calculate duration
                logger.info(f"Loaded 'crime' dataset in {duration:.2f} seconds.")
            return cls.crime_data
        elif dataset not in ['oil_well', 'crime']:
            raise ValueError(f"Invalid dataset: {dataset}. Expected 'oil_well' or 'crime'.")
        else:  # If data is already loaded, log that instead of loading time
            logger.info(f"'{dataset}' dataset already loaded; skipping reload.")

        # If data was previously loaded, we didn't measure loading time
        if dataset == 'oil_well':
            return cls.oil_well_data
        elif dataset == 'crime':
            return cls.crime_data

    @classmethod
    def create_oil_well_geojson_layer(cls) -> dl.GeoJSON:
        """
        Creates a Dash Leaflet GeoJSON layer with oil well data.

        Returns:
            dl.GeoJSON: A Dash Leaflet GeoJSON component.
        """
        ns = Namespace("myNamespace", "mySubNamespace")
        #if cls.oil_well_data is None:
        #    cls.load_geojson_data(filepath='assets/datasets/oil_well_optimized.geojson', dataset='oil_well')
        return dl.GeoJSON(
            id=str(uuid.uuid4()),
            #data=cls.oil_well_data,
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
        #if cls.crime_data is None:
        #    cls.load_geojson_data(filepath='assets/datasets/crime.geojson', dataset='crime')
        return dl.GeoJSON(
            id=str(uuid.uuid4()),
            #data=cls.crime_data,
            url='assets/datasets/crime.geojson',
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
