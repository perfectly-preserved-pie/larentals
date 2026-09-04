from collections.abc import Sequence
from dataclasses import dataclass
import json
from datetime import date
import math
import re
from typing import Any, Mapping
from dash import Input, Output, clientside_callback, dcc, html
from dash_extensions.javascript import Namespace
from dash_iconify import DashIconify
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_mantine_components as dmc
import numpy as np
import pandas as pd

from .component_models import DashId, FilterSection, PageConfig, PageParts
from functions.convex_hull import generate_convex_hulls
from functions.layers import (
    SCHOOL_LAYER_CAMPUS_CONFIGURATION_OPTIONS,
    DEFAULT_SCHOOL_LAYER_ENROLLMENT_MAX,
    SCHOOL_LAYER_FUNDING_TYPE_OPTIONS,
    SCHOOL_LAYER_GRADE_BAND_OPTIONS,
    SCHOOL_LAYER_LEVEL_OPTIONS,
)


@dataclass(frozen=True)
class CappedRangeBounds:
    """Robust display bounds that preserve values above the visible scale."""

    minimum: int | float
    maximum: int | float
    is_capped: bool
    capped_at: int | float | None = None

    @property
    def display_maximum(self) -> int | float:
        """Return the largest numeric value shown on a finite slider scale.

        Returns:
            The largest value displayed on the finite slider.
        """
        if self.is_capped and self.capped_at is not None:
            return self.capped_at
        return self.maximum

    def marks(
        self,
        *,
        currency: bool = False,
        suffix: str = "",
        include_open_end: bool = True,
        target_intervals: int = 5,
    ) -> Mapping[int | float, str] | None:
        """Return readable marks, optionally followed by an ``Unlimited`` stop.

        Args:
            currency: Whether currency behavior is enabled.
            suffix: Unit suffix appended to each generated slider label.
            include_open_end: Whether include open end behavior is enabled.
            target_intervals: Approximate number of labeled intervals to generate.

        Returns:
            A mapping containing the marks.
        """
        if not self.is_capped and include_open_end:
            return None

        finite_maximum = self.display_maximum

        def format_value(value: int | float) -> str:
            """Handle format value.

            Args:
                value: Numeric slider mark to format for display.

            Returns:
                The formatted value text.
            """
            numeric = float(value)
            absolute = abs(numeric)
            scale = 1.0
            unit = ""
            if absolute >= 1_000_000:
                scale = 1_000_000
                unit = "M"
            elif absolute >= 1_000:
                scale = 1_000
                unit = "k"
            scaled = numeric / scale
            rendered = (
                f"{scaled:,.0f}"
                if scaled.is_integer()
                else f"{scaled:,.2f}".rstrip("0").rstrip(".")
            )
            prefix = "$" if currency else ""
            return f"{prefix}{rendered}{unit}{suffix}"

        span = float(finite_maximum) - float(self.minimum)
        if span <= 0:
            return {
                self.minimum: format_value(self.minimum),
            }
        target_step = span / max(1, target_intervals)
        minimum_tick_step = 10 ** math.floor(math.log10(target_step))
        tick_step = _readable_ceiling(
            target_step,
            minimum_step=minimum_tick_step,
        )

        marks: dict[int | float, str] = {}
        current = float(self.minimum)
        while current <= float(finite_maximum):
            key: int | float = int(current) if current.is_integer() else current
            marks[key] = format_value(key)
            current = round(current + tick_step, 10)

        marks[finite_maximum] = format_value(finite_maximum)
        if include_open_end and self.is_capped:
            marks[self.maximum] = "Unlimited"
        return marks


def _readable_ceiling(value: float, *, minimum_step: float) -> float:
    """Round a positive value up to a readable slider endpoint.

    Args:
        value: Raw upper bound that should be rounded for display.
        minimum_step: Smallest permitted interval between adjacent rounded values.

    Returns:
        A rounded, human-readable upper bound.
    """
    if not np.isfinite(value) or value <= 0:
        return minimum_step

    magnitude = 10 ** math.floor(math.log10(value))
    normalized = value / magnitude
    multiplier = next(
        candidate
        for candidate in (1, 1.25, 1.5, 2, 2.5, 5, 10)
        if normalized <= candidate
    )
    rounded = multiplier * magnitude
    return max(rounded, minimum_step)


def iqr_capped_range_bounds(
    values: Sequence[Any] | pd.Series,
    *,
    minimum: int | float = 0,
    step: int | float = 1,
    iqr_multiplier: float = 1.5,
) -> CappedRangeBounds:
    """Build non-destructive slider bounds using the IQR fence as a display cap.

    Values above the IQR-derived display cap remain in the dataset. When
    ``is_capped`` is true, ``capped_at`` remains an exact selectable value and
    ``maximum`` is a separate final stop meaning no upper limit.

    Args:
        values: Observed numeric values used to derive slider limits.
        minimum: Observed lower bound of the slider range.
        step: Slider interval used when rounding and capping the range.
        iqr_multiplier: Number of interquartile ranges above Q3 used as the outlier fence.

    Returns:
        The calculated slider bounds and outlier cap metadata.
    """
    numeric = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    numeric = numeric[np.isfinite(numeric)]
    if numeric.empty:
        return CappedRangeBounds(minimum, minimum + step, False)

    observed_max = float(numeric.max())
    q1 = float(numeric.quantile(0.25))
    q3 = float(numeric.quantile(0.75))
    iqr = q3 - q1
    if iqr <= 0:
        return CappedRangeBounds(minimum, max(minimum + step, observed_max), False)

    upper_fence = q3 + iqr_multiplier * iqr
    display_max = _readable_ceiling(upper_fence, minimum_step=float(step))
    if display_max >= observed_max:
        return CappedRangeBounds(minimum, max(minimum + step, observed_max), False)

    if float(display_max).is_integer():
        display_max = int(display_max)

    span = float(display_max) - float(minimum)
    target_step = span / 5
    minimum_tick_step = 10 ** math.floor(math.log10(target_step))
    overflow_step = _readable_ceiling(
        target_step,
        minimum_step=minimum_tick_step,
    )
    slider_max = float(display_max) + overflow_step
    if slider_max.is_integer():
        slider_max = int(slider_max)
    return CappedRangeBounds(minimum, slider_max, True, display_max)


