"""Add MCP 2026-07-28 support to Dash's legacy MCP endpoint.

Dash 4.4.1 implements the initialization-based 2025-11-25 protocol. This
module adds the stateless 2026-07-28 wire protocol at the same HTTP endpoint
while leaving Dash's native handler available to legacy clients.
"""

from __future__ import annotations

import base64
import binascii
from collections import deque
from collections.abc import Collection
from copy import deepcopy
import importlib.metadata
import json
from threading import Lock
import time
from typing import Any
from urllib.parse import urlsplit

from dash.mcp._server import _process_mcp_message
from flask import Flask, Response, request


MODERN_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (
    MODERN_PROTOCOL_VERSION,
    LEGACY_PROTOCOL_VERSION,
)

SERVER_NAME = "WhereToLive.LA"
SERVER_INSTRUCTIONS = (
    "Search current Los Angeles County rental and for-sale listings. "
    "Results are read-only, paginated, and include a data_as_of date."
)
DISCOVERY_TTL_MS = 3_600_000
TOOLS_TTL_MS = 300_000
DEFAULT_TOOL_RATE_LIMIT = 120
DEFAULT_TOOL_RATE_WINDOW_SECONDS = 60.0

_PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"
_CLIENT_INFO_META_KEY = "io.modelcontextprotocol/clientInfo"
_CLIENT_CAPABILITIES_META_KEY = "io.modelcontextprotocol/clientCapabilities"
_SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"
_LEGACY_PROTOCOL_VERSIONS = frozenset(
    {"2024-11-05", "2025-03-26", "2025-06-18", LEGACY_PROTOCOL_VERSION}
)


def _server_version() -> str:
    """Return the installed application version for MCP server metadata.

    Returns:
        The installed project version, or ``development`` outside a package.
    """
    try:
        return importlib.metadata.version("WhereToLive.LA")
    except importlib.metadata.PackageNotFoundError:
        return "development"


def _server_info() -> dict[str, str]:
    """Build the server identity included in modern MCP results.

    Returns:
        An MCP Implementation mapping containing the server name and version.
    """
    return {"name": SERVER_NAME, "version": _server_version()}


def _json_response(payload: dict[str, Any], status: int = 200) -> Response:
    """Create a compact JSON response without legacy session headers.

    Args:
        payload: JSON-serializable response object to send to the MCP client.
        status: HTTP response status code.

    Returns:
        A Flask JSON response containing the serialized payload.
    """
    return Response(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        status=status,
        content_type="application/json",
    )


def _jsonrpc_error(
    request_id: str | int | None,
    code: int,
    message: str,
    *,
    status: int,
    data: dict[str, Any] | None = None,
) -> Response:
    """Return one MCP JSON-RPC error with the required HTTP status.

    Args:
        request_id: Request identifier to echo, or ``None`` if unavailable.
        code: Integer JSON-RPC or MCP error code.
        message: Human-readable description of the protocol error.
        status: HTTP status required for this error class.
        data: Optional structured details attached to the error.

    Returns:
        A Flask response containing the JSON-RPC error object.
    """
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return _json_response(
        {"jsonrpc": "2.0", "id": request_id, "error": error}, status=status
    )


def _request_id(payload: Any) -> str | int | None:
    """Read a valid JSON-RPC request ID without accepting booleans.

    Args:
        payload: Parsed request body whose identifier should be inspected.

    Returns:
        A string or integer request identifier, or ``None`` when invalid.
    """
    if not isinstance(payload, dict):
        return None
    value = payload.get("id")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return value


def _normalize_origin(origin: str) -> str | None:
    """Normalize an HTTP Origin value for exact allow-list comparison.

    Args:
        origin: Origin header or configured origin URL to normalize.

    Returns:
        A canonical scheme and authority, or ``None`` for invalid input.
    """
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return None
    host = parsed.hostname.lower()
    default_port = (parsed.scheme == "http" and port == 80) or (
        parsed.scheme == "https" and port == 443
    )
    authority = host if port is None or default_port else f"{host}:{port}"
    return f"{parsed.scheme.lower()}://{authority}"


def _origin_is_allowed(origin: str, allowed_origins: frozenset[str]) -> bool:
    """Return whether an Origin header is valid for this MCP endpoint.

    Args:
        origin: Incoming Origin header supplied by the HTTP client.
        allowed_origins: Canonical origins accepted by the endpoint.

    Returns:
        ``True`` when the normalized origin appears in the allow list.
    """
    normalized = _normalize_origin(origin)
    return normalized is not None and normalized in allowed_origins


