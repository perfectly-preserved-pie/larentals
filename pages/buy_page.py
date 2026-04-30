from functools import lru_cache

from .components import BuyComponents
from dash import dcc, callback, clientside_callback, ClientsideFunction
from functions.layers import LayersClass, register_responsive_layers_control_callback
from functions.zip_geocoding_utils import (
  geocode_place_cached,
  get_zip_feature_for_point,
  intersect_bbox_with_zip_polygons,
  get_zip_features_for_place,
  load_zip_place_crosswalk,
  load_zip_polygons,
)
from functions.sql_helpers import get_earliest_listed_date
from dash.dependencies import ALL, Input, Output, State
from loguru import logger
import bleach
import dash
import dash_bootstrap_components as dbc
import pandas as pd
import sys
import time

dash.register_page(
  __name__,
  path='/buy',
  name='LA County Homes for Sale',
  title='Where to Buy in LA',
  description='An interactive map of available residential properties for sale in Los Angeles County. Updated weekly.',
)

logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME]

pd.set_option("display.precision", 10)

# Load the ZIP polygons once at module load time
ZIP_POLYGONS = load_zip_polygons("assets/datasets/la_county_zip_codes.geojson")

# Load the HUD ZIP-to-city crosswalk once at module load time
ZIP_PLACE_CROSSWALK = load_zip_place_crosswalk("assets/datasets/ZIP_COUNTY_092025.csv")


@lru_cache(maxsize=1)
def get_buy_components() -> BuyComponents:
  start_time = time.perf_counter()
  components = BuyComponents()
  duration = time.perf_counter() - start_time
  logger.info(f"Created BuyComponents object in {duration:.2f} seconds.")
  return components

def layout(**_: object) -> dbc.Container:
  """
  Build the buy page layout on demand.

  Dash Pages may pass query-string parameters into page layout
  callables. This page does not use them, so extra kwargs are ignored.

  Returns:
    The buy page layout container.
  """
  components = get_buy_components()
  collapse_store = dcc.Store(id="collapse-store", data={"is_open": False})
  geojson_store = dcc.Store(id="buy-geojson-store", storage_type="memory", data=None)
  zip_boundary_store = dcc.Store(id="buy-zip-boundary-store", storage_type="memory", data={"zip_codes": [], "features": [], "error": None})
  school_layer_prompt_state_store = dcc.Store(
    id="buy-school-layer-prompt-state",
    storage_type="memory",
    data={"dismissed": False, "schools_active": False},
  )
  school_layer_focus_store = dcc.Store(
    id="buy-school-layer-focus-store",
    storage_type="memory",
    data=None,
  )
  kickstart = dcc.Interval(id="buy-boot", interval=250, n_intervals=0, max_intervals=1)
  earliest_date_store = dcc.Store(id="earliest_date_store", data=get_earliest_listed_date("assets/datasets/larentals.db", table_name="buy", date_column="listed_date"))

  return dbc.Container(
    [
      collapse_store,
      geojson_store,
      zip_boundary_store,
      school_layer_prompt_state_store,
      school_layer_focus_store,
      kickstart,
      earliest_date_store,
      dbc.Row(
        [
          dbc.Col(
          [components.title_card, components.user_options_card], 
            lg=3, md=12, sm=12, xs=12,
            style={"height": "100vh", "overflowY": "auto"},  # Full height with scroll on desktop
            className="d-lg-block"  # Always visible on desktop
        ),
          dbc.Col(
          [components.map_card], 
            lg=9, md=12, sm=12, xs=12,
            style={"height": "100vh"},  # Full viewport height
            className="position-lg-relative"
          ),
        ],
        className="g-0",
        style={"minHeight": "100vh"}
      ),
      # Keep the subtype selection available for any future callbacks that need it.
      dcc.Store(id='selected_subtype', data=[])
    ],
    fluid=True,
    className="dbc p-0",
    style={"overflowX": "hidden"}  # Prevent horizontal scroll
  )

## BEGIN CALLBACKS ##
# Keep subtype selection in sync with the store
@callback(Output('selected_subtype', 'data'), Input('subtype_checklist', 'value'))
def update_selected_subtype(value: list[str] | None) -> list[str] | None:
    """
    Keep the subtype store synchronized with the current checklist selection.

    Args:
        value: Selected subtype values from the checklist.

    Returns:
        The same selected subtype values for storage.
    """
    return value

