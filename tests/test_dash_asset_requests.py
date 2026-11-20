"""Check invalid chunk handling against Dash's actual asset routes."""

import pytest
from dash import Dash, dcc, html
from flask import Flask
from flask.testing import FlaskClient

from functions.dash_asset_requests import register_dash_asset_request_guard


@pytest.fixture
def dash_client() -> FlaskClient:
    """Create a small app without loading production data or services.

    The fixture isolates request-routing behavior from external dependencies.

    Returns:
        Client for requests to the isolated Dash app.
    """
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
def test_scanned_assets_return_404_without_errors(
    dash_client: FlaskClient,
    caplog: pytest.LogCaptureFixture,
    method: str,
    filename: str,
) -> None:
    """Invalid filenames produce a normal 404, not a Dash exception.

    This covers malformed and traversal-style asset paths at the HTTP boundary.

    Args:
        dash_client: Test client with the Dash asset guard installed.
        caplog: Captured logs used to check for unexpected errors.
        method: HTTP method used to request the route.
        filename: Asset filename requested from the Dash component suite.

    Returns:
        None.
    """
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

    Production nested Plotly paths should fail as a normal missing asset, not a Dash routing exception.

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

    The request guard must not block Plotly assets at their real component route.

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
def test_valid_dash_assets_still_load(dash_client: FlaskClient, filename: str) -> None:
    """Keep real JavaScript bundles and source maps available.

    The guard should reject suspicious names without blocking legitimate Dash
    assets required by the browser.

    Args:
        dash_client: Test client with the Dash asset guard installed.
        filename: Asset filename requested from the Dash component suite.

    Returns:
        None.
    """
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
def test_guard_scope(path: str, expected: int) -> None:
    """Only matching component filenames are intercepted before routing.

    Unrelated paths must continue through Dash's normal route handling.

    Args:
        path: URL path exercised by the test client.
        expected: Expected HTTP status for the guarded or pass-through path.

    Returns:
        None.
    """
    server = Flask(__name__)
    register_dash_asset_request_guard(server)
    server.add_url_rule("/<path:path>", view_func=lambda path: "passed through")
    assert server.test_client().get(path).status_code == expected


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize(
    "path",
    [
        "/_dash-component-suites/dash/dcc/forwardRef((function(t,n){",
        "/_dash-component-suites/dash/deps/.env",
        "/_dash-component-suites/dash/deps/phpinfo.php",
        "/_dash-component-suites/dash/deps/",
        "/_dash-component-suites/unknown/bundle.js",
        "/_dash-component-suites/dash/dcc/missing.js.map",
    ],
)
def test_unregistered_assets_return_404(
    dash_client: FlaskClient,
    caplog: pytest.LogCaptureFixture,
    method: str,
    path: str,
) -> None:
    """Reject scanner paths through Dash's actual package validation.

    These names bypass the early malformed-chunk checks and previously raised
    dependency exceptions, including probes under otherwise valid packages.

    Args:
        dash_client: Test client with the Dash asset guard installed.
        caplog: Captured logs used to check for unexpected errors.
        method: HTTP method used to request the route.
        path: URL path exercised by the test client.

    Returns:
        None.
    """
    response = dash_client.open(path, method=method)
    assert response.status_code == 404
    assert not [record for record in caplog.records if record.levelno >= 40]


@pytest.mark.parametrize(
    "path, method",
    [("/callback", "GET"), ("/_dash-component-suites/dash/bundle.js", "POST")],
)
def test_other_dependency_failures_remain_visible(path: str, method: str) -> None:
    """Keep unrelated dependency errors from becoming misleading 404s.

    The handler is registered on Flask globally, so both the route prefix and
    request method must constrain which failures it translates.

    Args:
        path: URL path exercised by the test client.
        method: HTTP method used to request the route.

    Returns:
        None.
    """
    from dash.exceptions import DependencyException

    server = Flask(__name__)
    server.config["TESTING"] = True
    register_dash_asset_request_guard(server)

    def fail() -> None:
        """Simulate a dependency failure outside component asset retrieval.

        A real callback failure must still propagate to Flask's error handling.

        Returns:
            Raises the simulated dependency error.
        """
        raise DependencyException("unrelated dependency failure")

    server.add_url_rule(path, view_func=fail, methods=[method])
    with pytest.raises(DependencyException, match="unrelated dependency failure"):
        server.test_client().open(path, method=method)


def test_fingerprinted_asset_still_loads(dash_client: FlaskClient) -> None:
    """Let Dash normalize cache fingerprints before validating asset names.

    Browser bundle URLs contain version and modification-time tokens that are
    absent from the registered filename and must not be rejected literally.

    Args:
        dash_client: Test client with the Dash asset guard installed.

    Returns:
        None.
    """
    response = dash_client.get(
        "/_dash-component-suites/dash/dcc/"
        "dash_core_components.v4_4_1m1234567890.js"
    )
    assert response.status_code == 200
    assert response.data