def _decode_mcp_header_value(value: str) -> str:
    """Decode the MCP Base64 sentinel form or validate a plain header value.

    Args:
        value: Raw mirrored MCP header value to validate and decode.

    Returns:
        The decoded UTF-8 or validated plain-ASCII value.

    Raises:
        ValueError: If the value is malformed or not valid visible ASCII.
    """
    prefix = "=?base64?"
    suffix = "?="
    if value.startswith(prefix) or value.endswith(suffix):
        if not (value.startswith(prefix) and value.endswith(suffix)):
            raise ValueError("malformed Base64 sentinel")
        encoded = value[len(prefix) : -len(suffix)]
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ValueError("invalid Base64 header value") from exc
        return decoded

    if value != value.strip() or any(
        character != "\t" and not 0x20 <= ord(character) <= 0x7E
        for character in value
    ):
        raise ValueError("plain header value is not safe ASCII")
    return value


def _modern_request_signal(payload: Any, protocol_header: str | None) -> bool:
    """Distinguish a modern request from traffic intended for Dash's handler.

    Args:
        payload: Parsed HTTP request body to classify by wire-protocol era.
        protocol_header: Optional MCP protocol version header value.

    Returns:
        ``True`` when the compatibility layer should handle the request.
    """
    if protocol_header and protocol_header not in _LEGACY_PROTOCOL_VERSIONS:
        return True
    if not isinstance(payload, dict):
        return protocol_header == MODERN_PROTOCOL_VERSION
    if payload.get("method") == "server/discover":
        return True
    params = payload.get("params")
    meta = params.get("_meta") if isinstance(params, dict) else None
    if isinstance(meta, dict) and _PROTOCOL_VERSION_META_KEY in meta:
        return True
    return request.headers.get("Mcp-Method") is not None


def _validate_jsonrpc_request(payload: Any) -> Response | None:
    """Validate the common JSON-RPC request envelope.

    Args:
        payload: Parsed JSON request body to validate.

    Returns:
        An error response when invalid, otherwise ``None``.
    """
    request_id = _request_id(payload)
    if not isinstance(payload, dict):
        return _jsonrpc_error(
            None, -32600, "Invalid Request: expected a JSON object", status=400
        )
    if payload.get("jsonrpc") != "2.0":
        return _jsonrpc_error(
            request_id, -32600, "Invalid Request: jsonrpc must be '2.0'", status=400
        )
    if not isinstance(payload.get("method"), str) or not payload["method"]:
        return _jsonrpc_error(
            request_id, -32600, "Invalid Request: method must be a string", status=400
        )
    if "id" in payload and request_id is None:
        return _jsonrpc_error(
            None,
            -32600,
            "Invalid Request: id must be a string or integer",
            status=400,
        )
    params = payload.get("params")
    if not isinstance(params, dict):
        return _jsonrpc_error(
            request_id, -32602, "Invalid params: params must be an object", status=400
        )
    return None


def _validate_request_meta(payload: dict[str, Any]) -> Response | None:
    """Validate metadata required on every MCP 2026-07-28 request.

    Args:
        payload: Structurally valid JSON-RPC request containing parameters.

    Returns:
        An Invalid params response when metadata is invalid, otherwise ``None``.
    """
    request_id = _request_id(payload)
    meta = payload["params"].get("_meta")
    if not isinstance(meta, dict):
        return _jsonrpc_error(
            request_id,
            -32602,
            "Invalid params: params._meta is required",
            status=400,
        )
    version = meta.get(_PROTOCOL_VERSION_META_KEY)
    if not isinstance(version, str) or not version:
        return _jsonrpc_error(
            request_id,
            -32602,
            f"Invalid params: {_PROTOCOL_VERSION_META_KEY} is required",
            status=400,
        )
    capabilities = meta.get(_CLIENT_CAPABILITIES_META_KEY)
    if not isinstance(capabilities, dict):
        return _jsonrpc_error(
            request_id,
            -32602,
            f"Invalid params: {_CLIENT_CAPABILITIES_META_KEY} must be an object",
            status=400,
        )
    client_info = meta.get(_CLIENT_INFO_META_KEY)
    if client_info is not None and (
        not isinstance(client_info, dict)
        or not isinstance(client_info.get("name"), str)
        or not isinstance(client_info.get("version"), str)
    ):
        return _jsonrpc_error(
            request_id,
            -32602,
            f"Invalid params: {_CLIENT_INFO_META_KEY} must contain name and version",
            status=400,
        )
    return None