clientside_callback(
  ClientsideFunction(namespace='clientside', function_name='loadingMapSpinner'),
  Output("buy-map-spinner", "style"),
  Input("buy-geojson-store", "data"),
  Input("buy_geojson", "data"),
  State("buy-map-spinner", "style"),
)

register_responsive_layers_control_callback("buy")

# Server-side callbacks
@callback(
  Output("buy-geojson-store", "data"),
  Input("buy-boot", "n_intervals"),
  running=[
    (
      Output("buy-map-spinner", "style", allow_duplicate=True),
      {
        "position": "absolute",
        "inset": "0",
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "center",
        "backgroundColor": "rgba(0, 0, 0, 0.25)",
        "zIndex": "10000",
      },
      {
        "position": "absolute",
        "inset": "0",
        "display": "none",
        "alignItems": "center",
        "justifyContent": "center",
        "backgroundColor": "rgba(0, 0, 0, 0.25)",
        "zIndex": "10000",
      },
    ),
  ],
  prevent_initial_call=True,
)
def load_buy_geojson(_: int) -> dict:
  """
  Load the full buy GeoJSON into the browser store once, after the page renders.

  Returns:
    A GeoJSON dict suitable for dl.GeoJSON(data=...).
  """
  return BuyComponents.get_cached_geojson_payload()

@callback(
  Output({"type": "lazy-layer-geojson", "page": "buy", "layer": ALL}, "data"),
  Input(LayersClass.layers_control_id("buy"), "overlays"),
  State({"type": "lazy-layer-geojson", "page": "buy", "layer": ALL}, "id"),
  State({"type": "lazy-layer-geojson", "page": "buy", "layer": ALL}, "data"),
)
def load_buy_optional_layers(
  selected_overlays: list[str] | None,
  layer_ids: list[dict[str, str]] | None,
  current_data: list[dict] | None,
) -> list[dict]:
  """
  Lazy-load optional map layers only after the user enables them.
  """
  return LayersClass.resolve_lazy_layer_data(
    selected_overlays=selected_overlays,
    layer_ids=layer_ids,
    current_data=current_data,
    excluded_layer_keys=("schools",),
  )


@callback(
  Output("buy-school-layer-controls-collapse", "is_open"),
  Input(LayersClass.layers_control_id("buy"), "overlays"),
)
def toggle_buy_school_layer_controls(selected_overlays: list[str] | None) -> bool:
  """
  Show the map-only school filter panel when the Schools overlay is enabled.
  """
  return LayersClass.overlay_is_selected(selected_overlays, "schools")


@callback(
  Output("buy-school-layer-prompt-state", "data"),
  Input(LayersClass.layers_control_id("buy"), "overlays"),
  Input("buy-school-layer-show-filters-button", "n_clicks"),
  Input("buy-school-layer-dismiss-prompt-button", "n_clicks"),
  State("buy-school-layer-prompt-state", "data"),
  prevent_initial_call=True,
)
def update_buy_school_layer_prompt_state(
  selected_overlays: list[str] | None,
  _show_clicks: int | None,
  _dismiss_clicks: int | None,
  prompt_state: dict | None,
) -> dict[str, bool]:
  """
  Keep the school-layer prompt visible until the user dismisses it.
  """
  state = prompt_state or {"dismissed": False, "schools_active": False}
  schools_active = LayersClass.overlay_is_selected(selected_overlays, "schools")
  was_active = bool(state.get("schools_active"))
  triggered_id = dash.ctx.triggered_id

  if triggered_id == LayersClass.layers_control_id("buy"):
    if schools_active and not was_active:
      return {"dismissed": False, "schools_active": True}
    if not schools_active:
      return {"dismissed": False, "schools_active": False}
    return {
      "dismissed": bool(state.get("dismissed")),
      "schools_active": True,
    }

  if not schools_active:
    return {"dismissed": False, "schools_active": False}

  return {"dismissed": True, "schools_active": True}


