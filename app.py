from dash import Dash, _dash_renderer
import dash
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import logging

# Set the React version to 18.2.0
# https://www.dash-mantine-components.com/getting-started#simple-usage
_dash_renderer._set_react_version("18.2.0")

logging.getLogger().setLevel(logging.INFO)

external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME]

# Create the app
app = Dash(
  __name__, 
  external_stylesheets=external_stylesheets,
  use_pages=True,
  # Add meta tags for mobile devices
  # https://community.plotly.com/t/reorder-website-for-mobile-view/33669/5?
  meta_tags = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1"}
  ],
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

if __name__ == '__main__':
	app.run_server(debug=True)