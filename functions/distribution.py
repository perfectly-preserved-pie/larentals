"""Histogram strips for range filters."""

from __future__ import annotations

from collections.abc import Sequence
from dash import Input, Output, clientside_callback, html
import pandas as pd

BIN_COUNT = 44


def compute_distribution(
    series: pd.Series, *, minimum: float, maximum: float, bins: int = BIN_COUNT
) -> list[int]:
    """Return listing counts for equal-width bins across a slider range."""
    if maximum <= minimum or bins < 1:
        return []
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy()
    values = values[values >= minimum]
    if not len(values):
        return []
    indices = ((values - minimum) / ((maximum - minimum) / bins)).astype(int)
    indices = indices.clip(0, bins - 1)
    counts = pd.Series(indices).value_counts().reindex(range(bins), fill_value=0)
    return [int(count) for count in counts]


def build_distribution_strip(
    *,
    slider_id: str,
    counts: Sequence[int],
    minimum: float,
    maximum: float,
    prefix: str = "",
    suffix: str = "",
) -> html.Div | None:
    """Render count bars and masks synchronized with a range slider."""
    if not counts or not any(counts):
        return None
    peak = max(counts)
    bars = [
        html.Div(
            className="dist__bar",
            style={"height": f"{max((count / peak) ** 0.5 * 100, 2):.1f}%"},
        )
        for count in counts
    ]
    return html.Div(
        [
            html.Div(bars, className="dist__bars"),
            html.Div(id=f"{slider_id}_dist_lo", className="dist__mask"),
            html.Div(id=f"{slider_id}_dist_hi", className="dist__mask"),
            html.Div(className="dist__cursor"),
            html.Div(className="dist__readout"),
        ],
        className="dist",
        **{
            "aria-hidden": "true",
            "data-min": str(minimum),
            "data-max": str(maximum),
            "data-prefix": prefix,
            "data-suffix": suffix,
        },
    )


def attach_distribution(
    *,
    slider_id: str,
    series: pd.Series,
    minimum: float,
    maximum: float,
    prefix: str = "",
    suffix: str = "",
) -> html.Div | None:
    """Build a distribution strip and register live selection shading."""
    strip = build_distribution_strip(
        slider_id=slider_id,
        counts=compute_distribution(series, minimum=minimum, maximum=maximum),
        minimum=minimum,
        maximum=maximum,
        prefix=prefix,
        suffix=suffix,
    )
    if strip is None or maximum <= minimum:
        return strip
    span = maximum - minimum
    clientside_callback(
        f"""function(value, dragValue) {{
            const ctx = dash_clientside.callback_context;
            const prop = ctx && ctx.triggered && ctx.triggered.length ? ctx.triggered[0].prop_id : '';
            const range = prop.endsWith('.drag_value') ? dragValue : value;
            const lo = Array.isArray(range) ? range[0] : {minimum};
            const hi = Array.isArray(range) ? range[1] : {maximum};
            const pct = v => Math.min(Math.max((v - {minimum}) / {span}, 0), 1) * 100;
            return [{{left:'0%', width:pct(lo)+'%'}}, {{left:pct(hi)+'%', right:'0%'}}];
        }}""",
        Output(f"{slider_id}_dist_lo", "style"),
        Output(f"{slider_id}_dist_hi", "style"),
        Input(slider_id, "value"), Input(slider_id, "drag_value"),
    )
    return strip
