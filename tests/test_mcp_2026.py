"""Protocol and transport tests for the MCP 2026-07-28 compatibility layer."""

from __future__ import annotations

from collections.abc import Iterator
import json
from typing import Any

from dash import Dash, html
from flask.testing import FlaskClient
import pytest
from werkzeug.test import TestResponse

from functions.mcp_2026 import (
    MODERN_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    register_mcp_2026_transport,
)
from functions.mcp_listings import configure_listings_mcp


CLIENT_INFO = {"name": "mcp-2026-test", "version": "1.0.0"}


@pytest.fixture()
def mcp_client() -> Iterator[FlaskClient]:
    """Create a Dash MCP endpoint supporting both protocol eras.

    Yields:
        A Flask test client connected to the dual-era MCP endpoint.
    """
    configure_listings_mcp()
    app = Dash(__name__, enable_mcp=True)
    app.layout = html.Div("MCP 2026 test")
    register_mcp_2026_transport(
        app.server, allowed_origins={"https://wheretolive.la"}
    )
    with app.server.test_client() as client:
        yield client


def _payload(
    method: str,
    *,
    request_id: str | int | None = 1,
    params: dict[str, Any] | None = None,
    version: str = MODERN_PROTOCOL_VERSION,
) -> dict[str, Any]:
    """Build one modern MCP request with its required per-request metadata.

    Args:
        method: MCP RPC method to place in the request.
        request_id: JSON-RPC identifier, or ``None`` for a notification.
        params: Optional method-specific parameters to include.
        version: Protocol revision declared in the request metadata.

    Returns:
        A JSON-RPC request mapping with modern MCP metadata.
    """
    request_params = dict(params or {})
    request_params["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": version,
        "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    message: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
        "params": request_params,
    }
    if request_id is not None:
        message["id"] = request_id
    return message


def _post(
    client: FlaskClient,
    payload: dict[str, Any],
    *,
    protocol_header: str | None = MODERN_PROTOCOL_VERSION,
    method_header: str | None = None,
    name_header: str | None = None,
    origin: str | None = None,
) -> TestResponse:
    """POST a modern MCP request with configurable mirrored headers.

    Args:
        client: Flask test client used to send the request.
        payload: JSON-RPC request body to post.
        protocol_header: Optional MCP protocol version header value.
        method_header: Optional override for the mirrored method header.
        name_header: Optional mirrored tool or resource name header.
        origin: Optional HTTP Origin header value.

    Returns:
        The response returned by the MCP endpoint.
    """
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if protocol_header is not None:
        headers["MCP-Protocol-Version"] = protocol_header
    if method_header is not None:
        headers["Mcp-Method"] = method_header
    elif isinstance(payload.get("method"), str):
        headers["Mcp-Method"] = payload["method"]
    if name_header is not None:
        headers["Mcp-Name"] = name_header
    if origin is not None:
        headers["Origin"] = origin
    return client.post("/_mcp", json=payload, headers=headers)


def test_server_discover_advertises_dual_era_stateless_server(
    mcp_client: FlaskClient,
) -> None:
    """Return all mandatory discovery, identity, and caching fields.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    response = _post(mcp_client, _payload("server/discover", request_id="discover"))
    payload = response.get_json()
    result = payload["result"]

    assert response.status_code == 200
    assert response.headers.get("Mcp-Session-Id") is None
    assert payload["id"] == "discover"
    assert result["resultType"] == "complete"
    assert result["supportedVersions"] == list(SUPPORTED_PROTOCOL_VERSIONS)
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["ttlMs"] > 0
    assert result["cacheScope"] == "public"
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == (
        "WhereToLive.LA"
    )


def test_tools_list_is_stateless_deterministic_and_cacheable(
    mcp_client: FlaskClient,
) -> None:
    """List the curated tool without initialization or a session header.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    first = _post(mcp_client, _payload("tools/list", request_id=10))
    second = _post(
        mcp_client,
        _payload("tools/list", request_id=11),
        protocol_header=MODERN_PROTOCOL_VERSION,
    )
    first_result = first.get_json()["result"]
    second_result = second.get_json()["result"]

    assert first.status_code == second.status_code == 200
    assert first.headers.get("Mcp-Session-Id") is None
    assert second.headers.get("Mcp-Session-Id") is None
    assert [tool["name"] for tool in first_result["tools"]] == ["search_listings"]
    assert first_result["tools"] == second_result["tools"]
    tool = first_result["tools"][0]
    assert tool["inputSchema"]["additionalProperties"] is False
    assert "$defs" in tool["outputSchema"]
    assert "$defs" not in tool["outputSchema"]["properties"]["result"]
    assert tool["outputSchema"]["properties"]["result"]["properties"][
        "listings"
    ]["items"]["$ref"] == "#/$defs/Listing"
    assert first_result["resultType"] == "complete"
    assert first_result["ttlMs"] > 0
    assert first_result["cacheScope"] == "public"
    assert "io.modelcontextprotocol/serverInfo" in first_result["_meta"]


