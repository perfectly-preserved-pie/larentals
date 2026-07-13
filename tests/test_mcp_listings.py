import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from dash import Dash, html
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from functions.mcp_listings import (
    MAX_PAGE_SIZE,
    configure_listings_mcp,
    search_listings_in_database,
)


LEASE_SCHEMA = """
CREATE TABLE lease (
    mls_number TEXT, full_street_address TEXT, city TEXT, zip_code TEXT,
    subtype TEXT, list_price INTEGER, bedrooms INTEGER,
    total_bathrooms INTEGER, sqft INTEGER, ppsqft REAL, year_built INTEGER,
    parking_spaces INTEGER, laundry_category TEXT, pet_policy TEXT, terms TEXT,
    furnished TEXT, security_deposit INTEGER, pet_deposit INTEGER,
    listed_date TEXT, listing_url TEXT, latitude REAL, longitude REAL,
    date_processed TEXT
)
"""

BUY_SCHEMA = """
CREATE TABLE buy (
    mls_number TEXT, full_street_address TEXT, city TEXT, zip_code TEXT,
    subtype TEXT, list_price TEXT, bedrooms TEXT, total_bathrooms TEXT,
    sqft TEXT, ppsqft TEXT, year_built TEXT, lot_size REAL,
    garage_spaces TEXT, hoa_fee REAL, hoa_fee_frequency TEXT, space_rent TEXT,
    park_name TEXT, pets_allowed TEXT, senior_community TEXT, listed_date TEXT,
    listing_url TEXT, latitude REAL, longitude REAL, date_processed TEXT
)
"""

LEASE_INSERT_SQL = """
INSERT INTO lease VALUES (
    :mls_number, :full_street_address, :city, :zip_code, :subtype,
    :list_price, :bedrooms, :total_bathrooms, :sqft, :ppsqft,
    :year_built, :parking_spaces, :laundry_category, :pet_policy, :terms,
    :furnished, :security_deposit, :pet_deposit, :listed_date, :listing_url,
    :latitude, :longitude, :date_processed
)
"""

BUY_INSERT_SQL = """
INSERT INTO buy VALUES (
    :mls_number, :full_street_address, :city, :zip_code, :subtype,
    :list_price, :bedrooms, :total_bathrooms, :sqft, :ppsqft, :year_built,
    :lot_size, :garage_spaces, :hoa_fee, :hoa_fee_frequency, :space_rent,
    :park_name, :pets_allowed, :senior_community, :listed_date, :listing_url,
    :latitude, :longitude, :date_processed
)
"""


def _lease_listing(**overrides: object) -> dict[str, object]:
    """Build a complete lease row for test database fixtures.

    Keyword overrides keep individual test cases focused on relevant fields.
    """
    listing: dict[str, object] = {
        "mls_number": "L1",
        "full_street_address": "100 Main St, Los Angeles 90012",
        "city": "Los Angeles",
        "zip_code": "90012",
        "subtype": "Apartment",
        "list_price": 2200,
        "bedrooms": 2,
        "total_bathrooms": 2,
        "sqft": 900,
        "ppsqft": 2.44,
        "year_built": 1990,
        "parking_spaces": 1,
        "laundry_category": "In Unit",
        "pet_policy": "Yes",
        "terms": "12M",
        "furnished": "Unfurnished",
        "security_deposit": 2200,
        "pet_deposit": 300,
        "listed_date": "2026-07-01",
        "listing_url": "https://example.test/l1",
        "latitude": 34.05,
        "longitude": -118.24,
        "date_processed": "2026-07-06",
    }
    listing.update(overrides)
    return listing


def _buy_listing(**overrides: object) -> dict[str, object]:
    """Build a complete for-sale row for test database fixtures.

    Values intentionally mirror the source table's text-heavy schema.
    """
    listing: dict[str, object] = {
        "mls_number": "B1",
        "full_street_address": "500 Oak Ave, Pasadena 91101",
        "city": "Pasadena",
        "zip_code": "91101.0",
        "subtype": "Single Family Residence",
        "list_price": "750000",
        "bedrooms": "3",
        "total_bathrooms": "2.5",
        "sqft": "1600",
        "ppsqft": "468.75",
        "year_built": "1955",
        "lot_size": 6000,
        "garage_spaces": "2",
        "hoa_fee": 100,
        "hoa_fee_frequency": "Monthly",
        "space_rent": None,
        "park_name": None,
        "pets_allowed": "Yes",
        "senior_community": "N",
        "listed_date": "2026-07-04",
        "listing_url": "https://example.test/b1",
        "latitude": 34.14,
        "longitude": -118.14,
        "date_processed": "2026-07-06",
    }
    listing.update(overrides)
    return listing


