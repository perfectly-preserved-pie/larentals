"""Check invalid chunk handling against Dash's actual asset routes."""

import pytest
from dash import Dash, dcc, html
from flask import Flask
from flask.testing import FlaskClient

from functions.dash_asset_requests import register_dash_asset_request_guard


@pytest.fixture
def dash_client():
    """Create a small app without loading production data or services."""
    app = Dash(__name__)
    app.layout = html.Div(
        [dcc.Slider(), dcc.Graph(), dcc.DatePickerSingle(), dcc.Dropdown()]
    )
    app.server.config["TESTING"] = True
    register_dash_asset_request_guard(app.server)
    return app.server.test_client()


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize(
    "filename",
    [
        "737.async-slider.js",
        "746.async-graph.js",
        "400.async-datepicker.js",
        "157.async-dropdown.js",
    ],
)
def test_scanned_assets_return_404_without_errors(dash_client, caplog, method, filename):
    """Invalid filenames produce a normal 404, not a Dash exception."""
    response = dash_client.open(
        f"/_dash-component-suites/dash/dcc/{filename}?v=1", method=method
    )
    assert response.status_code == 404
    assert not [record for record in caplog.records if record.levelno >= 40]


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_nested_plotly_asset_returns_404_without_errors(
    dash_client: FlaskClient, caplog: pytest.LogCaptureFixture, method: str
) -> None:
    """The nested Plotly URL from production must not raise a Dash exception.

    Args:
        dash_client: Isolated Dash application client.
        caplog: Captured logs used to detect server errors.
        method: HTTP request method to exercise.

    Returns:
        None.
    """
    response = dash_client.open(
        "/_dash-component-suites/dash/dash-renderer/build/"
        "_dash-component-suites/plotly/package_data/plotly.min.js?v=1",
        method=method,
    )
    assert response.status_code == 404
    assert not [record for record in caplog.records if record.levelno >= 40]


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_valid_plotly_asset_still_loads(dash_client: FlaskClient, method: str) -> None:
    """Keep the Plotly bundle available at its actual component route.

    Args:
        dash_client: Isolated Dash application client.
        method: HTTP request method to exercise.

    Returns:
        None.
    """
    response = dash_client.open(
        "/_dash-component-suites/plotly/package_data/plotly.min.js", method=method
    )
    assert response.status_code == 200
    if method == "GET":
        assert response.data


@pytest.mark.parametrize(
    "filename",
    [
        "async-slider.js",
        "async-graph.js",
        "async-datepicker.js",
        "async-dropdown.js",
        "async-slider.js.map",
        "dash_core_components.js",
    ],
)
def test_valid_dash_assets_still_load(dash_client, filename):
    """Keep real JavaScript bundles and source maps available."""
    response = dash_client.get(f"/_dash-component-suites/dash/dcc/{filename}")
    assert response.status_code == 200
    assert response.data


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/_dash-component-suites/dash_leaflet/123.async-GeoJSON.js", 404),
        ("/_dash-component-suites/dash/dcc/737.async-slider.js.map", 200),
        ("/_dash-component-suites/dash/dcc/737Xasync-slider.js", 200),
        ("/_dash-component-suites/dash/dcc/737.async-sliderXjs", 200),
        ("/assets/737.async-slider.js", 200),
        ("/assets/_dash-component-suites/plotly/package_data/plotly.min.js", 200),
        ("/api/listings", 200),
    ],
)
def test_guard_scope(path, expected):
    """Only matching component filenames are intercepted before routing."""
    server = Flask(__name__)
    register_dash_asset_request_guard(server)
    server.add_url_rule("/<path:path>", view_func=lambda path: "passed through")
    assert server.test_client().get(path).status_code == expected
