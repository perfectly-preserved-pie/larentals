from collections.abc import Sequence
from datetime import date
from typing import Any, Mapping
from dash import dcc, html
from dash_extensions.javascript import Namespace
from dash_iconify import DashIconify
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_mantine_components as dmc
import numpy as np

from .component_models import DashId, FilterSection, PageConfig, PageParts
from functions.commute_utils import (
    COMMUTE_DEFAULT_MODE,
    COMMUTE_HELP_TEXT,
    COMMUTE_MAX_MINUTES,
    COMMUTE_MIN_MINUTES,
    COMMUTE_MODE_OPTIONS,
    COMMUTE_STEP_MINUTES,
    default_commute_departure_datetime,
    normalize_commute_minutes,
)
from functions.convex_hull import generate_convex_hulls
from functions.layers import (
    SCHOOL_LAYER_CAMPUS_CONFIGURATION_OPTIONS,
    DEFAULT_SCHOOL_LAYER_ENROLLMENT_MAX,
    SCHOOL_LAYER_FUNDING_TYPE_OPTIONS,
    SCHOOL_LAYER_GRADE_BAND_OPTIONS,
    SCHOOL_LAYER_LEVEL_OPTIONS,
)


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
    marks: Mapping[int, str] | None = None,
    container_style: Mapping[str, Any] | None = None,
    header_children: Sequence[Any] | None = None,
) -> html.Div:
    """
    Build a standard slider-based filter section.

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

    Returns:
        A fully assembled filter ``Div``.
    """
    tooltip = {
        "placement": "bottom",
        "always_visible": True,
    }
    if tooltip_transform is not None:
        tooltip["transform"] = tooltip_transform

    slider_kwargs = {
        "id": slider_id,
        "min": min_value,
        "max": max_value,
        "value": value,
        "updatemode": "mouseup",
        "tooltip": tooltip,
    }
    if step is not None:
        slider_kwargs["step"] = step
    if marks is not None:
        slider_kwargs["marks"] = marks

    body_children = [dcc.RangeSlider(**slider_kwargs)]

    if include_missing_switch_id and include_missing_switch_label:
        body_children.append(
            dmc.Switch(
                id=include_missing_switch_id,
                label=include_missing_switch_label,
                checked=True,
                size="sm",
                color="teal",
                style=switch_style or {"marginTop": "10px"},
            )
        )

    return html.Div(
        [
            html.Div(list(header_children or [])),
            html.Div(body_children, id=dynamic_id),
        ],
        style=container_style,
        id=component_id,
    )


def build_isp_speed_components(max_download: float, max_upload: float) -> html.Div:
    """
    Build download and upload speed controls.

    Args:
        max_download: Upper bound for download speed.
        max_upload: Upper bound for upload speed.

    Returns:
        A ``Div`` containing both ISP speed sliders.
    """
    return html.Div(
        [
            html.Div(
                [
                    html.H6("Download Speed (Mbps)", style={"marginBottom": "5px"}),
                    dcc.RangeSlider(
                        min=0,
                        max=max_download,
                        value=[0, max_download],
                        id="isp_download_speed_slider",
                        updatemode="mouseup",
                        tooltip={
                            "placement": "bottom",
                            "always_visible": True,
                            "transform": "formatIspSpeed",
                        },
                    ),
                ],
                style={"marginBottom": "15px"},
            ),
            html.Div(
                [
                    html.H6("Upload Speed (Mbps)", style={"marginBottom": "5px"}),
                    dcc.RangeSlider(
                        min=0,
                        max=max_upload,
                        value=[0, max_upload],
                        id="isp_upload_speed_slider",
                        updatemode="mouseup",
                        tooltip={
                            "placement": "bottom",
                            "always_visible": True,
                            "transform": "formatIspSpeed",
                        },
                    ),
                ],
            ),
            dmc.Switch(
                id="isp_speed_missing_switch",
                label="Include properties with an unknown ISP speed",
                checked=True,
                size="sm",
                color="teal",
                style={"marginTop": "15px"},
            ),
        ],
        id="isp_speed_div",
    )