def build_range_filter(
    *,
    slider_id: str,
    min_value: Any,
    max_value: Any,
    value: Any,
    component_id: str,
    dynamic_id: DashId,
    tooltip_transform: str | None = None,
    include_missing_switch_id: str | None = None,
    include_missing_switch_label: str | None = None,
    switch_style: Mapping[str, Any] | None = None,
    step: int | float | None = None,
    marks: Mapping[int | float, str] | None = None,
    container_style: Mapping[str, Any] | None = None,
    header_children: Sequence[Any] | None = None,
    show_exact_inputs: bool = False,
    input_prefix: str = "",
    input_suffix: str = "",
    distribution: Any = None,
) -> html.Div:
    """Build a standard slider-based filter section.

    Args:
        slider_id: Dash id for the slider.
        min_value: Lower bound shown by the slider.
        max_value: Upper bound shown by the slider.
        value: Initial slider selection.
        component_id: Outer container id.
        dynamic_id: Pattern-matching id for the dynamic content block.
        tooltip_transform: Optional clientside tooltip formatter.
        include_missing_switch_id: Optional id for the missing-values switch.
        include_missing_switch_label: Label for the missing-values switch.
        switch_style: Optional style override for the missing-values switch.
        step: Optional slider step value.
        marks: Optional slider marks.
        container_style: Optional style for the outer wrapper.
        header_children: Optional header content shown above the slider.
        show_exact_inputs: Show synchronized minimum and maximum number fields.
        input_prefix: Prefix displayed inside both exact-value fields.
        input_suffix: Suffix displayed inside both exact-value fields.
        distribution: Optional listing-count strip drawn behind the track.

    Returns:
        A fully assembled filter ``Div``.
    """
    has_open_upper_bound = bool(
        marks
        and any(
            str(mark.get("label", "") if isinstance(mark, Mapping) else mark) == "Unlimited"
            for mark in marks.values()
        )
    )
    tooltip = {"placement": "bottom"}
    if not show_exact_inputs:
        tooltip.update(
            {
                "placement": "top" if has_open_upper_bound else "bottom",
                "always_visible": False,
            }
        )
    if tooltip_transform is not None:
        tooltip["transform"] = tooltip_transform

    slider_kwargs = {
        "id": slider_id,
        "min": min_value,
        "max": max_value,
        "value": value,
        "updatemode": "drag" if show_exact_inputs else "mouseup",
        "allow_direct_input": False,
    }
    if not show_exact_inputs:
        slider_kwargs["tooltip"] = tooltip
    if step is not None:
        slider_kwargs["step"] = step
    if marks is not None:
        slider_kwargs["marks"] = marks
    if show_exact_inputs:
        slider_kwargs["className"] = "range-filter__hybrid-slider"
    elif has_open_upper_bound:
        slider_kwargs["className"] = "range-filter__open-ended-slider"

    slider = dcc.RangeSlider(**slider_kwargs)
    has_missing_switch = bool(
        include_missing_switch_id and include_missing_switch_label
    )
    body_children: list[Any] = []
    if show_exact_inputs:
        input_step = step if step is not None else 1
        input_common = {
            "min": min_value,
            "step": input_step,
            "allowNegative": False,
            "allowDecimal": False,
            "hideControls": True,
            "clampBehavior": "none",
            "thousandSeparator": ",",
            "debounce": 250,
            "autoComplete": "off",
            "className": "range-filter__exact-input",
        }
        if input_prefix:
            input_common["prefix"] = input_prefix
        if input_suffix:
            input_common["suffix"] = input_suffix
        input_stem = slider_id.removesuffix("_slider")
        minimum_clear_button = dmc.ActionIcon(
            DashIconify(icon="tabler:x", width=17),
            id=f"{input_stem}_minimum_clear",
            n_clicks=0,
            variant="subtle",
            color="gray",
            size=26,
            radius="sm",
            className="range-filter__minimum-clear-button",
            style={"visibility": "hidden"},
            buttonProps={
                "type": "button",
                "aria-label": "Reset minimum to zero",
                "title": "Reset minimum to zero",
            },
        )
        unlimited_button = dmc.ActionIcon(
            DashIconify(icon="tabler:x", width=17),
            id=f"{input_stem}_maximum_clear",
            n_clicks=0,
            variant="subtle",
            color="gray",
            size=26,
            radius="sm",
            className="range-filter__unlimited-button",
            style={"visibility": "hidden"},
            buttonProps={
                "type": "button",
                "aria-label": "Set maximum to unlimited",
                "title": "Set maximum to unlimited",
            },
        )
        body_children.append(
            html.Div(
                [
                    dmc.NumberInput(
                        id=f"{input_stem}_minimum_input",
                        value=min_value,
                        placeholder=str(min_value),
                        rightSection=minimum_clear_button,
                        rightSectionWidth=30,
                        rightSectionPointerEvents="auto",
                        **{"aria-label": "Minimum"},
                        **input_common,
                    ),
                    dmc.NumberInput(
                        id=f"{input_stem}_maximum_input",
                        value=None,
                        placeholder="Unlimited",
                        rightSection=unlimited_button,
                        rightSectionWidth=30,
                        rightSectionPointerEvents="auto",
                        **{"aria-label": "Maximum"},
                        **input_common,
                    ),
                ],
                className="range-filter__exact-inputs",
            )
        )
        body_children.append(
            html.Div(
                [distribution, slider] if distribution is not None else slider,
                className="range-filter__hybrid-slider-wrap",
            )
        )
    else:
        body_children.append(
            html.Div(
                [distribution, slider],
                className="range-filter__slider-with-switch",
            )
            if distribution is not None
            else slider
        )

    outer: list[Any] = []
    if header_children:
        outer.append(html.Div(list(header_children), className="range-filter__header"))
    outer.append(
        html.Div(body_children, id=dynamic_id, className="range-filter__controls")
    )

    return html.Div(outer, style=container_style, id=component_id)


def _format_speed_mark(value: float) -> str:
    """Format a speed tick as Mbps or Gbps.

    Args:
        value: Speed in megabits per second.

    Returns:
        A short label such as ``500M`` or ``1G``.
    """
    if value >= 1000:
        gigabits = value / 1000
        return f"{gigabits:g}G"
    return f"{value:g}M"


