from dataclasses import dataclass
from dash import ClientsideFunction, clientside_callback, no_update
from dash.dependencies import Input, Output, State
from dash_extensions.javascript import Namespace
from dotenv import load_dotenv
from functions.parking_tickets import build_parking_tickets_heat_geojson
from loguru import logger
from typing import Any, Callable, ClassVar, Optional, Sequence, TypedDict, TypeAlias
import dash_leaflet as dl
import geopandas as gpd
import json
from pathlib import Path
import pandas as pd
import re
import time
import uuid
from urllib.parse import urlencode

load_dotenv()

GeoJsonDict: TypeAlias = dict[str, Any]

DEFAULT_SCHOOL_LAYER_GEOJSON_PATH = Path("assets/datasets/schools_socal.geojson")
DEFAULT_SCHOOL_LAYER_GPKG_PATH = Path("assets/datasets/california_public_schools_2024_25.gpkg")
DEFAULT_SCHOOL_LAYER_ENROLLMENT_MAX = 12000
SCHOOL_LAYER_CAMPUS_CONFIGURATION_OPTIONS: tuple[str, ...] = (
    "PK-5",
    "PK-6",
    "PK-8",
    "K-2",
    "K-5",
    "K-6",
    "K-8",
    "6-8",
    "7-8",
    "9-12",
    "10-12",
    "6-12",
    "7-12",
    "K-12",
    "PK-12",
)
SCHOOL_LAYER_GRADE_BAND_OPTIONS: tuple[str, ...] = ("Elementary", "Middle", "High")
SCHOOL_LAYER_FUNDING_TYPE_OPTIONS: tuple[str, ...] = (
    "Directly funded",
    "Locally funded",
)
SCHOOL_LAYER_LEVEL_OPTIONS: tuple[str, ...] = (
    "Adult Education",
    "Not reported",
    "Other",
    "Preschool",
    "Secondary",
)

class LazyLayerGeoJsonId(TypedDict):
    """
    Pattern-matching id payload for lazy-loaded optional GeoJSON layers.

    Attributes:
        type: Dash pattern-matching component type.
        page: Page key owning the layer, such as "lease" or "buy".
        layer: Internal layer key used to resolve its config.
    """
    type: str
    page: str
    layer: str

@dataclass(frozen=True)
class LayerConfig:
    """
    Declarative configuration for an optional or reusable GeoJSON overlay.

    Attributes:
        name: Display name shown in `dl.LayersControl`.
        dataset: Internal cache key for the loaded GeoJSON payload.
        filepath: Optional on-disk path to the GeoJSON source file.
        loader: Optional callable used to build or fetch GeoJSON data dynamically.
        point_to_layer: JavaScript namespace function used to render point features.
        cluster_to_layer: Optional JavaScript namespace function used to render
            clustered point features when superclustering is enabled.
        cluster: Whether the layer should use Dash Leaflet marker clustering.
        zoom_to_bounds_on_click: Whether clicking a feature/cluster should fit its bounds.
        bubbling_mouse_events: Whether layer mouse events should bubble to the map.
        supercluster_options: Optional supercluster configuration passed to `dl.GeoJSON`.
        valid_bounds: Optional lon/lat bounding box used to discard clearly invalid points.
        cache_ttl_seconds: Optional TTL for in-process layer cache entries. `None`
            means cache indefinitely for the current worker process.
    """
    name: str
    dataset: str
    point_to_layer: str
    cluster_to_layer: str | None = None
    filepath: str | None = None
    loader: Callable[[], GeoJsonDict] | None = None
    cluster: bool = True
    zoom_to_bounds_on_click: bool = True
    bubbling_mouse_events: bool = False
    supercluster_options: Optional[dict[str, Any]] = None
    valid_bounds: Optional[tuple[float, float, float, float]] = None
    cache_ttl_seconds: int | None = None


def _normalize_school_text(value: object) -> str | None:
    """
    Return a trimmed text value, or ``None`` when the source is blank.
    """
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized or normalized.lower() in {"none", "null", "nan"}:
        return None
    return normalized


def _normalize_school_flag(value: object) -> int | None:
    """
    Normalize common `Y`/`N` flag values into integers for GeoJSON properties.
    """
    if value is None or pd.isna(value):
        return None

    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return 1
        if value == 0:
            return 0

    normalized = _normalize_school_text(value)
    if normalized is None:
        return None

    upper = normalized.upper()
    if upper in {"Y", "YES", "TRUE", "1"}:
        return 1
    if upper in {"N", "NO", "FALSE", "0"}:
        return 0
    return None


