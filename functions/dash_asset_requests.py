"""Reject known malformed Dash component asset requests before routing."""

import re

from flask import Flask, abort, request


_NUMERIC_ASYNC_ASSET = re.compile(
    r"/_dash-component-suites/(?:[^/]+/)+[0-9]+\.async-[^/]+\.js"
)
_NESTED_COMPONENT_ASSET = re.compile(
    r"/_dash-component-suites/(?:[^/]+/)+_dash-component-suites/.+"
)


def register_dash_asset_request_guard(server: Flask) -> None:
    """Return 404 for malformed asset paths before Dash raises an exception.

    Args:
        server: Flask application serving Dash component assets.

    Returns:
        None.
    """

    @server.before_request
    def reject_malformed_component_asset() -> None:
        """Reject invalid asset GET/HEAD requests; leave other routing to Dash.

        Returns:
            None when the request can proceed through normal routing.
        """
        if request.method in {"GET", "HEAD"} and (
            _NUMERIC_ASYNC_ASSET.fullmatch(request.path)
            or _NESTED_COMPONENT_ASSET.fullmatch(request.path)
        ):
            abort(404)
