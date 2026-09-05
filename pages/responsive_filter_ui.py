from __future__ import annotations

from dash import ClientsideFunction, Input, Output, State, clientside_callback, dcc, html
from dash.development.base_component import Component
import dash_bootstrap_components as dbc


FILTER_UI_BREAKPOINT = 1100

_HYBRID_RANGE_SLIDERS = {
    "lease": ("rental_price_slider",),
    "buy": (
        "list_price_slider",
        "lot_size_slider",
        "hoa_fee_slider",
    ),
}
_registered_hybrid_range_sliders: set[str] = set()


def _hybrid_range_input_id(slider_id: str, bound: str) -> str:
    """Return the exact-value field id paired with a range slider.

    Args:
        slider_id: Dash identifier of the hybrid range slider.
        bound: Range endpoint, either ``minimum`` or ``maximum``.

    Returns:
        The hybrid range input identifier text.
    """
    return f"{slider_id.removesuffix('_slider')}_{bound}_input"


def _register_hybrid_range_callbacks(page_type: str) -> None:
    """Keep exact-value fields and their finite display slider synchronized.

    Args:
        page_type: Listing page type, either ``buy`` or ``lease``.

    Returns:
        None.
    """
    for slider_id in _HYBRID_RANGE_SLIDERS[page_type]:
        if slider_id in _registered_hybrid_range_sliders:
            continue
        _registered_hybrid_range_sliders.add(slider_id)
        minimum_input_id = _hybrid_range_input_id(slider_id, "minimum")
        maximum_input_id = _hybrid_range_input_id(slider_id, "maximum")
        minimum_clear_id = f"{slider_id.removesuffix('_slider')}_minimum_clear"
        maximum_clear_id = f"{slider_id.removesuffix('_slider')}_maximum_clear"
        clientside_callback(
            ClientsideFunction(
                namespace="clientside",
                function_name="syncHybridRangeFilter",
            ),
            Output(slider_id, "value"),
            Output(minimum_input_id, "value"),
            Output(maximum_input_id, "value"),
            Output(minimum_clear_id, "style"),
            Output(maximum_clear_id, "style"),
            Input(slider_id, "value"),
            Input(minimum_input_id, "value"),
            Input(maximum_input_id, "value"),
            Input(minimum_clear_id, "n_clicks"),
            Input(maximum_clear_id, "n_clicks"),
            State(slider_id, "min"),
            State(slider_id, "max"),
            prevent_initial_call=True,
        )


def build_filter_ui_stores(page_type: str) -> list[dcc.Store]:
    """Create the client-side stores used by a listing page's filters.

    The stores keep draft values, applied values, and the preview result count
    separate so mobile users can cancel edits without changing the map.

    Args:
        page_type: Listing page type, either ``buy`` or ``lease``.

    Returns:
        The client-side stores used to retain filter UI state.
    """
    return [
        dcc.Store(id=f"{page_type}-filter-draft-store", storage_type="memory"),
        dcc.Store(id=f"{page_type}-filter-applied-store", storage_type="memory"),
        dcc.Store(
            id=f"{page_type}-filter-preview-store",
            storage_type="memory",
            data={"count": None},
        ),
    ]