@pytest.fixture()
def listing_db(tmp_path: Path) -> Path:
    """Create a temporary database containing lease and buy tables.

    The returned path is read by both unit and MCP transport tests.
    """
    db_path: Path = tmp_path / "listings.db"
    lease_rows: list[dict[str, object]] = [
        _lease_listing(),
        _lease_listing(
            mls_number="L2",
            full_street_address="200 Ocean Ave, Santa Monica 90401",
            city="Santa Monica",
            zip_code="90401",
            subtype="Condominium",
            list_price=3000,
            bedrooms=1,
            total_bathrooms=1,
            pet_policy="No",
            furnished="Furnished",
            listed_date="2026-07-03",
            listing_url="https://example.test/l2",
        ),
        _lease_listing(
            mls_number="L3",
            full_street_address="300 Hill St, LOS ANGELES 90013",
            city="LOS ANGELES",
            list_price=1800,
            total_bathrooms=1,
            sqft=850,
            pet_policy="Cats OK",
            listed_date="2026-06-25",
            listing_url="https://example.test/l3",
        ),
    ]
    buy_rows: list[dict[str, object]] = [
        _buy_listing(),
        _buy_listing(
            mls_number="B2",
            full_street_address="600 Pine St, Los Angeles 90012",
            city="Los Angeles",
            zip_code="90012.0",
            list_price="1000000",
            bedrooms="4",
            total_bathrooms="3",
            sqft="2200",
            lot_size=7500,
            hoa_fee=0,
            listed_date="2026-07-05",
            listing_url="https://example.test/b2",
        ),
    ]
    with sqlite3.connect(db_path) as connection:
        connection.execute(LEASE_SCHEMA)
        connection.execute(BUY_SCHEMA)
        connection.executemany(LEASE_INSERT_SQL, lease_rows)
        connection.executemany(BUY_INSERT_SQL, buy_rows)
    return db_path


def _post_mcp(
    client: FlaskClient,
    session_id: str | None,
    payload: dict[str, Any],
) -> TestResponse:
    """Post one JSON-RPC message through the test MCP transport.

    Session and protocol headers match a Streamable HTTP client.
    """
    headers: dict[str, str] = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-11-25",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return client.post("/_mcp", data=json.dumps(payload), headers=headers)


def test_searches_and_paginates_lease_listings(listing_db: Path) -> None:
    result = search_listings_in_database(
        listing_db,
        listing_type="lease",
        location="los angeles",
        property_type="apartment",
        max_price=2500,
        min_bedrooms=2,
        pet_friendly=True,
        sort="price_low_to_high",
        page_size=1,
    )

    assert result["listing_type"] == "lease"
    assert result["data_as_of"] == "2026-07-06"
    assert result["total_results"] == 2
    assert result["total_pages"] == 2
    assert result["has_next_page"] is True
    listing = result["listings"][0]
    assert listing["mls_number"] == "L3"
    assert listing["price"] == 1800
    assert listing["price_description"] == "monthly_rent"
    assert listing["address"] == "300 Hill St, LOS ANGELES 90013"
    assert listing["listing_url"] == "https://example.test/l3"
    assert listing["lease_details"]["pet_policy"] == "Cats OK"
    assert listing["sale_details"] is None


def test_searches_buy_listings_with_numeric_and_buy_specific_filters(
    listing_db: Path,
) -> None:
    result = search_listings_in_database(
        listing_db,
        listing_type="buy",
        location="Pasadena",
        max_price=800_000,
        min_bedrooms=3,
        min_lot_size=5_000,
        max_hoa_fee=150,
    )

    assert result["listing_type"] == "buy"
    assert result["total_results"] == 1
    listing = result["listings"][0]
    assert listing["mls_number"] == "B1"
    assert listing["zip_code"] == "91101"
    assert listing["price"] == 750_000
    assert listing["price_description"] == "sale_price"
    assert listing["bathrooms"] == 2.5
    assert listing["lease_details"] is None
    assert listing["sale_details"] == {
        "lot_size_square_feet": 6000.0,
        "garage_spaces": 2.0,
        "hoa_fee": 100.0,
        "hoa_fee_frequency": "Monthly",
        "space_rent": None,
        "park_name": None,
        "pets_allowed": "Yes",
        "senior_community": "N",
    }