def build_location_filter_components(page_type: str) -> html.Div:
    """
    Build the shared location filter controls.

    Args:
        page_type: Current page key such as ``lease`` or ``buy``.

    Returns:
        A location input block with status text and nearby switch.
    """
    return html.Div(
        [
            dcc.Input(
                id=f"{page_type}-location-input",
                type="text",
                debounce=True,
                placeholder="Neighborhood or ZIP code (e.g., Highland Park or 90042)",
            ),
            html.Div(
                id=f"{page_type}-location-status",
                style={
                    "marginTop": "6px",
                    "fontSize": "0.85rem",
                    "color": "#9aa0a6",
                },
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


def build_commute_filter_components(page_type: str) -> html.Div:
    """
    Create the commute-time filter controls shown in the sidebar.

    Args:
        page_type: Current page key such as ``lease`` or ``buy``.

    Returns:
        A container with destination, mode, duration, and status controls.
    """
    default_minutes = normalize_commute_minutes(30)
    default_departure = default_commute_departure_datetime()
    slider_marks = {minutes: str(minutes) for minutes in (10, 20, 30, 45, 60, 90)}

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        "Filter listings by commute time to a destination of your choice.",
                        style={
                            "fontSize": "0.98rem",
                            "color": "#243447",
                            "marginBottom": "4px",
                        },
                    ),
                    html.Div(
                        "e.g., your workplace or favorite cafe.",
                        style={
                            "fontSize": "0.85rem",
                            "color": "#6b7280",
                            "lineHeight": 1.4,
                            "marginBottom": "10px",
                        },
                    ),
                ]
            ),
            dcc.Input(
                id=f"{page_type}-commute-input",
                type="text",
                debounce=True,
                placeholder="Destination (e.g., UCLA or 8565 Melrose Ave)",
            ),
            html.Div(
                [
                    html.H6("Mode", style={"marginTop": "12px", "marginBottom": "6px"}),
                    dcc.Dropdown(
                        id=f"{page_type}-commute-mode",
                        options=COMMUTE_MODE_OPTIONS,
                        value=COMMUTE_DEFAULT_MODE,
                        clearable=False,
                        searchable=False,
                    ),
                ]
            ),
            html.Div(
                [
                    html.H6(
                        "Departure Time",
                        style={"marginTop": "12px", "marginBottom": "6px"},
                    ),
                    dmc.DateTimePicker(
                        id=f"{page_type}-commute-departure-datetime",
                        value=default_departure,
                        valueFormat="ddd MMM D, YYYY h:mm A",
                        clearable=False,
                        debounce=250,
                        withSeconds=False,
                        timePickerProps={
                            "withDropdown": True,
                            "format": "12h",
                        },
                        popoverProps={"withinPortal": False},
                        persistence=True,
                        persistence_type="local",
                        w="100%",
                    ),
                ]
            ),
            html.Div(
                [
                    html.H6(
                        "Max Minutes",
                        style={"marginTop": "12px", "marginBottom": "6px"},
                    ),
                    dcc.Slider(
                        id=f"{page_type}-commute-minutes",
                        min=COMMUTE_MIN_MINUTES,
                        max=COMMUTE_MAX_MINUTES,
                        step=COMMUTE_STEP_MINUTES,
                        value=default_minutes,
                        updatemode="mouseup",
                        marks=slider_marks,
                        tooltip={
                            "placement": "bottom",
                            "always_visible": True,
                        },
                    ),
                ]
            ),
            html.Div(
                id=f"{page_type}-commute-status",
                style={
                    "marginTop": "14px",
                    "fontSize": "0.86rem",
                    "color": "#4b5563",
                    "lineHeight": 1.45,
                    "whiteSpace": "pre-line",
                },
            ),
            html.Div(
                [
                    html.Div(
                        "Show",
                        style={
                            "fontSize": "0.78rem",
                            "fontWeight": 600,
                            "letterSpacing": "0.01em",
                            "color": "#4b5563",
                            "marginBottom": "6px",
                        },
                    ),
                    dcc.RadioItems(
                        id=f"{page_type}-commute-display-mode",
                        options=[
                            {"label": "Verified only", "value": "verified_only"},
                            {"label": "Show all matches", "value": "include_rough"},
                        ],
                        value="verified_only",
                        persistence=True,
                        persistence_type="local",
                        labelStyle={"display": "block", "marginBottom": "4px"},
                        inputStyle={"marginRight": "6px"},
                    ),
                    html.Div(
                        [
                            html.Span(
                                "Estimated",
                                id=f"{page_type}-commute-estimated-info-target",
                                style={
                                    "fontWeight": 600,
                                    "textDecoration": "underline dotted",
                                    "cursor": "help",
                                },
                            ),
                            html.Span(
                                " listings haven't been individually route-checked yet."
                            ),
                        ],
                        style={
                            "marginTop": "8px",
                            "fontSize": "0.78rem",
                            "color": "#6b7280",
                            "lineHeight": 1.45,
                        },
                    ),
                    dbc.Tooltip(
                        "Estimated listings are inside the broader commute area, but each one has not been checked one-by-one yet.",
                        target=f"{page_type}-commute-estimated-info-target",
                        placement="top",
                    ),
                ],
                id=f"{page_type}-commute-display-mode-container",
                style={
                    "display": "none",
                    "marginTop": "12px",
                    "padding": "10px 12px",
                    "border": "1px solid #d7dde6",
                    "borderRadius": "10px",
                    "backgroundColor": "#f8fafc",
                },
            ),
            html.Div(
                COMMUTE_HELP_TEXT,
                style={
                    "marginTop": "18px",
                    "fontSize": "0.85rem",
                    "color": "#9aa0a6",
                    "lineHeight": 1.45,
                },
            ),
        ],
        style={"marginBottom": "10px"},
    )