def _validate_method_params(payload: dict[str, Any]) -> Response | None:
    """Validate fields used by the modern methods this server supports.

    Args:
        payload: Structurally valid modern MCP request to inspect.

    Returns:
        An Invalid params response when method fields are invalid, else ``None``.
    """
    method = payload["method"]
    params = payload["params"]
    request_id = _request_id(payload)
    if method == "tools/list":
        cursor = params.get("cursor")
        if cursor is not None and not isinstance(cursor, str):
            return _jsonrpc_error(
                request_id,
                -32602,
                "Invalid params: cursor must be a string",
                status=400,
            )
    elif method == "subscriptions/listen":
        notifications = params.get("notifications")
        if not isinstance(notifications, dict):
            return _jsonrpc_error(
                request_id,
                -32602,
                "Invalid params: notifications must be an object",
                status=400,
            )
        for field in (
            "toolsListChanged",
            "promptsListChanged",
            "resourcesListChanged",
        ):
            if field in notifications and not isinstance(notifications[field], bool):
                return _jsonrpc_error(
                    request_id,
                    -32602,
                    f"Invalid params: notifications.{field} must be a boolean",
                    status=400,
                )
        resources = notifications.get("resourceSubscriptions")
        if resources is not None and (
            not isinstance(resources, list)
            or any(not isinstance(uri, str) for uri in resources)
        ):
            return _jsonrpc_error(
                request_id,
                -32602,
                "Invalid params: resourceSubscriptions must be a string array",
                status=400,
            )
    elif method == "tools/call":
        if not isinstance(params.get("name"), str) or not params["name"]:
            return _jsonrpc_error(
                request_id,
                -32602,
                "Invalid params: tool name is required",
                status=400,
            )
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _jsonrpc_error(
                request_id,
                -32602,
                "Invalid params: arguments must be an object",
                status=400,
            )
        if "task" in params:
            return _jsonrpc_error(
                request_id,
                -32602,
                "Invalid params: core MCP 2026-07-28 does not define task",
                status=400,
            )
    return None


def _header_mismatch(request_id: str | int | None, message: str) -> Response:
    """Return the protocol-defined HeaderMismatch error.

    Args:
        request_id: Request identifier to echo in the error response.
        message: Explanation of the missing, malformed, or mismatched header.

    Returns:
        An HTTP 400 response using MCP error code ``-32020``.
    """
    return _jsonrpc_error(request_id, -32020, message, status=400)


def _validate_modern_headers(payload: dict[str, Any]) -> Response | None:
    """Validate mirrored MCP HTTP headers against the JSON-RPC body.

    Args:
        payload: Modern MCP request whose standard headers should be checked.

    Returns:
        A HeaderMismatch response when validation fails, otherwise ``None``.
    """
    request_id = _request_id(payload)
    method = payload["method"]
    meta = payload["params"]["_meta"]
    body_version = meta[_PROTOCOL_VERSION_META_KEY]

    protocol_header = request.headers.get("MCP-Protocol-Version")
    if protocol_header is None:
        return _header_mismatch(
            request_id, "Header mismatch: MCP-Protocol-Version header is required"
        )
    if protocol_header != body_version:
        return _header_mismatch(
            request_id,
            "Header mismatch: MCP-Protocol-Version does not match request metadata",
        )

    method_header = request.headers.get("Mcp-Method")
    if method_header is None:
        return _header_mismatch(
            request_id, "Header mismatch: Mcp-Method header is required"
        )
    try:
        decoded_method = _decode_mcp_header_value(method_header)
    except ValueError as exc:
        return _header_mismatch(
            request_id, f"Header mismatch: invalid Mcp-Method header ({exc})"
        )
    if decoded_method != method_header or decoded_method != method:
        return _header_mismatch(
            request_id, "Header mismatch: Mcp-Method does not match request method"
        )

    if method in {"tools/call", "resources/read", "prompts/get"}:
        name_header = request.headers.get("Mcp-Name")
        if name_header is None:
            return _header_mismatch(
                request_id, "Header mismatch: Mcp-Name header is required"
            )
        try:
            decoded_name = _decode_mcp_header_value(name_header)
        except ValueError as exc:
            return _header_mismatch(
                request_id, f"Header mismatch: invalid Mcp-Name header ({exc})"
            )
        body_name = payload["params"].get("name", payload["params"].get("uri"))
        if decoded_name != body_name:
            return _header_mismatch(
                request_id, "Header mismatch: Mcp-Name does not match request params"
            )
    return None