def _build_isp_speed_slider(label: str, slider_id: str, maximum: float) -> html.Div:
    """Build one single-handle "at least" speed slider.

    Args:
        label: Subtitle shown above the slider.
        slider_id: Dash component id for the slider.
        maximum: Upper bound of the slider track.

    Returns:
        A ``Div`` containing the labelled slider.
    """
    ticks = [0, maximum / 4, maximum / 2, maximum]
    return html.Div(
        [
            html.H6(label, className="filter-subtitle"),
            dcc.Slider(
                min=0,
                max=maximum,
                value=0,
                id=slider_id,
                updatemode="mouseup",
                allow_direct_input=False,
                marks={t: _format_speed_mark(t) for t in ticks},
                tooltip={"placement": "bottom", "transform": "formatIspSpeed"},
            ),
        ],
        className="isp-speed-filter__range",
    )


def build_isp_speed_components(max_download: float, max_upload: float) -> html.Div:
    """Build download and upload speed controls.

    Nobody shops for an upper bound on internet speed, so both controls are
    single-handle minimums ("at least N") rather than two-handle ranges. That
    halves the handles and drops the tick marks, which is most of the vertical
    space this section used to take.

    Args:
        max_download: Upper bound for download speed.
        max_upload: Upper bound for upload speed.

    Returns:
        A ``Div`` containing both ISP speed sliders.
    """
    return html.Div(
        [
            _build_isp_speed_slider("Download", "isp_download_speed_slider", max_download),
            _build_isp_speed_slider("Upload", "isp_upload_speed_slider", max_upload),
        ],
        id="isp_speed_div",
        className="isp-speed-filter",
    )


_COMMON_LA_LOCATION_SUGGESTIONS: tuple[str, ...] = (
    "Atwater Village, CA",
    "Boyle Heights, CA",
    "Chinatown, CA",
    "Downtown Los Angeles, CA",
    "Echo Park, CA",
    "Glassell Park, CA",
    "Highland Park, CA",
    "Hollywood, CA",
    "Koreatown, CA",
    "Los Feliz, CA",
    "Mar Vista, CA",
    "Mid-City, CA",
    "Silver Lake, CA",
    "Venice, CA",
    "West Adams, CA",
)
_INVALID_LISTING_LOCATION_LABELS = {
    "BDPK",
    "CNGA",
    "CULV",
    "LA",
    "NHLW",
    "SM",
    "TUJ",
}


def build_location_suggestions(
    city_values: Sequence[object] | None = None,
    zip_values: Sequence[object] | None = None,
) -> list[str]:
    """Build locally sourced suggestions for the location tags input.

    Args:
        city_values: City or neighborhood labels present in listing data.
        zip_values: ZIP codes present in listing data.

    Returns:
        Sorted, deduplicated California place labels followed by ZIP codes.
    """
    places = set(_COMMON_LA_LOCATION_SUGGESTIONS)
    for raw_city in city_values or []:
        city = " ".join(str(raw_city or "").strip().split())
        if (
            not city
            or city.casefold() in {"none", "nan", "unknown"}
            or city.upper() in _INVALID_LISTING_LOCATION_LABELS
        ):
            continue
        if city.startswith("#") or not any(character.isalpha() for character in city):
            continue
        city = city.title()
        if not re.search(r"(?:,\s*)?(?:CA|California)$", city, re.IGNORECASE):
            city = f"{city}, CA"
        places.add(city)

    zip_codes = {
        match.group(1)
        for raw_zip in zip_values or []
        if (match := re.fullmatch(r"\s*(\d{5})(?:-\d{4})?\s*", str(raw_zip or "")))
    }
    return sorted(places, key=str.casefold) + sorted(zip_codes)


def build_location_filter_components(
    page_type: str,
    suggestions: Sequence[str] | None = None,
) -> html.Div:
    """Build the shared location filter controls.

    Args:
        page_type: Current page key such as ``lease`` or ``buy``.
        suggestions: Canonical place and ZIP suggestions offered in the input.

    Returns:
        A location input block with status text and nearby switch.
    """
    return html.Div(
        [
            html.Label(
                "Filter listings by neighborhood or ZIP code",
                htmlFor=f"{page_type}-location-input",
                className="visually-hidden",
            ),
            dmc.Group(
                [
                    dmc.TagsInput(
                        id=f"{page_type}-location-input",
                        value=[],
                        searchValue="",
                        data=list(suggestions or _COMMON_LA_LOCATION_SUGGESTIONS),
                        limit=8,
                        placeholder="Search neighborhoods, cities, or ZIPs",
                        splitChars=[";"],
                        acceptValueOnBlur=False,
                        allowDuplicates=False,
                        clearable=True,
                        maxTags=5,
                        # The responsive filter sheet sits at z-index 2400.
                        # Keep the portaled suggestion menu above it on touch
                        # layouts, matching the location ZIP popover below.
                        comboboxProps={
                            "zIndex": 2410,
                            "position": "bottom-start",
                            "width": "target",
                            "floatingStrategy": "fixed",
                        },
                        flex=1,
                        className="location-tags-input",
                    ),
                    html.Button(
                        "Add",
                        id=f"{page_type}-location-add-button",
                        type="button",
                        className="btn btn-outline-info location-add-button",
                        style={"flexShrink": 0},
                        **{"aria-label": "Add typed location"},
                    ),
                ],
                align="flex-end",
                gap="xs",
                wrap="nowrap",
                w="100%",
                className="location-entry-row",
            ),
            html.Div(
                [
                    html.Span(
                        "press Enter to add. Max 5.",
                        className="location-entry-help--desktop",
                    ),
                    html.Span(
                        "tap Add. Max 5.",
                        className="location-entry-help--touch",
                    ),
                ],
                className="location-entry-help",
            ),
            dcc.Loading(
                html.Div(
                    id=f"{page_type}-location-status",
                    className="location-filter-status",
                    role="status",
                    **{
                        "aria-live": "polite",
                        "aria-atomic": "true",
                    },
                ),
                target_components={f"{page_type}-location-status": "children"},
                custom_spinner=html.Div(
                    [
                        html.Span(
                            className="location-resolving-indicator",
                            **{"aria-hidden": "true"},
                        ),
                        "Resolving locations…",
                    ],
                    className="location-resolving-status",
                    role="status",
                    **{
                        "aria-live": "polite",
                        "aria-atomic": "true",
                    },
                ),
                delay_show=150,
                delay_hide=100,
                parent_className="location-status-loading-wrapper",
            ),
            dmc.Switch(
                id=f"{page_type}-nearby-zip-switch",
                label="Include nearby ZIP codes",
                checked=False,
                size="sm",
                color="teal",
                style={"marginTop": "8px"},
            ),
        ],
        style={"marginBottom": "10px"},
    )


