from typing import Any
from functions.data_paths import LARENTALS_DB_PATH

from .isp import register_isp_routes
from .listings import register_listing_routes
from .report_listing import register_report_listing_routes
from .property_context import register_property_context_routes


def register_api_routes(server: Any, db_path: str = str(LARENTALS_DB_PATH)) -> None:
    """Register all Flask routes used by the app's API surface.

    Central registration keeps the Flask route set attached to the same app
    instance. Property records have a separate route so agency requests cannot
    delay the ordinary listing detail response.

    Args:
        server: Flask application receiving the registered API routes.
        db_path: Filesystem path to the SQLite database.

    Returns:
        None.
    """
    register_report_listing_routes(server, db_path=db_path)
    register_isp_routes(server, db_path=db_path)
    register_listing_routes(server, db_path=db_path)
    register_property_context_routes(server, db_path=db_path)
