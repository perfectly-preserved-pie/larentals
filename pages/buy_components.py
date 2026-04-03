from dash import dcc, html
import dash_mantine_components as dmc
import numpy as np
import pandas as pd

from .component_base import BaseClass, _build_cached_geojson_payload, _db_cache_token
from .component_factories import (
    build_commute_filter_components,
    build_isp_speed_components,
    build_listed_date_filter,
    build_location_filter_components,
    build_map,
    build_page_parts,
    build_range_filter,
    build_school_layer_filter_panel,
    build_subtype_filter,
    build_year_built_filter,
)
from .component_models import FilterSection, PageConfig, PageParts


class BuyComponents(BaseClass):
    """Buy-specific component builder for the for-sale page."""

    OPTIONAL_LAYER_KEYS: tuple[str, ...] = (
        "parking_tickets_density",
        "breakfast_burritos",
        "farmers_markets",
        "supermarkets_grocery",
        "schools",
        "oil_well",
    )

    BUY_COLUMNS: tuple[str, ...] = (
        "mls_number",
        "latitude",
        "longitude",
        "zip_code",
        "subtype",
        "list_price",
        "bedrooms",
        "total_bathrooms",
        "sqft",
        "ppsqft",
        "year_built",
        "lot_size",
        "garage_spaces",
        "hoa_fee",
        "hoa_fee_frequency",
        "school_district_name",
        "nearest_high_school_mi",
        "full_street_address",
        "listed_date",
        "listing_url",
        "mls_photo",
    )

    BUY_MAP_COLUMNS: tuple[str, ...] = (
        "mls_number",
        "latitude",
        "longitude",
        "subtype",
        "list_price",
        "bedrooms",
        "total_bathrooms",
        "sqft",
        "ppsqft",
        "year_built",
        "lot_size",
        "garage_spaces",
        "hoa_fee",
        "hoa_fee_frequency",
        "school_district_name",
        "nearest_high_school_mi",
        "listed_date",
    )

    CONFIG = PageConfig(
        table_name="buy",
        page_type="buy",
        select_columns=BUY_COLUMNS,
        map_columns=BUY_MAP_COLUMNS,
        geojson_id="buy_geojson",
        title="WhereToLive.LA",
        subtitle="An interactive map of available residential properties for sale in Los Angeles County. Updated weekly.",
        map_style={
            "width": "100%",
            "height": "90vh",
            "margin": "auto",
            "display": "inline-block",
        },
        active_filter_items=(
            "listed_date",
            "location",
            "subtypes",
            "list_price",
            "bedrooms",
            "bathrooms",
        ),
        accordion_class_name="options-accordion",
        map_card_class_name="d-block d-md-block sticky-top",
    )

    @classmethod
    def get_cached_geojson_payload(cls) -> dict:
        """
        Return the cached buy GeoJSON payload for the current database version.

        Returns:
            A GeoJSON feature collection for the buy map store.
        """
        return _build_cached_geojson_payload(
            table_name=cls.CONFIG.table_name,
            page_type=cls.CONFIG.page_type,
            select_columns=cls.CONFIG.map_columns,
            db_mtime_ns=_db_cache_token(),
        )

    def __init__(self) -> None:
        """
        Load buy data and assemble the top-level page cards.
        """
        super().__init__(
            table_name=self.CONFIG.table_name,
            page_type=self.CONFIG.page_type,
            select_columns=self.CONFIG.select_columns,
        )

        self.parts = self._build_page_parts()
        self.title_card = self.parts.title_card
        self.user_options_card = self.parts.user_options_card
        self.map_card = self.parts.map_card

    def _build_page_parts(self) -> PageParts:
        """
        Build the title, sidebar, and map cards for the buy page.

        Returns:
            The assembled ``PageParts`` bundle.
        """
        parts = build_page_parts(
            config=self.CONFIG,
            last_updated=self.last_updated,
            filter_items=self._build_filter_sections(),
            map_component=self._build_map_component(),
        )
        return PageParts(
            title_card=parts.title_card,
            user_options_card=html.Div(
                [
                    parts.user_options_card,
                    build_school_layer_filter_panel(self.page_type),
                ]
            ),
            map_card=parts.map_card,
        )

    def _build_map_component(self) -> object:
        """
        Build the buy map component with shared overlays and styles.

        Returns:
            The configured buy map component.
        """
        center_lat, center_lng = self.map_center()
        return build_map(
            page_type=self.page_type,
            geojson_id=self.CONFIG.geojson_id,
            center_lat=center_lat,
            center_lng=center_lng,
            layers_control=self.create_optional_layers_control(),
            map_style=dict(self.CONFIG.map_style),
        )

    def _build_filter_sections(self) -> list[FilterSection]:
        """
        Build the accordion sections shown on the buy sidebar.

        Returns:
            Ordered filter-section tuples for the buy page.
        """
        return [
            ("Listed Date", self.create_listed_date_components(), "listed_date"),
            ("Location", build_location_filter_components(self.page_type), "location"),
            ("Subtypes", self.create_subtype_checklist(), "subtypes"),
            ("List Price", self._build_list_price_filter(), "list_price"),
            ("Bedrooms", self._build_bedrooms_filter(), "bedrooms"),
            ("Bathrooms", self._build_bathrooms_filter(), "bathrooms"),
            ("HOA Fees", self.create_hoa_fee_components(), "hoa_fees"),
            (
                "HOA Fee Frequency",
                self.create_hoa_fee_frequency_checklist(),
                "hoa_fee_frequency",
            ),
            (
                "Internet Service Provider (ISP) Speed",
                build_isp_speed_components(
                    max_download=self._safe_speed_max("best_dn"),
                    max_upload=self._safe_speed_max("best_up"),
                ),
                "isp_speed",
            ),
            (
                "Commute (EXPERIMENTAL)",
                build_commute_filter_components(self.page_type),
                "commute",
            ),
            ("Lot Size", self.create_lot_size_components(), "lot_size"),
            ("Price Per Sqft", self._build_ppsqft_filter(), "ppsqft"),
            ("Square Footage", self._build_square_footage_filter(), "square_footage"),
            ("Year Built", self.create_year_built_components(), "year_built"),
        ]

    def _build_list_price_filter(self) -> html.Div:
        """
        Build the list-price slider section.

        Returns:
            A list-price filter ``Div``.
        """
        return build_range_filter(
            slider_id="list_price_slider",
            min_value=self.df["list_price"].min(),
            max_value=self.df["list_price"].max(),
            value=[0, self.df["list_price"].max()],
            component_id="list_price_div_buy",
            dynamic_id=self.dynamic_output_id("list_price"),
            tooltip_transform="formatCurrency",
            container_style={"marginBottom": "10px"},
        )

    def _build_bedrooms_filter(self) -> html.Div:
        """
        Build the bedrooms slider section.

        Returns:
            A bedrooms filter ``Div``.
        """
        return build_range_filter(
            slider_id="bedrooms_slider",
            min_value=0,
            max_value=self.df["bedrooms"].max(),
            value=[0, self.df["bedrooms"].max()],
            component_id="bedrooms_div_buy",
            dynamic_id=self.dynamic_output_id("bedrooms"),
            step=1,
        )

    def _build_bathrooms_filter(self) -> html.Div:
        """
        Build the bathrooms slider section.

        Returns:
            A bathrooms filter ``Div``.
        """
        return build_range_filter(
            slider_id="bathrooms_slider",
            min_value=0,
            max_value=self.df["total_bathrooms"].max(),
            value=[0, self.df["total_bathrooms"].max()],
            component_id="bathrooms_div_buy",
            dynamic_id=self.dynamic_output_id("bathrooms"),
            step=1,
        )

    def _build_ppsqft_filter(self) -> html.Div:
        """
        Build the price-per-square-foot slider section.

        Returns:
            A price-per-square-foot filter ``Div``.
        """
        return build_range_filter(
            slider_id="ppsqft_slider",
            min_value=self.df["ppsqft"].min(),
            max_value=self.df["ppsqft"].max(),
            value=[self.df["ppsqft"].min(), self.df["ppsqft"].max()],
            component_id="ppsqft_div",
            dynamic_id=self.dynamic_output_id("ppsqft"),
            tooltip_transform="formatCurrency",
            include_missing_switch_id="ppsqft_missing_switch",
            include_missing_switch_label="Include properties with an unknown price per square foot",
            container_style={"marginBottom": "10px"},
        )

    def _build_square_footage_filter(self) -> html.Div:
        """
        Build the square-footage slider section.

        Returns:
            A square-footage filter ``Div``.
        """
        return build_range_filter(
            slider_id="sqft_slider",
            min_value=self.df["sqft"].min(),
            max_value=self.df["sqft"].max(),
            value=[self.df["sqft"].min(), self.df["sqft"].max()],
            component_id="square_footage_div",
            dynamic_id=self.dynamic_output_id("sqft"),
            tooltip_transform="formatSqFt",
            include_missing_switch_id="sqft_missing_switch",
            include_missing_switch_label="Include properties with an unknown square footage",
            container_style={"marginBottom": "10px"},
        )

    def create_subtype_checklist(self) -> html.Div:
        """
        Build the subtype dropdown for buy listings.

        Returns:
            A subtype filter ``Div``.
        """
        unique_subtypes = sorted(
            {
                subtype if pd.notna(subtype) else "Unknown"
                for subtype in self.df["subtype"].unique()
            }
        )

        return build_subtype_filter(
            values=unique_subtypes,
            dynamic_id=self.dynamic_output_id("subtype"),
            placeholder="Type of home (e.g. Condominium, Single Family Residence, Townhouse)",
            outer_id="subtypes_div_buy",
            dropdown_style={"marginBottom": "10px"},
        )

    def create_lot_size_components(self) -> html.Div:
        """
        Build the lot-size slider section.

        Returns:
            A lot-size filter ``Div``.
        """
        lot_sizes = self.df["lot_size"]
        has_values = lot_sizes.notna().any()

        lot_min = float(np.nanmin(lot_sizes)) if has_values else 0.0
        lot_max = float(np.nanmax(lot_sizes)) if has_values else 1.0

        if not np.isfinite(lot_min):
            lot_min = 0.0
        if not np.isfinite(lot_max) or lot_max < lot_min:
            lot_max = max(lot_min, 1.0)

        return build_range_filter(
            slider_id="lot_size_slider",
            min_value=lot_min,
            max_value=lot_max,
            value=[lot_min, lot_max],
            component_id="lot_size_div_buy",
            dynamic_id=self.dynamic_output_id("lot_size"),
            tooltip_transform="formatSqFt",
            include_missing_switch_id="lot_size_missing_switch",
            include_missing_switch_label="Include properties with an unknown lot size",
            container_style={"marginBottom": "10px"},
        )

    def create_hoa_fee_components(self) -> html.Div:
        """
        Build the HOA-fee slider section.

        Returns:
            An HOA-fee filter ``Div``.
        """
        num_steps = 5
        span = self.df["hoa_fee"].max() - self.df["hoa_fee"].min()
        if not np.isfinite(span) or span <= 0:
            step_value = 1
        else:
            rough_step = span / num_steps
            step_value = np.round(rough_step, -int(np.floor(np.log10(rough_step))))

        return build_range_filter(
            slider_id="hoa_fee_slider",
            min_value=self.df["hoa_fee"].min(),
            max_value=self.df["hoa_fee"].max(),
            value=[self.df["hoa_fee"].min(), self.df["hoa_fee"].max()],
            component_id="hoa_fee_div_buy",
            dynamic_id=self.dynamic_output_id("hoa_fee"),
            tooltip_transform="formatCurrency",
            include_missing_switch_id="hoa_fee_missing_switch",
            include_missing_switch_label="Include properties with an unknown HOA fee",
            container_style={"marginBottom": "10px"},
            step=step_value,
            header_children=[
                html.H6(
                    [html.Em("Applies only to SFR and CONDO/TWNHS.")],
                    style={"display": "inline-block", "marginRight": "10px"},
                )
            ],
        )

    def create_hoa_fee_frequency_checklist(self) -> html.Div:
        """
        Build the HOA-frequency chip selector.

        Returns:
            An HOA-frequency filter ``Div``.
        """
        return html.Div(
            dmc.ChipGroup(
                id="hoa_fee_frequency_checklist",
                multiple=True,
                value=["N/A", "Monthly"],
                children=[
                    dmc.Chip(children="N/A", value="N/A", radius="sm"),
                    dmc.Chip(children="Monthly", value="Monthly", radius="sm"),
                ],
            ),
            id=self.dynamic_output_id("hoa_fee_frequency"),
            className="d-flex flex-wrap gap-2",
        )

    def create_listed_date_components(self) -> html.Div:
        """
        Build the listed-date filter section for the buy page.

        Returns:
            A listed-date filter ``Div``.
        """
        return build_listed_date_filter(
            earliest_date=self.earliest_date,
            dynamic_id=self.dynamic_output_id("listed_date"),
            datepicker_id="listed_date_datepicker_buy",
            component_id="listed_date_div_buy",
        )

    def create_year_built_components(self) -> html.Div:
        """
        Build the year-built filter section for the buy page.

        Returns:
            A year-built filter ``Div``.
        """
        return build_year_built_filter(
            min_year=int(self.df["year_built"].min()),
            max_year=int(self.df["year_built"].max()),
            dynamic_id=self.dynamic_output_id("year_built"),
            component_id="yrbuilt_div_buy",
        )