def _school_flag_label(value: object) -> str:
    """
    Return a popup-friendly label for a normalized school flag.
    """
    normalized = _normalize_school_flag(value)
    if normalized == 1:
        return "Yes"
    if normalized == 0:
        return "No"
    return "Unknown"


def _parse_school_grade_token(value: object) -> int | None:
    """
    Convert a grade token like `TK`, `K`, `06`, or `12` into a sortable integer.
    """
    normalized = _normalize_school_text(value)
    if normalized is None:
        return None

    token = normalized.upper()
    if token in {"P", "PK", "PS", "PREK"}:
        return -1
    if token in {"TK", "K", "KG"}:
        return 0
    if token.isdigit():
        return int(token)
    return None


def _format_school_grade_value(value: int | None) -> str | None:
    """
    Convert a numeric grade token back into a display label.
    """
    if value is None:
        return None
    if value == -1:
        return "PK"
    if value == 0:
        return "K"
    return str(int(value))


def _build_school_grade_bands(low_grade: object, high_grade: object) -> list[str]:
    """
    Return the canonical grade-band labels touched by a school.
    """
    low = _parse_school_grade_token(low_grade)
    high = _parse_school_grade_token(high_grade)
    if low is None or high is None:
        return []

    lower, upper = min(low, high), max(low, high)
    bands: list[str] = []
    if lower <= 5 and upper >= 0:
        bands.append("Elementary")
    if lower <= 8 and upper >= 6:
        bands.append("Middle")
    if lower <= 12 and upper >= 9:
        bands.append("High")
    return bands


def _build_school_grade_span_display(low_grade: object, high_grade: object) -> str | None:
    """
    Build a compact popup display value like `K-5` or `6-12`.
    """
    low = _parse_school_grade_token(low_grade)
    high = _parse_school_grade_token(high_grade)
    if low is None or high is None:
        return None

    low_label = _format_school_grade_value(min(low, high))
    high_label = _format_school_grade_value(max(low, high))
    if low_label is None or high_label is None:
        return None
    if low_label == high_label:
        return low_label
    return f"{low_label}-{high_label}"


def _normalize_school_url(value: object) -> str | None:
    """
    Normalize a school website into a browser-usable URL when possible.
    """
    normalized = _normalize_school_text(value)
    if normalized is None:
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*://", normalized, flags=re.IGNORECASE):
        return normalized
    return f"https://{normalized.lstrip('/')}"


def _normalize_school_date(value: object) -> str | None:
    """
    Normalize source dates into a compact YYYY-MM-DD display string.
    """
    if value is None or pd.isna(value):
        return None

    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")

    normalized = _normalize_school_text(value)
    if normalized is None:
        return None
    return normalized.split("T")[0]


def _school_grade_offered(value: object) -> bool:
    """
    Determine whether a grade-specific source field indicates the grade is offered.
    """
    if value is None or pd.isna(value):
        return False

    normalized = _normalize_school_text(value)
    if normalized is None:
        return False

    if normalized.casefold() in {"y", "yes", "true"}:
        return True

    numeric_value = pd.to_numeric([normalized], errors="coerce")[0]
    if pd.notna(numeric_value):
        return float(numeric_value) > 0

    return False


def _school_is_recently_opened(value: object) -> bool:
    """
    Flag schools with a source open date on or after 2018-01-01.
    """
    if value is None or pd.isna(value):
        return False

    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return False

    return bool(parsed >= pd.Timestamp("2018-01-01", tz="UTC"))


def build_school_preview_url(longitude: float | None, latitude: float | None) -> str | None:
    """
    Build a public ArcGIS World Imagery preview around a school point.
    """
    if longitude is None or latitude is None:
        return None

    pad = 0.0018
    params = urlencode(
        {
            "bbox": f"{longitude - pad:.6f},{latitude - pad:.6f},{longitude + pad:.6f},{latitude + pad:.6f}",
            "bboxSR": 4326,
            "imageSR": 4326,
            "size": "640,360",
            "format": "jpg",
            "transparent": "false",
            "f": "image",
        }
    )
    return (
        "https://services.arcgisonline.com/ArcGIS/rest/services/"
        f"World_Imagery/MapServer/export?{params}"
    )


