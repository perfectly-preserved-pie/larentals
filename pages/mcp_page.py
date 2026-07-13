"""Human-facing setup page for the public WhereToLive.LA MCP server."""

from __future__ import annotations

import dash
from dash import html

from functions.mcp_docs_ui import build_mcp_docs_layout


dash.register_page(
    __name__,
    path="/mcp",
    name="MCP Setup",
    title="Connect WhereToLive.LA to Your AI Assistant",
    description=(
        "Connect Claude, Hermes, and other MCP clients to read-only Los Angeles "
        "County lease and for-sale listing search."
    ),
)


def layout(**_: object) -> html.Main:
    """Build the MCP documentation page on demand.

    Dash may pass query-string values, which this static page does not use.
    """
    return build_mcp_docs_layout()
