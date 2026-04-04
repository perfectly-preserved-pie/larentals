import geopandas as gpd
from urllib.parse import parse_qs, urlparse

from functions.layers import (
    DEFAULT_SCHOOL_LAYER_GEOJSON_PATH,
    DEFAULT_SCHOOL_LAYER_GPKG_PATH,
    build_school_layer_geojson_from_gdf,
    build_school_preview_url,
    filter_school_layer_geojson,
)
from functions.listing_enrichment_utils import DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL, DEFAULT_REGION_NAME
from scripts.build_school_layer_geojson import parse_args as parse_school_layer_args


def test_school_layer_builder_parse_args_use_geopackage_defaults() -> None:
    args = parse_school_layer_args([])

    assert args.source == DEFAULT_CA_PUBLIC_SCHOOLS_GPKG_URL
    assert args.download_path == str(DEFAULT_SCHOOL_LAYER_GPKG_PATH)
    assert args.output == str(DEFAULT_SCHOOL_LAYER_GEOJSON_PATH)
    assert args.region == DEFAULT_REGION_NAME
    assert args.force_download is False


def test_build_school_layer_geojson_from_gdf_filters_closed_schools_and_normalizes_fields() -> None:
    schools = gpd.GeoDataFrame(
        {
            "SchoolName": ["Franklin High", "Closed Campus"],
            "DistrictName": ["Los Angeles Unified", "Los Angeles Unified"],
            "SchoolType": ["High", "High"],
            "SchoolLevel": ["High", "High"],
            "GradeLow": ["09", "09"],
            "GradeHigh": ["12", "12"],
            "Charter": ["N", "Y"],
            "FundingType": ["District", "District"],
            "Magnet": ["Y", "N"],
            "TitleIStatus": ["Y", "N"],
            "AssistStatusESSA": ["ATSI", "No Status"],
            "DASS": ["N", "Y"],
            "Status": ["Active", "Closed"],
            "OpenDate": ["2006-08-28T00:00:00.0Z", "2001-07-01T00:00:00.0Z"],
            "Street": ["820 N Ave 54", "123 Closed St"],
            "City": ["Los Angeles", "Los Angeles"],
            "Zip": ["90042", "90001"],
            "State": ["CA", "CA"],
            "Locale": ["11 - City, Large", "11 - City, Large"],
            "Website": ["franklinhs.example.edu", None],
            "EnrollTotal": [1800, 900],
            "ELpct": [7.2, 4.0],
            "FRPMpct": [65.1, 30.0],
            "SEDpct": [71.4, 25.0],
            "SWDpct": [12.3, 8.0],
        },
        geometry=gpd.points_from_xy([-118.204, -118.3], [34.112, 34.01]),
        crs="EPSG:4326",
    )

    geojson = build_school_layer_geojson_from_gdf(schools)

    assert len(geojson["features"]) == 1
    properties = geojson["features"][0]["properties"]
    assert properties["school_name"] == "Franklin High"
    assert properties["grade_span_display"] == "9-12"
    assert properties["grade_bands"] == ["High"]
    assert properties["magnet_label"] == "Yes"
    assert properties["title_i_label"] == "Yes"
    assert properties["assist_status_essa"] == "ATSI"
    assert properties["dass_flag"] == "No"
    assert properties["open_date"] == "2006-08-28"
    assert properties["website_url"] == "https://franklinhs.example.edu"


def test_build_school_layer_geojson_from_gdf_reprojects_coordinates_to_wgs84() -> None:
    schools = gpd.GeoDataFrame(
        {
            "SchoolName": ["Franklin High"],
            "DistrictName": ["Los Angeles Unified"],
            "SchoolType": ["High"],
            "SchoolLevel": ["High"],
            "GradeLow": ["09"],
            "GradeHigh": ["12"],
            "Charter": ["N"],
            "FundingType": ["District"],
            "Magnet": ["N"],
            "TitleIStatus": ["Y"],
            "AssistStatusESSA": ["No Status"],
            "DASS": ["N"],
            "Status": ["Active"],
            "OpenDate": ["2006-08-28T00:00:00.0Z"],
        },
        geometry=gpd.points_from_xy([-118.204], [34.112]),
        crs="EPSG:4326",
    ).to_crs("EPSG:3857")

    geojson = build_school_layer_geojson_from_gdf(schools)

    coordinates = geojson["features"][0]["geometry"]["coordinates"]
    assert round(coordinates[0], 3) == -118.204
    assert round(coordinates[1], 3) == 34.112


def test_build_school_preview_url_points_to_world_imagery_export() -> None:
    url = build_school_preview_url(-118.2437, 34.0522)

    assert url is not None
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.netloc == "services.arcgisonline.com"
    assert parsed.path.endswith("/World_Imagery/MapServer/export")
    assert params["bboxSR"] == ["4326"]
    assert params["imageSR"] == ["4326"]
    assert params["f"] == ["image"]


