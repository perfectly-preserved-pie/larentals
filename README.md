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
[I made a post detailing my idea, progress, challenges, etc.](https://automateordie.io/blog/2023/08/26/wheretolivela/)

## How to Build and Run
### Docker
1. Pull the Docker image: `docker pull strayingfromthepath:larentals`
3. Run the Docker image: `docker run -p 1337:80 larentals`
4. The Dash app will be accessible at `$HOST:1337`

### Non-Docker
1. Clone the repo `git clone https://github.com/perfectly-preserved-pie/larentals.git`
2. `cd` into the new directory
3. Install requirements with `pip install -r requirements.txt`
4. Launch the webserver with `gunicorn -b 0.0.0.0:8050 --workers=4 app:server` or `python3 app.py` for the default Dash webserver.
6. Have fun
