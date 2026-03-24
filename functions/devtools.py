"""Dash devtools hook for surfacing clientside filter exclusions.
See https://dash.plotly.com/dash-plugins-using-hooks#adding-components-to-dev-tools-ui-with-hooks.devtool
"""

from __future__ import annotations

import dash

_REGISTERED = False


def register_filter_exclusion_devtool() -> None:
    """Register the custom devtools panel once per process."""
    global _REGISTERED

    if _REGISTERED:
        return

    hooks = getattr(dash, "hooks", None)
    if hooks is None or not hasattr(hooks, "devtool"):
        return

    hooks.devtool(
        namespace="LarentalsDevtools",
        component_type="FilterExclusionPanel",
        props={"title": "Filter Exclusions"},
        position="left",
    )
    _REGISTERED = True
