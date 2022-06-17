from defusedxml import DTDForbidden
from requests import options
from yaml import compose
import plotly.express as px
from jupyter_dash import JupyterDash
import dash_core_components as dcc
from dash.dependencies import Input, Output
import dash
from dash import dcc
import dash_html_components as html
import dash_leaflet as dl
import folium
import pandas as pd
from geopy.geocoders import GoogleV3
from dotenv import load_dotenv, find_dotenv
import os

load_dotenv(find_dotenv())
g = GoogleV3(api_key=os.getenv(GOOGLE_API_KEY)) # https://github.com/geopy/geopy/issues/171

# import the csv
# Don't round the float. See https://stackoverflow.com/a/68027847
df = pd.read_csv("larentals.csv", float_precision="round_trip")
pd.set_option("display.precision", 10)

# Create a new column with the full street address
# Also strip whitespace from the St Name column
df["Full Street Address"] = df["St#"] + ' ' + df["St Name"].str.strip() + ',' + ' ' + df['City'] + ' ' + df["PostalCode"]

# Drop any rows with invalid data
df = df.dropna()

# Reindex the dataframe
df.reset_index(drop=True, inplace=True)

# Create a function to get coordinates from the full street address
def return_coordinates(address):
    try:
        geocode_info = g.geocode(address)
        lat = geocode_info.latitude
        lon = geocode_info.longitude
        coords = f"{lat}, {lon}"
    except Exception:
        lat = "NO COORDINATES FOUND"
        lon = "NO COORDINATES FOUND"
    return lat, lon, coords

# Fetch coordinates for every row
for row in df.itertuples():
    coordinates = return_coordinates(df.at[row.Index, 'Full Street Address'])
    df.at[row.Index, 'Latitude'] = coordinates[0]
    df.at[row.Index, 'Longitude'] = coordinates[1]
    df.at[row.Index, 'Coordinates'] = coordinates[2]


# Get the means so we can center the map
#lat_mean = df['Latitude'].mean()
#long_mean = df['Longitude'].mean()

# Define HTML code for the popup so it looks pretty and nice
def popup_html(row):
    i = row.Index
    street_address=df['Full Street Address'].iloc[i] 
    mls_number=df['Listing ID (MLS#)'].iloc[i]
    mls_number_hyperlink=f"https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/"
    lc_price = df['L/C Price'].iloc[i] 
    price_per_sqft=df['Price Per Square Foot'].iloc[i]                  
    brba = df['Br/Ba'].iloc[i]
    square_ft = df['Sqft'].iloc[i]
    year = df['YrBuilt'].iloc[i]
    garage = df['Garage Spaces'].iloc[i]
    pets = df['PetsAllowed'].iloc[i]
    phone = df['List Office Phone'].iloc[i]
    terms = df['Terms'].iloc[i]
    sub_type = df['Sub Type'].iloc[i]
    # Return the HTML snippet but NOT as a string. See https://github.com/thedirtyfew/dash-leaflet/issues/142#issuecomment-1157890463 
    return [
      html.Table([ # Create the table
        html.Tbody([ # Create the table body
          html.Tr([ # Start row #1
            html.Td("Street Address"), html.Td(f"{street_address}")
          ]), # end row #1
          html.Tr([ # Start row #2
            # Use a hyperlink to link to BHHS, don't use a referrer, and open the link in a new tab
            # https://www.freecodecamp.org/news/how-to-use-html-to-open-link-in-new-tab/
            html.Td("Listing ID (MLS#)"), html.Td(html.A(f"{mls_number}", href=f"{mls_number_hyperlink}", referrerPolicy='noreferrer', target='_blank'))
          ]), # end row #2
          html.Tr([ # Start row #3
            html.Td("L/C Price"), html.Td(f"{lc_price}")
          ]), # end row #3
          html.Tr([
            html.Td("Price Per Square Foot"), html.Td(f"{price_per_sqft}")
          ]),
          html.Tr([
            html.Td("Bedrooms/Bathrooms"), html.Td(f"{brba}")
          ]),
          html.Tr([
            html.Td("Square Feet"), html.Td(f"{square_ft}")
          ]),
          html.Tr([
            html.Td("Year Built"), html.Td(f"{year}")
          ]),
          html.Tr([
            html.Td("Garage Spaces"), html.Td(f"{garage}"),
          ]),
          html.Tr([
            html.Td("Pets Allowed?"), html.Td(f"{pets}"),
          ]),
          html.Tr([
            html.Td("List Office Phone"), html.Td(f"{phone}"),
          ]),
          html.Tr([
            html.Td("Rental Terms"), html.Td(f"{terms}"),
          ]),
          html.Tr([                                                                                            
            html.Td("Physical Sub Type"), html.Td(f"{sub_type}")                                                                                    
          ]), # end rows
        ]), # end body
      ]), # end table
    ]

