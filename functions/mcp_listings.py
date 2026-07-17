"""Provide curated MCP search tools for lease and for-sale listings.

The module keeps database access read-only and response sizes bounded.
"""

from __future__ import annotations

from contextlib import closing
from datetime import date
from math import ceil
from pathlib import Path
from functions.data_paths import LARENTALS_DB_PATH
import sqlite3
from typing import Any, Literal, TypeAlias, TypedDict

from dash.mcp import configure_mcp_server, mcp_enabled


DEFAULT_DB_PATH: Path = LARENTALS_DB_PATH
MAX_PAGE_SIZE: int = 20

ListingType: TypeAlias = Literal["lease", "buy"]
PriceDescription: TypeAlias = Literal["monthly_rent", "sale_price"]
SortOrder: TypeAlias = Literal[
    "newest",
    "price_low_to_high",
    "price_high_to_low",
    "most_bedrooms",
    "largest",
]


class LeaseDetails(TypedDict):
    """Describe fields that apply only to lease listings.

    These values are nested under ``lease_details`` in MCP results.
    """

    parking_spaces: int | None
    laundry: str | None
    pet_policy: str | None
    lease_terms: str | None
    furnished: str | None
    security_deposit: int | None
    pet_deposit: int | None


class SaleDetails(TypedDict):
    """Describe fields that apply only to for-sale listings.

    These values are nested under ``sale_details`` in MCP results.
    """

    lot_size_square_feet: float | None
    garage_spaces: float | None
    hoa_fee: float | None
    hoa_fee_frequency: str | None
    space_rent: float | None
    park_name: str | None
    pets_allowed: str | None
    senior_community: str | None


class Listing(TypedDict):
    """Represent one normalized lease or for-sale search result.

    Mode-specific values are kept in one of the two detail mappings.
    """

    listing_type: ListingType
    mls_number: str | None
    address: str | None
    city: str | None
    zip_code: str | None
    property_type: str | None
    price: int | None
    price_description: PriceDescription
    bedrooms: int | None
    bathrooms: float | None
    square_feet: int | None
    price_per_square_foot: float | None
    year_built: int | None
    listed_date: str | None
    listing_url: str | None
    latitude: float | None
    longitude: float | None
    lease_details: LeaseDetails | None
    sale_details: SaleDetails | None


class ListingSearchResult(TypedDict):
    """Represent a page returned by :func:`search_listings`.

    Pagination metadata lets MCP clients request subsequent result pages.
    """

    summary: str
    listing_type: ListingType
    data_as_of: str | None
    total_results: int
    page: int
    page_size: int
    total_pages: int
    has_next_page: bool
    applied_filters: dict[str, Any]
    listings: list[Listing]


_COMMON_SELECT: str = """
    mls_number,
    full_street_address AS address,
    city,
    zip_code,
    subtype AS property_type,
    CAST(NULLIF(TRIM(CAST(list_price AS TEXT)), '') AS INTEGER) AS price,
    CAST(NULLIF(TRIM(CAST(bedrooms AS TEXT)), '') AS INTEGER) AS bedrooms,
    CAST(NULLIF(TRIM(CAST(total_bathrooms AS TEXT)), '') AS REAL) AS bathrooms,
    CAST(NULLIF(TRIM(CAST(sqft AS TEXT)), '') AS INTEGER) AS square_feet,
    CAST(NULLIF(TRIM(CAST(ppsqft AS TEXT)), '') AS REAL) AS price_per_square_foot,
    CAST(NULLIF(TRIM(CAST(year_built AS TEXT)), '') AS INTEGER) AS year_built,
    DATE(listed_date) AS listed_date,
    listing_url,
    latitude,
    longitude
"""

