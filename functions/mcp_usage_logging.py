from __future__ import annotations

import time
from typing import Any

from flask import Response, g, request
from loguru import logger


MAX_LOG_VALUE_LENGTH = 160


def register_mcp_usage_logging(server: Any, *, mcp_path: str = "/_mcp") -> None:
    """
    Register metadata-only request logging for the Dash MCP endpoint.
    """
    normalized_mcp_path = _normalize_mcp_path(mcp_path)

    @server.before_request
    def start_mcp_usage_timer() -> None:
        if request.path == normalized_mcp_path:
            g.mcp_usage_start_time = time.perf_counter()

    @server.after_request
    def log_mcp_usage(response: Response) -> Response:
        if request.path != normalized_mcp_path:
            return response

        start_time = getattr(g, "mcp_usage_start_time", None)
        duration_ms = (
            (time.perf_counter() - start_time) * 1000
            if isinstance(start_time, float)
            else 0.0
        )
        payload = _get_json_payload()
        rpc_method = _rpc_method_from_payload(payload) or "-"
        target = _target_from_payload(payload) or "-"
        user_agent = request.user_agent.string or "-"

        logger.info(
            f"MCP request method={request.method} rpc_method={rpc_method} "
            f"target={target} status={response.status_code} "
            f"duration_ms={duration_ms:.1f} user_agent={user_agent!r}"
        )
        return response


def _normalize_mcp_path(mcp_path: str) -> str:
    path = str(mcp_path or "").strip() or "_mcp"
    return "/" + path.strip("/")


def _get_json_payload() -> dict[str, Any] | None:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


def _rpc_method_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    return _clean_log_value(payload.get("method"))


def _target_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None

    params = payload.get("params")
    if not isinstance(params, dict):
        return None

    for key in ("name", "uri", "taskId"):
        target = _clean_log_value(params.get(key))
        if target:
            return target
    return None


def _clean_log_value(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    if not text:
        return None

    if len(text) > MAX_LOG_VALUE_LENGTH:
        return f"{text[:MAX_LOG_VALUE_LENGTH]}..."
    return text
