from functools import lru_cache

from .components import LeaseComponents
from dash import dcc, clientside_callback, ClientsideFunction, callback
from dash.dependencies import ALL, Input, Output, State
from functions.layers import LayersClass, register_responsive_layers_control_callback
from functions.zip_geocoding_utils import (
  geocode_place_cached,
  get_zip_feature_for_point,
  get_zip_features_for_place,
  intersect_bbox_with_zip_polygons,
  load_zip_place_crosswalk,
  load_zip_polygons,
)
from functions.sql_helpers import get_earliest_listed_date
from loguru import logger
import bleach
import dash
import dash_bootstrap_components as dbc
import sys
import time

dash.register_page(
  __name__,
  path='/',
  name='LA County Homes for Rent',
  title='Where to Rent in LA',
  description='An interactive map of available rentals in Los Angeles County. Updated weekly.',
)


logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME]

# Load the ZIP polygons once at module load time
ZIP_POLYGONS = load_zip_polygons("assets/datasets/la_county_zip_codes.geojson")

# Load the HUD ZIP-to-city crosswalk once at module load time
ZIP_PLACE_CROSSWALK = load_zip_place_crosswalk("assets/datasets/ZIP_COUNTY_092025.csv")


@lru_cache(maxsize=1)
def get_lease_components() -> LeaseComponents:
  start_time = time.perf_counter()
  components = LeaseComponents()
  duration = time.perf_counter() - start_time
  logger.info(f"Created LeaseComponents in {duration:.2f} seconds.")
  return components

def layout(**_: object) -> dbc.Container:
  """
  Build the lease page layout on demand.

  Dash Pages may pass query-string parameters into page layout
  callables. This page does not use them, so extra kwargs are ignored.

  Returns:
    The lease page layout container.
  """
  lease_components = get_lease_components()

  collapse_store = dcc.Store(id="collapse-store", data={"is_open": False})
  geojson_store = dcc.Store(id="lease-geojson-store", storage_type="memory", data=None)
  zip_boundary_store = dcc.Store(id="lease-zip-boundary-store", storage_type="memory", data={"zip_codes": [], "features": [], "error": None})
  school_layer_prompt_state_store = dcc.Store(
    id="lease-school-layer-prompt-state",
    storage_type="memory",
    data={"dismissed": False, "schools_active": False},
  )
  school_layer_focus_store = dcc.Store(
    id="lease-school-layer-focus-store",
    storage_type="memory",
    data=None,
  )
  kickstart = dcc.Interval(id="lease-boot", interval=250, n_intervals=0, max_intervals=1)
  # Create a Store to hold the earliest listed date
  earliest_date_store = dcc.Store(id="earliest_date_store", data=get_earliest_listed_date("assets/datasets/larentals.db", table_name="lease", date_column="listed_date"))

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
            [lease_components.title_card, lease_components.user_options_card], 
            lg=3, md=12, sm=12, xs=12,
            className="options-col d-lg-block",  # Always visible on desktop
          ),
          dbc.Col(
            [lease_components.map_card], 
            lg=9, md=12, sm=12, xs=12,
            className="map-col position-lg-relative"
          ),
        ],
        className="g-0",
        style={"minHeight": "100vh"}
      ),
    ],
    fluid=True,
    className="dbc p-0",
    style={"overflowX": "hidden"}  # Prevent horizontal scroll
  )

