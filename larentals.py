import plotly.express as px
from jupyter_dash import JupyterDash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output
import folium
import pandas as pd
from geopy.geocoders import GoogleV3
from dotenv import load_dotenv, find_dotenv
import os

load_dotenv(find_dotenv())
g = GoogleV3(api_key=os.getenv(GOOGLE_API_KEY)) # https://github.com/geopy/geopy/issues/171

# import the csv
df = pd.read_csv("~/rentals.csv")

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
        lat = g.geocode(address).latitude
        lon = g.geocode(address).longitude
    except Exception:
        lat = "NO COORDINATES FOUND"
        lon = "NO COORDINATES FOUND"
    return lat, lon

# Fetch coordinates for every row
for row in df.itertuples():
    coordinates = return_coordinates(df.at[row.Index, 'Full Street Address'])
    df.at[row.Index, 'Latitude'] = coordinates[0]
    df.at[row.Index, 'Longitude'] = coordinates[1]

# Convert the string of coordinates into a list
# So that folium can understand it when we plot it later
# https://stackoverflow.com/a/64232799
df['Full Coordinates'] = df['Full Coordinates'].str.split(',')

# Split out the lat and lon
# And remove the comma in the latitude
# And strip whitespaces
# https://www.skytowner.com/explore/removing_characters_from_columns_in_pandas_dataframe
# https://datascienceparichay.com/article/pandas-split-column-by-delimiter/
#df['Latitude'] = 
#df['Longitude'] = df['Coordinates'][1].str.strip()



# Convert lat and lon columns to integers
# https://www.geeksforgeeks.org/python-pandas-to_numeric-method/
#df['Latitude'] = df['Latitude'].apply(pd.to_numeric)
#df['Longitude'] = df['Longitude'].apply(pd.to_numeric)

# Get the means so we can center the map
#lat_mean = df['Latitude'].mean()
#long_mean = df['Longitude'].mean()

# Count how many we couldn't get coords for
#df['Coordinates'].value_counts()['NO COORDINATES FOUND']

# Define HTML code for the popup so it looks pretty and nice
# https://gist.githubusercontent.com/insightsbees/f984e5b739010fe42f5cff6f66bee822/raw/8fe8d18992cde0b4776b1a6750a4e4e19d9acb46/Define%20popup_html%20function.py
# https://towardsdatascience.com/folium-map-how-to-create-a-table-style-pop-up-with-html-code-76903706b88a
# Generate an HTML table using https://www.tablesgenerator.com/html_tables
def popup_html(row):
    i = row.Index
    street_address=df['Full Street Address'].iloc[i] 
    mls_number=df['Listing ID (MLS#)'].iloc[i]
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

    html = f"""<!DOCTYPE html>
<table style="undefined;table-layout: fixed; width: 777px">
<colgroup>
<col style="width: 188px">
<col style="width: 589px">
</colgroup>
<tbody>
  <tr>
    <td>Street Address</td>
    <td>{street_address}</td>
  </tr>
  <tr>
    <td>Listing ID (MLS#)</td>
    <td><a href="https://www.bhhscalifornia.com/for-lease/{mls_number}-t_q;/" rel="noreferrer">{mls_number}</a></td>
  </tr>
  <tr>
    <td>Rent (per month)</td>
    <td>{lc_price}</td>
  </tr>
  <tr>
    <td>Square Feet</td>
    <td>{square_ft}</td>
  </tr>
  <tr>
    <td>Price Per Square Foot</td>
    <td>{price_per_sqft}</td>
  </tr>
  <tr>
    <td>Bedrooms/Bathrooms</td>
    <td>{brba}</td>
  </tr>
  <tr>
    <td>Year Built</td>
    <td>{year}</td>
  </tr>
  <tr>
    <td>Garage Spaces<br></td>
    <td>{garage}</td>
  </tr>
  <tr>
    <td>Pets Allowed?<br></td>
    <td>{pets}</td>
  </tr>
  <tr>
    <td>List Office Phone Number<br></td>
    <td>{phone}</td>
  </tr>
  <tr>
    <td>Rental Terms</td>
    <td>{terms}</td>
  </tr>
  <tr>
    <td>Rental Unit Type<br></td>
    <td>{sub_type}</td>
  </tr>
</tbody>
</table>
"""
    return html

