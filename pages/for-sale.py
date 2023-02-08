import dash
from dash import html, dcc, callback
from dash.dependencies import Input, Output
from datetime import date
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_leaflet.express as dlx
import logging
import pandas as pd
import uuid

dash.register_page(
  __name__,
  path='/for-sale',
  name='WhereToLive.LA - For Sale',
  title='WhereToLive.LA - For Sale',
  description='An interactive map of available residential properties for sale in Los Angeles County. Updated weekly.',
)


logging.getLogger().setLevel(logging.INFO)

external_stylesheets = [dbc.themes.DARKLY, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME]

# Make the dataframe a global variable
global df

# import the dataframe pickle file
df = pd.read_pickle(filepath_or_buffer='forsale_dataframe.pickle')
pd.set_option("display.precision", 10)

title_card = dbc.Card(
  [
    html.H3("WhereToLive.LA", className="card-title"),
    html.P("An interactive map of available residential properties for sale in Los Angeles County. Updated weekly."),
    html.P(f"Last updated: yeah uhhhh lol what"),
    # Add an icon for the for-sale page
    html.I(
        className="fa-building fa",
        style = {
            "margin-right": "5px",
        },
    ),
    html.A("Looking to rent a property instead?", href='/'),
    # Use a GitHub icon for my repo
    html.I(
      className="bi bi-github",
      style = {
        "margin-right": "5px",
        "margin-left": "15px"
      },
    ),
    html.A("GitHub", href='https://github.com/perfectly-preserved-pie/larentals', target='_blank'),
    # Add an icon for my blog
    html.I(
      className="fa-solid fa-blog",
      style = {
        "margin-right": "5px",
        "margin-left": "15px"
      },
    ),
    html.A("About This Project", href='https://automateordie.io/wheretolivedotla/', target='_blank'),
  ],
  body = True
)

layout = dbc.Container([
  dbc.Row( # First row: title card
    [
      dbc.Col([title_card]),
    ]
  ),
  dbc.Row( # Second row: the rest
    [
      
      html.Img(src='https://i.kym-cdn.com/photos/images/newsfeed/000/002/109/orly_owl.jpg', style={'width': '100%'})
    ]
  ),
],
fluid = True,
className = "dbc"
)
