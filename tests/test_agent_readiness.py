"""HTTP regression tests for agent discovery, schemas, and app compatibility."""

from collections.abc import Iterator
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup
from dash import Dash, html
from flask.testing import FlaskClient
from flask_compress import Compress
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate
import pytest

from api import register_api_routes
from api.public import build_openapi, register_api_errors, register_public_api
from functions.public_content import BASE_URL, PAGES
from functions.public_routes import register_public_pages
from functions.seo import build_structured_data_script
from scripts.search_cli import main
from test_mcp_listings import listing_db  # noqa: F401: shared database fixture


@pytest.fixture()
def client(listing_db: Path) -> Iterator[FlaskClient]:
    """Serve production route registration against an isolated test database.

    Args:
        listing_db: Small rental and sale database with deterministic records.

    Yields:
        Client exercising Dash's real catch-all and all API handlers.
    """
    app = Dash(__name__, assets_folder=str(Path("assets").resolve()), meta_tags=[{"property": "og:image", "content": ""}])
    app.index_string = app.index_string.replace('<html>', '<html lang="en">')
    app.layout = html.Div("Interactive map placeholder", id="map")
    app.server.config.update(TESTING=True, COMPRESS_MIMETYPES=["text/html", "text/markdown", "application/json"])
    Compress(app.server)
    register_api_errors(app.server)
    register_api_routes(app.server, str(listing_db))
    register_public_api(app.server, str(listing_db), BASE_URL)
    register_public_pages(app)
    with app.server.test_client() as test_client:
        yield test_client


@pytest.mark.parametrize("path", PAGES)
def test_pages_have_readable_content_and_metadata(client: FlaskClient, path: str) -> None:
    """Make every public page useful to an ordinary client without scripts.

    Args:
        client: App HTTP client with production page handlers.
        path: Public page to retrieve in HTML and Markdown.

    Returns:
        None.
    """
    response = client.get(path + "?utm_source=test")
    assert response.status_code == 200
    document = BeautifulSoup(response.data, "html.parser")
    main_element = document.select_one("main#public-content")
    assert len(main_element.get_text(" ", strip=True)) > 500
    assert len(main_element.select("h1")) == 1
    assert all(tag.name in {"h1", "h2"} for tag in main_element.select("h1,h2,h3,h4,h5,h6"))
    assert document.html["lang"] == "en"
    assert document.select_one('link[rel="canonical"]')["href"] == BASE_URL + path
    assert document.select_one('meta[property="og:type"]')["content"] == "website"
    assert len(document.select('meta[property="og:image"]')) == 1
    image = document.select_one('meta[property="og:image"]')["content"].removeprefix(BASE_URL)
    assert client.get(image).data.startswith(b"\x89PNG")
    assert document.select_one('a[href="/developers"]').get_text() == "Developers"
    if path in {"/", "/buy"}:
        assert not document.select('nav a[href="/mcp"], nav a[href="/openapi.json"]')
    if path == "/developers":
        resources = document.select_one('nav[aria-label="Developer resources"]')
        assert resources.select_one('a[href="/mcp"]').get_text() == "MCP"
        for fragment in ("rest-api", "cli"):
            assert resources.select_one(f'a[href="/developers#{fragment}"]')
            assert document.select_one(f'section#{fragment} h2')
    markdown = client.get(path, headers={"Accept": "text/markdown"})
    assert markdown.status_code == 200
    assert markdown.mimetype == "text/markdown"
    assert markdown.text.startswith("# " + PAGES[path][0])
    if path == "/developers":
        for label, target in (("REST API", "/developers#rest-api"), ("MCP", "/mcp"), ("CLI", "/developers#cli")):
            assert f"[{label}]({BASE_URL}{target})" in markdown.text
    for _, paragraphs in PAGES[path][1]:
        for paragraph in paragraphs:
            assert paragraph in markdown.text
            assert paragraph in main_element.get_text()
    for variant in (response, markdown):
        assert "accept" in {value.strip().lower() for value in variant.headers["Vary"].split(",")}
    assert client.head(path, headers={"Accept": "text/markdown"}).data == b""