# Dynamically generate the Folium HTML popup code for each row
for row in df.itertuples():
    df.at[row.Index, 'Folium HTML Snippet'] = popup_html(row)

# Set up a Folium map
# Use the mean of the latitude and longitude coords to center the map
map = folium.Map(location=[34.02865653675504, -118.42546831279408], zoom_start=14, control_scale=True)

### Now we need to add markers for every group
# Create a Folium feature group for pets
pets_fg = folium.FeatureGroup(name="Pets Allowed")
# Iterate over only the rows that allow pets and add markers to the feature group
for row in df.loc[df['PetsAllowed'] != 'No'].itertuples():
    pets_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] )) 
# Add this feature group to the map
map.add_child(pets_fg)

# Create a Folium feature group for pets
no_pets_fg = folium.FeatureGroup(name="Pets Not Allowed")
# Iterate over only the rows that allow pets and add markers to the feature group
for row in df.loc[df['PetsAllowed'] == 'No'].itertuples():
    no_pets_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] )) 
# Add this feature group to the map
map.add_child(no_pets_fg)

## RENTAL TERMS ##
# Create a Folium group for month-to-month rental terms
terms_mo_fg = folium.FeatureGroup(name="Lease Length: Monthly")
# Iterate over only the rows that have monthly terms and add markers to the feature group
for row in df.loc[df['Terms'] == 'MO'].itertuples():
    terms_mo_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] )) 
map.add_child(terms_mo_fg)

# Create a Folium feature group for yearly rental terms
terms_12mo_fg = folium.FeatureGroup(name="Lease Length: 12 Months")
# Iterate over only the rows that have yearly terms and add markers to the feature group
for row in df.loc[df['Terms'] == '12M'].itertuples():
    terms_12mo_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] )) 
# Add this feature group to the map
map.add_child(terms_12mo_fg)

# Create a Folium group for 2 year rental terms
terms_2yr_fg = folium.FeatureGroup(name="Lease Length: 24 Months")
# Iterate over only the rows that have 2 year terms and add markers to the feature group
for row in df.loc[df['Terms'] == '24M'].itertuples():
    terms_2yr_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))  
map.add_child(terms_2yr_fg)

# Create a Folium group for negotiable rental terms
terms_ng_fg = folium.FeatureGroup(name="Lease Length: Negotiable")
# Iterate over only the rows that have negotiable terms and add markers to the feature group
for row in df.loc[df['Terms'] == 'NG'].itertuples():
    terms_ng_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))  
map.add_child(terms_ng_fg)
## RENTAL TERMS END ##

## SUB TYPES ##
# Create a Folium feature group for apartments
apt_fg = folium.FeatureGroup(name="Apartment")
# Iterate over only the rows that are apartments and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'APT/A'].itertuples():
    apt_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] )) 
# Add this feature group to the map
map.add_child(apt_fg)

# Create a Folium feature group for studios
studio_fg = folium.FeatureGroup(name="Studio")
# Iterate over only the rows that are apartments and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'STUD/A'].itertuples():
    studio_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] )) 
# Add this feature group to the map
map.add_child(studio_fg)

# Create a Folium feature group for attached SFRs and misc??? SFRs
sfr_fg = folium.FeatureGroup(name="Single Family Residence")
# Iterate over only the rows that are SFR and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'SFR'].itertuples():
    sfr_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] )) 
# Iterate over only the rows that are SFR/A and add markers to the feature group too
for row in df.loc[df['Sub Type'] == 'SFR/A'].itertuples():
    sfr_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] )) 
# Add this feature group to the map
map.add_child(sfr_fg)

# Create a Folium feature group for detached SFRs
sfr_a_fg = folium.FeatureGroup(name="Single Family Residence (Attached)")
# Iterate over only the rows that are apartments and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'SFR/D'].itertuples():
    sfr_a_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] )) 
