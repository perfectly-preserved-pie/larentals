from contextlib import closing
from datetime import date
from functools import lru_cache
from html import unescape
from typing import Any, Optional, Sequence
import dash_leaflet as dl
import geopandas as gpd
import json
import logging
import numpy as np
import os
import pandas as pd
import re
import sqlite3

from functions.layers import LayersClass
from functions.sql_helpers import get_latest_date_processed

DB_PATH = "assets/datasets/larentals.db"
DEFAULT_SPEED_MAX = 1.0
logger = logging.getLogger(__name__)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def categorize_laundry_features(feature: object) -> str:
    """
    Collapse raw laundry text into a smaller set of filter buckets.

    Args:
        feature: Raw laundry text from the listing row.

    Returns:
        A normalized category label used by the lease filters.
    """
    if pd.isna(feature) or feature in ["Unknown", ""]:
        return "Unknown"
    if any(
        keyword in feature
        for keyword in [
            "In Closet",
            "In Kitchen",
            "In Garage",
            "Inside",
            "Individual Room",
        ]
    ):
        return "In Unit"
    if any(keyword in feature for keyword in ["Community Laundry", "Common Area", "Shared"]):
        return "Shared"
    if any(
        keyword in feature
        for keyword in [
            "Hookup",
            "Electric Dryer Hookup",
            "Gas Dryer Hookup",
            "Washer Hookup",
        ]
    ):
        return "Hookups"
    if any(keyword in feature for keyword in ["Dryer Included", "Washer Included"]):
        return "Included Appliances"
    if any(keyword in feature for keyword in ["Outside", "Upper Level", "In Carport"]):
        return "Location Specific"
    return "Other"


def _normalize_unknown_text(
    series: pd.Series,
    *,
    decode_html: bool = False,
) -> pd.Series:
    """
    Replace missing-like values with ``Unknown`` and optionally decode HTML.

    Args:
        series: Series to normalize.
        decode_html: Whether to unescape HTML entities after normalization.

    Returns:
        The cleaned pandas Series.
    """
    normalized = series.fillna("Unknown").replace({None: "Unknown", "None": "Unknown"})
    if decode_html:
        normalized = normalized.astype(str).apply(unescape)
    return normalized


def _db_cache_token(db_path: str = DB_PATH) -> int:
    """Return a cheap cache-busting token derived from the backing SQLite file."""
    try:
        return os.stat(db_path).st_mtime_ns
    except OSError:
        return 0


def _require_safe_identifier(name: str, *, field_name: str) -> str:
    """
    Validate a SQL identifier (table/column/index name).

    Args:
        name: The identifier to validate.
        field_name: Label for error messages.

    Returns:
        The original name if valid.

    Raises:
        ValueError: If the identifier is unsafe.
    """
    if not _IDENTIFIER_RE.fullmatch(name):
        raise ValueError(f"Unsafe SQL identifier for {field_name}: {name!r}")
    return name


