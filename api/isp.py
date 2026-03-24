import sqlite3
from typing import Any

from flask import Blueprint, Response, jsonify

LEASE_ISP_SQL = """
  SELECT
    DBA,

    CASE
      WHEN TechCode IN (10, 11, 12, 20) THEN 'DSL'
      WHEN TechCode = 40 THEN 'Cable'
      WHEN TechCode = 50 THEN 'Fiber'
      WHEN TechCode = 60 THEN 'Satellite'
      WHEN TechCode IN (70, 71, 72) THEN 'Terrestrial Fixed Wireless'
      ELSE COALESCE(Service_Type, 'Unknown')
    END AS Service_Type,

    TechCode,
    MaxAdDn,
    MaxAdUp,
    MaxDnTier,
    MaxUpTier,
    MinDnTier,
    MinUpTier,

    CASE
      WHEN TechCode = 50 THEN 'best'
      WHEN TechCode IN (40, 43) AND COALESCE(MaxAdDn, 0) >= 1000 THEN 'best'
      WHEN COALESCE(MaxAdDn, 0) >= 1000 THEN 'best'
      WHEN TechCode IN (40, 43) THEN 'good'
      WHEN TechCode IN (70, 71, 72) AND COALESCE(MaxAdDn, 0) >= 100 THEN 'good'
      WHEN COALESCE(MaxAdDn, 0) >= 100 THEN 'good'
      ELSE 'fallback'
    END AS bucket

  FROM lease_provider_options
  WHERE listing_id = ?
    AND DBA IS NOT NULL
    AND NOT (COALESCE(MaxAdDn, 0) = 0 AND COALESCE(MaxAdUp, 0) = 0)
  ORDER BY COALESCE(MaxAdDn, -1) DESC
  LIMIT 8;
"""

BUY_ISP_SQL = """
  SELECT
    DBA,

    CASE
      WHEN TechCode IN (10, 11, 12, 20) THEN 'DSL'
      WHEN TechCode = 40 THEN 'Cable'
      WHEN TechCode = 50 THEN 'Fiber'
      WHEN TechCode = 60 THEN 'Satellite'
      WHEN TechCode IN (70, 71, 72) THEN 'Terrestrial Fixed Wireless'
      ELSE COALESCE(Service_Type, 'Unknown')
    END AS Service_Type,

    TechCode,
    MaxAdDn,
    MaxAdUp,
    MaxDnTier,
    MaxUpTier,
    MinDnTier,
    MinUpTier,

    CASE
      WHEN TechCode = 50 THEN 'best'
      WHEN TechCode IN (40, 43) AND COALESCE(MaxAdDn, 0) >= 1000 THEN 'best'
      WHEN COALESCE(MaxAdDn, 0) >= 1000 THEN 'best'
      WHEN TechCode IN (40, 43) THEN 'good'
      WHEN TechCode IN (70, 71, 72) AND COALESCE(MaxAdDn, 0) >= 100 THEN 'good'
      WHEN COALESCE(MaxAdDn, 0) >= 100 THEN 'good'
      ELSE 'fallback'
    END AS bucket

  FROM buy_provider_options
  WHERE listing_id = ?
    AND DBA IS NOT NULL
    AND NOT (COALESCE(MaxAdDn, 0) = 0 AND COALESCE(MaxAdUp, 0) = 0)
  ORDER BY COALESCE(MaxAdDn, -1) DESC
  LIMIT 8;
"""


def build_provider_option_payload(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """
    Convert ISP database rows into the JSON payload expected by the popup renderer.

    Args:
        rows: SQLite rows returned from the lease/buy provider-options queries.

    Returns:
        List of normalized provider option dictionaries consumed by `assets/js/isp.js`.
    """
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "dba": row["DBA"],
                "service_type": row["Service_Type"],
                "tech_code": row["TechCode"],
                "max_dn_mbps": row["MaxAdDn"],
                "max_up_mbps": row["MaxAdUp"],
                "max_dn_tier": row["MaxDnTier"],
                "max_up_tier": row["MaxUpTier"],
                "min_dn_tier": row["MinDnTier"],
                "min_up_tier": row["MinUpTier"],
                "bucket": row["bucket"],
            }
        )
    return result


def register_isp_routes(server: Any, db_path: str = "assets/datasets/larentals.db") -> None:
    """
    Register HTTP routes for fetching ISP options on-demand.

    Args:
        server: The Flask server instance (typically `app.server` in Dash).
        db_path: Path to the SQLite database file.
    """
    bp = Blueprint("isp_api", __name__)

    @bp.get("/api/lease/isp-options/<listing_id>")
    def get_lease_isp_options(listing_id: str) -> Response:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(LEASE_ISP_SQL, (listing_id,)).fetchall()

        return jsonify(build_provider_option_payload(rows))

    @bp.get("/api/buy/isp-options/<listing_id>")
    def get_buy_isp_options(listing_id: str) -> Response:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(BUY_ISP_SQL, (listing_id,)).fetchall()

        return jsonify(build_provider_option_payload(rows))

    server.register_blueprint(bp)
