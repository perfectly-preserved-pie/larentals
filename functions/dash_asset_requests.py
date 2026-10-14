"""Reject known malformed Dash component asset requests before routing."""

from dash.exceptions import DependencyException
from flask import Flask, Response, abort, request
from werkzeug.exceptions import NotFound


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
    """Return 404 for malformed or unregistered Dash component assets.

    Known malformed paths are rejected before routing. Other filenames are
    validated by Dash itself so fingerprinted bundles and newly registered
    assets follow the framework's rules without a separate allowlist.

    Args:
        server: Flask application serving Dash component assets.

    Returns:
        None.
    """

    @server.errorhandler(DependencyException)
    def missing_component_asset(error: DependencyException) -> Response:
        """Translate Dash asset validation failures into ordinary missing files.

        Only component asset GET/HEAD requests qualify; dependency failures in
        callbacks or other routes must remain visible as application errors.

        Args:
            error: Dependency failure raised while dispatching the request.

        Returns:
            A standard 404 response for an unregistered component asset.
        """
        if request.method in {"GET", "HEAD"} and request.path.startswith(
            _COMPONENT_SUITES_PREFIX
        ):
            return NotFound().get_response(request.environ)
        raise error

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
