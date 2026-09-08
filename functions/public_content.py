"""Shared, factual content for raw HTML and negotiated Markdown pages."""

from html import escape

BASE_URL = "https://wheretolive.la"
SOURCE_URL = "https://github.com/perfectly-preserved-pie/larentals"
# Each section has a heading and paragraphs. Both representations use this source.
PAGES: dict[str, tuple[str, list[tuple[str, list[str]]]]] = {
    "/": ("WhereToLive.LA — Los Angeles rental map", [
        ("Find a rental in Los Angeles County", [
            "WhereToLive.LA is an interactive map of rental and for-sale housing listings in Los Angeles County. It brings the weekly spreadsheets shared by /u/WilliamMcCarty and /u/TannerBeyer in /r/LArentals and /r/LosAngelesRealEstate into a map you can search and filter. The rental map helps you compare monthly rent, bedrooms, bathrooms, square footage, deposits, parking, and pet policies.",
            "Enable JavaScript to explore the interactive map, open property photos, and follow source listing links. Switch to the for-sale map to compare asking prices, lot sizes, garage spaces, and HOA fees. Optional map layers provide nearby context. A listing in the dataset is not a guarantee that a property is still available; check the source listing and contact its representative before making plans.",
        ]),
        ("Search with an assistant or API", [
            "The public listing search API and MCP search_listings tool return paginated results with source URLs and a data_as_of date. No account or API key is required. Start with the developer guide for filters, example requests, and response schemas. Cite WhereToLive.LA together with the source listing and include the returned data date when sharing results.",
        ]),
    ]),
    "/buy": ("WhereToLive.LA — Los Angeles homes for sale", [
        ("Compare homes for sale", [
            "Explore for-sale housing listings in Los Angeles County with WhereToLive.LA. The interactive map organizes the weekly source spreadsheets into properties that can be compared by asking price, bedrooms, bathrooms, square footage, lot size, garage spaces, and HOA fees. Open a property to review available details, photos, and its source listing link.",
            "Enable JavaScript to use the map and its filters. For programmatic searches, request the public API with listing_type=buy or call the MCP search_listings tool. Sale prices describe asking prices, not monthly rent. Listings and neighborhood context may be incomplete or change between updates. Verify fees, availability, and property details with the listing representative before relying on them.",
        ]),
    ]),
    "/mcp": ("Connect WhereToLive.LA to your AI assistant", [
        ("Public MCP listing search", [
            "Connect an MCP client using Streamable HTTP at https://wheretolive.la/_mcp. No API key or account is required. The server exposes the read-only search_listings tool for Los Angeles County rentals and homes for sale. It is a tool-only server; layout and callback resources are not exposed.",
            "Set listing_type to lease or buy. Use location for a city, ZIP code, neighborhood, or address fragment; max_price means monthly rent for lease searches and asking price for buy searches. Results include source links, data_as_of, and pagination. Use page_size up to 20 and increment page while has_next_page is true. Do not infer present availability from inclusion in the dataset.",
            "The endpoint supports the stateless 2026-07-28 protocol and initialization-based 2025-11-25 clients. In a client with a remote MCP connection dialog, enter the endpoint URL and select Streamable HTTP. The interactive setup page includes copyable client configuration. REST clients can instead use the developer guide and OpenAPI specification.",
        ]),
    ]),
    "/about": ("About WhereToLive.LA", [
        ("A map built from community listing spreadsheets", [
            "WhereToLive.LA helps people explore rentals and homes for sale in Los Angeles County. The project turns the weekly listing spreadsheets shared by /u/WilliamMcCarty and /u/TannerBeyer in /r/LArentals and /r/LosAngelesRealEstate into an interactive, filterable map. Available fields include prices, bedrooms, property sizes, parking information, and links back to source listings.",
            "The project combines these listings with optional geographic context so visitors can investigate places that interest them. Coverage and freshness vary by source. Missing values mean information is unavailable, and a map marker does not establish current availability or confirm the accuracy of every listing detail. Consult the linked source and listing representative for confirmation.",
        ]),
        ("Project and feedback", [
            "The source repository documents the application and data pipelines. Questions about the project or corrections can be sent to hey@wheretolive.la. Developers and assistants can use the public REST API or MCP search tool to retrieve the same listing dataset in bounded pages without an account.",
        ]),
    ]),
    "/contact": ("Contact WhereToLive.LA", [
        ("Reach the project", [
            "Email hey@wheretolive.la for questions about WhereToLive.LA, technical problems, feedback, or requests concerning information displayed on the site. Include the page URL and a short description of what happened. For a listing issue, include its MLS number or source listing URL so the relevant record can be located. Avoid sending identity documents, payment information, or other sensitive personal details.",
            "The map also provides a listing report option for incorrect locations, unavailable properties, wrong details, and incorrect prices. Reports help identify problems in the displayed dataset. They do not contact the property representative or change the original source listing automatically. For tours, applications, pricing confirmation, and availability, use the contact information on the linked source listing.",
        ]),
        ("Developer questions", [
            "For API or MCP issues, include the endpoint, HTTP status, and a minimal example with private information removed. Public documentation explains supported filters, pagination, and errors. The GitHub repository provides implementation details and an issue tracker for technical reports. No response time or support service level is promised.",
        ]),
    ]),
    "/privacy": ("WhereToLive.LA privacy information", [
        ("Information used by the application", [
            "The public maps and listing search do not require an account. Listing data comes from source spreadsheets and linked property records. If you submit a listing report, the application stores the MLS number, listing type, selected reason, written details, page path, and report timestamp in its database. Reports are used to investigate listing issues. Do not include sensitive personal information in report text.",
            "The browser stores the selected light or dark theme in local storage. The site loads Plausible analytics from plausible.automateordie.dev and sends page and interaction events. Maps, imagery, fonts, scripts, and property photos may be requested from external providers; those providers receive the network information needed to serve their content. Following a source listing link takes you to a separate site's privacy practices.",
        ]),
        ("Operational records and requests", [
            "The application logs MCP tool calls, including bounded tool arguments, response summaries, timing, and user-agent information. Listing report details are also logged for maintenance. Hosting infrastructure may retain request logs. This page describes the application's observable behavior; it does not promise a retention period for every hosting or third-party service. For privacy questions or requests relating to a report you submitted, contact hey@wheretolive.la with enough context to locate the record and avoid adding unnecessary personal data.",
        ]),
    ]),
    "/developers": ("WhereToLive.LA developer guide and public API", [
        ("When to use this API", [
            "Use WhereToLive.LA to shortlist Los Angeles County rentals or homes for sale by price, location, bedrooms, and property characteristics. The API searches the same database as the MCP tool. It does not book tours, submit applications, or guarantee current availability. Return source listing links and data_as_of with your answer. Null fields are unknown, not zero or false.",
        ]),
        ("REST API", [
            "The public API requires no account, API key, or Authorization header. Send GET /api/listings?listing_type=lease&location=Pasadena&max_price=3000&page_size=5. Use listing_type=buy for sales. The OpenAPI 3.1 document at /openapi.json defines every supported query parameter and response schema. GET /api returns discovery links. All search requests are read-only.",
        ]),
        ("Filters and pagination", [
            "Required: listing_type (lease or buy). Optional: location, property_type, min_price, max_price, min_bedrooms, min_bathrooms, min_square_feet, pet_friendly, furnished, min_lot_size, max_hoa_fee, senior_community, listed_after, sort, page, and page_size. Location is a text match against city, ZIP, and address, not a radius search. Numeric filters are nonnegative integers; booleans are true or false. Dates use YYYY-MM-DD. Furnished is lease-only; lot size, HOA fee, and senior community are buy-only.",
            "Sort is newest (default), price_low_to_high, price_high_to_low, most_bedrooms, or largest. Pages start at 1 and are limited to 10000; page_size defaults to 10 and is limited to 20. Increment page while has_next_page is true. An empty result is a successful 200 response. Prices are USD monthly rent for leases and USD asking price for sales. data_as_of is the latest processing date in the selected dataset, not a real-time availability timestamp.",
        ]),
        ("Details, errors, and usage", [
            "Use GET /api/{listing_type}/listing-details/{listing_id} for property details and GET /api/{listing_type}/isp-options/{listing_id} for available broadband context, substituting lease or buy and an MLS number returned by search. POST /report_listing submits a correction report and writes to the database; only submit one when a person has identified an actual issue. Its request schema is in OpenAPI.",
            "Errors include status, message, and error with code, message, and hint. Correct parameters after a 400, check paths or identifiers after a 404, and retry later after a 500 or 503. The REST API has bounded pagination but no application-level request quota or service-level guarantee. Use modest concurrency and cache results for repeated questions. The modern MCP transport limits tool calls to 120 per peer per worker per 60 seconds; honor Retry-After on 429 responses.",
        ]),
        ("MCP", [
            "Connect an MCP client to https://wheretolive.la/_mcp and call search_listings. It is a tool-only service. The dedicated MCP setup page provides copyable client configurations and connection instructions.",
        ]),
        ("CLI", [
            "From a source checkout, run uv run wheretolive-search --listing-type lease --location Pasadena --max-price 3000 --page-size 5. The command prints JSON from the public REST API and exits with a nonzero status on errors. The CLI is included in the project; registry publication is not yet configured.",
        ]),
        ("Markdown", [
            "Public content pages support Accept: text/markdown and vary their cache by Accept. Unsupported content types receive 406. The sitemap and llms.txt list the public guides.",
        ]),
    ]),
}
LINKS = [("Rental map", "/"), ("For-sale map", "/buy"), ("Developers", "/developers"),
         ("About", "/about"), ("Contact", "/contact"), ("Privacy", "/privacy"),
         ("Sitemap", "/sitemap.xml"), ("Agent instructions", "/llms.txt")]