# Add this feature group to the map
map.add_child(sfr_a_fg)

# Create a Folium feature group for attached and misc??? condos
condo_fg = folium.FeatureGroup(name="Condo (Attached)")
# Iterate over only the rows that are attached condos and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'CONDO/A'].itertuples():
    condo_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))
# Iterate over only the rows that are CONDO and add markers to the feature group too
for row in df.loc[df['Sub Type'] == 'CONDO'].itertuples():
    condo_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] )) 
# Add this feature group to the map
map.add_child(condo_fg)

# Create a Folium feature group for detached condos
condo_d_fg = folium.FeatureGroup(name="Condo (Detached)")
# Iterate over only the rows that are detached condos and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'CONDO/D'].itertuples():
    condo_d_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))
# Add this feature group to the map
map.add_child(condo_d_fg)

# Create a Folium feature group for attached quadplexes
quad_fg = folium.FeatureGroup(name="Quadplex (Attached)")
# Iterate over only the rows that are attached quadplexes and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'QUAD/A'].itertuples():
    quad_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))
# Add this feature group to the map
map.add_child(quad_fg)

# Create a Folium feature group for detached quadplexes
quad_d_fg = folium.FeatureGroup(name="Quadplex (Detached)")
# Iterate over only the rows that are detached quadplexes and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'QUAD/D'].itertuples():
    quad_d_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))
# Add this feature group to the map
map.add_child(quad_d_fg)

# Create a Folium feature group for attached triplexes
triplex_fg = folium.FeatureGroup(name="Triplex (Attached)")
# Iterate over only the rows that are attached triplexes and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'TPLX/A'].itertuples():
    triplex_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))
# Add this feature group to the map
map.add_child(triplex_fg)

# Create a Folium feature group for attached townhouses
townhouse_a_fg = folium.FeatureGroup(name="Townhouse (Attached)")
# Iterate over only the rows that are attached townhouses and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'TWNHS/A'].itertuples():
    townhouse_a_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))
# Add this feature group to the map
map.add_child(townhouse_a_fg)

# Create a Folium feature group for detached townhouses
townhouse_d_fg = folium.FeatureGroup(name="Townhouse (Detached)")
# Iterate over only the rows that are detached townhouses and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'TWNHS/D'].itertuples():
    townhouse_d_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))
# Add this feature group to the map
map.add_child(townhouse_d_fg)

# Create a Folium feature group for attached duplexes
duplex_a_fg = folium.FeatureGroup(name="Duplex (Attached)")
# Iterate over only the rows that are attached duplexes and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'DPLX/A'].itertuples():
    duplex_a_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))
# Add this feature group to the map
map.add_child(duplex_a_fg)

# Create a Folium feature group for detached duplexes
duplex_d_fg = folium.FeatureGroup(name="Duplex (Detached)")
# Iterate over only the rows that are detached duplexes and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'DPLX/D'].itertuples():
    duplex_d_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))
# Add this feature group to the map
map.add_child(duplex_d_fg)

# Create a Folium feature group for detached ranch style house
ranch_d_fg = folium.FeatureGroup(name="Ranch House (Detached)")
# Iterate over only the rows that are detached ranch style houses and add markers to the feature group
for row in df.loc[df['Sub Type'] == 'RMRT/D'].itertuples():
    ranch_d_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))
# Add this feature group to the map
map.add_child(ranch_d_fg)

# Iterate over the new dataframe and add all the markers to the pets feature group
# https://github.com/BenjaRogers/Police-Violence/blob/0a3aab9f777283cb8c94902268a5689e284b89c1/shootings/shootings/shootings%2040.py
#for row in df_pets.itertuples():
#    pets_fg.add_child(folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ))



#for row in df.loc[df['PetsAllowed'] != 'No'].itertuples():
#    folium.Marker(location=[df.at[row.Index, 'Coordinates'][0], df.at[row.Index, 'Coordinates'][1]], popup = df.at[row.Index, 'Folium HTML Snippet'] ).add_to(map)    



# Add a layer control panel to the map
map.add_child(folium.LayerControl())



app = JupyterDash(__name__)