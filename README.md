# [WhereToLive.LA](https://wheretolive.la)
- [What I'm Using](#what-im-using)
- [A Deeper Dive](#a-deeper-dive)
- [How to Build and Run](#how-to-build-and-run)
  - [Docker](#docker)
  - [Non-Docker](#non-docker)
 
[![CodeQL](https://github.com/perfectly-preserved-pie/larentals/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/perfectly-preserved-pie/larentals/actions/workflows/codeql-analysis.yml)

[![Build image and publish to DockerHub](https://github.com/perfectly-preserved-pie/larentals/actions/workflows/docker-image.yml/badge.svg)](https://github.com/perfectly-preserved-pie/larentals/actions/workflows/docker-image.yml)

[![Build and Publish - Dev Build](https://github.com/perfectly-preserved-pie/larentals/actions/workflows/docker-image-dev.yml/badge.svg?branch=dev)](https://github.com/perfectly-preserved-pie/larentals/actions/workflows/docker-image-dev.yml)

This is an interactive map based on /u/WilliamMcCarty's and /u/TannerBeyer's weekly spreadsheets of new rental & for-sale listings in the /r/LArentals & /r/LosAngelesRealEstate subreddits. Just like the actual spreadsheets, you can filter the map based on different criteria, such as
* Monthly rent/List price
* Security deposit cost
* Number of bedrooms
* Number of garage spaces
* Pet Policy
* Square footage
* HOA fees (for-sale properties only)
* and more!

Some additional capabilities are offered, such as a featured MLS photo for the property and a link to the associated MLS listing page (if available).

### County map layers

The map layer control includes two selectable basemaps and an optional parcel overlay:

* **Street map** uses the canonical [OpenStreetMap raster tile service](https://operations.osmfoundation.org/policies/tiles/) with visible license attribution and a [report-a-map-issue link](https://www.openstreetmap.org/fixthemap).
* **LA County aerial (2023)** uses the public four-inch LARIAC7 orthophoto [WMTS item](https://www.arcgis.com/home/item.html?id=b301429f8bc1469bb2bbd5a6c3330abe), credited to LARIAC, EagleView, and Los Angeles County Enterprise GIS.
* **Parcel boundaries** uses the cached [LA County Assessor parcel map service](https://www.arcgis.com/home/item.html?id=5b277305f006459586a70165065d0fd6).

Tiles are requested by the user's browser directly from the upstream services; this project does not download, cache, or redistribute the imagery or countywide parcel tiles. Use of the County services remains subject to the [LA County Enterprise GIS terms](https://egis-lacounty.hub.arcgis.com/pages/terms-of-use) and each source item's license information.

The Dash MCP endpoint is available at `https://wheretolive.la/_mcp` for MCP clients that support Streamable HTTP.

You can click the toggle buttons next to the title to switch between For Rent and For Sale listings:

![image](https://github.com/user-attachments/assets/0d58d43a-0722-4bd2-9914-786b0f5e0dcf)




**⚠ This website is mobile-friendly but I highly recommend using an actual computer or tablet for the best experience**

## What I'm Using
* [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) (webscraping MLS photos and links)
*    [Dash Leaflet](https://dash-leaflet.herokuapp.com/) (displaying the map and graphing the markers)
*    [Dash Bootstrap Components](https://dash-bootstrap-components.opensource.faculty.ai/) (the website layout and icons)
*    [GeoPy](https://geopy.readthedocs.io/en/stable/) (geocoding coordinates via the Google Maps API)
*    [ImageKit](https://github.com/imagekit-developer/imagekit-python) (resizing MLS photos into a standard size on the fly)
*    [Pandas](https://pandas.pydata.org/) (handling and manipulating the rental property data for each address)

## A Deeper Dive
[I made a post detailing my idea, progress, challenges, etc.](hhttps://automateordie.dev/wheretolivedotla/)

## How to Build and Run
1. Clone the repo `git clone https://github.com/perfectly-preserved-pie/larentals.git`
2. `cd` into the new directory
3. Run `uv run wheretolive-la`. `uv` will install the project into its managed environment and expose the configured CLI commands from `pyproject.toml`.

### Docker

Build the app image:

```bash
docker build -t larentals .
```

Run the app container:

```bash
docker run --rm -p 8080:8080 larentals
```

### Non-Docker

Run the Dash app directly:

```bash
uv run wheretolive-la
```
