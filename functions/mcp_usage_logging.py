from __future__ import annotations

import json
import time
from typing import Any

from flask import Response, g, request
from loguru import logger


MAX_LOG_VALUE_LENGTH = 160
MAX_LOG_ARGUMENTS_LENGTH = 1_000


def register_mcp_usage_logging(server: Any, *, mcp_path: str = "/_mcp") -> None:
    """
    Register tool-usage logging for the Dash MCP endpoint.

    MCP clients make several protocol and discovery requests for every session.
    Those requests are intentionally ignored: a log record is emitted only when
    a client invokes a tool.
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

        payload = _get_json_payload()
        if _rpc_method_from_payload(payload) != "tools/call":
            return response

        start_time = getattr(g, "mcp_usage_start_time", None)
        duration_ms = (
            (time.perf_counter() - start_time) * 1000
            if isinstance(start_time, float)
            else 0.0
        )
        tool_name = _target_from_payload(payload) or "-"
        arguments = _arguments_from_payload(payload)
        result_summary = _result_summary(response)

        logger.info(
            f"MCP tool call tool={tool_name} arguments={arguments} "
            f"status={response.status_code} duration_ms={duration_ms:.1f} "
            f"result={result_summary} user_agent={(request.user_agent.string or '-')!r}"
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


def _arguments_from_payload(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return "{}"

    params = payload.get("params")
    if not isinstance(params, dict):
        return "{}"

    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        return "{}"

    serialized = json.dumps(arguments, ensure_ascii=True, sort_keys=True, default=str)
    if len(serialized) > MAX_LOG_ARGUMENTS_LENGTH:
        return f"{serialized[:MAX_LOG_ARGUMENTS_LENGTH]}..."
    return serialized


def _result_summary(response: Response) -> str:
    """Return useful outcome metadata without logging a tool's full response."""
    payload = response.get_json(silent=True)
    if not isinstance(payload, dict):
        return "unparseable"

    if isinstance(payload.get("error"), dict):
        return "rpc_error"

    result = payload.get("result")
    if not isinstance(result, dict):
        return "missing"

    if result.get("isError") is True:
        return "tool_error"

    structured_content = result.get("structuredContent")
    if not isinstance(structured_content, dict):
        return "success"

    tool_result = structured_content.get("result")
    if not isinstance(tool_result, dict):
        return "success"

    details: list[str] = []
    for key in ("listing_type", "total_results", "page", "page_size"):
        value = _clean_log_value(tool_result.get(key))
        if value is not None:
            details.append(f"{key}={value}")
    return f"success({','.join(details)})" if details else "success"


def _clean_log_value(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    if not text:
        return None

    if len(text) > MAX_LOG_VALUE_LENGTH:
        return f"{text[:MAX_LOG_VALUE_LENGTH]}..."
    return text