# Server-side callbacks
@callback(
  Output("lease-geojson-store", "data"),
  Input("lease-boot", "n_intervals"),
  running=[
    (
      Output("lease-map-spinner", "style", allow_duplicate=True),
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
def load_lease_geojson(_: int) -> dict:
  """
  Load the full lease GeoJSON into the browser store once, after the page renders.

  Returns:
    A GeoJSON dict suitable for dl.GeoJSON(data=...).
  """
  return LeaseComponents.get_cached_geojson_payload()

@callback(
  Output({"type": "lazy-layer-geojson", "page": "lease", "layer": ALL}, "data"),
  Input(LayersClass.layers_control_id("lease"), "overlays"),
  State({"type": "lazy-layer-geojson", "page": "lease", "layer": ALL}, "id"),
  State({"type": "lazy-layer-geojson", "page": "lease", "layer": ALL}, "data"),
)
def load_lease_optional_layers(
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
  Output("lease-school-layer-controls-collapse", "is_open"),
  Input(LayersClass.layers_control_id("lease"), "overlays"),
)
def toggle_lease_school_layer_controls(selected_overlays: list[str] | None) -> bool:
  """
  Show the map-only school filter panel when the Schools overlay is enabled.
  """
  return LayersClass.overlay_is_selected(selected_overlays, "schools")


@callback(
  Output("lease-school-layer-prompt-state", "data"),
  Input(LayersClass.layers_control_id("lease"), "overlays"),
  Input("lease-school-layer-show-filters-button", "n_clicks"),
  Input("lease-school-layer-dismiss-prompt-button", "n_clicks"),
  State("lease-school-layer-prompt-state", "data"),
  prevent_initial_call=True,
)
def update_lease_school_layer_prompt_state(
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

  if triggered_id == LayersClass.layers_control_id("lease"):
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
  Output("lease-school-layer-map-prompt", "className"),
  Input(LayersClass.layers_control_id("lease"), "overlays"),
  Input("lease-school-layer-prompt-state", "data"),
)
def update_lease_school_layer_prompt_class(
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
  Output("lease-fire-hazard-zone-legend", "className"),
  Input(LayersClass.layers_control_id("lease"), "overlays"),
)
def update_lease_fire_hazard_legend_class(selected_overlays: list[str] | None) -> str:
  """
  Reveal the CAL FIRE FHSZ legend only while the overlay is active.
  """
  base_class_name = "fire-hazard-zone-legend"
  if LayersClass.overlay_is_selected(selected_overlays, "fire_hazard_zones"):
    return f"{base_class_name} fire-hazard-zone-legend--visible"
  return base_class_name


@callback(
  Output("lease-school-layer-controls-card", "className"),
  Input(LayersClass.layers_control_id("lease"), "overlays"),
)
def update_lease_school_layer_controls_card_class(
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
    LayersClass.lazy_layer_geojson_id("lease", "schools"),
    "data",
    allow_duplicate=True,
  ),
  Input(LayersClass.layers_control_id("lease"), "overlays"),
  Input("lease-school-layer-search-input", "value"),
  Input("lease-school-layer-level-dropdown", "value"),
  Input("lease-school-layer-grade-band-checklist", "value"),
  Input("lease-school-layer-campus-configuration-dropdown", "value"),
  Input("lease-school-layer-early-grades-checklist", "value"),
  Input("lease-school-layer-funding-type-dropdown", "value"),
  Input("lease-school-layer-enrollment-slider", "value"),
  Input("lease-school-layer-charter-switch", "checked"),
  Input("lease-school-layer-magnet-switch", "checked"),
  Input("lease-school-layer-title-i-switch", "checked"),
  Input("lease-school-layer-recently-opened-switch", "checked"),
  prevent_initial_call=True,
)
def update_lease_school_layer(
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
  Output("lease-zip-boundary-store", "data"),
  Output("lease-location-status", "children"),
  Input("lease-location-input", "value"),
  Input("lease-nearby-zip-switch", "checked"),
)
def update_lease_zip_boundary(
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
  ClientsideFunction(namespace='clientside', function_name='loadingMapSpinner'),
  Output("lease-map-spinner", "style"),
  Input("lease-geojson-store", "data"),
  Input("lease_geojson", "data"),
  State("lease-map-spinner", "style"),
)

register_responsive_layers_control_callback("lease")

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='focusSchoolLayerControls'
  ),
  Output('lease-school-layer-focus-store', 'data'),
  Input('lease-school-layer-show-filters-button', 'n_clicks'),
  State('lease-school-layer-controls-card', 'id'),
  prevent_initial_call=True,
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='showMapSpinner'
  ),
  Output("lease-map-spinner", "style", allow_duplicate=True),
  [
    Input('rental_price_slider', 'value'),
    Input('bedrooms_slider', 'value'),
    Input('bathrooms_slider', 'value'),
    Input('pets_radio', 'value'),
    Input('sqft_slider', 'value'),
    Input('sqft_missing_switch', 'checked'),
    Input('ppsqft_slider', 'value'),
    Input('ppsqft_missing_switch', 'checked'),
    Input('garage_spaces_slider', 'value'),
    Input('garage_missing_switch', 'checked'),
    Input('yrbuilt_slider', 'value'),
    Input('yrbuilt_missing_switch', 'checked'),
    Input('fire_hazard_severity_checklist', 'value'),
    Input('terms_checklist', 'value'),
    Input('terms_missing_switch', 'checked'),
    Input('furnished_checklist', 'value'),
    Input('security_deposit_slider', 'value'),
    Input('security_deposit_missing_switch', 'checked'),
    Input('pet_deposit_slider', 'value'),
    Input('pet_deposit_missing_switch', 'checked'),
    Input('key_deposit_slider', 'value'),
    Input('key_deposit_missing_switch', 'checked'),
    Input('other_deposit_slider', 'value'),
    Input('other_deposit_missing_switch', 'checked'),
    Input('laundry_checklist', 'value'),
    Input('subtype_checklist', 'value'),
    Input('listed_date_datepicker_lease', 'start_date'),
    Input('listed_date_datepicker_lease', 'end_date'),
    Input('listed_date_missing_switch', 'checked'),
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
  Output("lease-map-spinner", "style", allow_duplicate=True),
  [
    Input('lease-location-input', 'value'),
    Input('lease-nearby-zip-switch', 'checked'),
  ],
  prevent_initial_call=True,
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='showLazyLayerSpinnerOnToggle'
  ),
  Output("lease-map-spinner", "style", allow_duplicate=True),
  Input(LayersClass.layers_control_id("lease"), "overlays"),
  State({"type": "lazy-layer-geojson", "page": "lease", "layer": ALL}, "id"),
  State({"type": "lazy-layer-geojson", "page": "lease", "layer": ALL}, "data"),
  prevent_initial_call=True,
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='syncLazyLayerSpinner'
  ),
  Output("lease-map-spinner", "style", allow_duplicate=True),
  Input({"type": "lazy-layer-geojson", "page": "lease", "layer": ALL}, "data"),
  State(LayersClass.layers_control_id("lease"), "overlays"),
  State({"type": "lazy-layer-geojson", "page": "lease", "layer": ALL}, "id"),
  prevent_initial_call=True,
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='filterAndClusterLease'
  ),
  Output('lease_geojson', 'data'),
  [ # The order of these inputs must match the order of the arguments in the filterAndCluster function
    Input('rental_price_slider', 'value'),
    Input('bedrooms_slider', 'value'),
    Input('bathrooms_slider', 'value'),
    Input('pets_radio', 'value'),
    Input('sqft_slider', 'value'),
    Input('sqft_missing_switch', 'checked'),
    Input('ppsqft_slider', 'value'),
    Input('ppsqft_missing_switch', 'checked'),
    Input('garage_spaces_slider', 'value'),
    Input('garage_missing_switch', 'checked'),
    Input('yrbuilt_slider', 'value'),
    Input('yrbuilt_missing_switch', 'checked'),
    Input('fire_hazard_severity_checklist', 'value'),
    Input('terms_checklist', 'value'),
    Input('terms_missing_switch', 'checked'),
    Input('furnished_checklist', 'value'),
    Input('security_deposit_slider', 'value'),
    Input('security_deposit_missing_switch', 'checked'),
    Input('pet_deposit_slider', 'value'),
    Input('pet_deposit_missing_switch', 'checked'),
    Input('key_deposit_slider', 'value'),
    Input('key_deposit_missing_switch', 'checked'),
    Input('other_deposit_slider', 'value'),
    Input('other_deposit_missing_switch', 'checked'),
    Input('laundry_checklist', 'value'),
    Input('subtype_checklist', 'value'),
    Input('listed_date_datepicker_lease', 'start_date'),
    Input('listed_date_datepicker_lease', 'end_date'),
    Input('listed_date_missing_switch', 'checked'),
    Input('isp_download_speed_slider', 'value'),
    Input('isp_upload_speed_slider', 'value'),
    Input('isp_speed_missing_switch', 'checked'),
    Input('lease-zip-boundary-store', 'data'),
    Input('lease-geojson-store', "data"),
  ],
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='updateDatePicker'
  ),
  Output('listed_date_datepicker_lease', 'start_date'),
  Input('listed_time_range_radio', 'value'),
  State('earliest_date_store', 'data'),
  
)