def build_location_filter_status(
    boundary_payload: Mapping[str, Any],
    status: str,
) -> str | list[Any]:
    """Render a compact ZIP summary with additional ZIPs in a popover.

    Args:
        boundary_payload: Resolved boundary data used to build the location status.
        status: Current status text to render for the user.

    Returns:
        The location-filter status text and optional ZIP-code popover.
    """
    zip_codes = sorted(
        str(zip_code)
        for zip_code in boundary_payload.get("zip_codes", [])
        if zip_code
    )
    if len(zip_codes) <= 5:
        return status

    visible_zip_codes = zip_codes[:5]
    additional_zip_codes = zip_codes[5:]
    additional_count = len(additional_zip_codes)
    zip_label = "ZIP code" if additional_count == 1 else "ZIP codes"
    summary = (
        f"Filtering by ZIP codes: {', '.join(visible_zip_codes)} "
        f"+{additional_count} more."
    )
    suffix = status[len(summary):] if status.startswith(summary) else ""

    return [
        f"Filtering by ZIP codes: {', '.join(visible_zip_codes)} ",
        dmc.Popover(
            [
                dmc.PopoverTarget(
                    dmc.UnstyledButton(
                        f"+{additional_count} more",
                        className="location-zip-more-button",
                        **{
                            "aria-label": (
                                f"Show {additional_count} additional {zip_label}"
                            ),
                        },
                    )
                ),
                dmc.PopoverDropdown(
                    [
                        html.Div(
                            f"{additional_count} additional {zip_label}",
                            className="location-zip-popover-title",
                        ),
                        html.Div(
                            [
                                html.Span(zip_code, role="listitem")
                                for zip_code in additional_zip_codes
                            ],
                            className="location-zip-popover-list",
                            role="list",
                        ),
                    ],
                    className="location-zip-popover",
                ),
            ],
            position="bottom-start",
            shadow="md",
            withArrow=True,
            width=240,
            # The responsive filter sheet sits at z-index 2400. Mantine's
            # portaled dropdown must clear it on phones and tablets.
            zIndex=2410,
        ),
        ".",
        suffix,
    ]


def build_title_card(
    *,
    title: str,
    last_updated: str | None,
    page_type: str,
) -> dbc.Card:
    """Build the shared page identity block at the top of the sidebar.

    The block sits above every filter, so it stays four short rows: name and
    theme, the rent/sale switch, the data date, and the project links. The old
    standing subtitle repeated what the switch and the date already say.

    Args:
        title: Site name shown at the top of the sidebar.
        last_updated: Optional display date for the latest data refresh.
        page_type: Current page key such as ``lease`` or ``buy``, used to mark
            which side of the rent/sale switch is active.

    Returns:
        A populated Bootstrap card.
    """
    is_lease = page_type == "lease"

    identity_row = html.Div(
        [
            html.H1(title, className="site-name"),
            dmc.Switch(
                id="color-scheme-switch",
                offLabel=DashIconify(
                    icon="radix-icons:sun",
                    width=15,
                    color="var(--mantine-color-yellow-8)",
                ),
                onLabel=DashIconify(
                    icon="radix-icons:moon",
                    width=15,
                    color="var(--mantine-color-yellow-6)",
                ),
                className="theme-switch-control",
                color="gray",
                persisted_props=["checked"],
                persistence=True,
                persistence_type="local",
                size="md",
                **{"aria-label": "Toggle light and dark mode"},
            ),
        ],
        className="site-identity",
    )

    mode_switch = html.Div(
        [
            dbc.Button(
                [html.I(className="fa fa-building"), html.Span("For rent")],
                href="/",
                className="mode-switch__option",
                active=is_lease,
            ),
            dbc.Button(
                [html.I(className="fa fa-home"), html.Span("For sale")],
                href="/buy",
                className="mode-switch__option",
                active=not is_lease,
            ),
        ],
        className="mode-switch",
        role="group",
        **{"aria-label": "Show rentals or homes for sale"},
    )

    links = html.Div(
        [
            html.A(
                [html.I(className="bi bi-github"), html.Span("GitHub")],
                href="https://github.com/perfectly-preserved-pie/larentals",
                target="_blank",
                className="title-card-link",
            ),
            html.A(
                [html.I(className="fa-solid fa-blog"), html.Span("About")],
                href="https://automateordie.dev/wheretolivedotla/",
                target="_blank",
                className="title-card-link",
            ),
            html.A(
                [DashIconify(icon="lucide:bot", width=16), html.Span("MCP")],
                href="/mcp",
                title="MCP setup instructions",
                className="title-card-link",
                **{"aria-label": "MCP setup instructions"},
            ),
            html.A(
                [html.I(className="fa fa-envelope"), html.Span("Contact")],
                href="mailto:hey@wheretolive.la",
                target="_blank",
                className="title-card-link",
            ),
        ],
        className="title-card-links",
    )

    children: list[Any] = [identity_row, mode_switch]

    if last_updated is not None:
        children.append(
            html.P(f"Listings updated {last_updated}", className="site-updated")
        )

    children.append(links)

    return dbc.Card(children, body=True, className="title-card")


_MAP_VIEWPORT_REGISTERED: list[bool] = []