_SELECT_SQL: dict[ListingType, str] = {
    "lease": _COMMON_SELECT
    + """,
    CAST(NULLIF(TRIM(CAST(parking_spaces AS TEXT)), '') AS INTEGER) AS parking_spaces,
    COALESCE(NULLIF(TRIM(laundry_category), ''), 'Unknown') AS laundry,
    pet_policy,
    terms AS lease_terms,
    furnished,
    CAST(NULLIF(TRIM(CAST(security_deposit AS TEXT)), '') AS INTEGER) AS security_deposit,
    CAST(NULLIF(TRIM(CAST(pet_deposit AS TEXT)), '') AS INTEGER) AS pet_deposit
    """,
    "buy": _COMMON_SELECT
    + """,
    CAST(NULLIF(TRIM(CAST(lot_size AS TEXT)), '') AS REAL) AS lot_size_square_feet,
    CAST(NULLIF(TRIM(CAST(garage_spaces AS TEXT)), '') AS REAL) AS garage_spaces,
    CAST(NULLIF(TRIM(CAST(hoa_fee AS TEXT)), '') AS REAL) AS hoa_fee,
    NULLIF(TRIM(hoa_fee_frequency), '') AS hoa_fee_frequency,
    CAST(NULLIF(TRIM(CAST(space_rent AS TEXT)), '') AS REAL) AS space_rent,
    NULLIF(TRIM(park_name), '') AS park_name,
    NULLIF(TRIM(pets_allowed), '') AS pets_allowed,
    NULLIF(TRIM(senior_community), '') AS senior_community
    """,
}

_PRICE_SQL: str = "CAST(NULLIF(TRIM(CAST(list_price AS TEXT)), '') AS REAL)"
_BEDROOMS_SQL: str = "CAST(NULLIF(TRIM(CAST(bedrooms AS TEXT)), '') AS REAL)"
_BATHROOMS_SQL: str = "CAST(NULLIF(TRIM(CAST(total_bathrooms AS TEXT)), '') AS REAL)"
_SQFT_SQL: str = "CAST(NULLIF(TRIM(CAST(sqft AS TEXT)), '') AS REAL)"
_LOT_SIZE_SQL: str = "CAST(NULLIF(TRIM(CAST(lot_size AS TEXT)), '') AS REAL)"
_HOA_FEE_SQL: str = "CAST(NULLIF(TRIM(CAST(hoa_fee AS TEXT)), '') AS REAL)"

_SORT_SQL: dict[SortOrder, str] = {
    "newest": "DATE(listed_date) DESC, mls_number ASC",
    "price_low_to_high": f"{_PRICE_SQL} ASC, DATE(listed_date) DESC, mls_number ASC",
    "price_high_to_low": f"{_PRICE_SQL} DESC, DATE(listed_date) DESC, mls_number ASC",
    "most_bedrooms": f"{_BEDROOMS_SQL} DESC, {_PRICE_SQL} ASC, mls_number ASC",
    "largest": f"{_SQFT_SQL} DESC, {_PRICE_SQL} ASC, mls_number ASC",
}


def configure_listings_mcp() -> None:
    """Configure Dash to expose only curated listing tools.

    Layout resources and raw callback tools are intentionally disabled.
    """
    configure_mcp_server(
        include_layout=False,
        include_callbacks=False,
        include_clientside_callbacks=False,
        include_pages=False,
        expose_callback_docstrings=True,
    )