@callback(
  Output("buy-school-layer-map-prompt", "className"),
  Input(LayersClass.layers_control_id("buy"), "overlays"),
  Input("buy-school-layer-prompt-state", "data"),
)
def update_buy_school_layer_prompt_class(
  selected_overlays: list[str] | None,
  prompt_state: dict | None,
) -> str:
  """
  Reveal the map prompt only while the school overlay is active and undisposed.
  """
  base_class_name = "school-layer-map-prompt"
  prompt_dismissed = bool((prompt_state or {}).get("dismissed"))
  if (
    LayersClass.overlay_is_selected(selected_overlays, "schools")
    and not prompt_dismissed
  ):
    return f"{base_class_name} school-layer-map-prompt--visible"
  return base_class_name


@callback(
  Output("buy-fire-hazard-zone-legend", "className"),
  Input(LayersClass.layers_control_id("buy"), "overlays"),
)
def update_buy_fire_hazard_legend_class(selected_overlays: list[str] | None) -> str:
  """
  Reveal the CAL FIRE FHSZ legend only while the overlay is active.
  """
  base_class_name = "fire-hazard-zone-legend"
  if LayersClass.overlay_is_selected(selected_overlays, "fire_hazard_zones"):
    return f"{base_class_name} fire-hazard-zone-legend--visible"
  return base_class_name


@callback(
  Output("buy-school-layer-controls-card", "className"),
  Input(LayersClass.layers_control_id("buy"), "overlays"),
)
def update_buy_school_layer_controls_card_class(
  selected_overlays: list[str] | None,
) -> str:
  """
  Add an accent state so the school control card reads as newly available.
  """
  base_class_name = "mt-3 school-layer-panel-card"
  if LayersClass.overlay_is_selected(selected_overlays, "schools"):
    return f"{base_class_name} school-layer-panel-card--active"
  return base_class_name


@callback(
  Output(
    LayersClass.lazy_layer_geojson_id("buy", "schools"),
    "data",
    allow_duplicate=True,
  ),
  Input(LayersClass.layers_control_id("buy"), "overlays"),
  Input("buy-school-layer-search-input", "value"),
  Input("buy-school-layer-level-dropdown", "value"),
  Input("buy-school-layer-grade-band-checklist", "value"),
  Input("buy-school-layer-campus-configuration-dropdown", "value"),
  Input("buy-school-layer-early-grades-checklist", "value"),
  Input("buy-school-layer-funding-type-dropdown", "value"),
  Input("buy-school-layer-enrollment-slider", "value"),
  Input("buy-school-layer-charter-switch", "checked"),
  Input("buy-school-layer-magnet-switch", "checked"),
  Input("buy-school-layer-title-i-switch", "checked"),
  Input("buy-school-layer-recently-opened-switch", "checked"),
  prevent_initial_call=True,
)
def update_buy_school_layer(
  selected_overlays: list[str] | None,
  search_text: str | None,
  school_levels: list[str] | None,
  grade_bands: list[str] | None,
  campus_configurations: list[str] | None,
  early_grades: list[str] | None,
  funding_types: list[str] | None,
  enrollment_range: list[float] | None,
  charter_only: bool | None,
  magnet_only: bool | None,
  title_i_only: bool | None,
  recently_opened_only: bool | None,
) -> dict | object:
  """
  Filter the school overlay from the cached raw GeoJSON payload.
  """
  if not LayersClass.overlay_is_selected(selected_overlays, "schools"):
    return dash.no_update

  raw_geojson = LayersClass.load_layer_data("schools")
  return LayersClass.filter_school_layer_geojson(
    raw_geojson,
    search_text=search_text,
    school_levels=school_levels,
    grade_bands=grade_bands,
    campus_configurations=campus_configurations,
    early_grades=early_grades,
    funding_types=funding_types,
    enrollment_range=enrollment_range,
    charter_only=bool(charter_only),
    magnet_only=bool(magnet_only),
    title_i_only=bool(title_i_only),
    recently_opened_only=bool(recently_opened_only),
  )