def build_map_filter_toolbar(page_type: str) -> html.Div:
    """Build the compact toolbar shown over the map on smaller screens.

    ``page_type`` selects the Rent or Buy labels, links, and quick-filter chips.
    The toolbar itself is hidden when the persistent desktop sidebar is visible.

    Args:
        page_type: Listing page type, either ``buy`` or ``lease``.

    Returns:
        The responsive filter toolbar component for the map.
    """
    price_label = "Monthly rent" if page_type == "lease" else "List price"
    price_section = "monthly_rent" if page_type == "lease" else "list_price"
    listing_label = "rentals" if page_type == "lease" else "homes"

    chips: list[Component] = [
        _quick_filter_button(page_type, "location", "Location", "location"),
        _quick_filter_button(page_type, "price", price_label, price_section),
        _quick_filter_button(page_type, "bedrooms", "Beds", "bedrooms"),
        _quick_filter_button(page_type, "bathrooms", "Baths", "bathrooms"),
    ]
    if page_type == "lease":
        chips.append(
            _quick_filter_button(page_type, "pets", "Pets", "pet_policy")
        )
    chips.append(
        html.Button(
            "More",
            id=f"{page_type}-quick-more",
            type="button",
            className="map-filter-chip map-filter-chip--more",
            **{
                "data-filter-open": page_type,
                "data-filter-source": "more-chip",
                "aria-controls": f"{page_type}-filter-panel",
            },
        )
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.A(
                                "WhereToLive.LA",
                                href="/" if page_type == "lease" else "/buy",
                                className="map-filter-toolbar__brand",
                            ),
                            html.Span(
                                f"0 {listing_label}",
                                id=f"{page_type}-map-result-count",
                                className="map-filter-toolbar__result-count",
                                **{"aria-live": "polite"},
                            ),
                        ],
                        className="map-filter-toolbar__identity",
                    ),
                    html.Div(
                        [
                            html.Nav(
                                [
                                    html.A(
                                        [
                                            html.I(
                                                className="bi bi-check2",
                                                **{"aria-hidden": "true"},
                                            ),
                                            html.Span("Rent"),
                                        ],
                                        href="/",
                                        className=(
                                            "map-filter-toolbar__mode-button is-selected"
                                            if page_type == "lease"
                                            else "map-filter-toolbar__mode-button"
                                        ),
                                        **(
                                            {"aria-current": "page"}
                                            if page_type == "lease"
                                            else {}
                                        ),
                                    ),
                                    html.A(
                                        [
                                            html.I(
                                                className="bi bi-check2",
                                                **{"aria-hidden": "true"},
                                            ),
                                            html.Span("Buy"),
                                        ],
                                        href="/buy",
                                        className=(
                                            "map-filter-toolbar__mode-button is-selected"
                                            if page_type == "buy"
                                            else "map-filter-toolbar__mode-button"
                                        ),
                                        **(
                                            {"aria-current": "page"}
                                            if page_type == "buy"
                                            else {}
                                        ),
                                    ),
                                ],
                                className="map-filter-toolbar__mode",
                                **{"aria-label": "Listing type"},
                            ),
                            html.Button(
                                [
                                    html.I(
                                        className="bi bi-sliders2",
                                        **{"aria-hidden": "true"},
                                    ),
                                    html.Span("Filters"),
                                    html.Span(
                                        "0",
                                        id=f"{page_type}-filter-count-badge",
                                        className="map-filter-toolbar__badge",
                                        hidden=True,
                                    ),
                                ],
                                id=f"{page_type}-filter-open-button",
                                type="button",
                                className="map-filter-toolbar__open",
                                **{
                                    "data-filter-open": page_type,
                                    "data-filter-source": "toolbar",
                                    "aria-controls": f"{page_type}-filter-panel",
                                    "aria-expanded": "false",
                                    "aria-haspopup": "dialog",
                                },
                            ),
                        ],
                        className="map-filter-toolbar__actions",
                    ),
                ],
                className="map-filter-toolbar__top",
            ),
            html.Div(chips, className="map-filter-toolbar__chips"),
        ],
        className="map-filter-toolbar",
        **{"data-filter-toolbar": page_type},
    )


