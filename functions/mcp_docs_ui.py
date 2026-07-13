"""Build the human-facing MCP setup and documentation interface."""

from __future__ import annotations

from collections.abc import Sequence

from dash import dcc, html
from dash.development.base_component import Component
from dash_iconify import DashIconify
import dash_mantine_components as dmc


MCP_ENDPOINT = "https://wheretolive.la/_mcp"


def _setup_card(
    *,
    icon: str,
    label: str,
    title: str,
    children: Sequence[Component | str],
) -> html.Article:
    """Build one client-specific setup card.

    The shared structure keeps Claude, Hermes, and generic instructions aligned.
    """
    return html.Article(
        [
            html.Div(
                DashIconify(icon=icon, width=22),
                className="mcp-docs__card-icon",
            ),
            html.Div(label, className="mcp-docs__card-label"),
            html.H3(title),
            *children,
        ],
        className="mcp-docs__setup-card",
    )


def _feature_card(*, icon: str, title: str, copy: str) -> html.Article:
    """Build a compact capability card for the page overview.

    Each card pairs one MCP capability with a short plain-language explanation.
    """
    return html.Article(
        [
            DashIconify(icon=icon, width=20),
            html.Div([html.H3(title), html.P(copy)]),
        ],
        className="mcp-docs__feature-card",
    )


