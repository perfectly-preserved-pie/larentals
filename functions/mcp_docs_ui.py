"""Build the human-facing MCP setup and documentation interface."""

from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc

from functions.site_identity import DTLA_RIDGELINE, DTLA_SKYLINE


MCP_ENDPOINT = "https://wheretolive.la/_mcp"

def _copyable_snippet(name: str, text: str, copy_label: str) -> html.Div:
    """Show a URL or configuration alongside its copy control.

    The clipboard script reads the code's text directly, preserving commands
    and YAML indentation when lines wrap. Keep feedback separate from the
    accessible button name so it can be announced without disrupting focus.

    Args:
        name: Unique snippet name used in the code and clipboard IDs.
        text: The exact URL, command, or configuration to show and copy.
        copy_label: Visible instruction on the copy button.

    Returns:
        A selectable snippet with a native copy button and status region.
    """
    code_id = f"mcp-{name}-value"
    return html.Div(
        [
            html.Pre(html.Code(text, id=code_id)),
            html.Div(
                [
                    html.Button(
                        html.Span(copy_label, **{"aria-hidden": "true"}),
                        id=f"mcp-{name}-copy",
                        type="button",
                        **{"aria-label": copy_label, "data-mcp-copy": code_id},
                    ),
                    html.Span(
                        className="mcp-docs__copy-status",
                        role="status",
                    ),
                ],
                className="mcp-docs__copy",
            ),
        ],
        className="mcp-docs__snippet",
    )