def build_responsive_listing_shell(
    *,
    page_type: str,
    title_card: Component,
    user_options_card: Component,
    map_card: Component,
) -> html.Div:
    """Arrange one filter tree beside or over the listing map.

    Desktop widths show the filter content as a sidebar. Smaller widths reuse
    that same content inside a dismissible drawer or bottom sheet.

    Args:
        page_type: Listing page type, either ``buy`` or ``lease``.
        title_card: Dash card containing the page title and introductory content.
        user_options_card: Dash card containing the listing filter controls.
        map_card: Dash card containing the interactive listing map.

    Returns:
        The responsive page shell containing filters, listings, and the map.
    """
    listing_label = "rentals" if page_type == "lease" else "homes"

    backdrop = html.Button(
        type="button",
        id=f"{page_type}-filter-backdrop",
        className="filter-panel-backdrop",
        **{
            "data-filter-close": page_type,
            "data-filter-close-source": "backdrop",
            "aria-label": "Close filters",
            "tabIndex": "-1",
        },
    )

    panel = html.Aside(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H2(
                                "Filters",
                                id=f"{page_type}-filter-panel-title",
                                className="responsive-filter-panel__title",
                                tabIndex=-1,
                            ),
                            html.Div(
                                f"All {listing_label}",
                                id=f"{page_type}-filter-panel-count",
                                className="responsive-filter-panel__count",
                                **{"aria-live": "polite"},
                            ),
                        ]
                    ),
                    html.Button(
                        html.I(className="bi bi-x-lg", **{"aria-hidden": "true"}),
                        id=f"{page_type}-filter-close-button",
                        type="button",
                        className="responsive-filter-panel__close",
                        **{
                            "data-filter-close": page_type,
                            "data-filter-close-source": "close-button",
                            "aria-label": "Close filters and discard unapplied changes",
                        },
                    ),
                ],
                className="responsive-filter-panel__header",
            ),
            html.Div(
                [title_card, user_options_card],
                className="responsive-filter-panel__body",
            ),
            html.Div(
                [
                    html.Button(
                        "Clear all",
                        id=f"{page_type}-filter-clear-button",
                        type="button",
                        className="responsive-filter-panel__clear",
                        **{
                            "data-filter-clear": page_type,
                            "aria-label": "Clear all listing filters",
                        },
                    ),
                    html.Button(
                        f"Show {listing_label}",
                        id=f"{page_type}-filter-apply-button",
                        type="button",
                        className="responsive-filter-panel__apply",
                        **{
                            "data-filter-apply": page_type,
                            "aria-label": f"Apply filters and show matching {listing_label}",
                        },
                    ),
                ],
                className="responsive-filter-panel__footer",
            ),
        ],
        id=f"{page_type}-filter-panel",
        className="responsive-filter-panel options-col",
        role="complementary",
        **{
            "aria-labelledby": f"{page_type}-filter-panel-title",
            "data-filter-panel": page_type,
        },
    )

    results_panel = html.Aside(
        [
            html.Div(
                [
                    html.H2("In view", className="results-panel__title"),
                    html.Span(
                        id=f"{page_type}-results-count",
                        className="results-panel__count",
                        **{"aria-live": "polite"},
                    ),
                ],
                className="results-panel__header",
            ),
            html.Div(
                html.Select(
                    [
                        html.Option("Price, low to high", value="price-asc"),
                        html.Option("Price, high to low", value="price-desc"),
                        html.Option("Beds, most first", value="beds-desc"),
                        html.Option("Size, largest first", value="sqft-desc"),
                        html.Option("Price per sq ft, low to high", value="ppsqft-asc"),
                        html.Option("Newest first", value="newest"),
                    ],
                    id=f"{page_type}-results-sort",
                    className="results-panel__sort",
                    **{
                        "data-results-sort": page_type,
                        "aria-label": "Sort the listings in view",
                    },
                ),
                className="results-panel__sort-row",
            ),
            html.Div(
                id=f"{page_type}-results-list",
                className="results-panel__list",
            ),
        ],
        id=f"{page_type}-results-panel",
        className="results-panel",
        role="complementary",
        **{
            "aria-label": f"{listing_label} currently visible on the map",
            "data-results-panel": page_type,
        },
    )

    # Both toggles sit on the layout rather than inside a column, so a collapsed
    # column can still be reopened.
    column_toggles = [
        html.Button(
            html.I(className="bi bi-layout-sidebar", **{"aria-hidden": "true"}),
            id=f"{page_type}-toggle-filters",
            type="button",
            className="column-toggle column-toggle--left",
            **{
                "data-column-toggle": "filters",
                "aria-label": "Hide or show the filters column",
            },
        ),
        html.Button(
            html.I(className="bi bi-layout-sidebar-reverse", **{"aria-hidden": "true"}),
            id=f"{page_type}-toggle-results",
            type="button",
            className="column-toggle column-toggle--right",
            **{
                "data-column-toggle": "results",
                "aria-label": "Hide or show the listings column",
            },
        ),
    ]

    return html.Div(
        [
            backdrop,
            panel,
            html.Main(
                map_card,
                id=f"{page_type}-map-main",
                className="listing-map-col map-col",
            ),
            results_panel,
            *column_toggles,
        ],
        className="listing-page-layout",
        **{"data-listing-page": page_type},
    )


def _quick_filter_button(
    page_type: str,
    key: str,
    label: str,
    section: str,
) -> html.Button:
    """Create a shortcut that opens one section of the responsive filter panel.

    ``key`` supplies the button identity while ``section`` identifies the
    accordion section that should receive focus.

    Args:
        page_type: Listing page type, either ``buy`` or ``lease``.
        key: Lookup, component, or object key identifying the requested item.
        label: User-facing label displayed for the component.
        section: Filter section associated with the quick-filter button.

    Returns:
        A button component for the requested quick filter.
    """
    return html.Button(
        label,
        id=f"{page_type}-quick-{key}",
        type="button",
        className="map-filter-chip",
        **{
            "data-filter-open": page_type,
            "data-filter-source": f"quick-{key}",
            "data-filter-group": key,
            "data-filter-section": section,
            "aria-controls": f"{page_type}-filter-panel",
        },
    )


_SUBTYPE_QUICK_REGISTERED = False