DEVELOPER_LINKS = [("REST API", "/developers#rest-api"), ("MCP", "/mcp"),
                   ("CLI", "/developers#cli"), ("OpenAPI specification", "/openapi.json")]
SECTION_IDS = {"REST API": "rest-api", "CLI": "cli"}


def page_markdown(path: str) -> str:
    """Render a complete content page as Markdown.

    Args:
        path: Canonical page path present in PAGES.

    Returns:
        Markdown with sequential headings and absolute discovery links.
    """
    title, sections = PAGES[path]
    lines = [f"# {title}", ""]
    if path == "/developers":
        lines.extend(["## Developer resources", "", *[f"- [{label}]({BASE_URL}{url})" for label, url in DEVELOPER_LINKS], ""])
    for heading, paragraphs in sections:
        lines.extend([f"## {heading}", "", *[p + "\n" for p in paragraphs]])
    lines.extend(["## Links", "", *[f"- [{label}]({BASE_URL}{url})" for label, url in LINKS],
                  f"- [Source repository]({SOURCE_URL})", "- [Email](mailto:hey@wheretolive.la)", ""])
    return "\n".join(lines)


def page_html(path: str) -> str:
    """Render shared prose as a semantic, script-independent content section.

    Args:
        path: Canonical page path present in PAGES.

    Returns:
        Escaped HTML suitable for a standalone page or Dash loading entry.
    """
    title, sections = PAGES[path]
    parts = [f'<main class="public-content" id="public-content"><h1>{escape(title)}</h1>']
    if path == "/developers":
        parts.append('<nav aria-label="Developer resources"><ul>')
        parts.extend(f'<li><a href="{url}">{escape(label)}</a></li>' for label, url in DEVELOPER_LINKS)
        parts.append('</ul></nav>')
    for heading, paragraphs in sections:
        section_id = f' id="{SECTION_IDS[heading]}"' if heading in SECTION_IDS else ""
        parts.append(f"<section{section_id}><h2>{escape(heading)}</h2>")
        parts.extend(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
        parts.append("</section>")
    if path == "/developers":
        parts.append('<section><h2>Try a read-only search</h2><form action="/api/listings" method="get">'
                     '<label>Market <select name="listing_type"><option value="lease">Rentals</option>'
                     '<option value="buy">For sale</option></select></label> '
                     '<label>Location <input name="location" value="Pasadena" maxlength="100"></label> '
                     '<input type="hidden" name="page_size" value="5"><button type="submit">Search JSON</button>'
                     '</form><pre><code>curl "https://wheretolive.la/api/listings?listing_type=lease&amp;page_size=5"</code></pre></section>')
    parts.append('<nav aria-label="Site resources"><h2>Links</h2><ul>')
    parts.extend(f'<li><a href="{url}">{escape(label)}</a></li>' for label, url in LINKS)
    parts.append(f'<li><a href="{SOURCE_URL}">Source repository</a></li>'
                 '<li><a href="mailto:hey@wheretolive.la">hey@wheretolive.la</a></li></ul></nav></main>')
    return "".join(parts)
