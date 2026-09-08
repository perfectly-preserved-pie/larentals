"""Read-only smoke checks for local or deployed agent-facing HTTP endpoints."""

import argparse
from typing import Any
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate
import requests

from functions.public_content import BASE_URL, PAGES


def verify(base_url: str) -> list[str]:
    """Check public pages, machine files, REST operations, and both MCP eras.

    Args:
        base_url: Local or deployed origin to probe without writing listing reports.

    Returns:
        Human-readable verification outcomes; raises on any failed assertion.
    """
    session = requests.Session()
    results: list[str] = []

    def get(path: str, status: int = 200, **kwargs: Any) -> requests.Response:
        """Retrieve an endpoint with a timeout and assert its HTTP status.

        Args:
            path: URL path and optional query string.
            status: Expected HTTP status.
            **kwargs: Additional request options, such as representation headers.

        Returns:
            Response for content and schema assertions.
        """
        response = session.get(base_url.rstrip("/") + path, timeout=30, **kwargs)
        assert response.status_code == status, (path, response.status_code, response.text[:200])
        results.append(f"{status} GET {path}")
        return response

    for path in PAGES:
        response = get(path)
        document = BeautifulSoup(response.text, "html.parser")
        assert document.html["lang"] == "en"
        assert len(document.main.get_text(" ", strip=True)) >= 500
        assert len(document.select("main h1")) == 1
        assert document.select_one('link[rel="canonical"]')["href"] == BASE_URL + path
        images = document.select('meta[property="og:image"]')
        assert len(images) == 1 and images[0]["content"] == BASE_URL + "/assets/social-card.png"
        markdown = get(path, headers={"Accept": "text/markdown", "Accept-Encoding": "gzip"})
        assert markdown.headers["Content-Type"].startswith("text/markdown")
        assert markdown.text.startswith("# ")
        for variant in (response, markdown):
            assert "accept" in variant.headers["Vary"].lower()
        get(path, status=406, headers={"Accept": "application/json"})
    assert get("/assets/social-card.png").content.startswith(b"\x89PNG")
    assert get("/some-path-that-does-not-exist", 404).headers["Content-Type"].startswith("text/markdown")
    assert get("/api/no-such-endpoint", 404).json()["error"]["hint"]
    assert get("/api/listings", 400).json()["error"]["code"] == "invalid_request"
    assert get("/report_listing", 405).json()["error"]["hint"]
    assert get("/api").json()["openapi"] == BASE_URL + "/openapi.json"
    assert "When to use this" in get("/llms.txt").text
    assert "Sitemap: " + BASE_URL + "/sitemap.xml" in get("/robots.txt").text
    sitemap = ElementTree.fromstring(get("/sitemap.xml").content)
    urls = {node.text for node in sitemap.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
    assert urls == {BASE_URL + path for path in PAGES}
    get("/health")
    spec = get("/openapi.json").json()
    validate(spec)
    for market in ("lease", "buy"):
        search = get(f"/api/listings?listing_type={market}&page_size=2").json()
        Draft202012Validator(spec["components"]["schemas"]["ListingSearchResult"]).validate(search)
        assert search["listings"], "Cannot verify listing details with an empty dataset"
        listing_id = requests.utils.quote(search["listings"][0]["mls_number"], safe="")
        for suffix in ("listing-details", "isp-options"):
            response = get(f"/api/{market}/{suffix}/{listing_id}")
            schema = spec["paths"][f"/api/{market}/{suffix}/{{listing_id}}"]['get']['responses']['200']['content']['application/json']['schema']
            Draft202012Validator(schema).validate(response.json())
        get(f"/api/{market}/listing-details/definitely-not-a-listing", 404)
    # Invalid body checks validation without inserting a report into the database.
    invalid_report = session.post(base_url + "/report_listing", json={}, timeout=30)
    assert invalid_report.status_code == 400
    Draft202012Validator(spec["components"]["schemas"]["Error"]).validate(invalid_report.json())
    results.append("400 POST /report_listing (invalid body; no write)")
    initialize = session.post(base_url + "/_mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "readiness-check", "version": "1.0"}}}, timeout=30)
    assert initialize.status_code == 200
    assert "resources" not in initialize.json()["result"]["capabilities"]
    headers = {"Mcp-Session-Id": initialize.headers["Mcp-Session-Id"], "MCP-Protocol-Version": "2025-11-25"}
    tool_list = session.post(base_url + "/_mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, timeout=30)
    assert [tool["name"] for tool in tool_list.json()["result"]["tools"]] == ["search_listings"]
    modern = session.post(base_url + "/_mcp", headers={"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "server/discover"}, json={"jsonrpc": "2.0", "id": 3, "method": "server/discover", "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientInfo": {"name": "readiness-check", "version": "1.0"}, "io.modelcontextprotocol/clientCapabilities": {}}}}, timeout=30)
    assert modern.status_code == 200 and "tools" in modern.json()["result"]["capabilities"]
    results.append("200 POST /_mcp (legacy initialize/tools list and modern discovery)")
    return results


def main() -> None:
    """Run the endpoint audit against an explicitly selectable origin.

    Returns:
        None; assertion or request failures produce a nonzero process exit.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8050")
    results = verify(parser.parse_args().base_url.rstrip("/"))
    print("\n".join(results))
    print(f"Verified {len(results)} endpoint responses and both MCP transports.")


if __name__ == "__main__":
    main()