def _register_subtype_quick_callbacks() -> None:
    """Wire the two quick subtype toggles to the subtype dropdown, once.

    ``subtype_checklist`` is a single global id shared by both listing pages,
    while this module's callbacks register per page. Without the guard the second
    registration is a duplicate output and Dash refuses to start.

    Side Effects:
        Registers two clientside callbacks the first time it is called.

    Returns:
        None.
    """
    global _SUBTYPE_QUICK_REGISTERED
    if _SUBTYPE_QUICK_REGISTERED:
        return
    _SUBTYPE_QUICK_REGISTERED = True

    # The quick toggles and the dropdown are one filter with two faces. The
    # buttons write into the dropdown (the single source of truth), and a second
    # callback reads that value back to light them up. Splitting it this way
    # keeps the buttons' own state out of the graph, so there is no cycle.
    clientside_callback(
        """
        function (aptClicks, houseClicks, current) {
            const trigger = (window.dash_clientside.callback_context.triggered || [])[0];
            if (!trigger || !trigger.prop_id) return window.dash_clientside.no_update;
            const id = trigger.prop_id.split(".")[0];
            const button = document.getElementById(id);
            const value = button && button.dataset ? button.dataset.subtypeValue : null;
            if (!value) return window.dash_clientside.no_update;
            const selected = Array.isArray(current) ? current.slice() : [];
            const at = selected.indexOf(value);
            if (at === -1) selected.push(value);
            else selected.splice(at, 1);
            return selected;
        }
        """,
        Output("subtype_checklist", "value"),
        Input("subtype-quick-0", "n_clicks"),
        Input("subtype-quick-1", "n_clicks"),
        State("subtype_checklist", "value"),
        prevent_initial_call=True,
    )

    clientside_callback(
        """
        function (selected) {
            const chosen = Array.isArray(selected) ? selected : [];
            const base = "mode-switch__option btn";
            return ["subtype-quick-0", "subtype-quick-1"].map(function (id) {
                const button = document.getElementById(id);
                const value = button && button.dataset ? button.dataset.subtypeValue : null;
                return value && chosen.indexOf(value) !== -1 ? base + " active" : base;
            });
        }
        """,
        Output("subtype-quick-0", "className"),
        Output("subtype-quick-1", "className"),
        Input("subtype_checklist", "value"),
    )


def register_responsive_filter_callbacks(page_type: str) -> None:
    """Register the client-side callbacks for one listing page.

    These callbacks capture control values, calculate preview counts, apply
    committed filters to the map, and open the requested accordion section.

    Args:
        page_type: Listing page type, either ``buy`` or ``lease``.

    Returns:
        None.

    Raises:
        ValueError: If the operation cannot be completed.
    """
    _register_hybrid_range_callbacks(page_type)

    if page_type == "lease":
        capture_inputs = _lease_capture_inputs()
        capture_function = "captureLeaseFilterState"
        preview_function = "previewLeaseFilterState"
        applied_function = "applyLeaseFilterState"
        quick_ids = ["location", "price", "bedrooms", "bathrooms", "pets", "more"]
    elif page_type == "buy":
        capture_inputs = _buy_capture_inputs()
        capture_function = "captureBuyFilterState"
        preview_function = "previewBuyFilterState"
        applied_function = "applyBuyFilterState"
        quick_ids = ["location", "price", "bedrooms", "bathrooms", "more"]
    else:  # pragma: no cover - guarded by static page registration
        raise ValueError(f"Unsupported listing page: {page_type}")

    clientside_callback(
        ClientsideFunction(namespace="clientside", function_name=capture_function),
        Output(f"{page_type}-filter-draft-store", "data"),
        Output(f"{page_type}-filter-applied-store", "data"),
        [
            *capture_inputs,
            Input(f"{page_type}-filter-apply-button", "n_clicks"),
            Input("viewport-listener", "event"),
        ],
        State(f"{page_type}-filter-applied-store", "data"),
    )

    clientside_callback(
        ClientsideFunction(namespace="clientside", function_name=preview_function),
        Output(f"{page_type}-filter-preview-store", "data"),
        Input(f"{page_type}-filter-draft-store", "data"),
        State(f"{page_type}-geojson-store", "data"),
    )

    clientside_callback(
        ClientsideFunction(namespace="clientside", function_name=applied_function),
        Output(f"{page_type}_geojson", "data"),
        Input(f"{page_type}-filter-applied-store", "data"),
        Input(f"{page_type}-geojson-store", "data"),
    )

    _register_subtype_quick_callbacks()

    clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="scrollToFilterSection"),
        Output(f"{page_type}-analytics-section-store", "data"),
        [Input(f"{page_type}-quick-{key}", "n_clicks") for key in quick_ids],
        prevent_initial_call=True,
    )


