from __future__ import annotations

from typing import Any

from dash import Input, Output, html
from dash.exceptions import PreventUpdate
from dash_extensions import EventListener
import dash_ag_grid as dag
import dash_mantine_components as dmc
from loguru import logger

from functions.lahd import fetch_lahd_property_record_details


LAHD_RECORD_EVENT_NAME = "lahdrecordrequest"
LAHD_RECORD_EVENT_PROPS = [
    "detail.apn",
    "detail.address",
    "detail.source",
    "detail.requestedAt",
]


def create_lahd_records_listener() -> EventListener:
    """
    Create the hidden browser-event bridge used by Leaflet popup buttons.
    """
    return EventListener(
        id="lahd-records-listener",
        events=[{"event": LAHD_RECORD_EVENT_NAME, "props": LAHD_RECORD_EVENT_PROPS}],
        style={"display": "none"},
    )


def create_lahd_records_drawer() -> dmc.Drawer:
    """
    Create the global Housing Department records drawer shared by lease and buy pages.
    """
    return dmc.Drawer(
        id="lahd-records-drawer",
        title=html.Div("Housing Department Records", id="lahd-records-drawer-title"),
        children=html.Div(
            [
                dag.AgGrid(
                    id="lahd-records-ag-grid-loader",
                    rowData=[],
                    columnDefs=[],
                    style={"display": "none"},
                ),
                html.Div(id="lahd-records-drawer-content"),
            ]
        ),
        opened=False,
        position="right",
        size="min(94vw, 980px)",
        padding="md",
        withOverlay=True,
        closeOnClickOutside=True,
        closeOnEscape=True,
        lockScroll=False,
        zIndex=2400,
        className="lahd-records-drawer",
    )


def register_lahd_records_drawer_callback(app: Any) -> None:
    """
    Register the callback that fills the Housing Department records drawer from an APN event.
    """

    @app.callback(
        Output("lahd-records-drawer", "opened"),
        Output("lahd-records-drawer-title", "children"),
        Output("lahd-records-drawer-content", "children"),
        Input("lahd-records-listener", "event"),
        prevent_initial_call=True,
    )
    def open_lahd_records_drawer(event: dict[str, Any] | None) -> tuple[bool, Any, Any]:
        apn = _event_value(event, "detail.apn")
        if not apn:
            raise PreventUpdate

        address = _event_value(event, "detail.address")

        try:
            details = fetch_lahd_property_record_details(str(apn))
        except Exception as exc:  # pragma: no cover - exercised manually against live data
            logger.exception(f"Failed fetching Housing Department records for APN {apn}.")
            title = _build_drawer_title(apn, address)
            return True, title, _build_error_content(apn, exc)

        title = _build_drawer_title(apn, address or _primary_address_from_summary(details.get("summary")))
        return True, title, build_lahd_records_drawer_content(details)


def build_lahd_records_drawer_content(details: dict[str, Any]) -> Any:
    """
    Build the drawer body for one APN's Housing Department records.
    """
    cases = _as_list(details.get("cases"))
    violations = _as_list(details.get("violations"))
    summary = details.get("summary") if isinstance(details.get("summary"), dict) else {}
    truncated = details.get("truncated") if isinstance(details.get("truncated"), dict) else {}
    detail_status = details.get("detail_status") if isinstance(details.get("detail_status"), dict) else {}
    sources = details.get("sources") if isinstance(details.get("sources"), dict) else {}
    live_records_available = detail_status.get("live_records_available") is not False
    empty_case_message = (
        "Row-level Housing Department case records are unavailable right now."
        if not live_records_available
        else "No Housing Department investigation/enforcement cases found for this APN."
    )
    empty_violation_message = (
        "Row-level Housing Department code-violation records are unavailable right now."
        if not live_records_available
        else "No Housing Department code-violation records found for this APN."
    )

    return html.Div(
        [
            _build_summary(summary),
            _build_detail_status_notice(detail_status),
            _build_truncation_notice(truncated),
            dmc.Tabs(
                [
                    dmc.TabsList(
                        [
                            dmc.TabsTab(f"Cases ({len(cases):,})", value="cases"),
                            dmc.TabsTab(f"Code Violations ({len(violations):,})", value="violations"),
                        ],
                        grow=True,
                    ),
                    dmc.TabsPanel(
                        _build_grid(
                            "lahd-cases-grid",
                            cases,
                            CASE_COLUMN_DEFS,
                            empty_case_message,
                        ),
                        value="cases",
                        pt="sm",
                    ),
                    dmc.TabsPanel(
                        _build_grid(
                            "lahd-violations-grid",
                            violations,
                            VIOLATION_COLUMN_DEFS,
                            empty_violation_message,
                        ),
                        value="violations",
                        pt="sm",
                    ),
                ],
                value="cases",
                keepMounted=True,
            ),
            _build_source_links(sources),
        ],
        className="lahd-records-content",
    )


