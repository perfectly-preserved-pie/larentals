"""Reject known malformed Dash component asset requests before routing."""

import re

from flask import Flask, abort, request


# Matches only the final path segment of a numeric async asset, e.g.
# "12345.async-abc123.js".  Applied to a single segment so no
# multi-segment backtracking is possible.
_NUMERIC_ASYNC_FILENAME = re.compile(r"[0-9]+\.async-[^/]+\.js")

_COMPONENT_SUITES_PREFIX = "/_dash-component-suites/"


def _is_numeric_async_asset(path: str) -> bool:
    """Return True when *path* looks like a Dash numeric async asset URL.

    Splits on ``/`` and validates only the final filename segment with a
    simple anchored regex instead of applying a multi-segment pattern to
    the whole path, which avoids polynomial backtracking.

    Args:
        path: URL path from the incoming request.

    Returns:
        True when the path starts with the component-suites prefix, has at
        least one package directory between the prefix and the filename, and
        the filename matches the ``DIGITS.async-NAME.js`` pattern.
    """
    if not path.startswith(_COMPONENT_SUITES_PREFIX):
        return False
    parts = path.split("/")
    # Expected structure: ['', '_dash-component-suites', pkg, ..., filename]
    return len(parts) >= 4 and bool(_NUMERIC_ASYNC_FILENAME.fullmatch(parts[-1]))


def _is_nested_component_asset(path: str) -> bool:
    """Return True when *path* embeds a second ``_dash-component-suites`` segment.

    Uses a plain substring search rather than a regex so there is no
    backtracking risk.

    Args:
        path: URL path from the incoming request.

    Returns:
        True when the path starts with the component-suites prefix and the
        prefix appears again within the remainder of the path.
    """
    if not path.startswith(_COMPONENT_SUITES_PREFIX):
        return False
    rest = path[len(_COMPONENT_SUITES_PREFIX):]
    return _COMPONENT_SUITES_PREFIX in rest


def register_dash_asset_request_guard(server: Flask) -> None:
    """Return 404 for malformed asset paths before Dash raises an exception.

    Installing once avoids duplicate Flask before-request hooks during app setup.

    Args:
        server: Flask application serving Dash component assets.

    Returns:
        None.
    """

    @server.before_request
    def reject_malformed_component_asset() -> None:
        """Reject invalid asset GET/HEAD requests; leave other routing to Dash.

        Only suspicious asset requests are intercepted; valid Dash routes continue through the framework.

        Returns:
            None when the request can proceed through normal routing.
        """
        if request.method in {"GET", "HEAD"} and (
            _is_numeric_async_asset(request.path)
            or _is_nested_component_asset(request.path)
        ):
            abort(404)