def _register_map_viewport_callback() -> None:
    """Restore the map to wherever the reader last left it.

    A ``moveend`` handler writes the centre and zoom to local storage; this
    replays them once the map mounts, so a reload does not throw away the part
    of the county someone had navigated to.

    Registration is global rather than per page because both listing pages use
    the same ``map`` id and only one is ever mounted.

    Side Effects:
        Registers one clientside callback the first time it is called.

    Returns:
        None.
    """
    if _MAP_VIEWPORT_REGISTERED:
        return
    _MAP_VIEWPORT_REGISTERED.append(True)

    clientside_callback(
        """
        function () {
            try {
                const raw = window.localStorage.getItem("wttl:map-viewport");
                if (!raw) return window.dash_clientside.no_update;
                const saved = JSON.parse(raw);
                if (!saved || !saved.center || typeof saved.zoom !== "number") {
                    return window.dash_clientside.no_update;
                }
                return {center: saved.center, zoom: saved.zoom, transition: "none"};
            } catch (err) {
                return window.dash_clientside.no_update;
            }
        }
        """,
        Output("map", "viewport"),
        Input("map", "id"),
    )


def build_map(
    *,
    page_type: str,
    geojson_id: str,
    center_lat: float,
    center_lng: float,
    layers_control: dl.LayersControl | None,
    map_style: Mapping[str, Any],
) -> dl.Map:
    """Build the shared Dash Leaflet map shell.

    Args:
        page_type: Current page key such as ``lease`` or ``buy``.
        geojson_id: Id of the main listing GeoJSON layer.
        center_lat: Initial latitude for the map center.
        center_lng: Initial longitude for the map center.
        layers_control: Optional overlays control.
        map_style: Style mapping for the map component.

    Returns:
        A configured Leaflet map.
    """
    ns = Namespace("dash_props", "module")
    map_event_handlers = {
        "load": ns("register_map_for_gesture_controls"),
        "layeradd": ns("register_map_for_gesture_controls"),
    }
    _register_map_viewport_callback()
    map_children = [
        dl.GeoJSON(
            id=geojson_id,
            data=None,
            cluster=True,
            clusterToLayer=generate_convex_hulls,
            onEachFeature=ns("on_each_feature"),
            zoomToBoundsOnClick=True,
            superClusterOptions={
                # maxZoom is the last zoom that groups at all, so 14 leaves every
                # listing as its own pin from neighborhood level in. Below that
                # the map is unreadable ungrouped, hence the wide radius.
                "radius": 110,
                "maxZoom": 14,
                "minPoints": 5,
                "minZoom": 3,
            },
        ),
        dl.FullScreenControl(),
    ]
    if layers_control is None:
        map_children.insert(0, dl.TileLayer(detectRetina=False, maxZoom=21))
    else:
        map_children.append(layers_control)

    return dl.Map(
        map_children,
        id="map",
        zoom=9,
        minZoom=9,
        maxZoom=21,
        center={"lat": center_lat, "lng": center_lng},
        preferCanvas=True,
        closePopupOnClick=True,
        eventHandlers=map_event_handlers,
        style=map_style,
    )


def build_map_gesture_control() -> html.Div:
    """Build the webcam gesture-control panel for the shared map.

    Returns:
        A map overlay that is docked into the Leaflet controls stack.
    """
    return html.Div(
        [
            html.Button(
                [
                    html.I(className="bi bi-camera-video", **{"aria-hidden": "true"}),
                    html.Span("Hand/gesture control", className="map-gesture-panel-toggle__label"),
                ],
                type="button",
                className="map-gesture-panel-toggle",
                title="Open hand gesture map control",
                **{
                    "aria-controls": "map-gesture-panel",
                    "aria-expanded": "false",
                    "aria-label": "Open hand gesture map control",
                    "data-map-gesture-panel": "toggle",
                },
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Hand/gesture control", className="map-gesture-panel__title"),
                            html.Div(
                                "Control the map with your webcam. Video stays on your device.",
                                className="map-gesture-panel__copy",
                            ),
                        ],
                        className="map-gesture-panel__intro",
                    ),
                    html.Button(
                        [
                            html.I(className="bi bi-camera-video", **{"aria-hidden": "true"}),
                            html.Span("Start camera", className="map-gesture-action-label"),
                        ],
                        type="button",
                        className="map-gesture-action-button",
                        title="Start hand gesture map control",
                        **{
                            "aria-label": "Start hand gesture map control",
                            "aria-pressed": "false",
                            "data-map-gesture-control": "toggle",
                        },
                    ),
                    html.Ul(
                        [
                            html.Li("Left fist or pinch: pan the map"),
                            html.Li("Right fist or pinch: zoom in or out"),
                            html.Li("Both hands: rotate the map"),
                            html.Li("Hands together for 1 second: reset view"),
                        ],
                        className="map-gesture-panel__list",
                    ),
                    html.Div(
                        className="map-gesture-control-status",
                        role="status",
                        **{"aria-live": "polite"},
                    ),
                ],
                id="map-gesture-panel",
                className="map-gesture-panel",
                hidden=True,
                **{"aria-hidden": "true"},
            ),
        ],
        className="map-gesture-control",
    )


_MATCH_COUNT_PAGES: set[str] = set()


def _register_match_count_callback(page_type: str) -> None:
    """Show how many listings survived the current filters.

    The count reads the GeoJSON actually handed to the map, so it can never
    disagree with what is drawn.

    Args:
        page_type: Current page key such as ``lease`` or ``buy``.

    Side Effects:
        Registers one clientside callback per page.

    Returns:
        None.
    """
    if page_type in _MATCH_COUNT_PAGES:
        return
    _MATCH_COUNT_PAGES.add(page_type)

    noun = "rentals" if page_type == "lease" else "homes"

    clientside_callback(
        """
        function (data) {
            const features = (data && data.features) || [];
            const total = features.length;
            if (!total) return "No %(noun)s match";
            return total.toLocaleString("en-US") + " %(noun)s";
        }
        """ % {"noun": noun},
        Output(f"{page_type}-match-count", "children"),
        Input(f"{page_type}_geojson", "data"),
    )