# Create markers & associated popups from dataframe
markers = [dl.Marker(children=dl.Popup(popup_html(row)), position=[row.Latitude, row.Longitude]) for row in df.itertuples()]

# Add them to a MarkerCluster
cluster = dl.MarkerClusterGroup(id="markers", children=markers)

app = JupyterDash(__name__)

app.layout = html.Div([
  # Create a checklist of options for the user
  # https://dash.plotly.com/dash-core-components/checklist
  dcc.Checklist( 
      id = 'checklist',
      options=[
        {'label': 'Apartment (Attached)', 'value': 'APT/A'},
        {'label': 'Studio (Attached)', 'value': 'STUD/A'},
        {'label': 'Single Family Residence (Attached)', 'value': 'SFR/A'},
        {'label': 'Single Family Residence (Detached)', 'value': 'SFR/D'},
        {'label': 'Condo (Attached)', 'value': 'CONDO/A)'},
        {'label': 'Condo (Detached)', 'value': 'CONDO/D'},
        {'label': 'Quadplex (Attached)', 'value': 'QUAD/A'},
        {'label': 'Quadplex (Detached)', 'value': 'QUAD/D'},
        {'label': 'Triplex (Attached)', 'value': 'TPLX/A'},
        {'label': 'Townhouse (Attached)', 'value': 'TWNHS/A'},
        {'label': 'Townhouse (Detached)', 'value': 'TWNHS/D'},
        {'label': 'Duplex (Attached)', 'value': 'DPLX/A'},
        {'label': 'Duplex (Detached)', 'value': 'DPLX/D'},
        {'label': 'Ranch House (Detached)', 'value': 'RMRT/D'}
    ],
      value=['APT/A'] # Set the default value
  ),

  # Generate the map
  dl.Map(
    [dl.TileLayer(), cluster],
    id='map',
    zoom=3,
    center=(51, 10),
    style={'width': '100%', 'height': '50vh', 'margin': "auto", "display": "block"}
  )

])

@app.callback(
  Output(component_id='map', component_property='children'),
  Input(component_id='checklist', component_property='value')
)
def update_map(options_chosen):
  df_filtered = df[df['Sub Type'].isin(options_chosen)]

  # Create markers & associated popups from dataframe
  markers = [dl.Marker(children=dl.Popup(popup_html(row)), position=[row.Latitude, row.Longitude]) for row in df_filtered.itertuples()]

  # Add them to a MarkerCluster
  cluster = dl.MarkerClusterGroup(id="markers", children=markers)

  # Generate the map
  return dl.Map(
    [dl.TileLayer(), cluster],
    id='map',
    zoom=3,
    center=(51, 10),
    style={'width': '100%', 'height': '50vh', 'margin': "auto", "display": "block"}
  )



# Launch the Flask app
if __name__ == '__main__':
    app.run_server(mode='external', host='192.168.4.196', port='9208', debug='false')