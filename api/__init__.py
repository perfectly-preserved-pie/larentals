from typing import Any

from .isp import register_isp_routes
from .listings import register_listing_routes
from .report_listing import register_report_listing_routes


def register_api_routes(server: Any, db_path: str = "assets/datasets/larentals.db") -> None:
    """Register all Flask routes used by the app's API surface."""
    register_report_listing_routes(server, db_path=db_path)
    register_isp_routes(server, db_path=db_path)
    register_listing_routes(server, db_path=db_path)