def _sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """
    Return whether a SQLite table or view exists.

    Args:
        conn: Open SQLite connection.
        table_name: Candidate table/view name.

    Returns:
        ``True`` when the table or view exists, else ``False``.
    """
    safe_table = _require_safe_identifier(table_name, field_name="table_name")
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view') AND name = ?
        LIMIT 1
        """,
        (safe_table,),
    ).fetchone()
    return row is not None


def _sqlite_table_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    """
    Return the column names declared on a SQLite table or view.

    Args:
        conn: Open SQLite connection.
        table_name: Table/view name to inspect.

    Returns:
        A set of declared column names.
    """
    safe_table = _require_safe_identifier(table_name, field_name="table_name")
    rows = conn.execute(f"PRAGMA table_info({safe_table})").fetchall()
    return {str(row[1]) for row in rows}


@lru_cache(maxsize=8)
def _build_cached_geojson_payload(
    table_name: str,
    page_type: str,
    select_columns: tuple[str, ...],
    db_mtime_ns: int,
    categorize_lease_laundry: bool = False,
) -> dict:
    """
    Build and cache a GeoJSON payload without constructing any Dash UI components.

    Args:
        table_name: Source table name.
        page_type: Page identifier such as ``lease`` or ``buy``.
        select_columns: Columns to load for the payload.
        db_mtime_ns: Database modification time used for cache invalidation.
        categorize_lease_laundry: Whether to normalize lease laundry labels.

    Returns:
        A GeoJSON feature collection ready for the client store.
    """
    del db_mtime_ns  # Used only as part of the cache key.

    loader = BaseClass(
        table_name=table_name,
        page_type=page_type,
        select_columns=select_columns,
        include_last_updated=False,
    )

    if categorize_lease_laundry and "laundry" in loader.df.columns:
        loader.df["laundry"] = loader.df["laundry"].apply(categorize_laundry_features)

    return loader.return_geojson()


class BaseClass:
    """Shared listing-data loader and transformer for page component builders."""

    OPTIONAL_LAYER_KEYS: tuple[str, ...] = ()

    def __init__(
        self,
        table_name: str,
        page_type: str,
        *,
        select_columns: Optional[Sequence[str]] = None,
        include_last_updated: bool = True,
    ) -> None:
        """
        Load a table/view from SQLite and prepare the DataFrame.

        Args:
            table_name: SQLite table/view name (e.g. "lease" or "buy").
            page_type: Page context ("lease" or "buy").
            select_columns: Optional list/tuple of columns to select instead of SELECT *.
                Use this to shrink payload for faster startup and smaller GeoJSON.
            include_last_updated: Whether to query the table's processed timestamp.
        """
        safe_table = _require_safe_identifier(table_name, field_name="table_name")

        with closing(sqlite3.connect(DB_PATH)) as conn:
            base_table_columns = _sqlite_table_columns(conn, safe_table)

            if select_columns is None:
                sql = f"SELECT * FROM {safe_table}"
                requested_cols: list[str] | None = None
            else:
                if not select_columns:
                    raise ValueError("select_columns cannot be empty when provided")

                requested_cols = [
                    _require_safe_identifier(col, field_name="select_columns")
                    for col in select_columns
                ]
                query_cols = [col for col in requested_cols if col in base_table_columns]

                # Keep the join key available internally even when callers only
                # request enrichment columns populated by later merge steps.
                if "mls_number" in base_table_columns and "mls_number" not in query_cols:
                    query_cols.insert(0, "mls_number")

                if not query_cols:
                    raise ValueError(
                        f"No selectable base-table columns found for {safe_table}: {requested_cols!r}"
                    )

                sql = f"SELECT {', '.join(query_cols)} FROM {safe_table}"

            self.df = pd.read_sql_query(sql, conn)
            self._attach_isp_speeds(conn, table_name=safe_table)
            self._attach_listing_enrichment(conn, table_name=safe_table)
            if select_columns is not None:
                keep_cols = [col for col in requested_cols or [] if col in self.df.columns]
                for col in ("mls_number", "best_dn", "best_up"):
                    if col in self.df.columns and col not in keep_cols:
                        keep_cols.append(col)
                self.df = self.df[keep_cols]

        self.page_type = page_type

        numeric_cols = [
            "latitude",
            "longitude",
            "bedrooms",
            "sqft",
            "year_built",
            "ppsqft",
            "list_price",
            "olp",
            "parking_spaces",
            "garage_spaces",
            "lot_size",
            "total_bathrooms",
            "full_bathrooms",
            "half_bathrooms",
            "three_quarter_bathrooms",
            "quarter_bathrooms",
            "hoa_fee",
            "space_rent",
            "key_deposit",
            "other_deposit",
            "pet_deposit",
            "security_deposit",
            "best_dn",
            "best_up",
            "nearest_elem_school_mi",
            "nearest_mid_school_mi",
            "nearest_high_school_mi",
        ]
        for col in numeric_cols:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors="coerce")

        if "listed_date" in self.df.columns:
            self.df["listed_date"] = pd.to_datetime(
                self.df["listed_date"], errors="coerce"
            )

        if {"latitude", "longitude"}.issubset(self.df.columns):
            geom = gpd.points_from_xy(self.df["longitude"], self.df["latitude"])
            self.df = gpd.GeoDataFrame(self.df, geometry=geom)

        if "listed_date" in self.df.columns and not self.df["listed_date"].isna().all():
            self.earliest_date = self.df["listed_date"].min().to_pydatetime()
        else:
            self.earliest_date = date.today()

        self.last_updated = (
            get_latest_date_processed(DB_PATH, table_name=safe_table)
            if include_last_updated
            else None
        )

        if "subtype" in self.df.columns:
            self.df["subtype"] = _normalize_unknown_text(
                self.df["subtype"],
                decode_html=True,
            ).astype(str)

        if "furnished" in self.df.columns:
            self.df["furnished"] = _normalize_unknown_text(self.df["furnished"])

        if "laundry_category" in self.df.columns:
            self.df["laundry_category"] = _normalize_unknown_text(
                self.df["laundry_category"]
            )

    def dynamic_output_id(self, index: str) -> dict[str, str]:
        """
        Build the pattern-matching output id used by dynamic filter sections.

        Args:
            index: Logical filter name.

        Returns:
            The Dash id dictionary for the current page type.
        """
        return {"type": f"dynamic_output_div_{self.page_type}", "index": index}

    def map_center(self) -> tuple[float, float]:
        """
        Compute the average map center from the current geometry column.

        Returns:
            A ``(lat, lng)`` tuple for the initial map center.
        """
        return float(self.df.geometry.y.mean()), float(self.df.geometry.x.mean())

    def create_optional_layers_control(self) -> Optional[dl.LayersControl]:
        """
        Build the optional layers control when a page enables extra overlays.

        Returns:
            A configured ``LayersControl`` or ``None`` when unused.
        """
        if not self.OPTIONAL_LAYER_KEYS:
            return None

        return LayersClass.create_layers_control(
            page_key=self.page_type,
            layer_keys=self.OPTIONAL_LAYER_KEYS,
        )

    def return_geojson(self) -> dict:
        """
        Return a GeoJSON FeatureCollection for the current GeoDataFrame.
        Convert datetime-like columns to ISO strings.
        """
        gdf = self.df.copy()

        if "listed_date" in gdf.columns and pd.api.types.is_datetime64_any_dtype(
            gdf["listed_date"]
        ):
            gdf["listed_date"] = (
                gdf["listed_date"].dt.strftime("%Y-%m-%dT%H:%M:%S").fillna("")
            )

        if "latitude" in gdf.columns:
            gdf["latitude"] = gdf["latitude"].round(6)
        if "longitude" in gdf.columns:
            gdf["longitude"] = gdf["longitude"].round(6)

        for col in [
            "list_price",
            "ppsqft",
            "security_deposit",
            "pet_deposit",
            "key_deposit",
            "other_deposit",
            "hoa_fee",
            "space_rent",
        ]:
            if col in gdf.columns:
                gdf[col] = gdf[col].round(2)

        if {"best_dn", "best_up"}.issubset(gdf.columns):
            gdf[["best_dn", "best_up"]] = gdf[["best_dn", "best_up"]].replace(
                {np.nan: None}
            )

        geojson_str = gdf.to_json(drop_id=True)
        return json.loads(geojson_str)

    def _attach_isp_speeds(self, conn: sqlite3.Connection, table_name: str) -> None:
        """
        Join best available ISP speeds onto the listing dataframe.

        Args:
            conn: Open SQLite connection.
            table_name: Listing table currently being loaded.
        """
        if table_name not in {"lease", "buy"}:
            return

        safe_table = _require_safe_identifier(table_name, field_name="table_name")
        provider_table = {
            "lease": "lease_provider_options",
            "buy": "buy_provider_options",
        }.get(safe_table)
        if not provider_table:
            return

        provider_table = _require_safe_identifier(
            provider_table,
            field_name="provider_table",
        )
        try:
            speed_df = pd.read_sql_query(
                f"""
                SELECT
                    listing_id AS mls_number,
                    MAX(MaxAdDn) AS best_dn,
                    MAX(MaxAdUp) AS best_up
                FROM {provider_table}
                GROUP BY listing_id
                """,
                conn,
            )
        except sqlite3.Error as exc:
            logger.warning("Failed to load ISP speeds from %s: %s", provider_table, exc)
            self.df["best_dn"] = np.nan
            self.df["best_up"] = np.nan
            return

        if speed_df.empty:
            self.df["best_dn"] = np.nan
            self.df["best_up"] = np.nan
            return

        self.df = self.df.merge(speed_df, on="mls_number", how="left")

    def _attach_listing_enrichment(
        self,
        conn: sqlite3.Connection,
        table_name: str,
    ) -> None:
        """
        Join listing-level enrichment fields onto the current dataframe.

        Enrichment tables follow the convention ``<listing_table>_enrichment`` and
        must expose an ``mls_number`` join key. This keeps derived spatial/context
        fields out of the raw source tables while still letting page configs opt in
        to enrichment columns as needed.

        Args:
            conn: Open SQLite connection.
            table_name: Listing table currently being loaded.
        """
        if table_name not in {"lease", "buy"}:
            return

        enrichment_table = _require_safe_identifier(
            f"{table_name}_enrichment",
            field_name="enrichment_table",
        )
        if not _sqlite_table_exists(conn, enrichment_table):
            return

        enrichment_columns = _sqlite_table_columns(conn, enrichment_table)
        if "mls_number" not in enrichment_columns:
            logger.warning(
                "Skipping %s because it does not define an mls_number join key.",
                enrichment_table,
            )
            return

        selectable_columns = [
            "mls_number",
            *sorted(
                col
                for col in enrichment_columns
                if col != "mls_number" and col not in self.df.columns
            ),
        ]
        if len(selectable_columns) == 1:
            return

        try:
            enrichment_df = pd.read_sql_query(
                f"SELECT {', '.join(selectable_columns)} FROM {enrichment_table}",
                conn,
            )
        except sqlite3.Error as exc:
            logger.warning(
                "Failed to load listing enrichments from %s: %s",
                enrichment_table,
                exc,
            )
            return

        if enrichment_df.empty:
            return

        self.df = self.df.merge(enrichment_df, on="mls_number", how="left")

    def _safe_speed_max(self, column: str) -> float:
        """
        Return a safe slider maximum for an ISP speed column.

        Args:
            column: Dataframe column to inspect.

        Returns:
            A positive float suitable for a range-slider max value.
        """
        if column not in self.df.columns:
            return DEFAULT_SPEED_MAX

        max_value = pd.to_numeric(self.df[column], errors="coerce").max()
        if not np.isfinite(max_value) or max_value <= 0:
            return DEFAULT_SPEED_MAX
        return float(max_value)
