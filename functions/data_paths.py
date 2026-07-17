"""Canonical filesystem locations for application data artifacts."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

RUNTIME_DIR = DATA_DIR / "runtime"
SOURCE_DIR = DATA_DIR / "sources"
DERIVED_DIR = DATA_DIR / "derived"
CACHE_DIR = DATA_DIR / "cache"

LARENTALS_DB_PATH = RUNTIME_DIR / "larentals.db"

BROADBAND_SOURCE_DIR = SOURCE_DIR / "broadband"
EDUCATION_SOURCE_DIR = SOURCE_DIR / "education"
GEOGRAPHY_SOURCE_DIR = SOURCE_DIR / "geography"

CA_BROADBAND_GEOPACKAGE_PATH = BROADBAND_SOURCE_DIR / "ca_broadband_geopackage.gpkg"
CA_PUBLIC_SCHOOLS_GPKG_PATH = EDUCATION_SOURCE_DIR / "california_public_schools_2024_25.gpkg"
CA_SCHOOL_DISTRICTS_GEOJSON_PATH = EDUCATION_SOURCE_DIR / "california_school_district_areas_2024_25.geojson"
ZIP_PLACE_CROSSWALK_PATH = GEOGRAPHY_SOURCE_DIR / "ZIP_COUNTY_092025.csv"
LA_CITY_BOUNDARY_PATH = GEOGRAPHY_SOURCE_DIR / "la_city_boundary.geojson"
LA_COUNTY_ZIP_CODES_PATH = GEOGRAPHY_SOURCE_DIR / "la_county_zip_codes.geojson"

LAYER_DIR = DERIVED_DIR / "layers"
LOOKUP_DIR = DERIVED_DIR / "lookups"

ALPR_CAMERAS_PATH = LAYER_DIR / "alpr_cameras.geojson.gz"
BREAKFAST_BURRITOS_PATH = LAYER_DIR / "breakfast_burritos.geojson"
FARMERS_MARKETS_PATH = LAYER_DIR / "farmers_markets.geojson"
LAHD_PROPERTY_HEATMAP_PATH = LAYER_DIR / "lahd_property_heatmap.json.gz"
OIL_WELLS_PATH = LAYER_DIR / "oil_wells.geojson"
PARKING_TICKETS_HEATMAP_PATH = LAYER_DIR / "parking_tickets_heatmap_2025.json.gz"
SCHOOLS_SOCAL_PATH = LAYER_DIR / "schools_socal.geojson"
SOCAL_SERVICE_AREA_ZIP_CODES_PATH = LAYER_DIR / "socal_service_area_zip_codes.geojson"
SUPERMARKETS_PATH = LAYER_DIR / "supermarkets_and_grocery_stores.geojson"
LAHD_PROPERTY_LOOKUP_PATH = LOOKUP_DIR / "lahd_property_lookup.json.gz"
RSO_PROPERTY_LOOKUP_PATH = LOOKUP_DIR / "rso_property_lookup.json.gz"

LAHD_PROPERTY_GEOCODE_CACHE_PATH = CACHE_DIR / "lahd_property_geocode_cache.json"
SANTA_MONICA_SUPERMARKETS_GEOCODE_CACHE_PATH = CACHE_DIR / "santa_monica_supermarkets_geocode_cache.json"
