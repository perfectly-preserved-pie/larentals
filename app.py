from dash import Dash, clientside_callback, ClientsideFunction, Input, Output, dcc
from api import register_api_routes
from functions.data_paths import LARENTALS_DB_PATH
from dash_extensions import EventListener
from flask_compress import Compress
from flask import Response, abort, redirect, render_template, request
from markupsafe import Markup
from functions.devtools import register_filter_exclusion_devtool
from functions.lahd_records_ui import (
  create_lahd_records_drawer,
  create_lahd_records_listener,
  register_lahd_records_drawer_callback,
)
from functions.lahd import (
  prewarm_lahd_listing_lookup_cache,
  lahd_records_snapshot_available,
)
from functions.rso import prewarm_rso_property_lookup_cache
from functions.mcp_usage_logging import register_mcp_usage_logging
from functions.mcp_2026 import register_mcp_2026_transport
from functions.source_map_logging import register_source_map_error_filter
from functions.dash_asset_requests import register_dash_asset_request_guard
from functions.security_headers import register_security_headers
from functions.mcp_listings import configure_listings_mcp
from functions.mcp_guide import (
  MCP_CLIENTS,
  MCP_CONNECTION,
  MCP_ENDPOINT,
  MCP_EXAMPLES,
  MCP_FILTERS,
  MCP_GUIDE_INTRO,
  MCP_GUIDE_TITLE,
  MCP_SEARCH_GUIDANCE,
)
from functions.site_identity import DTLA_RIDGELINE, DTLA_SKYLINE
from functions.seo import (
  CANONICAL_BASE_URL,
  PAGE_MARKDOWN_PATHS,
  SOCIAL_PREVIEW_IMAGE_URL,
  build_initial_page_content,
  build_llms_full_txt,
  build_page_head,
  build_page_markdown,
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
import json
import os
import time
from html import escape

# DMC 3 uses Mantine 9, whose components require React 19.
dash._dash_renderer._set_react_version("19.2.4")

STRUCTURED_DATA_SCRIPT = build_structured_data_script(CANONICAL_BASE_URL)
PAGE_LASTMOD = json.loads(os.environ.get("SITE_PAGE_LASTMOD", "{}"))
VIEWPORT_EVENT_PROPS: list[str] = ["detail.width", "detail.isMobile"]

external_stylesheets = [
  dbc.themes.BOOTSTRAP,
  dbc.icons.BOOTSTRAP,
  dbc.icons.FONT_AWESOME,
  # Supplies Mapbox's required, unmodified logo styling when Satellite imagery is active.
  "https://api.mapbox.com/mapbox-gl-js/v3.33.0/mapbox-gl.css",
]
analytics_scripts = [
  {
    "src": "/analytics/script.js?siteId=3bc288cd62a8",
    "defer": "defer",
  },
  {
    "src": "https://plausible.automateordie.dev/js/pa-DWgFshrhRptVOrZUWP7Ia.js",
    "async": "async",
  },
]
external_scripts = [
  *analytics_scripts,
  'https://cdn.jsdelivr.net/npm/@turf/turf@7.4.0/turf.min.js', # Turf.js for convex hulls and ZIP boundary filtering
  'https://cdn.jsdelivr.net/npm/sweetalert2@11.26.25/dist/sweetalert2.all.min.js' # SweetAlert2 for popups
]

register_filter_exclusion_devtool()
dmc.pre_render_color_scheme()


@dash.hooks.index()
def complete_page_index(index: str) -> str:
  """Add public page metadata and readable content to Dash's initial response.

  Run after Mantine's hook, which matches a bare html tag when seeding the
  color scheme. Keeping that order preserves its pre-render theme handling.
  Put the introductory content inside React's mount point so mounting the
  interactive page replaces it without leaving duplicate headings.

  Args:
      index: Dash's rendered HTML after earlier index hooks.

  Returns:
      The HTML shell with language, public-page identity, and initial content.
  """
  head = build_page_head(
    CANONICAL_BASE_URL, request.path, get_public_page_paths(dash.page_registry),
  )
  index = index.replace("<html", '<html lang="en"', 1).replace("</head>", head + "\n</head>", 1)
  for page in dash.page_registry.values():
    if page["path"] == request.path:
      title = page["title"]
      if isinstance(title, str):
        index = index.replace(
          f"<title>{escape(app.title)}</title>",
          f"<title>{escape(title)} | {escape(app.title)}</title>",
          1,
        )
      break
  initial_content = build_initial_page_content(request.path)
  if initial_content:
    entry = '<div id="react-entry-point">'
    start = index.index(entry) + len(entry)
    end = index.index("</div>", start) + len("</div>")
    index = index[:start] + initial_content + index[end:]
  return index


configure_listings_mcp()

# Create the app
app = Dash(
	external_scripts = external_scripts,
  external_stylesheets = external_stylesheets,
  enable_mcp=True,
  health_endpoint="health", # https://dash.plotly.com/app-monitoring
  # Add meta tags for mobile devices
  # https://community.plotly.com/t/reorder-website-for-mobile-view/33669/5?
  meta_tags = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1"}
  ],
  name = __name__,
  use_pages = True,
  assets_ignore = r"^mcp_docs\.js$",
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
register_security_headers(server, app.csp_hashes)
register_mcp_usage_logging(server)
register_mcp_2026_transport(server, allowed_origins={CANONICAL_BASE_URL})
register_source_map_error_filter(server)
register_dash_asset_request_guard(server)


@server.before_request
def enforce_public_page_routes() -> Response | None:
  """Return a real 404 for paths that would only hit Dash's fallback shell.

  Dash has a catch-all for browser pages, so Flask can otherwise serve HTML
  with a success status for missing discovery files or mistyped links. Explicit
  routes such as the MCP transport, health, and static assets bypass this check.

  Returns:
      A canonical redirect for a trailing slash, or None to continue routing.

  Raises:
      NotFound: The catch-all path does not match a public page.
  """
  if request.endpoint != "/<path:path>":
    return None
  page_paths = {"/mcp", *get_public_page_paths(dash.page_registry)}
  if request.path in page_paths:
    return None
  canonical_path = request.path.rstrip("/")
  if canonical_path in page_paths:
    query = "?" + request.query_string.decode("latin-1") if request.query_string else ""
    return redirect(canonical_path + query, code=308)
  abort(404)


@server.after_request
def advertise_page_alternates(response: Response) -> Response:
  """Expose the public text guides to clients that only inspect HTTP headers.

  These links describe variants of the public HTML pages, so error responses
  and the text guides themselves do not advertise them.

  Args:
      response: Flask response after route handling.

  Returns:
      The response with discovery links on successful HTML pages.
  """
  markdown = PAGE_MARKDOWN_PATHS.get(request.path)
  if markdown and response.status_code == 200:
    response.headers.add("Link", '</llms.txt>; rel="alternate"; type="text/plain"')
    response.headers.add("Link", f'<{markdown}>; rel="alternate"; type="text/markdown"')
  return response


@server.route("/sitemap.xml")
def sitemap_xml() -> Response:
  """Render the canonical sitemap for the map pages and standalone MCP guide.

  Read map paths from the Dash registry. The image build supplies
  modification dates from source history for both the maps and the guide.

  Returns:
      An HTTP response containing the sitemap XML.
  """
  page_paths = sorted({"/mcp", *get_public_page_paths(dash.page_registry)})
  return Response(
    build_sitemap_xml(CANONICAL_BASE_URL, page_paths, last_modified=PAGE_LASTMOD),
    mimetype="application/xml",
  )


@server.route("/mcp")
def mcp_guide_page() -> str:
  """Serve the setup guide directly so it can be read without Dash.

  The guide shares the sitemap, canonical metadata, theme assets, and Markdown
  source with the rest of the site. Only the copy and theme controls need JS.

  Returns:
      The full HTML document for the public MCP setup guide.
  """
  return render_template(
    "mcp_guide.html",
    page_title="Connect WhereToLive.LA to Your AI Assistant",
    description="Connect Claude, ChatGPT, Codex, and other MCP clients to read-only "
                "Los Angeles County lease and for-sale listing search.",
    image=SOCIAL_PREVIEW_IMAGE_URL,
    page_head=Markup(build_page_head(CANONICAL_BASE_URL, "/mcp", ["/mcp"])),
    structured_data=Markup(STRUCTURED_DATA_SCRIPT),
    asset=app.get_asset_url,
    bootstrap=dbc.themes.BOOTSTRAP,
    analytics=analytics_scripts,
    title=MCP_GUIDE_TITLE,
    intro=MCP_GUIDE_INTRO,
    ridgeline=DTLA_RIDGELINE,
    skyline=DTLA_SKYLINE,
    endpoint=MCP_ENDPOINT,
    connection=MCP_CONNECTION,
    clients=MCP_CLIENTS,
    filters=MCP_FILTERS,
    search_guidance=MCP_SEARCH_GUIDANCE,
    examples=MCP_EXAMPLES,
  )


@server.route("/robots.txt")
def robots_txt() -> Response:
  """Render crawler directives with the canonical sitemap location.

  The sitemap link gives crawlers the canonical source for discovering public pages.

  Returns:
      An HTTP response containing the robots text.
  """
  return Response(
    build_robots_txt(CANONICAL_BASE_URL),
    mimetype="text/plain",
  )


@server.route("/llms.txt")
def llms_txt() -> Response:
  """Render the machine-readable site description for language-model clients.

  This response describes the site separately from conventional search-engine directives.

  Returns:
      An HTTP response containing the llms text.
  """
  return Response(
    build_llms_txt(CANONICAL_BASE_URL),
    mimetype="text/plain",
  )


@server.route("/llms-full.txt")
def llms_full_txt() -> Response:
  """Serve the combined guide for clients that prefer a single request.

  The summary manifest links here so clients can choose the expanded material
  before fetching or rendering the interactive pages.

  Returns:
      The expanded guide as plain text.
  """
  return Response(build_llms_full_txt(CANONICAL_BASE_URL), mimetype="text/plain")


@server.route(PAGE_MARKDOWN_PATHS["/"], defaults={"page_path": "/"})
@server.route(PAGE_MARKDOWN_PATHS["/buy"], defaults={"page_path": "/buy"})
@server.route(PAGE_MARKDOWN_PATHS["/mcp"], defaults={"page_path": "/mcp"})
def page_markdown(page_path: str) -> Response:
  """Serve a Markdown companion at the alternate URL advertised by the page.

  The Link header identifies the original page for clients that read HTTP
  metadata without parsing the Markdown frontmatter.

  Args:
      page_path: Canonical HTML path associated with the companion route.

  Returns:
      The Markdown response with a canonical Link header.
  """
  return Response(
    build_page_markdown(CANONICAL_BASE_URL, page_path),
    mimetype="text/markdown",
    headers={"Link": f'<{CANONICAL_BASE_URL}{page_path}>; rel="canonical"'},
  )


app.index_string = """<!DOCTYPE html>
<html>
  <head>
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
  """Create a one-shot interval used to seed responsive clientside state.

  The one-shot interval seeds state after the clientside callback registry is ready.

  Returns:
    A short-lived interval that fires once after the app mounts.
  """
  return dcc.Interval(id="viewport-sync-initial", interval=250, n_intervals=0, max_intervals=1)

def create_viewport_listener() -> EventListener:
  """Create the hidden event bridge for viewport-aware Dash callbacks.

  A hidden Dash component carries browser viewport events into callback inputs.

  Returns:
    An `EventListener` configured to forward browser `viewportchange` events.
  """
  return EventListener(
    id="viewport-listener",
    events=[{"event": "viewportchange", "props": VIEWPORT_EVENT_PROPS}],
    style={"display": "none"},
  )

def prewarm_startup_caches() -> None:
  """Populate expensive local caches before the first browser/API request.

  Loading local snapshots during startup avoids expensive first-request work.

  Returns:
      None.
  """
  start_time = time.perf_counter()
  lahd_records_snapshot_available()
  prewarm_lahd_listing_lookup_cache()
  prewarm_rso_property_lookup_cache()

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
register_api_routes(server, db_path=str(LARENTALS_DB_PATH))
register_lahd_records_drawer_callback(app)
prewarm_startup_caches()

def main() -> None:
  """Start the Dash development server when invoked as a console script.

  React 19's development bundle uses `eval`, which the strict Content Security
  Policy blocks. Keep Python debugging and hot reload, but disable browser prop
  checks so Dash serves the CSP-safe production React bundles. Deployment servers
  import the configured app object instead of using this entry point.

  Side Effects:
    Binds the configured local web server and blocks while serving requests.

  Returns:
      None.
  """
  app.run(
    debug=True,
    dev_tools_props_check=False,
    dev_tools_serve_dev_bundles=False,
  )


if __name__ == '__main__':
	main()