@callback(
  Output("buy-zip-boundary-store", "data"),
  Output("buy-location-status", "children"),
  Input("buy-location-input", "value"),
  Input("buy-nearby-zip-switch", "checked"),
)
def update_buy_zip_boundary(
  location: str | None,
  include_nearby: bool | None,
) -> tuple[dict, str]:
  """
  Update the ZIP boundary store based on the user-entered location.

  Uses the HUD crosswalk to find ALL ZIPs belonging to the place first.
  Falls back to point-in-polygon + optional bbox intersection if the
  crosswalk has no match.

  Returns:
    A tuple of (boundary payload dict, status message string).
  """
  # Do some validation checks
  if not location or location.strip() == "":
    return {"zip_codes": [], "features": [], "error": None}, ""
  
  sanitized_location = bleach.clean(location or "", tags=[], attributes={}, strip=True)

  # Try the crosswalk first
  crosswalk_features = get_zip_features_for_place(sanitized_location, ZIP_PLACE_CROSSWALK, ZIP_POLYGONS)

  # Get the geocode bbox in case the "include nearby" switch is on
  geocoded = geocode_place_cached(sanitized_location)

  if crosswalk_features:
    # Start with crosswalk results
    zip_features = list(crosswalk_features)  

    # Optionally expand with nearby ZIPs from the geocoded bbox
    if include_nearby and geocoded:
      bbox = geocoded["bbox"]
      nearby_features = intersect_bbox_with_zip_polygons(bbox, ZIP_POLYGONS)
      existing_zips = {
        f.get("properties", {}).get("ZIPCODE") for f in zip_features
      }
      for feature in nearby_features:
        fzip = feature.get("properties", {}).get("ZIPCODE")
        if fzip and fzip not in existing_zips:
          zip_features.append(feature)
          existing_zips.add(fzip)

    # Extract ZIP codes from the features
    zip_codes = [
      f.get("properties", {}).get("ZIPCODE")
      for f in zip_features
    ]
    # Filter out any None values
    zip_codes = [z for z in zip_codes if z]
    logger.debug(f"Crosswalk matched '{sanitized_location}' → {zip_codes}")

    # Generate the label
    label = ", ".join(sorted(zip_codes)[:5])
    if len(zip_codes) > 5:
      label = f"{label} +{len(zip_codes) - 5} more"

    return (
      {"zip_codes": zip_codes, "features": zip_features, "error": None},
      f"Filtering by ZIP codes: {label}.",
    )
  
  # Fallback to geocoding + point-in-polygon if no crosswalk match
  if not geocoded:
    return (
      {"zip_codes": [], "features": [], "error": "place_not_found"},
      f"Could not find a California location matching '{sanitized_location}'.",
    )

  lat = geocoded["lat"]
  lon = geocoded["lon"]
  bbox = geocoded["bbox"]

  zip_features = []

  # Always include the ZIP containing the point
  zip_feature = get_zip_feature_for_point(lat, lon, ZIP_POLYGONS)
  if zip_feature:
    zip_features.append(zip_feature)

  # Optionally include nearby ZIPs intersecting the bounding box
  if include_nearby:
    nearby_features = intersect_bbox_with_zip_polygons(bbox, ZIP_POLYGONS)
    # First get the existing ZIPs to avoid duplicates
    existing_zips = {
      f.get("properties", {}).get("ZIPCODE") for f in zip_features
    }
    # Then add any nearby features that aren't already included
    for feature in nearby_features:
      fzip = feature.get("properties", {}).get("ZIPCODE")
      # If the feature has a ZIP code and it's not already in our list, add it
      if fzip and fzip not in existing_zips:
        zip_features.append(feature)
        existing_zips.add(fzip)

  if not zip_features:
    return (
      {"zip_codes": [], "features": [], "error": "place_outside"},
      "No ZIP code boundaries found for the specified location.",
    )

  # Extract ZIP codes from the features
  zip_codes = [feature.get("properties", {}).get("ZIPCODE") for feature in zip_features]
  # Filter out any None values
  zip_codes = [zip for zip in zip_codes if zip]
  logger.debug(f"Spatial fallback for '{sanitized_location}': {zip_codes}")

  # Generate a label for the status message based on the number of ZIPs found (up to 5)
  label = ", ".join(zip_codes[:5])
  if len(zip_codes) > 5:
    label = f"{label} +{len(zip_codes) - 5} more"

  return {"zip_codes": zip_codes, "features": zip_features, "error": None}, f"Filtering by ZIP codes: {label}."


clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='focusSchoolLayerControls'
  ),
  Output('buy-school-layer-focus-store', 'data'),
  Input('buy-school-layer-show-filters-button', 'n_clicks'),
  State('buy-school-layer-controls-card', 'id'),
  prevent_initial_call=True,
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='showMapSpinner'
  ),
  Output("buy-map-spinner", "style", allow_duplicate=True),
  [
    Input('list_price_slider', 'value'),
    Input('bedrooms_slider', 'value'),
    Input('bathrooms_slider', 'value'),
    Input('sqft_slider', 'value'),
    Input('sqft_missing_switch', 'checked'),
    Input('ppsqft_slider', 'value'),
    Input('ppsqft_missing_switch', 'checked'),
    Input('lot_size_slider', 'value'),
    Input('lot_size_missing_switch', 'checked'),
    Input('yrbuilt_slider', 'value'),
    Input('yrbuilt_missing_switch', 'checked'),
    Input('fire_hazard_severity_checklist', 'value'),
    Input('subtype_checklist', 'value'),
    Input('listed_date_datepicker_buy', 'start_date'),
    Input('listed_date_datepicker_buy', 'end_date'),
    Input('listed_date_missing_switch', 'checked'),
    Input('hoa_fee_slider', 'value'),
    Input('hoa_fee_missing_switch', 'checked'),
    Input('hoa_fee_frequency_checklist', 'value'),
    Input('isp_download_speed_slider', 'value'),
    Input('isp_upload_speed_slider', 'value'),
    Input('isp_speed_missing_switch', 'checked'),
  ],
  prevent_initial_call=True,
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='showMapSpinner'
  ),
  Output("buy-map-spinner", "style", allow_duplicate=True),
  [
    Input('buy-location-input', 'value'),
    Input('buy-nearby-zip-switch', 'checked'),
  ],
  prevent_initial_call=True,
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='showLazyLayerSpinnerOnToggle'
  ),
  Output("buy-map-spinner", "style", allow_duplicate=True),
  Input(LayersClass.layers_control_id("buy"), "overlays"),
  State({"type": "lazy-layer-geojson", "page": "buy", "layer": ALL}, "id"),
  State({"type": "lazy-layer-geojson", "page": "buy", "layer": ALL}, "data"),
  prevent_initial_call=True,
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='syncLazyLayerSpinner'
  ),
  Output("buy-map-spinner", "style", allow_duplicate=True),
  Input({"type": "lazy-layer-geojson", "page": "buy", "layer": ALL}, "data"),
  State(LayersClass.layers_control_id("buy"), "overlays"),
  State({"type": "lazy-layer-geojson", "page": "buy", "layer": ALL}, "id"),
  prevent_initial_call=True,
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='filterAndClusterBuy'
  ),
  Output('buy_geojson', 'data'),
  [
    Input('list_price_slider', 'value'),
    Input('bedrooms_slider', 'value'),
    Input('bathrooms_slider', 'value'),
    Input('sqft_slider', 'value'),
    Input('sqft_missing_switch', 'checked'),
    Input('ppsqft_slider', 'value'),
    Input('ppsqft_missing_switch', 'checked'),
    Input('lot_size_slider', 'value'),
    Input('lot_size_missing_switch', 'checked'),
    Input('yrbuilt_slider', 'value'),
    Input('yrbuilt_missing_switch', 'checked'),
    Input('fire_hazard_severity_checklist', 'value'),
    Input('subtype_checklist', 'value'),
    Input('listed_date_datepicker_buy', 'start_date'),
    Input('listed_date_datepicker_buy', 'end_date'),
    Input('listed_date_missing_switch', 'checked'),
    Input('hoa_fee_slider', 'value'),
    Input('hoa_fee_missing_switch', 'checked'),
    Input('hoa_fee_frequency_checklist', 'value'),
    Input('isp_download_speed_slider', 'value'),
    Input('isp_upload_speed_slider', 'value'),
    Input('isp_speed_missing_switch', 'checked'),
    Input('buy-zip-boundary-store', 'data'),
    Input('buy-geojson-store', "data")
  ],
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='updateDatePicker'
  ),
  Output('listed_date_datepicker_buy', 'start_date'),
  Input('listed_time_range_radio', 'value'),
  State('earliest_date_store', 'data'),
)