def build_mcp_docs_layout() -> html.Main:
    """Build the setup guide for the public listing search server.

    The contents menu jumps to the endpoint, setup instructions, and tool
    reference. Keep the skip link pointed at the page heading so keyboard
    users can bypass the shared site navigation and theme control.

    Returns:
        The complete Dash layout for the MCP documentation page.
    """
    claude_command = f"claude mcp add --transport http wheretolive {MCP_ENDPOINT}"
    hermes_config = f'mcp_servers:\n  wheretolive:\n    url: "{MCP_ENDPOINT}"'

    return html.Main(
        [
            html.A(
                "Skip to main content",
                href="#mcp-page-title",
                className="skip-link",
            ),
            html.Div(
                [
                    html.Header(
                        [
                            dcc.Link(
                                "WhereToLive.LA",
                                href="/",
                                className="mcp-docs__brand",
                            ),
                            html.Nav(
                                [
                                    dcc.Link("Rentals", href="/"),
                                    dcc.Link("For sale", href="/buy"),
                                    html.Span("MCP setup", **{"aria-current": "page"}),
                                ],
                                className="mcp-docs__site-links",
                                **{"aria-label": "Site navigation"},
                            ),
                            dmc.Switch(
                                id="color-scheme-switch",
                                label="Dark mode",
                                className="mcp-docs__theme-switch",
                                persisted_props=["checked"],
                                persistence=True,
                                persistence_type="local",
                                size="xs",
                            ),
                        ],
                        className="mcp-docs__masthead",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.P(
                                        "Model Context Protocol",
                                        className="mcp-docs__protocol",
                                    ),
                                    html.H1(
                                        "Search LA housing from your AI assistant.",
                                        id="mcp-page-title",
                                        tabIndex=-1,
                                    ),
                                    html.P(
                                        "Connect Claude, Hermes, or another MCP client "
                                        "to search current rentals and homes for sale "
                                        "in Los Angeles County.",
                                        className="mcp-docs__intro",
                                    ),
                                ],
                                className="mcp-docs__headline",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        "DOWNTOWN LOS ANGELES",
                                        className="mcp-docs__skyline-caption",
                                    ),
                                    html.Pre(
                                        [
                                            html.Span(
                                                DTLA_RIDGELINE,
                                                className="mcp-docs__ridgeline",
                                            ),
                                            html.Span(
                                                DTLA_SKYLINE,
                                                className="mcp-docs__buildings",
                                            ),
                                        ]
                                    ),
                                ],
                                className="mcp-docs__skyline",
                                role="img",
                                **{
                                    "aria-label": (
                                        "Downtown Los Angeles in ASCII, looking toward the San "
                                        "Gabriel Mountains. Wilshire Grand and U.S. Bank Tower "
                                        "rise above the surrounding blocks, with City Hall at right."
                                    )
                                },
                            ),
                        ],
                        className="mcp-docs__opening",
                    ),
                    html.Div(
                        [
                            html.Nav(
                                [
                                    html.H2("On this page"),
                                    html.Ul(
                                        [
                                            html.Li(html.A("Server address", href="#endpoint")),
                                            html.Li(html.A("Client setup", href="#setup")),
                                            html.Li(html.A("Listing search", href="#search")),
                                            html.Li(html.A("Examples", href="#examples")),
                                        ]
                                    ),
                                ],
                                className="mcp-docs__contents",
                                **{"aria-label": "On this page"},
                            ),
                            html.Div(
                                [
                                    html.Section(
                                        [
                                            html.H2("Server address", id="endpoint", tabIndex=-1),
                                            _copyable_snippet(
                                                "endpoint",
                                                MCP_ENDPOINT,
                                                "Copy URL",
                                            ),
                                            html.Dl(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Dt("Transport"),
                                                            html.Dd("Streamable HTTP"),
                                                        ]
                                                    ),
                                                    html.Div(
                                                        [
                                                            html.Dt("Authentication"),
                                                            html.Dd("None"),
                                                        ]
                                                    ),
                                                ],
                                                className="mcp-docs__connection",
                                            ),
                                        ]
                                    ),
                                    html.Section(
                                        [
                                            html.H2("Client setup", id="setup", tabIndex=-1),
                                            html.H3("Claude"),
                                            html.P(
                                                [
                                                    "In the Claude app, open ",
                                                    html.Strong("Customize → Connectors"),
                                                    ", choose ",
                                                    html.Strong("Add custom connector"),
                                                    ", and paste the server address.",
                                                ]
                                            ),
                                            html.P("For Claude Code, run this in your terminal."),
                                            _copyable_snippet(
                                                "claude-command", claude_command, "Copy command"
                                            ),
                                            html.H3("Hermes"),
                                            html.P(
                                                [
                                                    "Add this to ",
                                                    html.Code("~/.hermes/config.yaml"),
                                                    " and restart Hermes. If you already have "
                                                    "an ",
                                                    html.Code("mcp_servers"),
                                                    " section, add ",
                                                    html.Code("wheretolive"),
                                                    " under it.",
                                                ]
                                            ),
                                            _copyable_snippet(
                                                "hermes-yaml", hermes_config, "Copy YAML"
                                            ),
                                            html.H3("Other clients"),
                                            html.P(
                                                "Add a remote MCP server, choose Streamable "
                                                "HTTP (sometimes labeled HTTP), and paste "
                                                "the server address."
                                            ),
                                        ]
                                    ),
                                    html.Section(
                                        [
                                            html.H2("Listing search", id="search", tabIndex=-1),
                                            html.P(
                                                [
                                                    html.Code("search_listings"),
                                                    " is a read-only tool that returns 10 "
                                                    "listings by default and supports up to "
                                                    "100 per page.",
                                                ]
                                            ),
                                            html.Ul(
                                                [
                                                    html.Li(
                                                        [
                                                            html.Strong("Rentals"),
                                                            " — filter by rent, location, bedrooms, "
                                                            "pets, furnishing, size, or listing date.",
                                                        ]
                                                    ),
                                                    html.Li(
                                                        [
                                                            html.Strong("Homes for sale"),
                                                            " — filter by price, location, bedrooms, "
                                                            "HOA fees, lot size, or senior community.",
                                                        ]
                                                    ),
                                                ]
                                            ),
                                        ]
                                    ),
                                    html.Section(
                                        [
                                            html.H2(
                                                "Example searches",
                                                id="examples",
                                                tabIndex=-1,
                                            ),
                                            html.Ul(
                                                [
                                                    html.Li(
                                                        html.Q(
                                                            "Find pet-friendly lease listings in Pasadena "
                                                            "under $2,500 with at least two bedrooms."
                                                        )
                                                    ),
                                                    html.Li(
                                                        html.Q(
                                                            "Show me homes to buy in Long Beach under "
                                                            "$800,000, sorted by largest first."
                                                        )
                                                    ),
                                                ]
                                            ),
                                        ]
                                    ),
                                ],
                                className="mcp-docs__article",
                            ),
                        ],
                        className="mcp-docs__body",
                    ),
                    html.Footer(
                        [
                            html.A("Back to top", href="#mcp-page-title"),
                            html.A(
                                "Project on GitHub",
                                href="https://github.com/perfectly-preserved-pie/larentals",
                                target="_blank",
                                rel="noopener",
                            ),
                        ],
                        className="mcp-docs__footer",
                    ),
                ],
                className="mcp-docs__frame",
            ),
        ],
        className="mcp-docs",
    )