def build_school_layer_geojson_from_gdf(schools: gpd.GeoDataFrame) -> GeoJsonDict:
    """
    Normalize a public-schools GeoDataFrame into the final map-layer GeoJSON payload.
    """
    if schools.empty:
        return {"type": "FeatureCollection", "features": []}
    if schools.crs is None:
        raise ValueError("School layer GeoDataFrame must declare a CRS.")

    working = schools.to_crs("EPSG:4326").copy()

    expected_columns = [
        "SchoolName",
        "DistrictName",
        "SchoolType",
        "SchoolLevel",
        "GradeLow",
        "GradeHigh",
        "GradeTK",
        "GradeKG",
        "Charter",
        "FundingType",
        "Magnet",
        "TitleIStatus",
        "Status",
        "OpenDate",
        "Street",
        "City",
        "Zip",
        "State",
        "Locale",
        "Website",
        "EnrollTotal",
        "ELpct",
        "FRPMpct",
        "SEDpct",
        "SWDpct",
    ]
    for column_name in expected_columns:
        if column_name not in working.columns:
            working[column_name] = None

    if "Status" in working.columns:
        active_mask = (
            working["Status"]
            .astype("string")
            .str.strip()
            .str.casefold()
            .eq("active")
        )
        working = working[active_mask.fillna(False)].copy()

    working = working[working.geometry.notna()].copy()
    if working.empty:
        return {"type": "FeatureCollection", "features": []}

    working["school_name"] = working["SchoolName"].map(_normalize_school_text)
    working = working[working["school_name"].notna()].copy()
    working["district_name"] = working["DistrictName"].map(_normalize_school_text)
    working["school_type"] = working["SchoolType"].map(_normalize_school_text)
    working["school_level"] = working["SchoolLevel"].map(_normalize_school_text)
    working["grade_span_display"] = working.apply(
        lambda row: _build_school_grade_span_display(row.get("GradeLow"), row.get("GradeHigh")),
        axis=1,
    )
    working["grade_bands"] = working.apply(
        lambda row: _build_school_grade_bands(row.get("GradeLow"), row.get("GradeHigh")),
        axis=1,
    )
    working["charter_flag"] = working["Charter"].map(_normalize_school_flag)
    working["magnet_flag"] = working["Magnet"].map(_normalize_school_flag)
    working["title_i_flag"] = working["TitleIStatus"].map(_normalize_school_flag)
    working["charter_label"] = working["Charter"].map(_school_flag_label)
    working["magnet_label"] = working["Magnet"].map(_school_flag_label)
    working["title_i_label"] = working["TitleIStatus"].map(_school_flag_label)
    working["offers_tk_flag"] = working["GradeTK"].map(_school_grade_offered)
    working["offers_kindergarten_flag"] = working["GradeKG"].map(_school_grade_offered)
    working["funding_type"] = working["FundingType"].map(_normalize_school_text)
    working["open_date"] = working["OpenDate"].map(_normalize_school_date)
    working["recently_opened_flag"] = working["OpenDate"].map(_school_is_recently_opened)
    working["locale"] = working["Locale"].map(_normalize_school_text)
    working["website_url"] = working["Website"].map(_normalize_school_url)
    working["street"] = working["Street"].map(_normalize_school_text)
    working["city"] = working["City"].map(_normalize_school_text)
    working["zip_code"] = working["Zip"].map(_normalize_school_text)
    working["state"] = working["State"].map(_normalize_school_text)
    working["full_address"] = working.apply(
        lambda row: ", ".join(
            part
            for part in (
                row.get("street"),
                row.get("city"),
                row.get("state"),
                row.get("zip_code"),
            )
            if part
        ),
        axis=1,
    )
    working["enrollment_total"] = pd.to_numeric(working["EnrollTotal"], errors="coerce").round()
    working["el_pct"] = pd.to_numeric(working["ELpct"], errors="coerce")
    working["frpm_pct"] = pd.to_numeric(working["FRPMpct"], errors="coerce")
    working["sed_pct"] = pd.to_numeric(working["SEDpct"], errors="coerce")
    working["swd_pct"] = pd.to_numeric(working["SWDpct"], errors="coerce")
    working["latitude"] = working.geometry.y.round(6)
    working["longitude"] = working.geometry.x.round(6)
    working["school_preview_url"] = working.apply(
        lambda row: build_school_preview_url(
            float(row["longitude"]) if pd.notna(row["longitude"]) else None,
            float(row["latitude"]) if pd.notna(row["latitude"]) else None,
        ),
        axis=1,
    )
    working["search_text"] = working.apply(
        lambda row: " ".join(
            part.lower()
            for part in (
                row.get("school_name"),
                row.get("district_name"),
                row.get("city"),
                row.get("full_address"),
            )
            if part
        ),
        axis=1,
    )

    keep_columns = [
        "school_name",
        "district_name",
        "school_type",
        "school_level",
        "grade_span_display",
        "grade_bands",
        "charter_flag",
        "magnet_flag",
        "title_i_flag",
        "charter_label",
        "magnet_label",
        "title_i_label",
        "offers_tk_flag",
        "offers_kindergarten_flag",
        "funding_type",
        "open_date",
        "recently_opened_flag",
        "locale",
        "website_url",
        "full_address",
        "city",
        "zip_code",
        "enrollment_total",
        "el_pct",
        "frpm_pct",
        "sed_pct",
        "swd_pct",
        "latitude",
        "longitude",
        "school_preview_url",
        "search_text",
        "geometry",
    ]
    return json.loads(working[keep_columns].to_json(drop_id=True))


