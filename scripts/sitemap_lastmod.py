"""Collect modification dates for public pages from a complete Git checkout."""

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SHARED_PAGE_SOURCES = ("functions/seo.py",)
MAP_SOURCES = (
    "data/runtime/larentals.db",
    "pages/component_factories.py",
    "pages/responsive_filter_ui.py",
)
PAGE_SOURCES = {
    "/": ("pages/lease_page.py", "pages/lease_components.py", *MAP_SOURCES),
    "/buy": ("pages/buy_page.py", "pages/buy_components.py", *MAP_SOURCES),
    "/mcp": ("templates/mcp_guide.html", "functions/mcp_guide.py"),
}


def collect_page_dates() -> dict[str, str]:
    """Find the commit date of the most recent tracked content change per page.

    Both maps serve the same database snapshot. Track that file with each map's
    page sources so a listing refresh updates the map dates without touching
    the MCP guide. Skip paths without history so the sitemap stays truthful.

    Returns:
        ISO calendar dates keyed by canonical browser path.
    """
    dates = {}
    for route, paths in PAGE_SOURCES.items():
        modified = subprocess.check_output(
            ["git", "log", "-1", "--format=%cs", "--", *SHARED_PAGE_SOURCES, *paths],
            cwd=ROOT,
            text=True,
        ).strip()
        if modified:
            dates[route] = modified
    return dates


if __name__ == "__main__":
    print(json.dumps(collect_page_dates(), separators=(",", ":")))
