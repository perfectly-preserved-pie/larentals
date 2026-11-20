"""Connection instructions shared by the interactive and static MCP guides."""

from typing import NamedTuple


MCP_ENDPOINT = "https://wheretolive.la/_mcp"
MCP_GUIDE_TITLE = "Search LA housing from your AI assistant."
MCP_GUIDE_INTRO = (
    "Connect Claude, ChatGPT, Codex, or another MCP client to search current "
    "rentals and homes for sale in Los Angeles County."
)
MCP_CONNECTION = (("Transport", "Streamable HTTP"), ("Authentication", "None"))
MCP_SEARCH_GUIDANCE = (
    "search_listings is a read-only tool that returns 10 listings by default "
    "and supports up to 100 per page."
)
MCP_FILTERS = (
    ("Rentals", "filter by rent, location, bedrooms, pets, furnishing, size, or listing date."),
    ("Homes for sale", "filter by price, location, bedrooms, HOA fees, lot size, or senior community."),
)
MCP_EXAMPLES = (
    "Find pet-friendly lease listings in Pasadena under $2,500 with at least two bedrooms.",
    "Show me homes to buy in Long Beach under $800,000, sorted by largest first.",
)


class SetupSnippet(NamedTuple):
    name: str
    text: str
    copy_label: str
    language: str


class ClientSetup(NamedTuple):
    name: str
    paragraphs: tuple[str, ...]
    snippet: SetupSnippet | None = None


MCP_CLIENTS = (
    ClientSetup(
        "Claude",
        (
            "In the Claude app, open Customize → Connectors, choose Add custom connector, "
            "and paste the server address.",
            "For Claude Code, run this in your terminal.",
        ),
        SetupSnippet(
            "claude-command", f"claude mcp add --transport http wheretolive {MCP_ENDPOINT}",
            "Copy command", "sh",
        ),
    ),
    ClientSetup(
        "ChatGPT",
        (
            "On the web, open Plugins, select the plus button, then choose Add custom MCP server. "
            "Name it WhereToLive.LA, paste the server address, and choose No authentication. "
            "Review the prompt and select Create as a plugin.",
            "Install the plugin, then select it with @ in a new Work chat. Custom MCP access "
            "depends on your account and workspace settings.",
        ),
    ),
    ClientSetup(
        "Codex",
        ("For the Codex CLI, run this in your terminal.",),
        SetupSnippet(
            "codex-command", f"codex mcp add wheretolive --url {MCP_ENDPOINT}",
            "Copy Codex command", "sh",
        ),
    ),
    ClientSetup(
        "Hermes Agent",
        (
            "Add this to ~/.hermes/config.yaml and restart Hermes. If you already have an "
            "mcp_servers section, add wheretolive under it.",
        ),
        SetupSnippet(
            "hermes-yaml", f'mcp_servers:\n  wheretolive:\n    url: "{MCP_ENDPOINT}"',
            "Copy YAML", "yaml",
        ),
    ),
    ClientSetup(
        "Other clients",
        (
            "In Cursor, VS Code with GitHub Copilot, or another compatible client, add a remote "
            "MCP server using Streamable HTTP (sometimes labeled HTTP) and paste the server address.",
        ),
    ),
)