def load_school_layer_geojson_artifact(
    path: str | Path = DEFAULT_SCHOOL_LAYER_GEOJSON_PATH,
) -> GeoJsonDict:
    """
    Load the baked school-layer GeoJSON artifact from disk.
    """
    artifact_path = Path(path)
    if not artifact_path.exists():
        logger.warning(
            "School layer artifact is missing at {}. Run the school-layer builder first.",
            artifact_path,
        )
        return {"type": "FeatureCollection", "features": []}

    with artifact_path.open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)

    features = payload.get("features")
    if not isinstance(features, list):
        logger.warning("School layer artifact at {} is not a valid FeatureCollection.", artifact_path)
        return {"type": "FeatureCollection", "features": []}

    return payload


def filter_school_layer_geojson(
    geojson_data: GeoJsonDict | None,
    *,
    search_text: str | None = None,
    school_levels: Sequence[str] | None = None,
    grade_bands: Sequence[str] | None = None,
    campus_configurations: Sequence[str] | None = None,
    early_grades: Sequence[str] | None = None,
    funding_types: Sequence[str] | None = None,
    enrollment_range: Sequence[float] | None = None,
    charter_only: bool = False,
    magnet_only: bool = False,
    title_i_only: bool = False,
    recently_opened_only: bool = False,
) -> GeoJsonDict:
    """
    Filter the cached school layer payload for the map-only school controls.
    """
    if not geojson_data:
        return {"type": "FeatureCollection", "features": []}

    normalized_search = (_normalize_school_text(search_text) or "").casefold()
    selected_levels = {
        value.strip().casefold()
        for value in (school_levels or [])
        if isinstance(value, str) and value.strip()
    }
    selected_bands = {
        value.strip().casefold()
        for value in (grade_bands or [])
        if isinstance(value, str) and value.strip()
    }
    selected_campus_configurations = {
        value.strip().casefold()
        for value in (campus_configurations or [])
        if isinstance(value, str) and value.strip()
    }
    all_grade_bands = {
        value.strip().casefold()
        for value in SCHOOL_LAYER_GRADE_BAND_OPTIONS
    }
    if selected_bands == all_grade_bands:
        selected_bands = set()
    selected_early_grades = {
        value.strip().casefold()
        for value in (early_grades or [])
        if isinstance(value, str) and value.strip()
    }
    selected_funding_types = {
        value.strip().casefold()
        for value in (funding_types or [])
        if isinstance(value, str) and value.strip()
    }

    range_values = list(enrollment_range or [])
    has_enrollment_filter = len(range_values) >= 2
    min_enrollment = float(range_values[0]) if has_enrollment_filter else 0.0
    max_enrollment = float(range_values[1]) if has_enrollment_filter else float(DEFAULT_SCHOOL_LAYER_ENROLLMENT_MAX)
    full_enrollment_range = (
        min_enrollment <= 0
        and max_enrollment >= DEFAULT_SCHOOL_LAYER_ENROLLMENT_MAX
    )

    filtered_features: list[GeoJsonDict] = []
    for feature in geojson_data.get("features", []):
        properties = feature.get("properties") or {}
        if normalized_search:
            haystack = str(properties.get("search_text") or "").casefold()
            if normalized_search not in haystack:
                continue

        if selected_levels:
            level_value = str(properties.get("school_level") or "").strip().casefold()
            if level_value not in selected_levels:
                continue

        if selected_bands:
            feature_bands = {
                str(value).strip().casefold()
                for value in (properties.get("grade_bands") or [])
                if value
            }
            if feature_bands.isdisjoint(selected_bands):
                continue

        if selected_campus_configurations:
            campus_configuration_value = str(
                properties.get("grade_span_display") or ""
            ).strip().casefold()
            if campus_configuration_value not in selected_campus_configurations:
                continue

        if selected_early_grades:
            matches_early_grade = False
            if "tk" in selected_early_grades and bool(properties.get("offers_tk_flag")):
                matches_early_grade = True
            if (
                "kindergarten" in selected_early_grades
                and bool(properties.get("offers_kindergarten_flag"))
            ):
                matches_early_grade = True
            if not matches_early_grade:
                continue

        if selected_funding_types:
            funding_type_value = str(properties.get("funding_type") or "").strip().casefold()
            if funding_type_value not in selected_funding_types:
                continue

        enrollment_value = properties.get("enrollment_total")
        try:
            enrollment_number = (
                float(enrollment_value)
                if enrollment_value not in (None, "", "Unknown")
                else None
            )
        except (TypeError, ValueError):
            enrollment_number = None

        if has_enrollment_filter:
            if enrollment_number is None:
                if not full_enrollment_range:
                    continue
            elif not (min_enrollment <= enrollment_number <= max_enrollment):
                continue

        if charter_only and _normalize_school_flag(properties.get("charter_flag")) != 1:
            continue
        if magnet_only and _normalize_school_flag(properties.get("magnet_flag")) != 1:
            continue
        if title_i_only and _normalize_school_flag(properties.get("title_i_flag")) != 1:
            continue
        if recently_opened_only and not bool(properties.get("recently_opened_flag")):
            continue

        filtered_features.append(feature)

    return {
        **geojson_data,
        "features": filtered_features,
    }