def test_filter_school_layer_geojson_respects_search_bands_flags_and_enrollment() -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "school_name": "Franklin High",
                    "district_name": "Los Angeles Unified",
                    "school_level": "High",
                    "grade_bands": ["High"],
                    "funding_type": "Directly funded",
                    "assist_status_essa": "ATSI",
                    "enrollment_total": 1800,
                    "charter_flag": 0,
                    "magnet_flag": 1,
                    "title_i_flag": 1,
                    "search_text": "franklin high los angeles unified",
                },
                "geometry": {"type": "Point", "coordinates": [-118.2, 34.1]},
            },
            {
                "type": "Feature",
                "properties": {
                    "school_name": "Maple Elementary",
                    "district_name": "Burbank Unified",
                    "school_level": "Elementary",
                    "grade_bands": ["Elementary"],
                    "funding_type": "Locally funded",
                    "assist_status_essa": "No Status",
                    "enrollment_total": 450,
                    "charter_flag": 1,
                    "magnet_flag": 0,
                    "title_i_flag": 0,
                    "search_text": "maple elementary burbank unified",
                },
                "geometry": {"type": "Point", "coordinates": [-118.3, 34.2]},
            },
            {
                "type": "Feature",
                "properties": {
                    "school_name": "Pasadena Secondary Academy",
                    "district_name": "Pasadena Unified",
                    "school_level": "Secondary",
                    "grade_bands": ["Middle", "High"],
                    "funding_type": "Directly funded",
                    "assist_status_essa": "TSI",
                    "enrollment_total": None,
                    "charter_flag": 0,
                    "magnet_flag": 0,
                    "title_i_flag": 1,
                    "search_text": "pasadena secondary academy pasadena unified",
                },
                "geometry": {"type": "Point", "coordinates": [-118.1, 34.15]},
            },
        ],
    }

    filtered = filter_school_layer_geojson(
        geojson,
        search_text="unified",
        school_levels=["High", "Secondary"],
        grade_bands=["High"],
        funding_types=["Directly funded"],
        assist_statuses=["ATSI", "TSI"],
        enrollment_range=[0, 3000],
        charter_only=False,
        magnet_only=True,
        title_i_only=True,
    )

    assert [feature["properties"]["school_name"] for feature in filtered["features"]] == [
        "Franklin High"
    ]


def test_filter_school_layer_geojson_keeps_unknown_enrollment_at_default_range() -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "school_name": "Pasadena Secondary Academy",
                    "district_name": "Pasadena Unified",
                    "school_level": "Secondary",
                    "grade_bands": ["Middle", "High"],
                    "funding_type": "Directly funded",
                    "assist_status_essa": "TSI",
                    "enrollment_total": None,
                    "charter_flag": 0,
                    "magnet_flag": 0,
                    "title_i_flag": 1,
                    "search_text": "pasadena secondary academy pasadena unified",
                },
                "geometry": {"type": "Point", "coordinates": [-118.1, 34.15]},
            }
        ],
    }

    filtered = filter_school_layer_geojson(
        geojson,
        enrollment_range=[0, 12000],
        title_i_only=True,
    )

    assert len(filtered["features"]) == 1


def test_filter_school_layer_geojson_treats_all_grade_bands_as_unfiltered() -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "school_name": "Franklin High",
                    "district_name": "Los Angeles Unified",
                    "school_level": "High",
                    "grade_bands": ["High"],
                    "funding_type": "Directly funded",
                    "assist_status_essa": "No Status",
                    "search_text": "franklin high los angeles unified",
                },
                "geometry": {"type": "Point", "coordinates": [-118.2, 34.1]},
            },
            {
                "type": "Feature",
                "properties": {
                    "school_name": "Maple Elementary",
                    "district_name": "Burbank Unified",
                    "school_level": "Elementary",
                    "grade_bands": ["Elementary"],
                    "funding_type": "Locally funded",
                    "assist_status_essa": "ATSI",
                    "search_text": "maple elementary burbank unified",
                },
                "geometry": {"type": "Point", "coordinates": [-118.3, 34.2]},
            },
            {
                "type": "Feature",
                "properties": {
                    "school_name": "Adult Transition Center",
                    "district_name": "Pasadena Unified",
                    "school_level": "Adult Education",
                    "grade_bands": [],
                    "funding_type": "Directly funded",
                    "assist_status_essa": "No Status",
                    "search_text": "adult transition center pasadena unified",
                },
                "geometry": {"type": "Point", "coordinates": [-118.1, 34.15]},
            },
        ],
    }

    filtered = filter_school_layer_geojson(
        geojson,
        grade_bands=["Elementary", "Middle", "High"],
    )

    assert [feature["properties"]["school_name"] for feature in filtered["features"]] == [
        "Franklin High",
        "Maple Elementary",
        "Adult Transition Center",
    ]
