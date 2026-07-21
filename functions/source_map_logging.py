"""Logging controls for optional browser source-map requests."""

import logging
from typing import Any


class DashComponentSourceMapErrorFilter(logging.Filter):
    """Suppress missing Dash component source-map exceptions only.

    Component JavaScript continues to load normally when a package omits its
    optional ``.js.map`` file. Flask logs those missing files as application
    exceptions, which adds noise without indicating a user-facing failure.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        is_missing_component_source_map = (
            record.levelno >= logging.ERROR
            and message.startswith("Exception on /_dash-component-suites/")
            and ".js.map [" in message
        )
        return not is_missing_component_source_map


def register_source_map_error_filter(server: Any) -> None:
    """Prevent optional Dash component source-map lookup failures from logging."""
    server.logger.addFilter(DashComponentSourceMapErrorFilter())
