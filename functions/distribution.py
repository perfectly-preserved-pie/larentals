"""Histogram strips for range filters."""

from __future__ import annotations

from collections.abc import Sequence
from dash import Input, Output, clientside_callback, html
import pandas as pd

BIN_COUNT = 44


def compute_distribution(
    series: pd.Series, *, minimum: float, maximum: float, bins: int = BIN_COUNT
) -> list[int]:
    """Count usable values in the slider's equal-width histogram bins.

    Values below the displayed minimum are omitted. Values at or above the
    maximum land in the last bin so the strip still represents an open-ended
    slider limit. Invalid ranges and empty samples produce no bins.

    Args:
        series: Listing values shown by the filter.
        minimum: First displayed slider value.
        maximum: Last displayed slider value.
        bins: Number of equal-width bars to produce.

    Returns:
        Counts ordered from low to high, or an empty list.
    """
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
    """Build the histogram markup that sits behind a range slider.

    Mask and readout elements carry predictable IDs for the client-side
    selection callback. Bar heights use a square-root scale so a few dense
    bins do not flatten the rest of the distribution.

    Args:
        slider_id: Base ID shared with the slider callback.
        counts: Listing count for each histogram bin.
        minimum: First displayed slider value.
        maximum: Last displayed slider value.
        prefix: Text placed before values in the readout.
        suffix: Text placed after values in the readout.

    Returns:
        Histogram markup, or None when every bin is empty.
    """
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
    distribution_id: str | None = None,
) -> html.Div | None:
    """Build a distribution strip and register live selection shading.

    The server renders the histogram once; a client-side callback then moves
    only the masks while the slider is dragged. This keeps the visual response
    quick without rerunning the listing filter on every movement.

    Args:
        slider_id: ID of the range slider that drives the selection shading.
        series: Listing values used to calculate histogram bin counts.
        minimum: Lower bound of the displayed range.
        maximum: Upper bound of the displayed range.
        prefix: Optional text shown before values in the readout.
        suffix: Optional text shown after values in the readout.
        distribution_id: Optional unique ID for histogram elements and outputs.

    Returns:
        The histogram strip, or ``None`` when no distribution can be shown.
    """
    strip_id = distribution_id or slider_id
    strip = build_distribution_strip(
        slider_id=strip_id,
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
        Output(f"{strip_id}_dist_lo", "style"),
        Output(f"{strip_id}_dist_hi", "style"),
        Input(slider_id, "value"), Input(slider_id, "drag_value"),
    )
    return strip