def _optional_text(value: str | None, *, field_name: str) -> str | None:
    """Normalize an optional text filter and enforce its size limit.

    Empty strings become ``None`` so they do not add SQL predicates.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or null")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 100:
        raise ValueError(f"{field_name} must be 100 characters or fewer")
    return normalized


def _validate_iso_date(value: str | None) -> str | None:
    """Validate an optional ISO date used by the listing-date filter.

    The normalized ``YYYY-MM-DD`` value is returned unchanged.
    """
    normalized = _optional_text(value, field_name="listed_after")
    if normalized is None:
        return None
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("listed_after must use YYYY-MM-DD format") from exc
    return normalized


def _validate_non_negative(value: int | None, *, field_name: str) -> None:
    """Validate an optional integer filter that cannot be negative.

    Booleans are rejected even though they are integer subclasses in Python.
    """
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value < 0
    ):
        raise ValueError(f"{field_name} must be a non-negative integer")


def _connect_read_only(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite database connection that cannot perform writes.

    Rows are exposed by column name to simplify response normalization.
    """
    resolved_path = Path(db_path).resolve()
    connection = sqlite3.connect(f"file:{resolved_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _like_pattern(value: str) -> str:
    """Build a literal substring pattern for a SQL ``LIKE`` clause.

    User-provided wildcard characters are escaped before wrapping the value.
    """
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _normalize_zip_code(value: Any) -> str | None:
    """Normalize ZIP codes loaded from mixed SQLite column types.

    Spreadsheet-derived values such as ``91101.0`` become ``91101``.
    """
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized[:-2] if normalized.endswith(".0") else normalized


def _listing_from_row(row: sqlite3.Row, listing_type: ListingType) -> Listing:
    """Convert one database row into the public MCP listing shape.

    Only the detail mapping appropriate to ``listing_type`` is populated.
    """
    values: dict[str, Any] = dict(row)
    lease_details: LeaseDetails | None
    sale_details: SaleDetails | None
    price_description: PriceDescription

    if listing_type == "lease":
        lease_details = LeaseDetails(
            parking_spaces=values["parking_spaces"],
            laundry=values["laundry"],
            pet_policy=values["pet_policy"],
            lease_terms=values["lease_terms"],
            furnished=values["furnished"],
            security_deposit=values["security_deposit"],
            pet_deposit=values["pet_deposit"],
        )
        sale_details = None
        price_description = "monthly_rent"
    else:
        lease_details = None
        sale_details = SaleDetails(
            lot_size_square_feet=values["lot_size_square_feet"],
            garage_spaces=values["garage_spaces"],
            hoa_fee=values["hoa_fee"],
            hoa_fee_frequency=values["hoa_fee_frequency"],
            space_rent=values["space_rent"],
            park_name=values["park_name"],
            pets_allowed=values["pets_allowed"],
            senior_community=values["senior_community"],
        )
        price_description = "sale_price"

    return Listing(
        listing_type=listing_type,
        mls_number=values["mls_number"],
        address=values["address"],
        city=values["city"],
        zip_code=_normalize_zip_code(values["zip_code"]),
        property_type=values["property_type"],
        price=values["price"],
        price_description=price_description,
        bedrooms=values["bedrooms"],
        bathrooms=values["bathrooms"],
        square_feet=values["square_feet"],
        price_per_square_foot=values["price_per_square_foot"],
        year_built=values["year_built"],
        listed_date=values["listed_date"],
        listing_url=values["listing_url"],
        latitude=values["latitude"],
        longitude=values["longitude"],
        lease_details=lease_details,
        sale_details=sale_details,
    )


def search_listings_in_database(
    db_path: str | Path,
    *,
    listing_type: ListingType,
    location: str | None = None,
    property_type: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_bedrooms: int | None = None,
    min_bathrooms: int | None = None,
    min_square_feet: int | None = None,
    pet_friendly: bool | None = None,
    furnished: bool | None = None,
    min_lot_size: int | None = None,
    max_hoa_fee: int | None = None,
    senior_community: bool | None = None,
    listed_after: str | None = None,
    sort: SortOrder = "newest",
    page: int = 1,
    page_size: int = 10,
) -> ListingSearchResult:
    """Query one listing table with validated, parameterized filters.

    Results are normalized into a shared schema and capped by pagination.
    """
    if listing_type not in ("lease", "buy"):
        raise ValueError("listing_type must be either lease or buy")

    location = _optional_text(location, field_name="location")
    property_type = _optional_text(property_type, field_name="property_type")
    listed_after = _validate_iso_date(listed_after)

    for field_name, value in (
        ("min_price", min_price),
        ("max_price", max_price),
        ("min_bedrooms", min_bedrooms),
        ("min_bathrooms", min_bathrooms),
        ("min_square_feet", min_square_feet),
        ("min_lot_size", min_lot_size),
        ("max_hoa_fee", max_hoa_fee),
    ):
        _validate_non_negative(value, field_name=field_name)

    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError("min_price cannot be greater than max_price")
    if listing_type == "lease" and any(
        value is not None for value in (min_lot_size, max_hoa_fee, senior_community)
    ):
        raise ValueError(
            "min_lot_size, max_hoa_fee, and senior_community are only supported for buy listings"
        )
    if listing_type == "buy" and furnished is not None:
        raise ValueError("furnished is only supported for lease listings")
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 10_000:
        raise ValueError("page must be between 1 and 10000")
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= MAX_PAGE_SIZE
    ):
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    if sort not in _SORT_SQL:
        raise ValueError(f"sort must be one of: {', '.join(_SORT_SQL)}")
    for field_name, value in (
        ("pet_friendly", pet_friendly),
        ("furnished", furnished),
        ("senior_community", senior_community),
    ):
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{field_name} must be true, false, or null")

    where: list[str] = ["1 = 1"]
    params: list[Any] = []

    if location:
        where.append(
            "(LOWER(COALESCE(city, '')) LIKE LOWER(?) ESCAPE '\\' "
            "OR LOWER(COALESCE(zip_code, '')) LIKE LOWER(?) ESCAPE '\\' "
            "OR LOWER(COALESCE(full_street_address, '')) LIKE LOWER(?) ESCAPE '\\')"
        )
        params.extend([_like_pattern(location)] * 3)
    if property_type:
        where.append("LOWER(COALESCE(subtype, '')) = LOWER(?)")
        params.append(property_type)
    if min_price is not None:
        where.append(f"{_PRICE_SQL} >= ?")
        params.append(min_price)
    if max_price is not None:
        where.append(f"{_PRICE_SQL} <= ?")
        params.append(max_price)
    if min_bedrooms is not None:
        where.append(f"{_BEDROOMS_SQL} >= ?")
        params.append(min_bedrooms)
    if min_bathrooms is not None:
        where.append(f"{_BATHROOMS_SQL} >= ?")
        params.append(min_bathrooms)
    if min_square_feet is not None:
        where.append(f"{_SQFT_SQL} >= ?")
        params.append(min_square_feet)
    if listed_after:
        where.append("DATE(listed_date) >= DATE(?)")
        params.append(listed_after)

    if listing_type == "lease":
        if pet_friendly is True:
            where.append(
                "(LOWER(COALESCE(pet_policy, '')) LIKE '%yes%' "
                "OR LOWER(COALESCE(pet_policy, '')) LIKE '%cats ok%' "
                "OR LOWER(COALESCE(pet_policy, '')) LIKE '%dogs ok%') "
                "AND LOWER(COALESCE(pet_policy, '')) NOT LIKE '%no%'"
            )
        elif pet_friendly is False:
            where.append("LOWER(TRIM(COALESCE(pet_policy, ''))) = 'no'")
        if furnished is True:
            where.append(
                "LOWER(TRIM(COALESCE(furnished, ''))) IN ('furnished', 'both', 'partially')"
            )
        elif furnished is False:
            where.append("LOWER(TRIM(COALESCE(furnished, ''))) = 'unfurnished'")
    else:
        if pet_friendly is True:
            where.append("LOWER(TRIM(COALESCE(pets_allowed, ''))) IN ('yes', 'y', 'true', '1')")
        elif pet_friendly is False:
            where.append("LOWER(TRIM(COALESCE(pets_allowed, ''))) IN ('no', 'n', 'false', '0')")
        if min_lot_size is not None:
            where.append(f"{_LOT_SIZE_SQL} >= ?")
            params.append(min_lot_size)
        if max_hoa_fee is not None:
            where.append(f"{_HOA_FEE_SQL} <= ?")
            params.append(max_hoa_fee)
        if senior_community is True:
            where.append(
                "LOWER(TRIM(COALESCE(senior_community, ''))) IN ('yes', 'y', 'true', '1')"
            )
        elif senior_community is False:
            where.append(
                "LOWER(TRIM(COALESCE(senior_community, ''))) IN ('no', 'n', 'false', '0')"
            )

    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size
    table_name = listing_type

    with closing(_connect_read_only(db_path)) as connection:
        total_results = int(
            connection.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE {where_sql}",  # noqa: S608
                params,
            ).fetchone()[0]
        )
        rows: list[sqlite3.Row] = connection.execute(
            f"""
            SELECT {_SELECT_SQL[listing_type]}
            FROM {table_name}
            WHERE {where_sql}
            ORDER BY {_SORT_SQL[sort]}
            LIMIT ? OFFSET ?
            """,  # noqa: S608
            [*params, page_size, offset],
        ).fetchall()
        freshness_row: sqlite3.Row | None = connection.execute(
            f"SELECT MAX(DATE(date_processed)) FROM {table_name}"  # noqa: S608
        ).fetchone()

    total_pages: int = ceil(total_results / page_size) if total_results else 0
    listings: list[Listing] = [_listing_from_row(row, listing_type) for row in rows]
    applied_filters: dict[str, Any] = {
        key: value
        for key, value in {
            "listing_type": listing_type,
            "location": location,
            "property_type": property_type,
            "min_price": min_price,
            "max_price": max_price,
            "min_bedrooms": min_bedrooms,
            "min_bathrooms": min_bathrooms,
            "min_square_feet": min_square_feet,
            "pet_friendly": pet_friendly,
            "furnished": furnished,
            "min_lot_size": min_lot_size,
            "max_hoa_fee": max_hoa_fee,
            "senior_community": senior_community,
            "listed_after": listed_after,
            "sort": sort,
        }.items()
        if value is not None
    }

    listing_label: str = "lease" if listing_type == "lease" else "for-sale"
    return ListingSearchResult(
        summary=(
            f"Found {total_results} matching {listing_label} listing"
            f"{'s' if total_results != 1 else ''}; returning page {page} "
            f"with {len(listings)} listing{'s' if len(listings) != 1 else ''}."
        ),
        listing_type=listing_type,
        data_as_of=freshness_row[0] if freshness_row else None,
        total_results=total_results,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next_page=page < total_pages,
        applied_filters=applied_filters,
        listings=listings,
    )