# Create a base class for the additional layers
# The additional layers are used in both the Lease and Sale pages, so we can use inheritance to avoid code duplication
class LayersClass:
    """
    Shared factory and lazy-loading helpers for optional map overlays.

    This class centralizes:
    - static overlay configuration
    - per-process GeoJSON caching
    - creation of `dl.GeoJSON` / `dl.Overlay` / `dl.LayersControl`
    - lazy resolution of layer data when users enable overlays
    """
    DEFAULT_SUPERCLUSTER_OPTIONS: ClassVar[dict[str, int]] = {
        'radius': 160,
        'maxClusterRadius': 40,
        'minZoom': 3,
    }
    LAYER_CONFIGS: ClassVar[dict[str, LayerConfig]] = {
        'oil_well': LayerConfig(
            name='Oil & Gas Wells',
            dataset='oil_well',
            filepath='assets/datasets/oil_wells.geojson',
            point_to_layer='drawOilIcon',
            cluster_to_layer='drawOilCluster',
            supercluster_options=DEFAULT_SUPERCLUSTER_OPTIONS,
            valid_bounds=(-125.0, -113.0, 32.0, 35.5),
        ),
        'crime': LayerConfig(
            name='Crime',
            dataset='crime',
            filepath='assets/datasets/crime.geojson',
            point_to_layer='drawCrimeIcon',
            supercluster_options=DEFAULT_SUPERCLUSTER_OPTIONS,
        ),
        'farmers_markets': LayerConfig(
            name='Farmers Markets',
            dataset='farmers_markets',
            filepath='assets/datasets/farmers_markets.geojson',
            point_to_layer='drawFarmersMarketIcon',
            bubbling_mouse_events=False,
            supercluster_options=DEFAULT_SUPERCLUSTER_OPTIONS,
        ),
        'breakfast_burritos': LayerConfig(
            name='Breakfast Burritos',
            dataset='breakfast_burritos',
            filepath='assets/datasets/breakfast_burritos.geojson',
            point_to_layer='drawBreakfastBurritoIcon',
            bubbling_mouse_events=False,
            supercluster_options=DEFAULT_SUPERCLUSTER_OPTIONS,
            valid_bounds=(-125.0, -113.0, 32.0, 35.5),
        ),
        'supermarkets_grocery': LayerConfig(
            name='Supermarkets & Grocery Stores',
            dataset='supermarkets_grocery',
            filepath='assets/datasets/supermarkets_and_grocery_stores.geojson',
            point_to_layer='drawSupermarketIcon',
            bubbling_mouse_events=False,
            supercluster_options=DEFAULT_SUPERCLUSTER_OPTIONS,
            valid_bounds=(-125.0, -113.0, 32.0, 35.5),
        ),
        'schools': LayerConfig(
            name='Schools',
            dataset='schools',
            loader=load_school_layer_geojson_artifact,
            point_to_layer='drawSchoolIcon',
            cluster_to_layer='drawSchoolCluster',
            bubbling_mouse_events=False,
            supercluster_options=DEFAULT_SUPERCLUSTER_OPTIONS,
            cache_ttl_seconds=21600,
        ),
        'parking_tickets_density': LayerConfig(
            name='Parking Tickets Heatmap (2025)',
            dataset='parking_tickets_density',
            loader=build_parking_tickets_heat_geojson,
            point_to_layer='drawParkingHeatLayer',
            cluster=False,
            zoom_to_bounds_on_click=False,
            bubbling_mouse_events=False,
            cache_ttl_seconds=3600,
        ),
    }
    geojson_cache: ClassVar[dict[str, tuple[float, GeoJsonDict]]] = {}
    filter_school_layer_geojson = staticmethod(filter_school_layer_geojson)

    @classmethod
    def get_layer_config(cls, layer_key: str) -> LayerConfig:
        """
        Return the registered layer configuration for a given layer key.

        Args:
            layer_key: Internal layer identifier, such as `"farmers_markets"`.

        Returns:
            The corresponding `LayerConfig`.

        Raises:
            ValueError: If `layer_key` is not registered in `LAYER_CONFIGS`.
        """
        try:
            return cls.LAYER_CONFIGS[layer_key]
        except KeyError as exc:
            raise ValueError(
                f"Invalid layer_key: {layer_key}. Expected one of {sorted(cls.LAYER_CONFIGS)}."
            ) from exc

    @classmethod
    def load_layer_data(cls, layer_key: str) -> GeoJsonDict:
        """
        Load a registered layer payload with simple per-process caching.

        Args:
            layer_key: Internal layer identifier, such as `"farmers_markets"`.

        Returns:
            The parsed GeoJSON object.
        """
        spec = cls.get_layer_config(layer_key)
        dataset = spec.dataset
        cached_entry = cls.geojson_cache.get(dataset)
        if cached_entry is not None:
            cached_at, cached_data = cached_entry
            if spec.cache_ttl_seconds is None or (time.time() - cached_at) < spec.cache_ttl_seconds:
                logger.info(f"'{dataset}' dataset already loaded; skipping reload.")
                return cached_data

        start_time = time.time()
        if spec.loader is not None:
            loaded_data = spec.loader()
        elif spec.filepath is not None:
            with open(spec.filepath, 'r') as f:
                loaded_data = json.load(f)
        else:
            raise ValueError(
                f"Layer '{layer_key}' is missing both filepath and loader configuration."
            )

        if spec is not None and spec.valid_bounds is not None:
            loaded_data = cls.filter_geojson_to_bounds(loaded_data, spec.valid_bounds)

        cls.geojson_cache[dataset] = (time.time(), loaded_data)
        duration = time.time() - start_time
        logger.info(f"Loaded '{dataset}' dataset in {duration:.2f} seconds.")
        return loaded_data

    @classmethod
    def get_layer_config_by_dataset(cls, dataset: str) -> LayerConfig | None:
        """
        Return the first registered layer config matching a dataset cache key.

        Args:
            dataset: Dataset/cache identifier, such as `"oil_well"`.

        Returns:
            The matching `LayerConfig`, or `None` when no config uses that dataset key.
        """
        for spec in cls.LAYER_CONFIGS.values():
            if spec.dataset == dataset:
                return spec
        return None

    @classmethod
    def filter_geojson_to_bounds(
        cls,
        geojson_data: GeoJsonDict,
        bounds: tuple[float, float, float, float],
    ) -> GeoJsonDict:
        """
        Filter point features to a valid lon/lat bounding box.

        Args:
            geojson_data: GeoJSON FeatureCollection payload to filter.
            bounds: Tuple of `(min_lon, max_lon, min_lat, max_lat)`.

        Returns:
            A GeoJSON payload whose point features fall within the supplied bounds.
            Non-point features are preserved unchanged.
        """
        min_lon, max_lon, min_lat, max_lat = bounds
        features = geojson_data.get("features", [])
        filtered_features: list[GeoJsonDict] = []
        dropped_count = 0

        for feature in features:
            geometry = feature.get("geometry") or {}
            coords = geometry.get("coordinates") or []
            if geometry.get("type") != "Point" or len(coords) < 2:
                filtered_features.append(feature)
                continue

            lon, lat = coords[0], coords[1]
            if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                filtered_features.append(feature)
            else:
                dropped_count += 1

        if dropped_count:
            logger.warning(
                f"Filtered {dropped_count} out-of-bounds point features from GeoJSON payload."
            )

        return {
            **geojson_data,
            "features": filtered_features,
        }

    @classmethod
    def create_geojson_layer(
        cls,
        layer_key: str,
        *,
        component_id: str | LazyLayerGeoJsonId | None = None,
        data: GeoJsonDict | None = None,
    ) -> dl.GeoJSON:
        """
        Build a `dl.GeoJSON` component from a registered layer config.

        Args:
            layer_key: Internal key identifying which layer config to use.
            component_id: Optional Dash component id. When omitted, a UUID is generated.
            data: Optional GeoJSON payload. Pass `None` to create a lazy placeholder layer.

        Returns:
            A configured `dl.GeoJSON` component.
        """
        spec = cls.get_layer_config(layer_key)
        ns = Namespace("myNamespace", "mySubNamespace")

        geojson_kwargs = dict(
            id=component_id if component_id is not None else str(uuid.uuid4()),
            data=data,
            cluster=spec.cluster,
            zoomToBoundsOnClick=spec.zoom_to_bounds_on_click,
            bubblingMouseEvents=spec.bubbling_mouse_events,
            pointToLayer=ns(spec.point_to_layer),
        )
        if spec.cluster_to_layer is not None:
            geojson_kwargs["clusterToLayer"] = ns(spec.cluster_to_layer)
        if spec.supercluster_options is not None:
            geojson_kwargs["superClusterOptions"] = dict(spec.supercluster_options)

        return dl.GeoJSON(**geojson_kwargs)

    @classmethod
    def lazy_layer_geojson_id(cls, page_key: str, layer_key: str) -> LazyLayerGeoJsonId:
        """
        Build a pattern-matching id for a lazy-loaded GeoJSON layer component.

        Args:
            page_key: Page identifier, such as `"lease"` or `"buy"`.
            layer_key: Internal layer identifier.

        Returns:
            A pattern-matching id dict suitable for Dash callbacks.
        """
        return {
            "type": "lazy-layer-geojson",
            "page": page_key,
            "layer": layer_key,
        }

    @classmethod
    def layers_control_id(cls, page_key: str) -> str:
        """
        Return the Dash id used by a page's `dl.LayersControl`.

        Args:
            page_key: Page identifier, such as `"lease"` or `"buy"`.

        Returns:
            A stable string id for the page's layer control.
        """
        return f"{page_key}-layers-control"

    @classmethod
    def create_lazy_overlay(
        cls,
        page_key: str,
        layer_key: str,
        *,
        checked: bool = False,
    ) -> dl.Overlay:
        """
        Create a lazy overlay wrapper for a registered layer.

        The returned overlay contains a `dl.GeoJSON` child with `data=None`.
        A callback can later populate the child when the overlay is enabled.

        Args:
            page_key: Page identifier owning the overlay.
            layer_key: Internal layer identifier.
            checked: Whether the overlay should be enabled by default.

        Returns:
            A `dl.Overlay` configured for lazy GeoJSON loading.
        """
        spec = cls.get_layer_config(layer_key)
        geojson_layer = cls.create_geojson_layer(
            layer_key,
            component_id=cls.lazy_layer_geojson_id(page_key, layer_key),
            data=None,
        )
        return dl.Overlay(
            geojson_layer,
            name=spec.name,
            checked=checked,
        )

    @classmethod
    def create_layers_control(
        cls,
        page_key: str,
        layer_keys: Sequence[str],
        *,
        checked_layer_keys: Sequence[str] = (),
    ) -> dl.LayersControl:
        """
        Create a `dl.LayersControl` for a page's optional overlays.

        Args:
            page_key: Page identifier owning the control.
            layer_keys: Ordered collection of registered layer keys to expose.
            checked_layer_keys: Subset of `layer_keys` that should start enabled.

        Returns:
            A populated `dl.LayersControl` containing lazy overlays.
        """
        checked_keys = set(checked_layer_keys)
        overlays = [
            cls.create_lazy_overlay(page_key, layer_key, checked=layer_key in checked_keys)
            for layer_key in layer_keys
        ]
        return dl.LayersControl(
            overlays,
            id=cls.layers_control_id(page_key),
            collapsed=True,
            position='topleft',
            sortLayers=True,
        )

    @classmethod
    def resolve_lazy_layer_data(
        cls,
        selected_overlays: Optional[Sequence[str]],
        layer_ids: Optional[Sequence[LazyLayerGeoJsonId]],
        current_data: Optional[Sequence[GeoJsonDict | None]],
        *,
        excluded_layer_keys: Sequence[str] = (),
    ) -> list[Any]:
        """
        Resolve which lazy overlay payloads should be loaded for a callback update.

        This helper is designed for a Dash callback whose output targets
        `({"type": "lazy-layer-geojson", ...}, "data")`.

        Args:
            selected_overlays: Names currently enabled in `dl.LayersControl.overlays`.
            layer_ids: Pattern-matching ids for the targeted GeoJSON components.
            current_data: Existing GeoJSON payloads for those components.

        Returns:
            A list aligned to `layer_ids`, containing either:
            - a newly loaded GeoJSON payload when the layer was enabled and not yet loaded
            - `no_update` when nothing should change for that output
        """
        if not layer_ids:
            return []

        selected_overlay_names = set(selected_overlays or [])
        existing_payloads = list(current_data or [])
        if len(existing_payloads) < len(layer_ids):
            existing_payloads.extend([None] * (len(layer_ids) - len(existing_payloads)))

        resolved_payloads: list[Any] = []
        excluded_keys = set(excluded_layer_keys)
        for layer_id, existing_payload in zip(layer_ids, existing_payloads):
            layer_key = layer_id["layer"]
            spec = cls.get_layer_config(layer_key)

            if layer_key in excluded_keys:
                resolved_payloads.append(no_update)
                continue

            if spec.name not in selected_overlay_names:
                resolved_payloads.append(no_update)
                continue

            if existing_payload is not None:
                resolved_payloads.append(no_update)
                continue

            resolved_payloads.append(
                cls.load_layer_data(layer_key)
            )

        return resolved_payloads

    @classmethod
    def overlay_is_selected(
        cls,
        selected_overlays: Optional[Sequence[str]],
        layer_key: str,
    ) -> bool:
        """
        Return whether a named overlay is currently enabled in the map control.
        """
        spec = cls.get_layer_config(layer_key)
        return spec.name in set(selected_overlays or [])

    @classmethod
    def create_oil_well_geojson_layer(cls) -> dl.GeoJSON:
        """
        Create an eagerly loaded oil and gas wells GeoJSON layer.

        Returns:
            A configured `dl.GeoJSON` component for oil well data.
        """
        spec = cls.get_layer_config('oil_well')
        return cls.create_geojson_layer(
            'oil_well',
            data=cls.load_layer_data('oil_well'),
        )
    
    @classmethod
    def create_farmers_markets_layer(cls) -> dl.GeoJSON:
        """
        Create an eagerly loaded farmers markets GeoJSON layer.

        Returns:
            A configured `dl.GeoJSON` component for farmers market data.
        """
        spec = cls.get_layer_config('farmers_markets')
        return cls.create_geojson_layer(
            'farmers_markets',
            data=cls.load_layer_data('farmers_markets'),
        )

    @classmethod
    def create_supermarkets_grocery_layer(cls) -> dl.GeoJSON:
        """
        Create an eagerly loaded supermarkets and grocery stores GeoJSON layer.

        Returns:
            A configured `dl.GeoJSON` component for supermarket and grocery store data.
        """
        spec = cls.get_layer_config('supermarkets_grocery')
        return cls.create_geojson_layer(
            'supermarkets_grocery',
            data=cls.load_layer_data('supermarkets_grocery'),
        )

    @classmethod
    def create_breakfast_burritos_layer(cls) -> dl.GeoJSON:
        """
        Create an eagerly loaded breakfast burritos GeoJSON layer.

        Returns:
            A configured `dl.GeoJSON` component for breakfast burrito data.
        """
        spec = cls.get_layer_config('breakfast_burritos')
        return cls.create_geojson_layer(
            'breakfast_burritos',
            data=cls.load_layer_data('breakfast_burritos'),
        )

    @classmethod
    def create_crime_layer(cls) -> dl.GeoJSON:
        """
        Create an eagerly loaded crime GeoJSON layer.

        Returns:
            A configured `dl.GeoJSON` component for crime data.
        """
        spec = cls.get_layer_config('crime')
        return cls.create_geojson_layer(
            'crime',
            data=cls.load_layer_data('crime'),
        )


def register_responsive_layers_control_callback(page_key: str) -> None:
    """
    Register the shared clientside callback for a page's `dl.LayersControl`.

    Args:
        page_key: Page identifier, such as `"lease"` or `"buy"`.
    """
    clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="layersControlCollapsed"),
        Output(LayersClass.layers_control_id(page_key), "collapsed"),
        Input("viewport-sync-initial", "n_intervals"),
        Input("viewport-listener", "event"),
        State(LayersClass.layers_control_id(page_key), "collapsed"),
    )
