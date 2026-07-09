from dataclasses import dataclass
from typing import Any, Mapping, TypeAlias


FilterSection: TypeAlias = tuple[str, Any, str]
DashId: TypeAlias = str | dict[str, str]


@dataclass(frozen=True)
class PageConfig:
    """Static configuration used to assemble a listing page."""

    table_name: str
    page_type: str
    select_columns: tuple[str, ...]
    map_columns: tuple[str, ...]
    geojson_id: str
    title: str
    subtitle: str
    map_style: Mapping[str, str]
    active_filter_items: tuple[str, ...]
    accordion_class_name: str = "options-accordion"
    map_card_class_name: str | None = None
    map_body_class_name: str | None = None


@dataclass(frozen=True)
class PageParts:
    """Top-level cards consumed by the page layout modules."""

    title_card: Any
    user_options_card: Any
    map_card: Any
