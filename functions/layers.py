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
class LayersClass:
    oil_well_data: ClassVar[Optional[Any]] = None
    crime_data: ClassVar[Optional[Any]] = None
    farmers_markets_data: ClassVar[Optional[Any]] = None

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
        #logger.debug(f"load_geojson_data called from:\n{traceback.format_stack()}")

        dataset_attrs = {
            'oil_well': 'oil_well_data',
            'crime': 'crime_data',
            'farmers_markets': 'farmers_markets_data',
        }
        data_attr = dataset_attrs.get(dataset)
        if data_attr is None:
            raise ValueError(
                f"Invalid dataset: {dataset}. Expected one of {sorted(dataset_attrs)}."
            )

        cached_data = getattr(cls, data_attr)
        if cached_data is not None:
            logger.info(f"'{dataset}' dataset already loaded; skipping reload.")
            return cached_data

        start_time = time.time()
        with open(filepath, 'r') as f:
            loaded_data = json.load(f)

        setattr(cls, data_attr, loaded_data)
        duration = time.time() - start_time
        logger.info(f"Loaded '{dataset}' dataset in {duration:.2f} seconds.")
        return loaded_data

    @classmethod
    def create_oil_well_geojson_layer(cls) -> dl.GeoJSON:
        """
        Creates a Dash Leaflet GeoJSON layer with oil well data.

        Returns:
            dl.GeoJSON: A Dash Leaflet GeoJSON component.
        """
        ns = Namespace("myNamespace", "mySubNamespace")
        if cls.oil_well_data is None:
            cls.load_geojson_data(filepath='assets/datasets/oil_well_optimized.geojson', dataset='oil_well')
        return dl.GeoJSON(
            id=str(uuid.uuid4()),
            data=cls.oil_well_data,
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
    
    @classmethod
    def create_farmers_markets_layer(cls) -> dl.GeoJSON:
        ns = Namespace("myNamespace", "mySubNamespace")
        if cls.farmers_markets_data is None:
            cls.load_geojson_data(filepath='assets/datasets/farmers_markets.geojson', dataset='farmers_markets')
        return dl.GeoJSON(
            id=str(uuid.uuid4()),
            data=cls.farmers_markets_data,
            cluster=True,
            zoomToBoundsOnClick=True,
            bubblingMouseEvents=False,
            pointToLayer=ns("drawFarmersMarketIcon"),
            superClusterOptions={'radius':160,'maxClusterRadius':40,'minZoom':3},
        )

    def create_crime_layer(cls) -> dl.GeoJSON:
        """
        Creates a Dash Leaflet GeoJSON layer with crime data.

        Returns:
            dl.GeoJSON: A Dash Leaflet GeoJSON component.
        """
        ns = Namespace("myNamespace", "mySubNamespace")
        if cls.crime_data is None:
            cls.load_geojson_data(filepath='assets/datasets/crime.geojson', dataset='crime')
        return dl.GeoJSON(
            id=str(uuid.uuid4()),
            data=cls.crime_data,
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