CASE_COLUMN_DEFS: list[dict[str, Any]] = [
    {"field": "filed_date", "headerName": "Filed", "width": 120, "sort": "desc"},
    {"field": "closed_date", "headerName": "Closed", "width": 120},
    {"field": "status", "headerName": "Status", "width": 130},
    {"field": "case_type", "headerName": "Case Type", "minWidth": 210, "flex": 1},
]

VIOLATION_COLUMN_DEFS: list[dict[str, Any]] = [
    {"field": "violation_type", "headerName": "Violation Type", "minWidth": 220, "flex": 1},
    {"field": "violations_cited", "headerName": "Cited", "type": "rightAligned", "width": 110},
    {"field": "violations_cleared", "headerName": "Cleared", "type": "rightAligned", "width": 115},
    {"field": "uncleared_estimate", "headerName": "Uncleared Est.", "type": "rightAligned", "width": 145},
]

DEFAULT_COL_DEF = {
    "sortable": True,
    "filter": True,
    "floatingFilter": True,
    "resizable": True,
    "wrapText": True,
}

GRID_OPTIONS = {
    "animateRows": False,
    "pagination": True,
    "paginationPageSize": 25,
    "paginationPageSizeSelector": [10, 25, 50, 100],
    "rowHeight": 38,
    "suppressCellFocus": True,
}


def _event_value(event: dict[str, Any] | None, key: str) -> str | None:
    """
    Read an EventListener value from either flattened or nested event shapes.
    """
    if not isinstance(event, dict):
        return None

    value = event.get(key)
    if value is not None:
        return str(value).strip() or None

    if key.startswith("detail."):
        detail = event.get("detail")
        nested_key = key.split(".", 1)[1]
        if isinstance(detail, dict) and detail.get(nested_key) is not None:
            return str(detail.get(nested_key)).strip() or None

    return None


def _as_list(value: Any) -> list[dict[str, Any]]:
    """
    Return a list of record dictionaries.
    """
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _format_count(value: Any) -> str:
    """
    Format a summary count for display.
    """
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def _primary_address_from_summary(summary: Any) -> str | None:
    """
    Return the first Housing Department address for drawer-title fallback.
    """
    if not isinstance(summary, dict):
        return None
    addresses = summary.get("addresses")
    if not isinstance(addresses, list):
        return None
    for address in addresses:
        normalized = str(address or "").strip()
        if normalized:
            return normalized
    return None


def _build_drawer_title(apn: Any, address: Any) -> Any:
    """
    Build the drawer title block.
    """
    address_text = str(address or "").strip()
    return html.Div(
        [
            html.Div("Housing Department Records", className="lahd-records-title"),
            html.Div(
                f"APN {str(apn).strip()}" + (f" · {address_text}" if address_text else ""),
                className="lahd-records-subtitle",
            ),
        ]
    )


