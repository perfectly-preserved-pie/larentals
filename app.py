from dash import Dash, _dash_renderer
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import request, jsonify
from loguru import logger
import dash
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import json
import logging
import os
import smtplib

# Set the React version to 18.2.0
# https://www.dash-mantine-components.com/getting-started#simple-usage
_dash_renderer._set_react_version("18.2.0")

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
  name = __name__, 
  # Add meta tags for mobile devices
  # https://community.plotly.com/t/reorder-website-for-mobile-view/33669/5?
  meta_tags = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1"}
  ],
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

# Create a custom route for handling the email sending of listing reports
@app.server.route('/report_listing', methods=['POST'])
def report_listing():
  data = request.get_json()
  mls_number = data.get('mls_number')
  option = data.get('option')
  text_report = data.get('text')
  properties = data.get('properties')
  
  # Build the plain text email body
  email_body = (
    f"Report for MLS: {mls_number}\n\n"
    f"Option: {option}\n\n"
    f"Details: {text_report}\n\n"
    f"Properties:\n{json.dumps(properties, indent=2)}"
  )
  
  sender = "report@wheretolive.la"
  receiver = "hey@wheretolive.la"
  
  # Create a MIMEMultipart message; can attach both text and html if needed
  msg = MIMEMultipart('mixed')
  msg["Subject"] = f"Listing Report: {mls_number}"
  msg["From"] = sender
  msg["To"] = receiver
  
  # Create plain text message part
  text_message = MIMEText(email_body, 'plain')
  msg.attach(text_message)
  
  # Send an HTML version as well
  # html_message = MIMEText(f"<pre>{email_body}</pre>", 'html')
  # msg.attach(html_message)
  
  # SMTP2GO configuration
  username = os.getenv("SMTP2GO_USERNAME")
  password = os.getenv("SMTP2GO_PASSWORD")
  smtp_host = "mail.smtp2go.com"
  smtp_port = 2525 
  
  try:
    mailServer = smtplib.SMTP(smtp_host, smtp_port)
    mailServer.ehlo()
    mailServer.starttls()
    mailServer.ehlo()
    mailServer.login(username, password)
    mailServer.sendmail(sender, receiver, msg.as_string())
    mailServer.quit()
    logger.success(
        f"Successfully sent report listing email for MLS: {mls_number}. Email body: {email_body}"
    )
    return jsonify(status="success"), 200
  except Exception as e:
    logger.error("Error sending email:", e)
    return jsonify(status="error", message=str(e)), 500

if __name__ == '__main__':
	app.run_server(debug=True)