def _unsupported_version(payload: dict[str, Any]) -> Response | None:
    """Reject protocol revisions the dual-era endpoint does not implement.

    Args:
        payload: Validated modern MCP request carrying a protocol version.

    Returns:
        An UnsupportedProtocolVersion response, or ``None`` when supported.
    """
    requested = payload["params"]["_meta"][_PROTOCOL_VERSION_META_KEY]
    if requested == MODERN_PROTOCOL_VERSION:
        return None
    return _jsonrpc_error(
        _request_id(payload),
        -32022,
        "Unsupported protocol version",
        status=400,
        data={"supported": list(SUPPORTED_PROTOCOL_VERSIONS), "requested": requested},
    )


def _result_meta(result: dict[str, Any]) -> None:
    """Attach the server identity recommended on every modern result.

    Args:
        result: Mutable MCP result object that will receive server metadata.

    Returns:
        None.
    """
    meta = result.setdefault("_meta", {})
    if not isinstance(meta, dict):
        meta = {}
        result["_meta"] = meta
    meta[_SERVER_INFO_META_KEY] = _server_info()


def _normalize_json_schema(schema: dict[str, Any]) -> None:
    """Repair Dash's nested definitions and make input objects exact.

    Dash places output definitions below ``properties.result`` while emitting
    root-relative ``#/$defs/...`` references. Hoisting the definitions makes
    the advertised document valid JSON Schema 2020-12.

    Args:
        schema: Mutable input or output schema advertised for one tool.

    Returns:
        None.
    """
    root_definitions = dict(schema.get("$defs", {}))

    def collect_nested_definitions(value: Any, *, is_root: bool = False) -> None:
        """Move nested definition maps to the schema document root.

        Args:
            value: Current JSON Schema node or collection being traversed.
            is_root: Whether the current mapping is the schema document root.

        Returns:
            None.
        """
        if isinstance(value, dict):
            if not is_root:
                nested = value.pop("$defs", None)
                if isinstance(nested, dict):
                    for name, definition in nested.items():
                        root_definitions.setdefault(name, definition)
                    collect_nested_definitions(nested)
            for child in list(value.values()):
                collect_nested_definitions(child)
        elif isinstance(value, list):
            for child in value:
                collect_nested_definitions(child)

    collect_nested_definitions(schema, is_root=True)
    if root_definitions:
        schema["$defs"] = root_definitions


def _normalize_tool_definition(tool: dict[str, Any]) -> None:
    """Normalize one Dash tool definition for the modern MCP wire format.

    Args:
        tool: Mutable tool definition returned by Dash's MCP provider.

    Returns:
        None.
    """
    input_schema = tool.get("inputSchema")
    if isinstance(input_schema, dict):
        _normalize_json_schema(input_schema)
        if input_schema.get("type") == "object":
            input_schema.setdefault("additionalProperties", False)
    output_schema = tool.get("outputSchema")
    if isinstance(output_schema, dict):
        _normalize_json_schema(output_schema)


def _discover_response(payload: dict[str, Any]) -> Response:
    """Return the mandatory stateless server capability discovery result.

    Args:
        payload: Validated ``server/discover`` JSON-RPC request.

    Returns:
        A successful discovery response with capabilities and cache hints.
    """
    result: dict[str, Any] = {
        "resultType": "complete",
        "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
        "capabilities": {"tools": {"listChanged": False}},
        "instructions": SERVER_INSTRUCTIONS,
        "ttlMs": DISCOVERY_TTL_MS,
        "cacheScope": "public",
    }
    _result_meta(result)
    return _json_response(
        {"jsonrpc": "2.0", "id": _request_id(payload), "result": result}
    )