def _lease_capture_inputs() -> list[Input]:
    """Return every Dash input that contributes to the rental filter state.

    The order matches the arguments accepted by ``captureLeaseFilterState``.

    Returns:
        A list containing the lease capture inputs.
    """
    return [
        Input("rental_price_minimum_input", "value"),
        Input("rental_price_maximum_input", "value"),
        Input("rental_price_slider", "max"),
        Input("bedrooms_slider", "value"),
        Input("bedrooms_slider", "max"),
        Input("bathrooms_slider", "value"),
        Input("bathrooms_slider", "max"),
        Input("pets_radio", "value"),
        Input("sqft_slider", "value"),
        Input("sqft_slider", "max"),
        Input("include-missing", "checked"),
        Input("ppsqft_slider", "value"),
        Input("ppsqft_slider", "max"),
        Input("include-missing", "checked"),
        Input("garage_spaces_slider", "value"),
        Input("garage_spaces_slider", "max"),
        Input("include-missing", "checked"),
        Input("yrbuilt_slider", "value"),
        Input("include-missing", "checked"),
        Input("terms_checklist", "value"),
        Input("include-missing", "checked"),
        Input("furnished_checklist", "value"),
        Input("include-missing", "checked"),
        Input("security_deposit_slider", "value"),
        Input("security_deposit_slider", "max"),
        Input("include-missing", "checked"),
        Input("pet_deposit_slider", "value"),
        Input("pet_deposit_slider", "max"),
        Input("include-missing", "checked"),
        Input("key_deposit_slider", "value"),
        Input("key_deposit_slider", "max"),
        Input("include-missing", "checked"),
        Input("other_deposit_slider", "value"),
        Input("other_deposit_slider", "max"),
        Input("include-missing", "checked"),
        Input("laundry_checklist", "value"),
        Input("include-missing", "checked"),
        Input("subtype_checklist", "value"),
        Input("listed_time_range_radio", "value"),
        Input("listed_date_datepicker_lease", "start_date"),
        Input("listed_date_datepicker_lease", "end_date"),
        Input("include-missing", "checked"),
        Input("isp_download_speed_slider", "value"),
        Input("isp_upload_speed_slider", "value"),
        Input("include-missing", "checked"),
        Input("rent_control_status", "value"),
        Input("lease-location-input", "value"),
        Input("lease-nearby-zip-switch", "checked"),
        Input("lease-zip-boundary-store", "data"),
    ]


def _buy_capture_inputs() -> list[Input]:
    """Return every Dash input that contributes to the for-sale filter state.

    The order matches the arguments accepted by ``captureBuyFilterState``.

    Returns:
        A list containing the buy capture inputs.
    """
    return [
        Input("list_price_minimum_input", "value"),
        Input("list_price_maximum_input", "value"),
        Input("list_price_slider", "max"),
        Input("bedrooms_slider", "value"),
        Input("bedrooms_slider", "max"),
        Input("bathrooms_slider", "value"),
        Input("bathrooms_slider", "max"),
        Input("sqft_slider", "value"),
        Input("sqft_slider", "max"),
        Input("include-missing", "checked"),
        Input("ppsqft_slider", "value"),
        Input("ppsqft_slider", "max"),
        Input("include-missing", "checked"),
        Input("lot_size_minimum_input", "value"),
        Input("lot_size_maximum_input", "value"),
        Input("lot_size_slider", "max"),
        Input("include-missing", "checked"),
        Input("yrbuilt_slider", "value"),
        Input("include-missing", "checked"),
        Input("subtype_checklist", "value"),
        Input("listed_time_range_radio", "value"),
        Input("listed_date_datepicker_buy", "start_date"),
        Input("listed_date_datepicker_buy", "end_date"),
        Input("include-missing", "checked"),
        Input("hoa_fee_minimum_input", "value"),
        Input("hoa_fee_maximum_input", "value"),
        Input("hoa_fee_slider", "max"),
        Input("include-missing", "checked"),
        Input("hoa_fee_frequency_checklist", "value"),
        Input("isp_download_speed_slider", "value"),
        Input("isp_upload_speed_slider", "value"),
        Input("include-missing", "checked"),
        Input("buy-location-input", "value"),
        Input("buy-nearby-zip-switch", "checked"),
        Input("buy-zip-boundary-store", "data"),
    ]