def build_mcp_docs_layout() -> html.Main:
    """Build the responsive documentation page for the public MCP server.

    The page includes endpoint copying, client setup, capabilities, and prompts.
    """
    claude_command = (
        "claude mcp add --transport http wheretolive "
        "https://wheretolive.la/_mcp"
    )
    hermes_config = (
        "mcp_servers:\n"
        "  wheretolive:\n"
        '    url: "https://wheretolive.la/_mcp"'
    )

    return html.Main(
        [
            html.Nav(
                [
                    dcc.Link(
                        [
                            html.Span("W", className="mcp-docs__brand-mark"),
                            html.Span("WhereToLive.LA"),
                        ],
                        href="/",
                        className="mcp-docs__brand",
                        title="Return to the WhereToLive.LA rental map",
                    ),
                    html.Div(
                        [
                            dmc.Switch(
                                id="color-scheme-switch",
                                offLabel=DashIconify(
                                    icon="radix-icons:sun",
                                    width=14,
                                ),
                                onLabel=DashIconify(
                                    icon="radix-icons:moon",
                                    width=14,
                                ),
                                className="mcp-docs__theme-switch",
                                color="gray",
                                persisted_props=["checked"],
                                persistence=True,
                                persistence_type="local",
                                size="md",
                                **{"aria-label": "Toggle light/dark mode"},
                            ),
                        ],
                        className="mcp-docs__nav-actions",
                    ),
                ],
                className="mcp-docs__nav",
                **{"aria-label": "MCP documentation navigation"},
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    DashIconify(icon="lucide:bot", width=17),
                                    "Model Context Protocol",
                                ],
                                className="mcp-docs__eyebrow",
                            ),
                            html.H1(
                                [
                                    "Search LA housing from ",
                                    html.Span("your AI assistant."),
                                ]
                            ),
                            html.P(
                                "Connect Claude, Hermes, or any Streamable HTTP "
                                "client to current lease and for-sale listings.",
                                className="mcp-docs__lede",
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        [
                                            DashIconify(
                                                icon="lucide:eye",
                                                width=15,
                                            ),
                                            "Read-only",
                                        ]
                                    ),
                                    html.Span(
                                        [
                                            DashIconify(
                                                icon="lucide:shield-check",
                                                width=15,
                                            ),
                                            "No authentication",
                                        ]
                                    ),
                                    html.Span(
                                        [
                                            DashIconify(
                                                icon="lucide:search",
                                                width=15,
                                            ),
                                            "Live listing search",
                                        ]
                                    ),
                                ],
                                className="mcp-docs__trust-row",
                            ),
                        ],
                        className="mcp-docs__hero-copy",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Streamable HTTP endpoint"),
                                    html.Span("Ready", className="mcp-docs__ready"),
                                ],
                                className="mcp-docs__endpoint-header",
                            ),
                            html.Div(
                                [
                                    html.Code(
                                        MCP_ENDPOINT,
                                        id="mcp-endpoint-value",
                                    ),
                                    dcc.Clipboard(
                                        id="mcp-endpoint-copy",
                                        content=MCP_ENDPOINT,
                                        children=[
                                            DashIconify(
                                                icon="lucide:copy",
                                                width=16,
                                            ),
                                            html.Span("Copy endpoint"),
                                        ],
                                        copied_children=[
                                            DashIconify(
                                                icon="lucide:check",
                                                width=16,
                                            ),
                                            html.Span("Copied"),
                                        ],
                                        title="Copy MCP endpoint",
                                        className="mcp-docs__copy-button",
                                    ),
                                ],
                                className="mcp-docs__endpoint-value",
                            ),
                            html.P(
                                "Clients discover one bounded, read-only tool: "
                                "search_listings.",
                            ),
                        ],
                        className="mcp-docs__endpoint-card",
                    ),
                ],
                className="mcp-docs__hero",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div("Connect", className="mcp-docs__section-label"),
                            html.H2("Choose your client"),
                            html.P(
                                "Setup takes less than a minute. No API key is required."
                            ),
                        ],
                        className="mcp-docs__section-heading",
                    ),
                    html.Div(
                        [
                            _setup_card(
                                icon="simple-icons:anthropic",
                                label="Claude",
                                title="Claude app or Claude Code",
                                children=[
                                    html.P(
                                        "In Claude, open Customize → Connectors, "
                                        "choose Add custom connector, and paste the endpoint."
                                    ),
                                    html.Div(
                                        [
                                            html.Code(claude_command),
                                            dcc.Clipboard(
                                                content=claude_command,
                                                title="Copy Claude Code command",
                                                className="mcp-docs__inline-copy",
                                            ),
                                        ],
                                        className="mcp-docs__code-block",
                                    ),
                                ],
                            ),
                            _setup_card(
                                icon="lucide:terminal-square",
                                label="Hermes",
                                title="Add a remote server",
                                children=[
                                    html.P(
                                        "Add the server to ~/.hermes/config.yaml, "
                                        "then restart Hermes to discover its tools."
                                    ),
                                    html.Div(
                                        [
                                            html.Pre(html.Code(hermes_config)),
                                            dcc.Clipboard(
                                                content=hermes_config,
                                                title="Copy Hermes configuration",
                                                className="mcp-docs__inline-copy",
                                            ),
                                        ],
                                        className="mcp-docs__code-block",
                                    ),
                                ],
                            ),
                            _setup_card(
                                icon="lucide:plug-zap",
                                label="Other clients",
                                title="Use standard HTTP",
                                children=[
                                    html.P(
                                        "Create a remote MCP connection, select "
                                        "Streamable HTTP (sometimes labeled HTTP), "
                                        "and use the endpoint above."
                                    ),
                                    html.Div(
                                        [
                                            html.Span("Transport"),
                                            html.Strong("Streamable HTTP"),
                                        ],
                                        className="mcp-docs__config-row",
                                    ),
                                    html.Div(
                                        [
                                            html.Span("Authentication"),
                                            html.Strong("None"),
                                        ],
                                        className="mcp-docs__config-row",
                                    ),
                                ],
                            ),
                        ],
                        className="mcp-docs__setup-grid",
                    ),
                ],
                className="mcp-docs__section",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div("Capabilities", className="mcp-docs__section-label"),
                            html.H2("One focused tool, useful answers"),
                        ],
                        className="mcp-docs__section-heading",
                    ),
                    html.Div(
                        [
                            _feature_card(
                                icon="lucide:building-2",
                                title="Lease listings",
                                copy=(
                                    "Filter by rent, location, bedrooms, pets, "
                                    "furnishing, size, and listing date."
                                ),
                            ),
                            _feature_card(
                                icon="lucide:home",
                                title="Homes for sale",
                                copy=(
                                    "Search by price, location, bedrooms, HOA, "
                                    "lot size, senior community, and more."
                                ),
                            ),
                            _feature_card(
                                icon="lucide:gauge",
                                title="Bounded responses",
                                copy=(
                                    "Results are paginated and capped at 20 listings "
                                    "per call for fast, predictable answers."
                                ),
                            ),
                        ],
                        className="mcp-docs__feature-grid",
                    ),
                ],
                className="mcp-docs__section mcp-docs__section--compact",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div("Try it", className="mcp-docs__section-label"),
                            html.H2("Ask naturally"),
                            html.P(
                                "Just describe the home you’re looking for—your "
                                "assistant handles the search."
                            ),
                        ],
                        className="mcp-docs__section-heading",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    DashIconify(icon="lucide:message-circle", width=18),
                                    html.Span(
                                        "Find pet-friendly lease listings in Pasadena "
                                        "under $2,500 with at least two bedrooms."
                                    ),
                                ],
                                className="mcp-docs__prompt",
                            ),
                            html.Div(
                                [
                                    DashIconify(icon="lucide:message-circle", width=18),
                                    html.Span(
                                        "Show me homes to buy in Long Beach under "
                                        "$800,000, sorted by largest first."
                                    ),
                                ],
                                className="mcp-docs__prompt",
                            ),
                        ],
                        className="mcp-docs__prompt-grid",
                    ),
                ],
                className="mcp-docs__section mcp-docs__section--prompts",
            ),
            html.Footer(
                [
                    html.Div(
                        [
                            html.Strong("WhereToLive.LA"),
                            html.Span("Open housing search for Los Angeles County."),
                        ]
                    ),
                    html.Div(
                        [
                            dcc.Link("Rentals", href="/"),
                            dcc.Link("For sale", href="/buy"),
                            html.A(
                                "GitHub",
                                href=(
                                    "https://github.com/"
                                    "perfectly-preserved-pie/larentals"
                                ),
                                target="_blank",
                                rel="noopener",
                            ),
                        ]
                    ),
                ],
                className="mcp-docs__footer",
            ),
        ],
        className="mcp-docs dbc dmc",
    )
