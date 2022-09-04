# WhereToLive.LA

This is an interactive map based on /u/WilliamMcCarty's weekly spreadsheets of new rental listings in the /r/LArentals subreddit. Just like the actual spreadsheet, you can filter the map based on different criteria.

## The Tech Stack
* https://www.crummy.com/software/BeautifulSoup/bs4/doc/ (for webscraping MLS photos and links)
*    https://dash-leaflet.herokuapp.com/ (for displaying the map and graphing the markers)
*    https://dash-bootstrap-components.opensource.faculty.ai/ (for the website layout and icons)
*    GeoPyhttps://geopy.readthedocs.io/en/stable/ (for geocoding coordinates via the Google Maps API)
*    ImageKit (for resizing MLS photos into a standard size on the fly)
*    Pandas (for handling and manipulating the rental property data for each address)
