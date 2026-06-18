from dash import Dash, clientside_callback, ClientsideFunction, Input, Output, dcc
from api import register_api_routes
from dash_extensions import EventListener
from flask_compress import Compress
from flask import Response
from functions.devtools import register_filter_exclusion_devtool
from functions.lahd_records_ui import (
  create_lahd_records_drawer,
  create_lahd_records_listener,
  register_lahd_records_drawer_callback,
)
from functions.lahd import prewarm_lahd_listing_lookup_cache
from functions.seo import (
  build_llms_txt,
  build_robots_txt,
  build_sitemap_xml,
  build_structured_data_script,
  get_public_page_paths,
)
import dash
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import logging
import time

logging.getLogger().setLevel(logging.INFO)

CANONICAL_BASE_URL = "https://wheretolive.la"
STRUCTURED_DATA_SCRIPT = build_structured_data_script(CANONICAL_BASE_URL)
VIEWPORT_EVENT_PROPS: list[str] = ["detail.width", "detail.isMobile"]

external_stylesheets = [
	dbc.themes.BOOTSTRAP,
  dbc.icons.BOOTSTRAP,
  dbc.icons.FONT_AWESOME
]
external_scripts = [
  'https://cdn.jsdelivr.net/npm/@turf/turf@7.3.0/turf.min.js', # Turf.js for convex hulls
  'https://cdn.jsdelivr.net/npm/sweetalert2@11.26.24/dist/sweetalert2.all.min.js' # SweetAlert2 for popups
]

register_filter_exclusion_devtool()
dmc.pre_render_color_scheme()

# Create the app
app = Dash(
	external_scripts = external_scripts,
  external_stylesheets = external_stylesheets,
  health_endpoint="health", # https://dash.plotly.com/app-monitoring
  # Add meta tags for mobile devices
  # https://community.plotly.com/t/reorder-website-for-mobile-view/33669/5?
  meta_tags = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1"}
  ],
  name = __name__, 
  use_pages = True,
)

# Set the page title
app.title = "WhereToLive.LA"
app.description = "An interactive map of available rental & for-sale properties in Los Angeles County."

# Configure compression 
app.server.config["COMPRESS_MIN_SIZE"] = 1024  # only compress responses >= 1KB
app.server.config["COMPRESS_MIMETYPES"] = [
  "text/html",
  "text/css",
  "application/json",
  "application/javascript",
  "text/javascript",
]

# Enable Flask-Compress for compression
Compress(app.server)

# For Gunicorn
server = app.server


@server.route("/sitemap.xml")
def sitemap_xml() -> Response:
  page_paths = get_public_page_paths(dash.page_registry)
  return Response(
    build_sitemap_xml(CANONICAL_BASE_URL, page_paths),
    mimetype="application/xml",
  )


@server.route("/robots.txt")
def robots_txt() -> Response:
  return Response(
    build_robots_txt(CANONICAL_BASE_URL),
    mimetype="text/plain",
  )


@server.route("/llms.txt")
def llms_txt() -> Response:
  return Response(
    build_llms_txt(CANONICAL_BASE_URL),
    mimetype="text/plain",
  )

# Plausible privacy-friendly analytics
# https://dash.plotly.com/external-resources#usage (Option 1)
# Probably won't get past adblockers and NoScript but whatever, good enough
app.index_string = """<!DOCTYPE html>
<html>
  <head>
    <script defer data-domain="wheretolive.la" src="https://plausible.automateordie.dev/js/plausible.js" type="application/javascript"></script>
    {%metas%}
    <title>{%title%}</title>
    """ + STRUCTURED_DATA_SCRIPT + """
    {%favicon%}
    {%css%}
  </head>
  <body>
    {%app_entry%}
    <footer>
      {%config%}
      {%scripts%}
      {%renderer%}
    </footer>
  </body>
</html>
"""

def create_initial_viewport_sync() -> dcc.Interval:
  """
  Create a one-shot interval used to seed responsive clientside state.

  Returns:
    A short-lived interval that fires once after the app mounts.
  """
  return dcc.Interval(id="viewport-sync-initial", interval=250, n_intervals=0, max_intervals=1)

def create_viewport_listener() -> EventListener:
  """
  Create the hidden event bridge for viewport-aware Dash callbacks.

  Returns:
    An `EventListener` configured to forward browser `viewportchange` events.
  """
  return EventListener(
    id="viewport-listener",
    events=[{"event": "viewportchange", "props": VIEWPORT_EVENT_PROPS}],
    style={"display": "none"},
  )

def prewarm_startup_caches() -> None:
  """
  Populate expensive local caches before the first browser/API request.
  """
  start_time = time.perf_counter()
  prewarm_lahd_listing_lookup_cache()

  # Import after Dash is initialized because page modules call dash.register_page.
  from pages.buy_components import BuyComponents
  from pages.buy_page import get_buy_components
  from pages.lease_components import LeaseComponents
  from pages.lease_page import get_lease_components

  get_lease_components()
  get_buy_components()
  LeaseComponents.get_cached_geojson_payload()
  BuyComponents.get_cached_geojson_payload()

  duration = time.perf_counter() - start_time
  logging.info(f"Prewarmed startup caches in {duration:.2f} seconds.")

app.layout = dmc.MantineProvider(
  dmc.Container([
    create_initial_viewport_sync(),
    create_viewport_listener(),
    create_lahd_records_listener(),
    dcc.Interval(id="theme-switch-initial-sync", interval=100, n_intervals=0, max_intervals=1),
    dcc.Store(id="theme-switch-store", storage_type="local"),
    create_lahd_records_drawer(),
    dbc.Row( # Second row: the rest
      [
        dash.page_container
      ],
      # Remove the whitespace/padding between the two cards (aka the gutters)
      # https://stackoverflow.com/a/70495385
      className="g-0",
    ),
  #html.Link(href='/assets/style.css', rel='stylesheet'),
  ],
  fluid = True,
  className = "dmc app-shell",
  style={"margin": 0, "maxWidth": "none", "minHeight": "100vh", "padding": 0},
  ),
)

clientside_callback(
  ClientsideFunction(namespace='clientside', function_name='initializeThemeSwitch'),
  Output("color-scheme-switch", "checked"),
  Input("theme-switch-initial-sync", "n_intervals"),
)
clientside_callback(
  ClientsideFunction(namespace='clientside', function_name='themeSwitch'),
  Output("theme-switch-store", "data"),
  Input("color-scheme-switch", "checked"),
)
register_api_routes(server, db_path="assets/datasets/larentals.db")
register_lahd_records_drawer_callback(app)
prewarm_startup_caches()

def main() -> None:
  app.run(debug=True)


if __name__ == '__main__':
	main()