def _build_summary(summary: dict[str, Any]) -> html.Div:
    """
    Build the compact summary metrics above the tables.
    """
    metrics = [
        ("Documented Issues", summary.get("documented_issue_count"), "cases + citations"),
        ("Unresolved Est.", summary.get("unresolved_issue_count"), "open cases + uncleared citations"),
        ("Cases Filed", summary.get("case_count"), "case records"),
        ("Open Cases Est.", summary.get("open_case_count"), "no close date"),
        ("Citations Cited", summary.get("violations_cited"), "violation citation count"),
        ("Citations Uncleared", summary.get("unresolved_violation_count"), "cited - cleared"),
    ]

    return html.Div(
        [
            html.Div(
                [
                    html.Div(label, className="lahd-records-metric__label"),
                    html.Div(_format_count(value), className="lahd-records-metric__value"),
                    html.Div(hint, className="lahd-records-metric__hint"),
                ],
                className="lahd-records-metric",
            )
            for label, value, hint in metrics
        ],
        className="lahd-records-summary",
    )


def _build_truncation_notice(truncated: dict[str, Any]) -> Any:
    """
    Render a small notice if the row limit was reached.
    """
    cases_truncated = bool(truncated.get("cases"))
    violations_truncated = bool(truncated.get("violations"))
    if not cases_truncated and not violations_truncated:
        return None

    row_limit = _format_count(truncated.get("row_limit"))
    parts = []
    if cases_truncated:
        parts.append("cases")
    if violations_truncated:
        parts.append("violations")

    return html.Div(
        f"Showing the first {row_limit} {' and '.join(parts)} records from Housing Department data.",
        className="lahd-records-notice",
    )


def _build_detail_status_notice(detail_status: dict[str, Any]) -> Any:
    """
    Render a small notice when the drawer is showing aggregate snapshot data.
    """
    if detail_status.get("live_records_available") is not False:
        return None

    message = str(detail_status.get("message") or "").strip()
    if not message:
        message = "Showing the latest local aggregate snapshot."

    snapshot_generated_at = str(detail_status.get("snapshot_generated_at") or "").strip()
    if snapshot_generated_at:
        message = f"{message} Snapshot generated {snapshot_generated_at}."

    return html.Div(message, className="lahd-records-notice")


def _build_grid(
    grid_id: str,
    rows: list[dict[str, Any]],
    column_defs: list[dict[str, Any]],
    empty_message: str,
) -> Any:
    """
    Build a Dash AG Grid table for Housing Department records.
    """
    grid_options = {
        **GRID_OPTIONS,
        "overlayNoRowsTemplate": f'<span class="lahd-records-grid-empty">{empty_message}</span>',
    }
    return dag.AgGrid(
        id=grid_id,
        rowData=rows,
        columnDefs=column_defs,
        defaultColDef=DEFAULT_COL_DEF,
        dashGridOptions=grid_options,
        columnSize="responsiveSizeToFit",
        className="ag-theme-alpine lahd-records-grid",
        style={"height": "430px", "width": "100%"},
    )


def _build_source_links(sources: dict[str, Any]) -> html.Div:
    """
    Render source links under the grids.
    """
    return html.Div(
        [
            html.A(
                "Housing cases source",
                href=str(sources.get("investigation_source_url") or "https://data.lacity.org/d/eagk-wq48"),
                target="_blank",
                rel="noopener noreferrer",
            ),
            html.Span(" · "),
            html.A(
                "Housing violations source",
                href=str(sources.get("violation_source_url") or "https://data.lacity.org/d/cr8f-uc4j"),
                target="_blank",
                rel="noopener noreferrer",
            ),
        ],
        className="lahd-records-sources",
    )


def _build_error_content(apn: Any, exc: Exception) -> html.Div:
    """
    Render a recoverable load error inside the drawer.
    """
    return html.Div(
        [
            html.Div("Unable to load Housing Department records right now.", className="lahd-records-error__title"),
            html.Div(f"APN {str(apn).strip()}", className="lahd-records-error__meta"),
            html.Div(str(exc), className="lahd-records-error__message"),
        ],
        className="lahd-records-error",
    )