@pytest.mark.parametrize(
    ("header_name", "header_value"),
    [
        ("MCP-Protocol-Version", "2025-11-25"),
        ("Mcp-Method", "tools/list"),
    ],
)
def test_discovery_rejects_mismatched_standard_headers(
    mcp_client: FlaskClient,
    header_name: str,
    header_value: str,
) -> None:
    """Return HeaderMismatch when mirrored values disagree with the body.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.
        header_name: Mirrored standard header to override.
        header_value: Deliberately mismatched header value.

    Returns:
        None.
    """
    payload = _payload("server/discover")
    headers = {
        "MCP-Protocol-Version": MODERN_PROTOCOL_VERSION,
        "Mcp-Method": "server/discover",
    }
    headers[header_name] = header_value
    response = mcp_client.post("/_mcp", json=payload, headers=headers)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == -32020


def test_modern_request_requires_all_standard_headers(
    mcp_client: FlaskClient,
) -> None:
    """Reject a modern request that omits the mirrored method header.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    response = mcp_client.post(
        "/_mcp",
        json=_payload("server/discover"),
        headers={"MCP-Protocol-Version": MODERN_PROTOCOL_VERSION},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == -32020


def test_method_header_does_not_allow_base64_encoding(
    mcp_client: FlaskClient,
) -> None:
    """Restrict Base64 sentinel encoding to headers that permit it.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    response = _post(
        mcp_client,
        _payload("server/discover"),
        method_header="=?base64?c2VydmVyL2Rpc2NvdmVy?=",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == -32020


def test_modern_request_requires_per_request_metadata(
    mcp_client: FlaskClient,
) -> None:
    """Reject requests that omit mandatory client capabilities metadata.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    payload = _payload("server/discover")
    del payload["params"]["_meta"][
        "io.modelcontextprotocol/clientCapabilities"
    ]
    response = _post(mcp_client, payload)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == -32602


def test_unsupported_version_lists_server_versions(mcp_client: FlaskClient) -> None:
    """Return the protocol-defined version-negotiation error and data.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    unsupported = "2099-01-01"
    response = _post(
        mcp_client,
        _payload("server/discover", version=unsupported),
        protocol_header=unsupported,
    )
    error = response.get_json()["error"]

    assert response.status_code == 400
    assert error["code"] == -32022
    assert error["data"] == {
        "supported": list(SUPPORTED_PROTOCOL_VERSIONS),
        "requested": unsupported,
    }


def test_unknown_modern_method_uses_jsonrpc_and_http_errors(
    mcp_client: FlaskClient,
) -> None:
    """Return Method not found with the modern transport's HTTP 404.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    response = _post(mcp_client, _payload("unknown/method"))

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == -32601


def test_tools_call_requires_matching_name_header(mcp_client: FlaskClient) -> None:
    """Validate Mcp-Name before dispatching a tool call.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    payload = _payload(
        "tools/call",
        params={"name": "search_listings", "arguments": {"listing_type": "lease"}},
    )
    response = _post(mcp_client, payload, name_header="another_tool")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == -32020


def test_unknown_tool_is_invalid_params_not_unknown_rpc(
    mcp_client: FlaskClient,
) -> None:
    """Map Dash's ToolNotFound error to modern CallTool semantics.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    payload = _payload(
        "tools/call", params={"name": "unknown_tool", "arguments": {}}
    )
    response = _post(mcp_client, payload, name_header="unknown_tool")

    assert response.status_code == 200
    assert response.get_json()["error"]["code"] == -32602


def test_tool_calls_are_rate_limited() -> None:
    """Enforce a per-peer limit without affecting discovery or tool listing.

    Returns:
        None.
    """
    configure_listings_mcp()
    app = Dash(__name__, enable_mcp=True)
    app.layout = html.Div("MCP rate limit test")
    register_mcp_2026_transport(
        app.server,
        allowed_origins={"https://wheretolive.la"},
        tool_rate_limit=1,
        tool_rate_window_seconds=60,
    )
    client = app.server.test_client()
    payload = _payload(
        "tools/call", params={"name": "unknown_tool", "arguments": {}}
    )

    first = _post(client, payload, name_header="unknown_tool")
    second = _post(client, payload, name_header="unknown_tool")
    list_response = _post(client, _payload("tools/list"))

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.get_json()["error"]["code"] == -32800
    assert int(second.headers["Retry-After"]) >= 1
    assert list_response.status_code == 200


def test_invalid_origin_is_forbidden(mcp_client: FlaskClient) -> None:
    """Reject an Origin outside the endpoint's explicit allow list.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    response = _post(
        mcp_client,
        _payload("server/discover"),
        origin="https://attacker.example",
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["message"] == "Forbidden Origin"


def test_modern_get_and_delete_do_not_open_or_destroy_sessions(
    mcp_client: FlaskClient,
) -> None:
    """Reject session-era verbs when a request identifies as modern.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    headers = {"MCP-Protocol-Version": MODERN_PROTOCOL_VERSION}
    for method in (mcp_client.get, mcp_client.delete):
        response = method("/_mcp", headers=headers)
        assert response.status_code == 405
        assert response.headers.get("Mcp-Session-Id") is None
        assert response.headers["Allow"] == "POST"


def test_modern_notification_is_acknowledged_without_body(
    mcp_client: FlaskClient,
) -> None:
    """Use HTTP 202 and no JSON-RPC response for a notification.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    response = _post(
        mcp_client,
        _payload("notifications/example", request_id=None),
    )

    assert response.status_code == 202
    assert response.data == b""


def test_subscription_acknowledges_no_unsupported_notifications(
    mcp_client: FlaskClient,
) -> None:
    """Acknowledge an empty filter first and gracefully close the SSE stream.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    response = _post(
        mcp_client,
        _payload(
            "subscriptions/listen",
            request_id="subscription-1",
            params={
                "notifications": {
                    "toolsListChanged": True,
                    "resourceSubscriptions": ["file:///not-exposed"],
                }
            },
        ),
    )
    messages = [
        json.loads(line.removeprefix("data: "))
        for line in response.get_data(as_text=True).splitlines()
        if line.startswith("data: ")
    ]

    assert response.status_code == 200
    assert response.content_type.startswith("text/event-stream")
    assert response.headers["X-Accel-Buffering"] == "no"
    assert response.headers.get("Mcp-Session-Id") is None
    assert messages[0]["method"] == "notifications/subscriptions/acknowledged"
    assert messages[0]["params"]["notifications"] == {}
    assert messages[0]["params"]["_meta"][
        "io.modelcontextprotocol/subscriptionId"
    ] == "subscription-1"
    assert messages[1]["id"] == "subscription-1"
    assert messages[1]["result"]["resultType"] == "complete"


def test_legacy_initialize_and_get_still_reach_dash(mcp_client: FlaskClient) -> None:
    """Preserve Dash's native 2025-11-25 behavior for existing clients.

    Args:
        mcp_client: Dual-era MCP test client supplied by the fixture.

    Returns:
        None.
    """
    get_response = mcp_client.get("/_mcp")
    initialize_response = mcp_client.post(
        "/_mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        },
        headers={"MCP-Protocol-Version": "2025-11-25"},
    )

    assert get_response.status_code == 200
    assert "text/event-stream" in get_response.content_type
    assert get_response.headers.get("Mcp-Session-Id")
    assert initialize_response.status_code == 200
    assert initialize_response.headers.get("Mcp-Session-Id")
    assert initialize_response.get_json()["result"]["protocolVersion"] == (
        "2025-11-25"
    )
