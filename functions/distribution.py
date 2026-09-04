"""Listing-count distribution strips drawn behind range sliders.

A range slider tells you where the handles sit but not what that costs you. The
strip renders how many listings fall in each slice of the range, and dims the
slices outside the current selection, so moving a handle shows the inventory it
removes.

The counts are computed once from the full dataset when the page is built. The
dimming is clientside, so dragging a handle repaints without a server round-trip.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from dash import ClientsideFunction, Input, Output, clientside_callback, html
import pandas as pd

BIN_COUNT = 44


def compute_distribution(
    series: pd.Series,
    *,
    minimum: float,
    maximum: float,
    bins: int = BIN_COUNT,
) -> list[int]:
    """Count listings per equal-width slice of a slider's range.

    Values above ``maximum`` land in the final bin, matching how the sliders
    treat their top stop as an open "unlimited" end.

    Args:
        series: Column of listing values backing the slider.
        minimum: Lower bound of the slider.
        maximum: Upper bound of the slider.
        bins: Number of slices to divide the range into.

    Returns:
        A list of ``bins`` counts, ordered from the low end of the range up.
    """
    if maximum <= minimum or bins < 1:
        return []

    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return []

    width = (maximum - minimum) / bins
    counts = [0] * bins
    for value in numeric:
        if value < minimum:
            continue
        index = int((value - minimum) / width)
        counts[min(index, bins - 1)] += 1
    return counts


def build_distribution_strip(
    *,
    slider_id: str,
    counts: Sequence[int],
    minimum: float = 0,
    maximum: float = 0,
    prefix: str = "",
    suffix: str = "",
) -> html.Div | None:
    """Build the bar strip that sits directly above a range slider's track.

    Bar heights use a square-root scale. Housing prices are steeply skewed, so a
    linear scale flattens everything outside the most common band into nothing.

    Args:
        slider_id: Dash id of the slider this strip annotates.
        counts: Listing count per bin, from ``compute_distribution``.
        minimum: Lower bound of the slider, for the hover readout.
        maximum: Upper bound of the slider, for the hover readout.
        prefix: Text shown before the hovered value, such as a currency symbol.
        suffix: Text shown after the hovered value, such as a unit.

    Returns:
        A ``Div`` holding the bars and the two dimming masks, or ``None`` when
        there is no distribution worth drawing.
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


def register_distribution_callback(
    *,
    slider_id: str,
    minimum: float,
    maximum: float,
) -> None:
    """Dim the strip outside the slider's selection as its handles move.

    Args:
        slider_id: Dash id of the slider driving the strip.
        minimum: Lower bound of the slider.
        maximum: Upper bound of the slider.

    Side Effects:
        Registers a clientside callback that restyles the two masks.

    Returns:
        None.
    """
    span = maximum - minimum
    if span <= 0:
        return

    clientside_callback(
        f"""
        function (value) {{
            const lo = Array.isArray(value) ? value[0] : {minimum};
            const hi = Array.isArray(value) ? value[1] : {maximum};
            const pct = (v) => Math.min(Math.max((v - {minimum}) / {span}, 0), 1) * 100;
            return [
                {{left: "0%", width: pct(lo) + "%"}},
                {{left: pct(hi) + "%", right: "0%"}},
            ];
        }}
        """,
        Output(f"{slider_id}_dist_lo", "style"),
        Output(f"{slider_id}_dist_hi", "style"),
        Input(slider_id, "value"),
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
    """Build a strip for a slider and wire its clientside dimming.

    Args:
        slider_id: Dash id of the slider this strip annotates.
        series: Column of listing values backing the slider.
        minimum: Lower bound of the slider.
        maximum: Upper bound of the slider.
        prefix: Text shown before the hovered value, such as a currency symbol.
        suffix: Text shown after the hovered value, such as a unit.

    Side Effects:
        Registers the clientside callback that dims the strip.

    Returns:
        The strip ``Div``, or ``None`` when there is nothing to draw.
    """
    counts = compute_distribution(series, minimum=minimum, maximum=maximum)
    strip = build_distribution_strip(
        slider_id=slider_id,
        counts=counts,
        minimum=minimum,
        maximum=maximum,
        prefix=prefix,
        suffix=suffix,
    )
    if strip is None:
        return None
    register_distribution_callback(
        slider_id=slider_id, minimum=minimum, maximum=maximum
    )
    return strip


__all__ = [
    "attach_distribution",
    "build_distribution_strip",
    "compute_distribution",
    "register_distribution_callback",
]
