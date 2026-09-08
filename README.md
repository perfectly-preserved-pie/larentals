# [WhereToLive.LA](https://wheretolive.la)

## Table of contents

- [Public API and agent access](#public-api-and-agent-access)
- [MCP server](#mcp-server)
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

### Public API and agent access

[Developer guide](https://wheretolive.la/developers) ·
[OpenAPI specification](https://wheretolive.la/openapi.json) ·
[Agent instructions](https://wheretolive.la/llms.txt)

Public search uses the same read-only query as MCP and requires no API key:

```bash
curl 'https://wheretolive.la/api/listings?listing_type=lease&location=Pasadena&max_price=3000&page_size=5'
uv run wheretolive-search --listing-type lease --location Pasadena --max-price 3000 --page-size 5
```

Use `listing_type=buy` for homes for sale. Results include source links,
`data_as_of`, and pagination (at most 20 listings per page). The source CLI
prints JSON and exits nonzero on errors; it is not yet published separately
on a package registry. `wheretolive-la` remains the application server command.

Public content pages work without JavaScript and also support
`Accept: text/markdown`. Unknown page paths return Markdown with HTTP 404;
API failures return JSON with a stable error code, message, and hint.

To verify a running instance (all checks are read-only, including an invalid
report body that must be rejected before persistence):

```bash
uv sync --extra dev
uv run python -m scripts.verify_agent_endpoints --base-url http://127.0.0.1:8050
uv run pytest -q
npx playwright test tests/e2e/agent_readiness.spec.js tests/e2e/responsive_filters.spec.js
```

See [implementation and rollout notes](docs/agent-readiness.md) for audit
coverage and the remaining publishing, indexing, and organization decisions.

### MCP server

See the [MCP setup guide](https://wheretolive.la/mcp) for copyable Claude,
Hermes, and generic client instructions.

The endpoint supports the stateless MCP `2026-07-28` protocol and retains
Dash's initialization-based `2025-11-25` transport for legacy clients.


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
