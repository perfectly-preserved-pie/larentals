from dash import dcc, html
import dash_mantine_components as dmc
import numpy as np
import pandas as pd

from .component_base import (
    BaseClass,
    _build_cached_geojson_payload,
    _db_cache_token,
    categorize_laundry_features,
)
from .component_factories import (
    build_isp_speed_components,
    build_listed_date_filter,
    build_location_filter_components,
    build_location_suggestions,
    build_map,
    build_page_parts,
    build_range_filter,
    build_school_layer_filter_panel,
    build_school_layer_map_prompt,
    build_subtype_filter,
    build_year_built_filter,
    iqr_capped_range_bounds,
)
from .component_models import FilterSection, PageConfig, PageParts
from .responsive_filter_ui import build_map_filter_toolbar
from functions.distribution import attach_distribution
from functions.rso import add_rso_status_to_listing_geojson


class LeaseComponents(BaseClass):
    """Lease-specific component builder for the rentals page."""

    OPTIONAL_LAYER_KEYS: tuple[str, ...] = (
        "parking_tickets_density",
        "lahd_property_heatmap",
        "breakfast_burritos",
        "farmers_markets",
        "supermarkets_grocery",
        "alpr_cameras",
        "schools",
        "oil_well",
    )

    LEASE_COLUMNS: tuple[str, ...] = (
        "mls_number",
        "city",
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
        "parking_spaces",
        "laundry",
        "laundry_category",
        "pet_policy",
        "terms",
        "furnished",
        "phone_number",
        "security_deposit",
        "pet_deposit",
        "key_deposit",
        "other_deposit",
        "full_street_address",
        "listed_date",
        "listing_url",
        "mls_photo",
        "lot_size",
        "senior_community",
        "school_district_name",
        "nearest_high_school_mi",
    )

    LEASE_MAP_COLUMNS: tuple[str, ...] = (
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
        "parking_spaces",
        "laundry_category",
        "pet_policy",
        "terms",
        "furnished",
        "security_deposit",
        "pet_deposit",
        "key_deposit",
        "other_deposit",
        "full_street_address",
        "listed_date",
        "school_district_name",
        "nearest_high_school_mi",
    )

    CONFIG = PageConfig(
        table_name="lease",
        page_type="lease",
        select_columns=LEASE_COLUMNS,
        map_columns=LEASE_MAP_COLUMNS,
        geojson_id="lease_geojson",
        title="WhereToLive.LA",
        subtitle="An interactive map of available rentals in Los Angeles County. Updated weekly.",
        map_style={
            "width": "100%",
            "height": "100dvh",
            "margin": "0",
            "display": "block",
        },
        active_filter_items=(
            "location",
            "monthly_rent",
        ),
        accordion_class_name="options-accordion dmc",
        map_card_class_name="d-block d-md-block sticky-top dbc border-0 rounded-0",
        map_body_class_name="p-0 g-0 dbc",
    )

    @classmethod
    def get_cached_geojson_payload(cls) -> dict:
        """Return the cached lease GeoJSON payload for the current database version.

        Returns:
            A GeoJSON feature collection for the lease map store.
        """
        payload = _build_cached_geojson_payload(
            table_name=cls.CONFIG.table_name,
            page_type=cls.CONFIG.page_type,
            select_columns=cls.CONFIG.map_columns,
            db_mtime_ns=_db_cache_token(),
            categorize_lease_laundry=True,
        )
        return add_rso_status_to_listing_geojson(payload)

    def __init__(self) -> None:
        """Load lease data and assemble the top-level page cards.

        Returns:
            None.
        """
        super().__init__(
            table_name=self.CONFIG.table_name,
            page_type=self.CONFIG.page_type,
            select_columns=self.CONFIG.select_columns,
        )

        if "laundry" in self.df.columns:
            self.df["laundry"] = self.df["laundry"].apply(categorize_laundry_features)

        self.parts = self._build_page_parts()
        self.title_card = self.parts.title_card
        self.user_options_card = self.parts.user_options_card
        self.map_card = self.parts.map_card

    def _build_page_parts(self) -> PageParts:
        """Build the title, sidebar, and map cards for the lease page.

        Returns:
            The assembled ``PageParts`` bundle.
        """
        parts = build_page_parts(
            config=self.CONFIG,
            last_updated=self.last_updated,
            filter_items=self._build_filter_sections(),
            map_component=self._build_map_component(),
            map_overlay_children=[
                build_map_filter_toolbar(self.page_type),
                build_school_layer_map_prompt(self.page_type),
            ],
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
        """Build the lease map component with shared overlays and styles.

        Returns:
            The configured lease map component.
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
        """Build the accordion sections shown on the lease sidebar.

        Returns:
            Ordered filter-section tuples for the lease page.
        """
        return [
            (
                "Location",
                build_location_filter_components(
                    self.page_type,
                    build_location_suggestions(
                        self.df.get("city", []).tolist(),
                        self.df.get("zip_code", []).tolist(),
                    ),
                ),
                "location",
            ),
            ("Monthly Rent", self._build_rental_price_filter(), "monthly_rent"),
            ("Bedrooms", self._build_bedrooms_filter(), "bedrooms"),
            ("Bathrooms", self._build_bathrooms_filter(), "bathrooms"),
            ("Subtypes", self.create_subtype_checklist(), "subtypes"),
            ("Listed Date", self.create_listed_date_components(), "listed_date"),
            ("Square Footage", self._build_square_footage_filter(), "square_footage"),
            ("Pets", self.create_pets_radio_button(), "pet_policy"),
            ("Laundry", self.create_laundry_checklist(), "laundry"),
            ("Parking Spaces", self._build_parking_spaces_filter(), "parking_spaces"),
            ("Furnished", self.create_furnished_checklist(), "furnished"),
            ("Rent Control", self.create_rent_control_filter(), "rent_control"),
            ("Rental Terms", self.create_rental_terms_checklist(), "rental_terms"),
            (
                "Security deposit",
                [
                    self._create_deposit_filter(
                        title="",
                        column="security_deposit",
                        slider_id="security_deposit_slider",
                        dynamic_index="security_deposit",
                        component_id="security_deposit_div",
                    ),
                    # Key (19.5% coverage), other (5.6%) and pet (73.5%)
                    # deposits are too sparse to filter on without dropping most
                    # of the map. Still shown on the popup. Kept mounted and
                    # hidden at full range because the filter pipeline reads
                    # these ids positionally.
                    html.Div(
                        [
                            self._create_deposit_filter(
                                title="Key Deposit",
                                column="key_deposit",
                                slider_id="key_deposit_slider",
                                dynamic_index="key_deposit",
                                component_id="key_deposit_div",
                            ),
                            self._create_deposit_filter(
                                title="Other Deposit",
                                column="other_deposit",
                                slider_id="other_deposit_slider",
                                dynamic_index="other_deposit",
                                component_id="other_deposit_div",
                            ),
                            self._create_deposit_filter(
                                title="Pet Deposit",
                                column="pet_deposit",
                                slider_id="pet_deposit_slider",
                                dynamic_index="pet_deposit",
                                component_id="pet_deposit_div",
                            ),
                        ],
                        style={"display": "none"},
                    ),
                ],
                "deposits",
            ),
            ("Price Per Sqft", self._build_ppsqft_filter(), "ppsqft"),
            (
                "Internet speed",
                build_isp_speed_components(
                    download_tiers=self._speed_tiers("best_dn"),
                    upload_tiers=self._speed_tiers("best_up"),
                ),
                "isp_speed",
            ),
            ("Year Built", self.create_year_built_components(), "year_built"),
        ]

    def create_rent_control_filter(self) -> html.Div:
        """Build the mutually exclusive LA City rent-control status filter.

        Returns:
            A segmented control for the available coverage states.
        """
        return html.Div(
            [
                # The caveat is a footnote, not a heading, so it lives in hover
                # text rather than spending a permanent line in the sidebar.
                html.Div(
                    dmc.SegmentedControl(
                        id="rent_control_status",
                        value="any",
                        data=[
                            {"label": "Any", "value": "any"},
                            {"label": "All", "value": "all"},
                            {"label": "Some", "value": "some"},
                        ],
                        fullWidth=True,
                        size="xs",
                    ),
                    title="Rent control status is recorded for LA City only.",
                ),
            ]
        )

    def _build_rental_price_filter(self) -> html.Div:
        """Build the monthly-rent slider section.

        Returns:
            A rent filter ``Div``.
        """
        bounds = iqr_capped_range_bounds(self.df["list_price"], minimum=0, step=1)
        return build_range_filter(
            distribution=attach_distribution(
                slider_id="rental_price_slider",
                series=self.df["list_price"],
                minimum=bounds.minimum,
                maximum=bounds.display_maximum,
                prefix="$",
            ),
            slider_id="rental_price_slider",
            min_value=bounds.minimum,
            max_value=bounds.display_maximum,
            value=[bounds.minimum, bounds.display_maximum],
            component_id="rental_price_div",
            dynamic_id=self.dynamic_output_id("rental_price"),
            marks=bounds.marks(
                currency=True,
                include_open_end=False,
                target_intervals=3,
            ),
            container_style={"marginBottom": "10px"},
        )

    def _build_bedrooms_filter(self) -> html.Div:
        """Build the bedrooms slider section.

        Returns:
            A bedrooms filter ``Div``.
        """
        bounds = iqr_capped_range_bounds(self.df["bedrooms"], minimum=0, step=1)
        return build_range_filter(
            slider_id="bedrooms_slider",
            min_value=bounds.minimum,
            max_value=bounds.maximum,
            value=[bounds.minimum, bounds.maximum],
            component_id="bedrooms_div",
            dynamic_id=self.dynamic_output_id("bedrooms"),
            step=1,
            marks=bounds.marks(),
        )

    def _build_bathrooms_filter(self) -> html.Div:
        """Build the bathrooms slider section.

        Returns:
            A bathrooms filter ``Div``.
        """
        bounds = iqr_capped_range_bounds(
            self.df["total_bathrooms"], minimum=0, step=1
        )
        return build_range_filter(
            slider_id="bathrooms_slider",
            min_value=bounds.minimum,
            max_value=bounds.maximum,
            value=[bounds.minimum, bounds.maximum],
            component_id="bathrooms_div",
            dynamic_id=self.dynamic_output_id("bathrooms"),
            step=1,
            marks=bounds.marks(),
        )

    def _build_parking_spaces_filter(self) -> html.Div:
        """Build the parking-spaces slider section.

        Returns:
            A parking filter ``Div``.
        """
        bounds = iqr_capped_range_bounds(
            self.df["parking_spaces"], minimum=0, step=1
        )
        return build_range_filter(
            slider_id="garage_spaces_slider",
            min_value=bounds.minimum,
            max_value=bounds.maximum,
            value=[bounds.minimum, bounds.maximum],
            component_id="garage_spaces_div",
            dynamic_id=self.dynamic_output_id("garage_spaces"),
            step=1,
            marks=bounds.marks(),
            container_style={"marginBottom": "10px"},
        )

    def _build_ppsqft_filter(self) -> html.Div:
        """Build the price-per-square-foot slider section.

        Returns:
            A price-per-square-foot filter ``Div``.
        """
        bounds = iqr_capped_range_bounds(self.df["ppsqft"], minimum=0, step=1)
        return build_range_filter(
            slider_id="ppsqft_slider",
            min_value=bounds.minimum,
            max_value=bounds.display_maximum,
            value=[bounds.minimum, bounds.display_maximum],
            component_id="ppsqft_div",
            dynamic_id=self.dynamic_output_id("ppsqft"),
            marks=bounds.marks(
                currency=True,
                include_open_end=False,
                target_intervals=3,
            ),
            container_style={"marginBottom": "10px"},
        )

    def _build_square_footage_filter(self) -> html.Div:
        """Build the square-footage slider section.

        Returns:
            A square-footage filter ``Div``.
        """
        bounds = iqr_capped_range_bounds(self.df["sqft"], minimum=0, step=1)
        return build_range_filter(
            slider_id="sqft_slider",
            min_value=bounds.minimum,
            max_value=bounds.display_maximum,
            value=[bounds.minimum, bounds.display_maximum],
            component_id="square_footage_div",
            dynamic_id=self.dynamic_output_id("sqft"),
            marks=bounds.marks(
                include_open_end=False,
                target_intervals=3,
            ),
            switch_style={"marginTop": "15px"},
            container_style={"marginBottom": "10px"},
        )

    def _create_deposit_filter(
        self,
        *,
        title: str,
        column: str,
        slider_id: str,
        dynamic_index: str,
        component_id: str,
    ) -> html.Div:
        """Build a deposit slider section for one lease deposit field.

        Args:
            title: Visible section title.
            column: Dataframe column to inspect.
            slider_id: Dash id for the slider.
            dynamic_index: Pattern-matching id suffix for the content block.
            component_id: Outer container id.

        Returns:
            A deposit filter ``Div``.
        """
        bounds = iqr_capped_range_bounds(self.df[column], minimum=0, step=1)
        return build_range_filter(
            slider_id=slider_id,
            min_value=bounds.minimum,
            max_value=bounds.display_maximum,
            value=[bounds.minimum, bounds.display_maximum],
            component_id=component_id,
            dynamic_id=self.dynamic_output_id(dynamic_index),
            marks=bounds.marks(
                currency=True,
                include_open_end=False,
                target_intervals=3,
            ),
            container_style={"marginBottom": "10px"},
            header_children=[
                html.H5(
                    title,
                    style={"display": "inline-block", "marginRight": "10px"},
                )
            ],
        )

    def create_subtype_checklist(self) -> html.Div:
        """Build the subtype dropdown for lease listings.

        Returns:
            A subtype filter ``Div``.
        """
        subtype_series = (
            self.df["subtype"]
            .fillna("Unknown")
            .replace({None: "Unknown", "None": "Unknown"})
            .astype(str)
        )
        unique_subtypes = sorted(set(subtype_series.unique()))
        if "Unknown" not in unique_subtypes:
            unique_subtypes = sorted([*unique_subtypes, "Unknown"])

        return build_subtype_filter(
            values=unique_subtypes,
            dynamic_id=self.dynamic_output_id("subtype"),
            placeholder="Any type of home",
        )

    def create_pets_radio_button(self) -> html.Div:
        """Build the pet-policy radio controls.

        Returns:
            A pet-policy filter ``Div``.
        """
        return html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            dcc.RadioItems(
                                id="pets_radio",
                                options=[
                                    {"label": "Any", "value": "Both"},
                                    {"label": "Yes", "value": "yes"},
                                    {"label": "Maybe", "value": "maybe"},
                                ],
                                value="Both",
                                className="filter-inline-radio",
                                inline=True,
                            ),
                            title=(
                                "Yes: the listing says pets are welcome. "
                                "Maybe: anything that does not rule them out."
                            ),
                        ),
                    ],
                    id=self.dynamic_output_id("pets"),
                ),
            ],
            id="pet_policy_div",
        )

    def create_rental_terms_checklist(self) -> html.Div:
        """Build the rental-terms chip selector and unknown switch.

        Returns:
            A rental-terms filter ``Div``.
        """
        if isinstance(self.df["terms"].dtype, pd.CategoricalDtype):
            if "Unknown" not in self.df["terms"].cat.categories:
                self.df["terms"] = self.df["terms"].cat.add_categories("Unknown")

        terms_series = self.df["terms"].fillna("Unknown")
        unique_terms = pd.Series(
            [
                term.strip()
                for sublist in terms_series.str.split(",")
                if sublist
                for term in sublist
                if term and term.strip()
            ]
        ).unique()
        unique_terms = sorted([term for term in unique_terms if term != "Unknown"])

        term_abbreviations = {
            "12M": "12 Months",
            "24M": "24 Months",
            "6M": "6 Months",
            "DL": "Day-to-Day",
            "DR": "Deposit Required",
            "MO": "Month-to-Month",
            "NG": "Negotiable",
            "Other": "Other",
            "RO": "Renewal Options",
            "SN": "Seasonal",
            "STL": "Short Term Lease",
            "Unknown": "Unknown",
            "VR": "Vacation Rental",
            "WK": "Week-to-Week",
        }
        terms = {key: term_abbreviations.get(key, key) for key in unique_terms}

        rental_terms_checklist = html.Div(
            dcc.Dropdown(
                id="terms_checklist",
                multi=True,
                options=[
                    {"label": f"{terms[term]} ({term})", "value": term}
                    for term in unique_terms
                ],
                value=[],
                placeholder="Any rental term",
                searchable=True,
                clearable=True,
                closeOnSelect=False,
                maxHeight=360,
                labels={
                    "selected_count": "{num_selected} terms selected",
                    "select_all": "Select all",
                    "deselect_all": "Clear all",
                    "search": "Search terms",
                    "clear_selection": "Clear selected terms",
                    "no_options_found": "No terms found",
                },
            ),
            id=self.dynamic_output_id("rental_terms"),
        )

        return html.Div(
            [
                rental_terms_checklist,
            ],
            id="rental_terms_wrapper",
            style={"marginBottom": "10px"},
        )

    def create_furnished_checklist(self) -> html.Div:
        """Build the furnished-status filter.

        Returns:
            A furnished filter ``Div``.
        """
        furnished_options = ["Furnished", "Unfurnished"]

        return html.Div(
            [
                dcc.Checklist(
                    id="furnished_checklist",
                    options=[
                        {"label": label, "value": label}
                        for label in furnished_options
                    ],
                    value=[],
                    className="filter-chips",
                    inline=True,
                ),
            ],
            id="furnished_div",
        )

    def create_laundry_checklist(self) -> html.Div:
        """Build the laundry-category filter.

        Returns:
            A laundry filter ``Div``.
        """
        # Only the setups people actually search for. The full raw value still
        # shows on a listing's popup, so nothing is hidden, it is just not a
        # filter that would quietly drop most of the map.
        searchable = ("In Unit", "Shared", "Hookups")
        present = set(self.df["laundry"].fillna("Unknown").unique())
        laundry_options = [
            category for category in searchable if category in present
        ]

        return html.Div(
            [
                dcc.Checklist(
                    id="laundry_checklist",
                    options=[
                        {"label": category, "value": category}
                        for category in laundry_options
                    ],
                    value=[],
                    className="filter-chips",
                    inline=True,
                ),
            ],
            id=self.dynamic_output_id("laundry"),
        )

    def create_listed_date_components(self) -> html.Div:
        """Build the listed-date filter section for the lease page.

        Returns:
            A listed-date filter ``Div``.
        """
        return build_listed_date_filter(
            earliest_date=self.earliest_date,
            dynamic_id=self.dynamic_output_id("listed_date"),
            component_id="listed_date_div_lease",
        )

    def create_year_built_components(self) -> html.Div:
        """Build the year-built filter section for the lease page.

        Returns:
            A year-built filter ``Div``.
        """
        return build_year_built_filter(
            min_year=int(self.df["year_built"].min()),
            max_year=int(self.df["year_built"].max()),
            dynamic_id=self.dynamic_output_id("year_built"),
            component_id="year_built_div",
        )