def test_search_uses_parameterized_location_filter(listing_db: Path) -> None:
    result = search_listings_in_database(
        listing_db, listing_type="buy", location="' OR 1=1 --"
    )
    assert result["total_results"] == 0

    wildcard_result = search_listings_in_database(
        listing_db, listing_type="lease", location="%"
    )
    assert wildcard_result["total_results"] == 0


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"listing_type": "lease", "page_size": MAX_PAGE_SIZE + 1}, "page_size"),
        (
            {"listing_type": "buy", "min_price": 900_000, "max_price": 800_000},
            "min_price cannot",
        ),
        ({"listing_type": "lease", "listed_after": "07/01/2026"}, "YYYY-MM-DD"),
        ({"listing_type": "buy", "min_bedrooms": -1}, "non-negative integer"),
        ({"listing_type": "lease", "max_hoa_fee": 100}, "only supported for buy"),
        ({"listing_type": "buy", "furnished": True}, "only supported for lease"),
    ],
)
def test_search_rejects_invalid_filters(
    listing_db: Path,
    arguments: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        search_listings_in_database(listing_db, **arguments)


def test_mcp_exposes_one_tool_supporting_lease_and_buy(listing_db: Path) -> None:
    configure_listings_mcp()
    app = Dash(__name__, enable_mcp=True)
    app.layout = html.Div("Curated MCP test")
    client = app.server.test_client()

    initialize_response = _post_mcp(
        client,
        None,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "claude-test", "version": "1.0"},
            },
        },
    )
    session_id = initialize_response.headers["Mcp-Session-Id"]
    initialized_response = _post_mcp(
        client,
        session_id,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert initialized_response.status_code == 202

    tools_response = _post_mcp(
        client,
        session_id,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    tools_payload = tools_response.get_json()
    assert [tool["name"] for tool in tools_payload["result"]["tools"]] == [
        "search_listings"
    ]
    tool_schema = tools_payload["result"]["tools"][0]["inputSchema"]
    assert tool_schema["properties"]["listing_type"]["enum"] == ["lease", "buy"]
    assert "listing_type" in tool_schema["required"]
    assert "load_lease_geojson" not in json.dumps(tools_payload)
    assert "load_buy_geojson" not in json.dumps(tools_payload)

    for blocked_tool in ("load_lease_geojson", "load_buy_geojson"):
        blocked_response = _post_mcp(
            client,
            session_id,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": blocked_tool, "arguments": {"_": 0}},
            },
        )
        assert blocked_response.get_json()["error"]["code"] == -32601

    with patch("functions.mcp_listings.DEFAULT_DB_PATH", listing_db):
        lease_response = _post_mcp(
            client,
            session_id,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "search_listings",
                    "arguments": {
                        "listing_type": "lease",
                        "max_price": 2500,
                        "page_size": 2,
                    },
                },
            },
        )
        buy_response = _post_mcp(
            client,
            session_id,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "search_listings",
                    "arguments": {
                        "listing_type": "buy",
                        "max_price": 800_000,
                    },
                },
            },
        )

    assert len(lease_response.data) < 50_000
    lease_result = lease_response.get_json()["result"]["structuredContent"]["result"]
    buy_result = buy_response.get_json()["result"]["structuredContent"]["result"]
    assert lease_result["listing_type"] == "lease"
    assert lease_result["total_results"] == 2
    assert buy_result["listing_type"] == "buy"
    assert buy_result["total_results"] == 1


def test_mcp_validation_error_does_not_destabilize_session(listing_db: Path) -> None:
    configure_listings_mcp()
    app = Dash(__name__, enable_mcp=True)
    app.layout = html.Div("MCP validation test")
    client = app.server.test_client()
    initialize_response = _post_mcp(
        client,
        None,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    session_id = initialize_response.headers["Mcp-Session-Id"]

    with patch("functions.mcp_listings.DEFAULT_DB_PATH", listing_db):
        invalid_response = _post_mcp(
            client,
            session_id,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "search_listings",
                    "arguments": {
                        "listing_type": "buy",
                        "page_size": MAX_PAGE_SIZE + 1,
                    },
                },
            },
        )

    invalid_payload = invalid_response.get_json()
    assert invalid_response.status_code == 200
    assert invalid_payload["result"]["isError"] is True
    assert "page_size must be between" in invalid_payload["result"]["content"][0]["text"]

    healthy_response = _post_mcp(
        client,
        session_id,
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
    )
    assert healthy_response.status_code == 200
    assert healthy_response.get_json()["result"]["tools"][0]["name"] == "search_listings"