@pytest.mark.parametrize(("accept", "status", "mime"), [
    ("text/markdown;q=0.8,text/html;q=0.5", 200, "text/markdown"),
    ("text/markdown;q=0,text/html", 200, "text/html"),
    ("text/html;q=0,text/markdown", 200, "text/markdown"),
    ("text/*", 200, "text/html"), ("*/*", 200, "text/html"),
    ("application/json", 406, "text/plain"),
    ("text/html;q=0,text/markdown;q=0,*/*;q=0.5", 406, "text/plain"),
])
def test_negotiation_honors_quality_and_exclusions(client: FlaskClient, accept: str, status: int, mime: str) -> None:
    """Respect media-type preference, wildcards, exclusions, and cache variance.

    Args:
        client: App HTTP client.
        accept: Browser or agent content preference.
        status: Required response status.
        mime: Required selected representation.

    Returns:
        None.
    """
    response = client.get("/", headers={"Accept": accept, "Accept-Encoding": "gzip"})
    assert response.status_code == status
    assert response.mimetype == mime
    assert {"accept", "accept-encoding"} <= {item.strip().lower() for item in response.headers["Vary"].split(",")}


def test_unknown_pages_and_framework_routes(client: FlaskClient) -> None:
    """Reject invented URLs while preserving Dash assets and layout delivery.

    Args:
        client: App HTTP client using Dash's real routing table.

    Returns:
        None.
    """
    for path in ("/some-path-that-does-not-exist", "/docs/nope", "/buy/nope", "/favicon-missing.ico"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.mimetype == "text/markdown"
        assert "/sitemap.xml" in response.text and "/llms.txt" in response.text
        assert client.head(path).status_code == 404
    for path in ("/", "/developers"):
        invalid_method = client.post(path)
        assert invalid_method.status_code == 405
        assert set(invalid_method.headers["Allow"].split(", ")) == {"GET", "HEAD", "OPTIONS"}
        assert client.options(path).status_code == 204
    assert client.get("/_dash-layout").status_code == 200
    assert client.get("/_dash-dependencies").is_json
    shell = client.get("/").text
    assert 'id="react-entry-point"><main' in shell
    assert '_dash-config' in shell and 'DashRenderer' in shell
    assert client.get("/assets/css/public-content.css").status_code == 200


@pytest.mark.parametrize("market", ["lease", "buy"])
def test_search_matches_schema_and_paginates(client: FlaskClient, market: str) -> None:
    """Validate real database search responses against the published contract.

    Args:
        client: App HTTP client.
        market: Listing table to query through REST.

    Returns:
        None.
    """
    spec = client.get("/openapi.json").json
    validate(spec)
    operation_ids = [operation["operationId"] for path in spec["paths"].values() for operation in path.values()]
    assert len(operation_ids) == len(set(operation_ids))
    result = client.get(f"/api/listings?listing_type={market}&page_size=1").json
    Draft202012Validator(spec["components"]["schemas"]["ListingSearchResult"]).validate(result)
    assert len(result["listings"]) == 1 and result["has_next_page"]
    next_result = client.get(f"/api/listings?listing_type={market}&page_size=1&page=2").json
    assert next_result["listings"][0]["mls_number"] != result["listings"][0]["mls_number"]
    empty = client.get(f"/api/listings?listing_type={market}&location=no-such-place")
    assert empty.status_code == 200 and empty.json["listings"] == []
    assert client.get("/api").json["openapi"] == BASE_URL + "/openapi.json"


@pytest.mark.parametrize("query", [
    "", "listing_type=other", "listing_type=lease&page_size=21", "listing_type=lease&page=0",
    "listing_type=lease&max_price=-1", "listing_type=lease&max_price=1.5", "listing_type=lease&pet_friendly=yes",
    "listing_type=lease&min_price=2000&max_price=1000", "listing_type=lease&listed_after=not-a-date",
    "listing_type=lease&listed_after=20260901", "listing_type=lease&listed_after=2026-W01-1",
    "listing_type=lease&listed_after=2026-02-30",
    "listing_type=lease&sort=unknown", "listing_type=lease&typo=true", "listing_type=lease&page=1&page=2",
    "listing_type=lease&min_lot_size=1", "listing_type=buy&furnished=true",
])
def test_invalid_search_is_actionable_json(client: FlaskClient, query: str) -> None:
    """Reject invalid filters with stable codes and a recovery hint.

    Args:
        client: App HTTP client.
        query: Invalid serialized search parameters.

    Returns:
        None.
    """
    response = client.get("/api/listings?" + query)
    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_request"
    assert response.json["error"]["hint"]
    Draft202012Validator(build_openapi(BASE_URL)["components"]["schemas"]["Error"]).validate(response.json)


def test_existing_api_errors_and_unavailable_data(client: FlaskClient) -> None:
    """Return JSON for missing API paths, wrong methods, reports, and DB failures.

    Args:
        client: App HTTP client.

    Returns:
        None.
    """
    assert client.get("/api/nonexistent").json["error"]["code"] == "not_found"
    wrong_method = client.get("/report_listing")
    assert wrong_method.status_code == 405 and "POST" in wrong_method.headers["Allow"]
    assert wrong_method.json["error"]["code"] == "method_not_allowed"
    for body in (None, [], {"option": []}, {"option": "Other", "mls_number": ""}):
        assert client.post("/report_listing", json=body).status_code == 400
    with patch("api.public.search_listings_in_database", side_effect=sqlite3.OperationalError("secret/path")):
        failed = client.get("/api/listings?listing_type=lease")
    assert failed.status_code == 503 and "secret/path" not in failed.text
    with patch("api.public.search_listings_in_database", side_effect=RuntimeError("private details")):
        failed = client.get("/api/listings?listing_type=buy")
    assert failed.status_code == 500 and "private details" not in failed.text
    with patch("api.listings.sqlite3.connect") as connect:
        connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
        missing = client.get("/api/lease/listing-details/unknown")
    assert missing.status_code == 404 and missing.is_json
    with patch("api.report_listing.insert_listing_report", side_effect=RuntimeError("private DB failure")):
        report = client.post("/report_listing", json={"mls_number": "L1", "option": "Other"})
    assert report.status_code == 500 and report.json["error"]["code"] == "internal_error"
    assert "private DB failure" not in report.text


def test_organization_uses_verified_contact_without_inventing_address() -> None:
    """Publish project identity and existing contact details without fictional NAP.

    Returns:
        None.
    """
    document = BeautifulSoup(build_structured_data_script(BASE_URL), "html.parser")
    graph = json.loads(document.script.string)["@graph"]
    organization = next(entity for entity in graph if entity["@type"] == "Organization")
    assert organization["contactPoint"]["email"] == "hey@wheretolive.la"
    assert organization["contactPoint"]["contactType"]
    assert "address" not in organization


def test_cli_json_success_and_errors(capsys: pytest.CaptureFixture[str]) -> None:
    """Keep CLI output parseable and exit status useful in scripts.

    Args:
        capsys: Captured standard output and standard error.

    Returns:
        None.
    """
    with patch("scripts.search_cli.urlopen", return_value=BytesIO(b'{"listings": []}')) as opener:
        assert main(["--listing-type", "lease", "--location", "Los Angeles"]) == 0
        assert "location=Los+Angeles" in opener.call_args.args[0].full_url
    assert json.loads(capsys.readouterr().out) == {"listings": []}
    for exception in (URLError("offline"), HTTPError("https://example.com", 400, "bad", {}, BytesIO(b'{"error": "invalid"}')), ValueError("not JSON")):
        with patch("scripts.search_cli.urlopen", side_effect=exception):
            assert main(["--listing-type", "buy"]) == 1
        assert capsys.readouterr().err