def build_title_card(
    *,
    title: str,
    subtitle: str,
    last_updated: str | None,
) -> dbc.Card:
    """
    Build the shared page title card.

    Args:
        title: Heading shown at the top of the sidebar.
        subtitle: Secondary copy under the title.
        last_updated: Optional display date for the latest data refresh.

    Returns:
        A populated Bootstrap card.
    """
    title_card_children = [
        dbc.Row(
            [
                dbc.Col(html.H3(title, className="card-title"), width="auto"),
                dbc.Col(
                    dbc.ButtonGroup(
                        [
                            dbc.Button(
                                [
                                    html.I(
                                        className="fa fa-building",
                                        style={"marginRight": "5px"},
                                    ),
                                    "For Rent",
                                ],
                                href="/",
                                color="primary",
                            ),
                            html.Div(
                                style={
                                    "width": "1px",
                                    "backgroundColor": "#ccc",
                                    "margin": "0 1px",
                                    "height": "100%",
                                }
                            ),
                            dbc.Button(
                                [
                                    html.I(
                                        className="fa fa-home",
                                        style={"marginRight": "5px"},
                                    ),
                                    "For Sale",
                                ],
                                href="/buy",
                                color="primary",
                            ),
                        ],
                        className="ml-auto",
                    ),
                    width="auto",
                    className="ml-auto",
                ),
            ],
            align="center",
        ),
        html.P(subtitle),
    ]

    if last_updated is not None:
        title_card_children.append(
            html.P(f"Last updated: {last_updated}", style={"marginBottom": "5px"})
        )

    title_card_children.extend(
        [
            html.I(className="bi bi-github", style={"marginRight": "5px"}),
            html.A(
                "GitHub",
                href="https://github.com/perfectly-preserved-pie/larentals",
                target="_blank",
            ),
            html.I(
                className="fa-solid fa-blog",
                style={"marginRight": "5px", "marginLeft": "15px"},
            ),
            html.A(
                "About This Project",
                href="https://automateordie.io/blog/2023/08/26/wheretolivela/",
                target="_blank",
            ),
            html.I(
                className="fa fa-envelope",
                style={"marginRight": "5px", "marginLeft": "15px"},
            ),
            html.A(
                "hey@wheretolive.la",
                href="mailto:hey@wheretolive.la",
                target="_blank",
            ),
            html.Br(),
            dmc.Switch(
                color="grey",
                description="Toggle light/dark mode",
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
                persistence=True,
                size="md",
                style={"marginTop": "5px"},
            ),
        ]
    )

    return dbc.Card(title_card_children, body=True)


def build_map(
    *,
    page_type: str,
    geojson_id: str,
    center_lat: float,
    center_lng: float,
    layers_control: dl.LayersControl | None,
    map_style: Mapping[str, Any],
) -> dl.Map:
    """
    Build the shared Dash Leaflet map shell.

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
    map_children = [
        dl.TileLayer(detectRetina=False),
        dl.GeoJSON(
            id=f"{page_type}-commute-geojson",
            data={"type": "FeatureCollection", "features": []},
            cluster=False,
            bubblingMouseEvents=False,
            zoomToBoundsOnClick=False,
            style={
                "color": "#8f2d56",
                "weight": 4,
                "opacity": 0.9,
                "lineCap": "round",
                "lineJoin": "round",
                "fillColor": "#f4a7b9",
                "fillOpacity": 0.16,
            },
        ),
        dl.GeoJSON(
            id=geojson_id,
            data=None,
            cluster=True,
            clusterToLayer=generate_convex_hulls,
            onEachFeature=ns("on_each_feature"),
            zoomToBoundsOnClick=True,
            superClusterOptions={
                "radius": 160,
                "minZoom": 3,
            },
        ),
        dl.LayerGroup(
            id=f"{page_type}-commute-target-layer",
            children=[],
        ),
        dl.FullScreenControl(),
    ]
    if layers_control is not None:
        map_children.append(layers_control)

    return dl.Map(
        map_children,
        id="map",
        zoom=9,
        minZoom=9,
        center={"lat": center_lat, "lng": center_lng},
        preferCanvas=True,
        closePopupOnClick=True,
        eventHandlers=map_event_handlers,
        style=map_style,
    )


def build_map_gesture_control() -> html.Div:
    """
    Build the webcam gesture-control panel for the shared map.

    Returns:
        A map overlay that is docked into the Leaflet controls stack.
    """
    return html.Div(
        [
            html.Button(
                [
                    html.I(className="bi bi-camera-video", **{"aria-hidden": "true"}),
                    html.Span("Hand control", className="map-gesture-panel-toggle__label"),
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
                            html.Div("Hand control", className="map-gesture-panel__title"),
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
                **{"aria-hidden": "true"},
            ),
        ],
        className="map-gesture-control",
    )


def build_map_card(
    *,
    page_type: str,
    map_component: Any,
    overlay_children: Sequence[Any] | None = None,
    body_class_name: str | None = None,
    card_class_name: str | None = None,
) -> dbc.Card:
    """
    Wrap a map component in the standard loading-card layout.

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
    ]
    if overlay_children:
        body_children.extend(overlay_children)

    body = dbc.CardBody(
        html.Div(
            body_children,
            style={"position": "relative"},
        ),
        className=body_class_name,
    )

    return dbc.Card(body, className=card_class_name)


