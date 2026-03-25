from dash import Dash, clientside_callback, Input, Output, dcc, ClientsideFunction
from api import register_api_routes
from dash_extensions import EventListener
from flask_compress import Compress
from functions.devtools import register_filter_exclusion_devtool
import dash
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import logging

logging.getLogger().setLevel(logging.INFO)

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

# Plausible privacy-friendly analytics
# https://dash.plotly.com/external-resources#usage (Option 1)
# Probably won't get past adblockers and NoScript but whatever, good enough
app.index_string = """<!DOCTYPE html>
<html>
  <head>
    <script defer data-domain="wheretolive.la" src="https://plausible.automateordie.io/js/plausible.js" type="application/javascript"></script>
    {%metas%}
    <title>{%title%}</title>
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

app.layout = dmc.MantineProvider(
  dmc.Container([
    create_initial_viewport_sync(),
    create_viewport_listener(),
    dcc.Store(id="theme-switch-store", storage_type="local"),
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
  className = "dmc",
  ),
#forceColorScheme="dark",
)

clientside_callback(
  ClientsideFunction(namespace='clientside', function_name='themeSwitch'),
  Output("theme-switch-store", "data"),
  Input("color-scheme-switch", "checked"),
)
register_api_routes(server, db_path="assets/datasets/larentals.db")

if __name__ == '__main__':
	app.run(debug=True)