def build_map_card(
    *,
    page_type: str,
    map_component: Any,
    overlay_children: Sequence[Any] | None = None,
    body_class_name: str | None = None,
    card_class_name: str | None = None,
) -> dbc.Card:
    """Wrap a map component in the standard loading-card layout.

    Args:
        page_type: Current page key such as ``lease`` or ``buy``.
        map_component: Prebuilt map component to render.
        overlay_children: Optional floating UI layered above the map.
        body_class_name: Optional body class string.
        card_class_name: Optional card class string.

    Returns:
        A Bootstrap card containing the map and loading overlay.
    """
    body_children: list[Any] = [
        html.Div(
            id=f"{page_type}-map-spinner",
            children=[
                dbc.Spinner(size="lg"),
                html.P(
                    "Loading map...",
                    style={
                        "marginTop": "10px",
                        "marginLeft": "5px",
                        "color": "white",
                    },
                ),
            ],
            style={
                "position": "absolute",
                "inset": "0",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "backgroundColor": "rgba(0, 0, 0, 0.25)",
                "zIndex": "10000",
            },
        ),
        html.Div(map_component, style={"position": "relative", "zIndex": "0"}),
        html.Div(id=f"{page_type}-match-count", className="match-count"),
    ]
    if overlay_children:
        body_children.extend(overlay_children)

    _register_match_count_callback(page_type)

    body = dbc.CardBody(
        html.Div(
            body_children,
            style={"position": "relative"},
        ),
        className=body_class_name or "p-0 g-0",
    )

    return dbc.Card(body, className=card_class_name)


PERSISTED_PROPS: dict[str, str] = {
    "RangeSlider": "value",
    "Slider": "value",
    "Dropdown": "value",
    "Checklist": "value",
    "RadioItems": "value",
    "NumberInput": "value",
    "TagsInput": "value",
    "Switch": "checked",
    "DatePickerRange": "start_date",
}


def apply_filter_persistence(component: Any, *, token: str) -> None:
    """Make every filter control in a tree remember its value across reloads.

    Args:
        component: Component, or list of components, to walk.
        token: Persistence key. Changing it discards stored values, so passing
            the dataset's refresh date drops filters whose bounds no longer
            exist rather than restoring an out-of-range selection.

    Side Effects:
        Sets ``persistence`` and ``persistence_type`` on supported controls.

    Returns:
        None.
    """
    if isinstance(component, (list, tuple)):
        for child in component:
            apply_filter_persistence(child, token=token)
        return

    if type(component).__name__ in PERSISTED_PROPS and isinstance(
        getattr(component, "id", None), str
    ):
        component.persistence = token
        component.persistence_type = "local"

    children = getattr(component, "children", None)
    if children is not None:
        apply_filter_persistence(children, token=token)


def build_filter_card(
    *,
    items: Sequence[FilterSection],
    page_type: str,
    persistence_token: str = "v1",
    list_id: str | None = None,
    list_class_name: str = "options-accordion dmc",
) -> dbc.Card:
    """Build the flat, always-visible filter list for a page sidebar.

    Sections used to collapse behind accordion headers. The sidebar is taller
    than the viewport either way, so collapsing never removed the scroll; it
    only hid which filters exist, at the cost of a header bar per section.

    Args:
        items: Filter sections as ``(title, children, item_id)`` tuples.
        page_type: Current page key such as ``lease`` or ``buy``.
        persistence_token: Key under which control values are remembered.
        list_id: Optional stable id used by clientside callbacks.
        list_class_name: CSS class name for the section list.

    Returns:
        A Bootstrap card containing every filter section.
    """
    apply_filter_persistence(list(items), token=persistence_token)

    sections = html.Div(
        [
            html.Section(
                [
                    html.H6(title, className="filter-section__title"),
                    html.Div(children, className="filter-section__body"),
                ],
                id=f"{page_type}-section-{item_id}",
                className="filter-section",
            )
            for title, children, item_id in items
        ],
        id=list_id,
        className=list_class_name,
    )

    # One switch for the whole sidebar. Thirteen per-filter copies asked the
    # same question thirteen times, in thirteen slightly different wordings.
    include_missing = dmc.Switch(
        id="include-missing",
        label="Include listings missing details",
        checked=True,
        size="xs",
        className="filter-include-missing",
        persistence=persistence_token,
        persistence_type="local",
    )

    return dbc.Card([include_missing, sections], body=True, className="filter-card")


def build_school_layer_map_prompt(page_type: str) -> html.Div:
    """Build the floating map prompt that points users to school-layer controls.

    Args:
        page_type: Page key such as ``buy`` or ``lease``.

    Returns:
        An absolutely positioned prompt container layered above the map.
    """
    prefix = f"{page_type}-school-layer"

    return html.Div(
        html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            "School filters are ready",
                            className="school-layer-map-prompt__title",
                        ),
                        html.Div(
                            "These controls refine school points only, not home listings.",
                            className="school-layer-map-prompt__copy",
                        ),
                    ],
                    className="school-layer-map-prompt__content",
                ),
                html.Div(
                    [
                        html.Button(
                            "Show filters",
                            id=f"{prefix}-show-filters-button",
                            type="button",
                            className="btn btn-success btn-sm school-layer-map-prompt__button",
                            **{
                                "data-filter-open": page_type,
                                "data-filter-source": "school-prompt",
                            },
                        ),
                        dbc.Button(
                            "Dismiss",
                            id=f"{prefix}-dismiss-prompt-button",
                            color="link",
                            size="sm",
                            className="school-layer-map-prompt__dismiss",
                        ),
                    ],
                    className="school-layer-map-prompt__actions",
                ),
            ],
            className="school-layer-map-prompt__card",
        ),
        id=f"{prefix}-map-prompt",
        className="school-layer-map-prompt",
        role="status",
        **{"aria-live": "polite"},
    )