@mcp_enabled(name="search_listings", expose_docstring=True)
def search_listings(
    listing_type: ListingType,
    location: str | None = None,
    property_type: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_bedrooms: int | None = None,
    min_bathrooms: int | None = None,
    min_square_feet: int | None = None,
    pet_friendly: bool | None = None,
    furnished: bool | None = None,
    min_lot_size: int | None = None,
    max_hoa_fee: int | None = None,
    senior_community: bool | None = None,
    listed_after: str | None = None,
    sort: SortOrder = "newest",
    page: int = 1,
    page_size: int = 10,
) -> ListingSearchResult:
    """Search current Los Angeles-area lease or for-sale listings.

    Set ``listing_type`` to ``lease`` for rentals or ``buy`` for properties for
    sale. Results are read-only, sorted, and paginated, with address, price,
    property details, listing date, location, and source URL.

    Use ``location`` for a city, ZIP code, neighborhood, or address fragment.
    ``min_price`` and ``max_price`` mean monthly rent for lease searches and
    sale price for buy searches. ``furnished`` is lease-only. ``min_lot_size``,
    ``max_hoa_fee``, and ``senior_community`` are buy-only. ``listed_after``
    must use YYYY-MM-DD. At most 20 listings are returned per call; request the
    next page when ``has_next_page`` is true.
    """
    return search_listings_in_database(
        DEFAULT_DB_PATH,
        listing_type=listing_type,
        location=location,
        property_type=property_type,
        min_price=min_price,
        max_price=max_price,
        min_bedrooms=min_bedrooms,
        min_bathrooms=min_bathrooms,
        min_square_feet=min_square_feet,
        pet_friendly=pet_friendly,
        furnished=furnished,
        min_lot_size=min_lot_size,
        max_hoa_fee=max_hoa_fee,
        senior_community=senior_community,
        listed_after=listed_after,
        sort=sort,
        page=page,
        page_size=page_size,
    )
