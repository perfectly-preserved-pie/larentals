from dash import Dash
from flask import request, jsonify, abort, Blueprint
from loguru import logger
from typing import Any
import bleach
import dash
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import logging
import sqlite3

logging.getLogger().setLevel(logging.INFO)

external_stylesheets = [
	dbc.themes.DARKLY,
  dbc.icons.BOOTSTRAP,
  dbc.icons.FONT_AWESOME
]
external_scripts = [
  'https://cdn.jsdelivr.net/npm/@turf/turf@6/turf.min.js', # Turf.js for convex hulls
  'https://cdn.jsdelivr.net/npm/sweetalert2@11' # SweetAlert2 for popups
]

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

app.layout = dmc.MantineProvider(
  dbc.Container([
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
  className = "dbc",
  ),
forceColorScheme="dark"
)

ALLOWED_OPTIONS = {
  "Wrong Location",
  "Unavailable/Sold/Rented",
  "Wrong Details",
  "Incorrect Price",
  "Other"
}

# Create a custom route for the report form submission
@app.server.route('/report_listing', methods=['POST'])
def report_listing() -> tuple:
  """Handle listing reports. If marked 'Unavailable/Sold/Rented', update the database flag."""
  data = request.get_json()
  mls_number: str = data.get('mls_number')
  option: str = data.get('option')
  text_report: str = data.get('text')
  properties: dict = data.get('properties')

  if option not in ALLOWED_OPTIONS:
    abort(400, "Invalid option provided.")

  # Sanitize text input (disallow any tags)
  sanitized_text = bleach.clean(text_report, tags=[], attributes={}, strip=True)
  logger.info(f"Received report for MLS {mls_number}: Option='{option}', Details='{sanitized_text}'")

  try:
    # Determine which table to update based on context (lease or buy)
    page_type = None
    if properties and isinstance(properties.get('context'), dict):
      page_type = properties['context'].get('pageType')
    table_name = 'lease' if page_type == 'lease' else 'buy'

    conn = sqlite3.connect("assets/datasets/larentals.db")
    cur = conn.cursor()

    # make sure our two new columns exist
    cur.execute(f"PRAGMA table_info({table_name});")
    cols = [r[1] for r in cur.fetchall()]
    if 'report_option' not in cols:
      cur.execute(f"ALTER TABLE {table_name} ADD COLUMN report_option TEXT;")
    if 'report_text' not in cols:
      cur.execute(f"ALTER TABLE {table_name} ADD COLUMN report_text TEXT;")

    if option == "Unavailable/Sold/Rented":
      # mark tenatively inactive
      cur.execute(
        f"UPDATE {table_name} SET reported_as_inactive = 1 WHERE mls_number = ?",
        (mls_number,)
      )
      logger.success(f"Marked MLS {mls_number} as inactive in '{table_name}' table.")
    else:
      # record the other option + free‐form text
      cur.execute(
        f"""UPDATE {table_name}
          SET report_option = ?, report_text = ?
          WHERE mls_number = ?""",
        (option, sanitized_text, mls_number)
      )
      logger.success(
        f"Saved user-submitted report for MLS {mls_number}: option={option}, text='{sanitized_text}'"
      )

    conn.commit()
    conn.close()
    return jsonify(status="success"), 200

  except Exception as e:
    logger.error(f"Error handling report for MLS {mls_number}: {e}")
    return jsonify(status="error", message="Internal error, please try again later."), 500

# Create a custom route for fetching ISP options
def register_isp_routes(server: Any, db_path: str = 'assets/datasets/larentals.db') -> None:
  """
  Register HTTP routes for fetching ISP options on-demand.

  Args:
    server: The Flask server instance (typically `app.server` in Dash).
    db_path: Path to the SQLite database file. Defaults to 'assets/datasets/larentals.db'.
  """
  bp = Blueprint("isp_api", __name__)

  @bp.get("/api/lease/isp-options/<listing_id>")
  def get_lease_isp_options(listing_id: str):
    """
    Return top ISP options for a given listing_id (mls_number).

    Args:
      listing_id: MLS/listing identifier used in `lease_provider_options.listing_id`.

    Returns:
      JSON array of provider option dicts matching the structure expected by popup.js.
    """
    sql = """
    SELECT
      DBA,
      Service_Type,
      TechCode,
      MaxAdDn,
      MaxAdUp,
      MaxDnTier,
      MaxUpTier,
      MinDnTier,
      MinUpTier
    FROM lease_provider_options
    WHERE listing_id = ?
      AND DBA IS NOT NULL
    ORDER BY
      COALESCE(MaxAdDn, -1) DESC,
      COALESCE(MaxAdUp, -1) DESC,
      DBA ASC
    LIMIT 8;
    """

    with sqlite3.connect(db_path) as conn:
      conn.row_factory = sqlite3.Row
      rows = conn.execute(sql, (listing_id,)).fetchall()

    result: list[dict[str, Any]] = []
    for r in rows:
      result.append(
        {
          "dba": r["DBA"],
          "service_type": r["Service_Type"],
          "tech_code": r["TechCode"],
          "max_dn_mbps": r["MaxAdDn"],
          "max_up_mbps": r["MaxAdUp"],
          "max_dn_tier": r["MaxDnTier"],
          "max_up_tier": r["MaxUpTier"],
          "min_dn_tier": r["MinDnTier"],
          "min_up_tier": r["MinUpTier"],
        }
      )

    return jsonify(result)

  server.register_blueprint(bp)

register_isp_routes(server, db_path="assets/datasets/larentals.db")

if __name__ == '__main__':
	app.run(debug=True)