def build_school_layer_filter_panel(page_type: str) -> dbc.Collapse:
    """Build the conditional, map-only filter panel for the schools overlay.

    Args:
        page_type: Page key such as ``buy`` or ``lease``.

    Returns:
        A collapsed card that is shown only when the Schools overlay is enabled.
    """
    prefix = f"{page_type}-school-layer"

    search_children = html.Div(
        [
            html.Div(
                [
                    html.Label("Search school or district", className="form-label"),
                    dcc.Input(
                        id=f"{prefix}-search-input",
                        type="text",
                        debounce=True,
                        placeholder="Try LAUSD, Beverly Hills High, magnet, etc.",
                        style={"width": "100%"},
                    ),
                ],
                style={"marginBottom": "14px"},
            ),
            html.Div(
                [
                    html.Label("Grade bands", className="form-label"),
                    dcc.Dropdown(
                        id=f"{prefix}-grade-band-checklist",
                        multi=True,
                        options=[
                            {"label": f"{value} School", "value": value}
                            for value in SCHOOL_LAYER_GRADE_BAND_OPTIONS
                        ],
                        value=[],
                        placeholder="Any grade band",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Label("Early grades", className="form-label"),
                    dcc.Dropdown(
                        id=f"{prefix}-early-grades-checklist",
                        multi=True,
                        options=[
                            {"label": "Transitional Kindergarten (TK)", "value": "TK"},
                            {"label": "Kindergarten", "value": "Kindergarten"},
                        ],
                        value=[],
                        placeholder="Any early grade offering",
                    ),
                ],
                style={"marginTop": "14px"},
            ),
            html.Div(
                [
                    html.Label("Grade span", className="form-label"),
                    dcc.Dropdown(
                        id=f"{prefix}-campus-configuration-dropdown",
                        multi=True,
                        options=[
                            {"label": value, "value": value}
                            for value in SCHOOL_LAYER_CAMPUS_CONFIGURATION_OPTIONS
                        ],
                        value=[],
                        placeholder="Any grade span",
                    ),
                ],
                style={"marginTop": "14px"},
            ),
            html.Div(
                [
                    html.Label("Special school types", className="form-label"),
                    dcc.Dropdown(
                        id=f"{prefix}-level-dropdown",
                        multi=True,
                        options=[
                            {"label": value, "value": value}
                            for value in sorted(SCHOOL_LAYER_LEVEL_OPTIONS)
                        ],
                        placeholder="Preschool, secondary, adult ed, etc.",
                    ),
                ],
                style={"marginTop": "14px", "marginBottom": "14px"},
            ),
            html.Div(
                [
                    html.Label("Funding type", className="form-label"),
                    dcc.Dropdown(
                        id=f"{prefix}-funding-type-dropdown",
                        multi=True,
                        options=[
                            {"label": value, "value": value}
                            for value in SCHOOL_LAYER_FUNDING_TYPE_OPTIONS
                        ],
                        placeholder="Any funding type",
                    ),
                ],
                style={"marginBottom": "14px"},
            ),
        ]
    )

    program_children = html.Div(
        [
            dmc.Switch(
                id=f"{prefix}-recently-opened-switch",
                label="Only campuses opened since 2018",
                checked=False,
                size="sm",
                color="teal",
                style={"marginBottom": "14px"},
            ),
            html.Div(
                [
                    html.Label("Enrollment", className="form-label"),
                    dcc.RangeSlider(
                        id=f"{prefix}-enrollment-slider",
                        min=0,
                        max=DEFAULT_SCHOOL_LAYER_ENROLLMENT_MAX,
                        value=[0, DEFAULT_SCHOOL_LAYER_ENROLLMENT_MAX],
                        marks={
                            0: "0",
                            3000: "3k",
                            6000: "6k",
                            9000: "9k",
                            DEFAULT_SCHOOL_LAYER_ENROLLMENT_MAX: "12k",
                        },
                        updatemode="mouseup",
                        tooltip={
                            "placement": "bottom",
                            "always_visible": True,
                            "transform": "formatStudentCount",
                        },
                    ),
                ],
                className="school-layer-enrollment-control",
            ),
            dmc.Switch(
                id=f"{prefix}-charter-switch",
                label="Only charter schools",
                checked=False,
                size="sm",
                color="teal",
                style={"marginBottom": "10px"},
            ),
            dmc.Switch(
                id=f"{prefix}-magnet-switch",
                label="Only magnet schools",
                checked=False,
                size="sm",
                color="teal",
                style={"marginBottom": "10px"},
            ),
            dmc.Switch(
                id=f"{prefix}-title-i-switch",
                label="Only Title I schools",
                checked=False,
                size="sm",
                color="teal",
            ),
        ]
    )

    return dbc.Collapse(
        dbc.Card(
            [
                html.H6("School Filters", className="mb-1"),
                html.P(
                    "These controls filter school points only. They do not filter listings.",
                    className="card-text small text-muted mb-3",
                ),
                dbc.Accordion(
                    [
                        dbc.AccordionItem(
                            search_children,
                            title="Search & Type",
                            item_id=f"{prefix}-search-type",
                        ),
                        dbc.AccordionItem(
                            program_children,
                            title="Programs & Enrollment",
                            item_id=f"{prefix}-programs",
                        ),
                    ],
                    always_open=True,
                    active_item=[
                        f"{prefix}-search-type",
                        f"{prefix}-programs",
                    ],
                    flush=True,
                    className="options-accordion",
                ),
            ],
            id=f"{prefix}-controls-card",
            body=True,
            className="mt-3 school-layer-panel-card",
        ),
        id=f"{prefix}-controls-collapse",
        is_open=False,
    )


QUICK_SUBTYPE_LABELS: tuple[str, ...] = ("Apartment", "House", "Condo or townhouse")

SUBTYPE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Apartment", ("Apartment",)),
    ("House", ("Single Family Residence",)),
    ("Condo or townhouse", ("Condominium", "Townhouse")),
    ("Duplex, triplex or fourplex", ("Duplex", "Triplex", "Quadplex")),
    ("Loft or studio", ("Loft", "Studio")),
    ("Co-op", ("Stock Cooperative", "Own Your Own")),
    ("Room", ("Room For Rent",)),
)


def build_subtype_options(values: Sequence[str]) -> list[dict[str, str]]:
    """Collapse raw MLS subtypes into the handful of kinds people shop for.

    The feed carries sixteen subtypes, but four of them are almost every listing
    with a known type and the tail runs down to single listings. Shoppers pick
    "house" or "apartment", not "Stock Cooperative", so the filter offers groups
    and a listing's exact subtype stays on its popup.

    A group's value is a JSON array of the raw subtypes it covers. The filter
    expands it clientside, so membership travels with the option and the two
    sides cannot drift apart.

    Args:
        values: Raw subtype values present in the dataset.

    Returns:
        Dropdown options, common groups first, then anything unmatched.
    """
    available = set(values)
    options: list[dict[str, str]] = []
    claimed: set[str] = set()

    for label, members in SUBTYPE_GROUPS:
        present = [member for member in members if member in available]
        if not present:
            continue
        claimed.update(present)
        options.append(
            {
                "label": label,
                "value": present[0] if len(present) == 1 else json.dumps(present),
            }
        )

    leftovers = sorted(available - claimed - {"Unknown"})
    if leftovers:
        options.append({"label": "Other", "value": json.dumps(leftovers)})
    if "Unknown" in available:
        options.append({"label": "Unlisted", "value": "Unknown"})

    return options