def build_filter_card(
    *,
    items: Sequence[FilterSection],
    active_item: Sequence[str],
    accordion_class_name: str = "options-accordion dmc",
) -> dbc.Card:
    """
    Build the accordion card used for page filters.

    Args:
        items: Accordion sections as ``(title, children, item_id)`` tuples.
        active_item: Section ids to expand by default.
        accordion_class_name: CSS class name for the accordion.

    Returns:
        A Bootstrap card containing the filter accordion.
    """
    accordion = dbc.Accordion(
        [
            dbc.AccordionItem(children, title=title, item_id=item_id)
            for title, children, item_id in items
        ],
        flush=True,
        always_open=True,
        active_item=list(active_item),
        className=accordion_class_name,
    )

    return dbc.Card(
        [
            html.P(
                "Use the options below to filter the map according to your needs.",
                className="card-text",
            ),
            accordion,
        ],
        body=True,
    )


def build_school_layer_map_prompt(page_type: str) -> html.Div:
    """
    Build the floating map prompt that points users to school-layer controls.

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
                        dbc.Button(
                            "Show filters",
                            id=f"{prefix}-show-filters-button",
                            color="success",
                            size="sm",
                            className="school-layer-map-prompt__button",
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
    """
    Build the conditional, map-only filter panel for the schools overlay.

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


def build_subtype_filter(
    *,
    values: Sequence[str],
    dynamic_id: DashId,
    placeholder: str,
    outer_id: str | None = None,
    dropdown_style: Mapping[str, Any] | None = None,
) -> html.Div:
    """
    Build the shared subtype dropdown section.

    Args:
        values: Sorted subtype labels to offer.
        dynamic_id: Pattern-matching id for the dropdown wrapper.
        placeholder: Placeholder text for the dropdown.
        outer_id: Optional id for the outer container.
        dropdown_style: Optional inline style override for the dropdown.

    Returns:
        A subtype-selection ``Div``.
    """
    data = [{"label": value, "value": value} for value in values]
    container_kwargs = {}
    if outer_id is not None:
        container_kwargs["id"] = outer_id

    return html.Div(
        [
            html.Div([]),
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
            ),
        ],
        **container_kwargs,
    )


def build_listed_date_filter(
    *,
    earliest_date: date | str | None,
    dynamic_id: DashId,
    datepicker_id: str,
    component_id: str,
) -> html.Div:
    """
    Build the shared listed-date filter section.

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
                            html.H6(
                                html.Em("I want to see listings posted in the last..."),
                                style={"marginBottom": "5px"},
                            ),
                            dcc.RadioItems(
                                id="listed_time_range_radio",
                                options=[
                                    {"label": "2 Weeks", "value": 14},
                                    {"label": "1 Month", "value": 30},
                                    {"label": "3 Months", "value": 90},
                                    {"label": "All Time", "value": 0},
                                ],
                                value=0,
                                inline=True,
                                labelStyle={
                                    "fontSize": "0.8rem",
                                    "marginRight": "10px",
                                },
                            ),
                        ],
                        style={"marginBottom": "5px"},
                    ),
                    dcc.DatePickerRange(
                        id=datepicker_id,
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
    )


def build_year_built_filter(
    *,
    min_year: int,
    max_year: int,
    dynamic_id: DashId,
    component_id: str,
) -> html.Div:
    """
    Build the shared year-built slider section.

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
    """
    Assemble the top-level cards consumed by a page layout.

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
            subtitle=config.subtitle,
            last_updated=last_updated,
        ),
        user_options_card=build_filter_card(
            items=filter_items,
            active_item=config.active_filter_items,
            accordion_class_name=config.accordion_class_name,
        ),
        map_card=build_map_card(
            page_type=config.page_type,
            map_component=map_component,
            overlay_children=map_overlay_children,
            body_class_name=config.map_body_class_name,
            card_class_name=config.map_card_class_name,
        ),
    )