def _subscriptions_response(payload: dict[str, Any]) -> Response:
    """Acknowledge no supported notifications, then close the SSE stream.

    The server advertises no list-change or resource-subscription capability,
    so the acknowledged filter is empty. The graceful completion immediately
    follows the required first acknowledgment message.

    Args:
        payload: Validated ``subscriptions/listen`` request.

    Returns:
        A finite SSE response containing acknowledgment and completion messages.
    """
    subscription_id = _request_id(payload)
    acknowledgment = {
        "jsonrpc": "2.0",
        "method": "notifications/subscriptions/acknowledged",
        "params": {
            "_meta": {
                "io.modelcontextprotocol/subscriptionId": subscription_id,
            },
            "notifications": {},
        },
    }
    completion = {
        "jsonrpc": "2.0",
        "id": subscription_id,
        "result": {
            "resultType": "complete",
            "_meta": {
                "io.modelcontextprotocol/subscriptionId": subscription_id,
                _SERVER_INFO_META_KEY: _server_info(),
            },
        },
    }
    event_stream = "".join(
        f"data: {json.dumps(message, separators=(',', ':'), ensure_ascii=False)}\n\n"
        for message in (acknowledgment, completion)
    )
    response = Response(event_stream, content_type="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    return response


def _dash_tools_response(payload: dict[str, Any]) -> Response:
    """Dispatch a modern tools request through Dash and normalize its result.

    Args:
        payload: Validated modern ``tools/list`` or ``tools/call`` request.

    Returns:
        A modernized Dash MCP response without protocol-level session state.
    """
    dash_payload = deepcopy(payload)
    dash_response = _process_mcp_message(dash_payload)
    if dash_response is None:
        return Response(status=202)

    response_payload = deepcopy(dash_response)
    error = response_payload.get("error")
    if (
        payload["method"] == "tools/call"
        and isinstance(error, dict)
        and error.get("code") == -32601
    ):
        # In Dash this code means ToolNotFound. MCP 2026 treats an unknown tool
        # as invalid CallTool params; -32601 is reserved for an unknown RPC.
        error["code"] = -32602
    result = response_payload.get("result")
    if isinstance(result, dict):
        result["resultType"] = "complete"
        _result_meta(result)
        if payload["method"] == "tools/list":
            tools = result.get("tools")
            if isinstance(tools, list):
                for tool in tools:
                    if isinstance(tool, dict):
                        _normalize_tool_definition(tool)
                tools.sort(key=lambda tool: str(tool.get("name", "")))
            result["ttlMs"] = TOOLS_TTL_MS
            result["cacheScope"] = "public"
    return _json_response(response_payload)


def register_mcp_2026_transport(
    server: Flask,
    *,
    mcp_path: str = "/_mcp",
    allowed_origins: Collection[str] = ("https://wheretolive.la",),
    tool_rate_limit: int = DEFAULT_TOOL_RATE_LIMIT,
    tool_rate_window_seconds: float = DEFAULT_TOOL_RATE_WINDOW_SECONDS,
) -> None:
    """Register strict MCP 2026-07-28 handling ahead of Dash's legacy route.

    Requests carrying the modern per-request metadata or standard HTTP headers
    are handled here. Initialization-based traffic falls through to Dash.

    Args:
        server: Flask application that owns Dash's MCP endpoint.
        mcp_path: Absolute URL path of the shared MCP endpoint.
        allowed_origins: Exact HTTP origins accepted when Origin is present.
        tool_rate_limit: Maximum tool calls accepted from one peer per window.
        tool_rate_window_seconds: Length of one tool-rate-limit window.

    Returns:
        None.
    """
    normalized_path = "/" + str(mcp_path).strip().strip("/")
    normalized_origins = frozenset(
        origin
        for configured_origin in allowed_origins
        if (origin := _normalize_origin(configured_origin)) is not None
    )
    if not normalized_origins:
        raise ValueError("allowed_origins must contain at least one valid HTTP origin")
    if (
        isinstance(tool_rate_limit, bool)
        or not isinstance(tool_rate_limit, int)
        or tool_rate_limit < 1
    ):
        raise ValueError("tool_rate_limit must be a positive integer")
    if tool_rate_window_seconds <= 0:
        raise ValueError("tool_rate_window_seconds must be positive")

    tool_call_times: dict[str, deque[float]] = {}
    tool_rate_lock = Lock()

    def tool_rate_limit_response(payload: dict[str, Any]) -> Response | None:
        """Apply a bounded per-peer sliding-window limit to tool calls.

        Args:
            payload: Validated ``tools/call`` request being rate limited.

        Returns:
            An HTTP 429 response when the limit is exhausted, else ``None``.
        """
        now = time.monotonic()
        cutoff = now - tool_rate_window_seconds
        peer = request.remote_addr or "unknown"
        with tool_rate_lock:
            if peer not in tool_call_times and len(tool_call_times) >= 4096:
                peer = "overflow"
            timestamps = tool_call_times.setdefault(peer, deque())
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= tool_rate_limit:
                retry_after = max(1, int(timestamps[0] - cutoff) + 1)
                response = _jsonrpc_error(
                    _request_id(payload),
                    -32800,
                    "Tool call rate limit exceeded",
                    status=429,
                    data={"retryAfterMs": retry_after * 1000},
                )
                response.headers["Retry-After"] = str(retry_after)
                return response
            timestamps.append(now)

            # Keep attacker-controlled peer keys bounded without penalizing
            # active entries. This path is deliberately infrequent.
            if len(tool_call_times) > 4096:
                stale_peers = [
                    key
                    for key, calls in tool_call_times.items()
                    if not calls or calls[-1] <= cutoff
                ]
                for key in stale_peers:
                    tool_call_times.pop(key, None)
        return None

    @server.after_request
    def correct_legacy_capabilities(response: Response) -> Response:
        """Omit unsupported resources from the legacy initialize handshake.

        Args:
            response: Dash's legacy response, before compression.

        Returns:
            Response preserving the session and all supported capabilities.
        """
        if request.path != normalized_path or request.method != "POST":
            return response
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or payload.get("method") != "initialize":
            return response
        reply = response.get_json(silent=True)
        if isinstance(reply, dict) and isinstance(reply.get("result"), dict):
            capabilities = reply["result"].get("capabilities", {})
            # configure_listings_mcp disables all layout/page resources.
            capabilities.pop("resources", None)
            response.set_data(json.dumps(reply))
        return response

    @server.before_request
    def handle_mcp_2026_request() -> Response | None:
        """Intercept modern MCP traffic and let legacy traffic reach Dash.

        Returns:
            A completed modern response, or ``None`` to continue Flask routing.
        """
        if request.path != normalized_path:
            return None

        origin = request.headers.get("Origin")
        if origin is not None and not _origin_is_allowed(origin, normalized_origins):
            return _jsonrpc_error(None, -32600, "Forbidden Origin", status=403)

        protocol_header = request.headers.get("MCP-Protocol-Version")
        modern_header_signal = (
            protocol_header is not None
            and protocol_header not in _LEGACY_PROTOCOL_VERSIONS
        ) or request.headers.get("Mcp-Method") is not None
        if request.method in {"GET", "DELETE"}:
            if modern_header_signal:
                response = _jsonrpc_error(
                    None,
                    -32600,
                    "Method not allowed for MCP 2026-07-28",
                    status=405,
                )
                response.headers["Allow"] = "POST"
                return response
            return None
        if request.method != "POST":
            return None

        if request.mimetype != "application/json":
            if modern_header_signal:
                return _jsonrpc_error(
                    None,
                    -32600,
                    "Content-Type must be application/json",
                    status=415,
                )
            return None

        try:
            payload = json.loads(request.get_data(cache=True, as_text=True))
        except (json.JSONDecodeError, UnicodeDecodeError):
            if modern_header_signal:
                return _jsonrpc_error(None, -32700, "Parse error", status=400)
            return None

        if not _modern_request_signal(payload, protocol_header):
            return None

        validation_error = _validate_jsonrpc_request(payload)
        if validation_error is not None:
            return validation_error
        metadata_error = _validate_request_meta(payload)
        if metadata_error is not None:
            return metadata_error
        header_error = _validate_modern_headers(payload)
        if header_error is not None:
            return header_error
        version_error = _unsupported_version(payload)
        if version_error is not None:
            return version_error
        params_error = _validate_method_params(payload)
        if params_error is not None:
            return params_error

        # The 2026 HTTP core currently defines no client-to-server
        # notifications. A structurally valid notification is still accepted
        # according to the transport's generic notification mechanics.
        if "id" not in payload:
            return Response(status=202)

        method = payload["method"]
        if method == "server/discover":
            return _discover_response(payload)
        if method == "subscriptions/listen":
            return _subscriptions_response(payload)
        if method in {"tools/list", "tools/call"}:
            if method == "tools/call":
                limited_response = tool_rate_limit_response(payload)
                if limited_response is not None:
                    return limited_response
            return _dash_tools_response(payload)
        return _jsonrpc_error(
            _request_id(payload),
            -32601,
            f"Method not found: {method}",
            status=404,
        )