def build_subtype_filter(
    *,
    values: Sequence[str],
    dynamic_id: DashId,
    placeholder: str,
    outer_id: str | None = None,
    dropdown_style: Mapping[str, Any] | None = None,
) -> html.Div:
    """Build the shared subtype section: two quick toggles over a dropdown.

    Args:
        values: Raw subtype values present in the dataset.
        dynamic_id: Pattern-matching id for the dropdown wrapper.
        placeholder: Placeholder text for the dropdown.
        outer_id: Optional id for the outer container.
        dropdown_style: Optional inline style override for the dropdown.

    Returns:
        A subtype-selection ``Div``.
    """
    data = build_subtype_options(values)
    container_kwargs = {}
    if outer_id is not None:
        container_kwargs["id"] = outer_id

    quick = [option for option in data if option["label"] in QUICK_SUBTYPE_LABELS][:2]

    children: list[Any] = [html.Div([])]

    if len(quick) == 2:
        children.append(
            html.Div(
                [
                    html.Button(
                        option["label"],
                        id=f"subtype-quick-{index}",
                        n_clicks=0,
                        type="button",
                        className="mode-switch__option btn",
                        **{"data-subtype-value": option["value"]},
                    )
                    for index, option in enumerate(quick)
                ],
                className="mode-switch subtype-quick",
                role="group",
                **{"aria-label": "Filter to the two most common kinds of home"},
            )
        )

    children.append(
        html.Div(
            [
                dcc.Dropdown(
                    clearable=True,
                    id="subtype_checklist",
                    maxHeight=400,
                    multi=True,
                    options=data,
                    placeholder=placeholder,
                    searchable=True,
                    style=dropdown_style,
                    value=[],
                ),
            ],
            id=dynamic_id,
        )
    )

    return html.Div(children, **container_kwargs)


def build_listed_date_filter(
    *,
    earliest_date: date | str | None,
    dynamic_id: DashId,
    datepicker_id: str,
    component_id: str,
) -> html.Div:
    """Build the shared listed-date filter section.

    Args:
        earliest_date: Earliest date available in the dataset.
        dynamic_id: Pattern-matching id for the main content wrapper.
        datepicker_id: Id for the date picker component.
        component_id: Outer container id.

    Returns:
        A listed-date filter ``Div``.
    """
    today = date.today()

    return html.Div(
        [
            html.Div([]),
            html.Div(
                [
                    html.Div(
                        [
                            dcc.RadioItems(
                                id="listed_time_range_radio",
                                options=[
                                    {"label": "2 wk", "value": 14},
                                    {"label": "1 mo", "value": 30},
                                    {"label": "3 mo", "value": 90},
                                    {"label": "Any", "value": 0},
                                ],
                                value=0,
                                inline=True,
                                className="filter-inline-radio",
                            ),
                        ],
                        style={"marginBottom": "5px"},
                    ),
                    dcc.DatePickerRange(
                        id=datepicker_id,
                        number_of_months_shown=1,
                        max_date_allowed=today,
                        start_date=earliest_date,
                        end_date=today,
                        initial_visible_month=today,
                    ),
                    dmc.Switch(
                        id="listed_date_missing_switch",
                        label="Include properties with an unknown listed date",
                        checked=True,
                        size="sm",
                        color="teal",
                        style={"marginTop": "10px"},
                    ),
                ],
                id=dynamic_id,
            ),
        ],
        style={"marginBottom": "10px"},
        id=component_id,
        className="listed-date-filter",
    )


def build_year_built_filter(
    *,
    min_year: int,
    max_year: int,
    dynamic_id: DashId,
    component_id: str,
) -> html.Div:
    """Build the shared year-built slider section.

    Args:
        min_year: Minimum year in the dataset.
        max_year: Maximum year in the dataset.
        dynamic_id: Pattern-matching id for the slider wrapper.
        component_id: Outer container id.

    Returns:
        A year-built filter ``Div``.
    """
    marks_range = np.linspace(min_year, max_year, 5, dtype=int)

    return build_range_filter(
        slider_id="yrbuilt_slider",
        min_value=min_year,
        max_value=max_year,
        value=[0, max_year],
        component_id=component_id,
        dynamic_id=dynamic_id,
        include_missing_switch_id="yrbuilt_missing_switch",
        include_missing_switch_label="Include properties with an unknown year built",
        marks={int(year): str(int(year)) for year in marks_range},
        container_style={"marginBottom": "10px"},
    )


def build_page_parts(
    *,
    config: PageConfig,
    last_updated: str | None,
    filter_items: Sequence[FilterSection],
    map_component: Any,
    map_overlay_children: Sequence[Any] | None = None,
) -> PageParts:
    """Assemble the top-level cards consumed by a page layout.

    Args:
        config: Static page configuration.
        last_updated: Optional display date for the dataset refresh.
        filter_items: Accordion sections for the sidebar.
        map_component: Prebuilt map component for the page.
        map_overlay_children: Optional floating components rendered over the map.

    Returns:
        A ``PageParts`` bundle with title, filter, and map cards.
    """
    return PageParts(
        title_card=build_title_card(
            title=config.title,
            last_updated=last_updated,
            page_type=config.page_type,
        ),
        user_options_card=build_filter_card(
            items=filter_items,
            page_type=config.page_type,
            persistence_token=str(last_updated or "v1"),
            list_id=f"{config.page_type}-options-accordion",
            list_class_name=config.accordion_class_name,
        ),
        map_card=build_map_card(
            page_type=config.page_type,
            map_component=map_component,
            overlay_children=map_overlay_children,
            body_class_name=config.map_body_class_name,
            card_class_name=config.map_card_class_name,
        ),
    )
