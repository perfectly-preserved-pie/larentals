"""Reject known malformed Dash component asset requests before routing."""

from flask import Flask, abort, request


_COMPONENT_SUITES_PREFIX = "/_dash-component-suites/"


def _is_numeric_async_asset(path: str) -> bool:
    """Return True when *path* looks like a Dash numeric async asset URL.

    Validates the prefix and the final filename segment using only string
    operations (``endswith``, ``find``, ``isdigit``) to avoid any regex
    backtracking.  The expected filename shape is ``DIGITS.async-NAME.js``.

    Args:
        path: URL path from the incoming request.

    Returns:
        True when the path has the component-suites prefix, at least one
        package directory segment, and a final filename matching the
        ``DIGITS.async-NAME.js`` shape.
    """
    if not path.startswith(_COMPONENT_SUITES_PREFIX):
        return False
    parts = path.split("/")
    # Expected structure: ['', '_dash-component-suites', pkg, ..., filename]
    if len(parts) < 4:
        return False
    name = parts[-1]
    if not name.endswith(".js"):
        return False
    async_idx = name.find(".async-")
    if async_idx == -1:
        return False
    return name[:async_idx].isdigit()


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
