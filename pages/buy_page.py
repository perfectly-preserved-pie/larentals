from .components import BuyComponents
from dash import dcc, html, callback, clientside_callback, ClientsideFunction
import dash_leaflet as dl
from functions.commute_utils import (
  build_candidate_signature,
  build_commute_boundary_result,
  empty_commute_exact_result,
  empty_commute_request_data,
  empty_feature_collection,
  verify_exact_commute_matches,
)
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

# Create the components objects and log how long it takes to create them
start_time = time.time()
components = BuyComponents()
duration = time.time() - start_time
logger.info(f"Created BuyComponents object in {duration:.2f} seconds.")

# Load the ZIP polygons once at module load time
ZIP_POLYGONS = load_zip_polygons("assets/datasets/la_county_zip_codes.geojson")

# Load the HUD ZIP-to-city crosswalk once at module load time
ZIP_PLACE_CROSSWALK = load_zip_place_crosswalk("assets/datasets/ZIP_COUNTY_092025.csv")

def layout(**_: object) -> dbc.Container:
  """
  Build the buy page layout on demand.

  Dash Pages may pass query-string parameters into page layout
  callables. This page does not use them, so extra kwargs are ignored.

  Returns:
    The buy page layout container.
  """
  collapse_store = dcc.Store(id="collapse-store", data={"is_open": False})
  geojson_store = dcc.Store(id="buy-geojson-store", storage_type="memory", data=None)
  prefilter_geojson_store = dcc.Store(id="buy-prefilter-geojson-store", storage_type="memory", data=None)
  zip_boundary_store = dcc.Store(id="buy-zip-boundary-store", storage_type="memory", data={"zip_codes": [], "features": [], "error": None})
  commute_boundary_store = dcc.Store(id="buy-commute-boundary-store", storage_type="memory", data=empty_feature_collection())
  commute_request_store = dcc.Store(id="buy-commute-request-store", storage_type="memory", data=empty_commute_request_data())
  commute_exact_store = dcc.Store(id="buy-commute-exact-store", storage_type="memory", data=empty_commute_exact_result())
  kickstart = dcc.Interval(id="buy-boot", interval=250, n_intervals=0, max_intervals=1)
  earliest_date_store = dcc.Store(id="earliest_date_store", data=get_earliest_listed_date("assets/datasets/larentals.db", table_name="buy", date_column="listed_date"))

  return dbc.Container(
    [
      collapse_store,
      geojson_store,
      prefilter_geojson_store,
      zip_boundary_store,
      commute_boundary_store,
      commute_request_store,
      commute_exact_store,
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
      # Create a hidden Store to store the selected subtype value
      dcc.Store(id='selected_subtype', data='Single Family Residence')
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
)

register_responsive_layers_control_callback("buy")

# Server-side callbacks
@callback(
  Output("buy-geojson-store", "data"),
  Input("buy-boot", "n_intervals"),
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


@callback(
  Output("buy-commute-boundary-store", "data"),
  Output("buy-commute-request-store", "data"),
  Input("buy-commute-input", "value"),
  Input("buy-commute-mode", "value"),
  Input("buy-commute-minutes", "value"),
  Input("buy-commute-departure-datetime", "value"),
  running=[
    (
      Output("buy-commute-spinner", "style", allow_duplicate=True),
      {
        "position": "absolute",
        "inset": "0",
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "center",
        "backgroundColor": "rgba(0, 0, 0, 0.25)",
        "zIndex": "10001",
      },
      {
        "position": "absolute",
        "inset": "0",
        "display": "none",
        "alignItems": "center",
        "justifyContent": "center",
        "backgroundColor": "rgba(0, 0, 0, 0.25)",
        "zIndex": "10001",
      },
    ),
  ],
  prevent_initial_call=True,
)
def update_buy_commute_boundary(
  destination: str | None,
  mode: str | None,
  minutes: int | float | None,
  departure_datetime: str | None,
) -> tuple[dict, dict]:
  """
  Update the coarse commute boundary overlay and request metadata.

  Args:
    destination: User-entered destination text.
    mode: Selected commute mode.
    minutes: Selected maximum commute duration.
    departure_datetime: Selected local departure datetime.

  Returns:
    A tuple of (GeoJSON FeatureCollection, request metadata).
  """
  sanitized_destination = bleach.clean(
    destination or "",
    tags=[],
    attributes={},
    strip=True,
  ).strip()
  geocoded = geocode_place_cached(sanitized_destination) if sanitized_destination else None
  result = build_commute_boundary_result(
    destination=sanitized_destination,
    geocoded=geocoded,
    mode=mode,
    minutes=minutes,
    departure_datetime=departure_datetime,
  )
  return result["geojson"], result["request"]


@callback(
  Output("buy-commute-target-layer", "children"),
  Input("buy-commute-request-store", "data"),
)
def update_buy_commute_target_marker(
  commute_request: dict | None,
) -> list[object]:
  """
  Render a destination marker for the current commute target.

  Args:
    commute_request: Normalized commute request metadata from the coarse boundary callback.

  Returns:
    A target halo + pin list when the destination has coordinates, otherwise an empty list.
  """
  if not isinstance(commute_request, dict):
    return []

  lat = commute_request.get("center_lat")
  lon = commute_request.get("center_lon")
  if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
    return []

  display_name = commute_request.get("display_name") or commute_request.get("destination") or "Commute target"
  marker_position = [float(lat), float(lon)]
  return [
    dl.CircleMarker(
      center=marker_position,
      radius=10,
      color="#f4a261",
      weight=3,
      fill=True,
      fillColor="#f4a261",
      fillOpacity=0.25,
      children=[
        dl.Tooltip(str(display_name), direction="top", offset=[0, -12]),
      ],
    ),
    dl.Marker(
      position=marker_position,
      zIndexOffset=1000,
      riseOnHover=True,
    ),
  ]


@callback(
  Output("buy-commute-exact-store", "data"),
  Input("buy-prefilter-geojson-store", "data"),
  Input("buy-commute-request-store", "data"),
  running=[
    (
      Output("buy-commute-spinner", "style", allow_duplicate=True),
      {
        "position": "absolute",
        "inset": "0",
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "center",
        "backgroundColor": "rgba(0, 0, 0, 0.25)",
        "zIndex": "10001",
      },
      {
        "position": "absolute",
        "inset": "0",
        "display": "none",
        "alignItems": "center",
        "justifyContent": "center",
        "backgroundColor": "rgba(0, 0, 0, 0.25)",
        "zIndex": "10001",
      },
    ),
  ],
  prevent_initial_call=True,
)
def update_buy_exact_commute_matches(
  prefiltered_geojson: dict | None,
  commute_request: dict | None,
) -> dict:
  """
  Verify coarse commute matches against exact Valhalla route durations.

  Args:
    prefiltered_geojson: Current clientside-filtered buy FeatureCollection.
    commute_request: Normalized commute request metadata from the coarse boundary callback.

  Returns:
    Exact route-check results for the current candidate set.
  """
  return verify_exact_commute_matches(
    prefiltered_geojson=prefiltered_geojson,
    commute_request=commute_request,
  )


@callback(
  Output("buy-commute-status", "children"),
  Output("buy-commute-display-mode-container", "style"),
  Output("buy-commute-display-mode", "options"),
  Input("buy-commute-request-store", "data"),
  Input("buy-commute-exact-store", "data"),
  Input("buy-prefilter-geojson-store", "data"),
  Input("buy-commute-display-mode", "value"),
)
def update_buy_commute_status(
  commute_request: dict | None,
  exact_result: dict | None,
  prefiltered_geojson: dict | None,
  display_mode: str | None,
) -> tuple[object, dict, list[dict[str, str]]]:
  """
  Render the current commute summary and show the display-mode toggle when useful.

  Args:
    commute_request: Normalized request metadata from the coarse boundary step.
    exact_result: Exact verification metadata for the current shortlist.
    prefiltered_geojson: Current coarse shortlist after clientside filters.
    display_mode: Selected map display mode for partial verification results.

  Returns:
    A tuple of (status children, display-mode container style, radio options).
  """
  toggle_style = {
    "display": "none",
    "marginTop": "12px",
    "padding": "10px 12px",
    "border": "1px solid #d7dde6",
    "borderRadius": "10px",
    "backgroundColor": "#f8fafc",
  }
  radio_options = [
    {"label": "Verified only", "value": "verified_only"},
    {"label": "Include estimated matches", "value": "include_rough"},
  ]
  if not isinstance(commute_request, dict):
    return "", toggle_style, radio_options

  request_status = str(commute_request.get("status") or "").strip()
  if not commute_request.get("requested"):
    return request_status, toggle_style, radio_options

  children: list[object] = []
  mode_text = ""
  show_toggle = False
  error_text = ""
  features = prefiltered_geojson.get("features") if isinstance(prefiltered_geojson, dict) else None
  current_signature = build_candidate_signature(
    commute_request.get("signature"),
    (
      (
        feature.get("properties", {}).get("mls_number")
        for feature in features
        if isinstance(feature, dict)
        and isinstance(feature.get("properties"), dict)
      )
      if isinstance(features, list)
      else ()
    ),
  )

  if (
    isinstance(exact_result, dict)
    and exact_result.get("commute_signature") == commute_request.get("signature")
    and exact_result.get("signature") == current_signature
  ):
    matched_candidates = int(exact_result.get("matched_candidates") or 0)
    rough_candidates = int(exact_result.get("rough_candidates") or 0)
    error_text = str(exact_result.get("error") or "").strip()

    show_toggle = (
      rough_candidates > 0
      and int(exact_result.get("checked_candidates") or 0) > 0
      and not exact_result.get("error")
    )
    if show_toggle:
      radio_options = [
        {"label": f"Verified only ({matched_candidates})", "value": "verified_only"},
        {
          "label": f"Include estimated matches ({matched_candidates + rough_candidates})",
          "value": "include_rough",
        },
      ]
      mode_text = (
        "Showing verified listings only."
        if display_mode != "include_rough"
        else "Showing verified and estimated listings."
      )

  if error_text:
    children.append(
      html.Div(
        error_text,
        style={"marginTop": "6px", "fontSize": "0.8rem", "color": "#6b7280"},
      )
    )
  if mode_text:
    children.append(
      html.Div(
        mode_text,
        style={"marginTop": "6px", "fontSize": "0.8rem", "color": "#6b7280"},
      )
    )

  if show_toggle:
    toggle_style["display"] = "block"

  return children, toggle_style, radio_options

# Clientside callback to filter the full data in memory, then update the map
clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='filterAndClusterBuy'
  ),
  Output('buy-prefilter-geojson-store', 'data'),
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
    Input('buy-commute-boundary-store', 'data'),
    Input('buy-geojson-store', "data")
  ],
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='applyExactCommuteFilter'
  ),
  Output('buy_geojson', 'data'),
  Input('buy-prefilter-geojson-store', 'data'),
  Input('buy-commute-request-store', 'data'),
  Input('buy-commute-exact-store', 'data'),
  Input('buy-commute-display-mode', 'value'),
)

clientside_callback(
  ClientsideFunction(
    namespace='clientside',
    function_name='deriveDisplayedCommuteBoundary'
  ),
  Output('buy-commute-geojson', 'data'),
  Input('buy-commute-boundary-store', 'data'),
  Input('buy_geojson', 'data'),
  Input('buy-commute-request-store', 'data'),
  Input('buy-commute-exact-store', 'data'),
  Input('buy-commute-display-mode', 'value'),
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
