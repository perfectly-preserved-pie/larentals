"""Handle invalid numeric-prefixed Dash async asset requests."""

import re

from flask import Flask, abort, request


_NUMERIC_ASYNC_ASSET = re.compile(
    r"/_dash-component-suites/(?:[^/]+/)+[0-9]+\.async-[^/]+\.js"
)


def register_dash_asset_request_guard(server: Flask) -> None:
    """Return 404 for scanned chunk filenames before Dash raises an exception."""

    @server.before_request
    def reject_numeric_async_asset() -> None:
        """Reject invalid asset GET/HEAD requests; leave other routing to Dash."""
        if request.method in {"GET", "HEAD"} and _NUMERIC_ASYNC_ASSET.fullmatch(
            request.path
        ):
            abort(404)
