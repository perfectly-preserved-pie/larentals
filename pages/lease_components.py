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
    build_fire_hazard_layer_legend,
    build_isp_speed_components,
    build_listed_date_filter,
    build_location_filter_components,
    build_map,
    build_map_gesture_control,
    build_page_parts,
    build_range_filter,
    build_school_layer_filter_panel,
    build_school_layer_map_prompt,
    build_subtype_filter,
    build_year_built_filter,
)
from .component_models import FilterSection, PageConfig, PageParts


class LeaseComponents(BaseClass):
    """Lease-specific component builder for the rentals page."""

    OPTIONAL_LAYER_KEYS: tuple[str, ...] = (
        "parking_tickets_density",
        "breakfast_burritos",
        "farmers_markets",
        "supermarkets_grocery",
        "schools",
        "fire_hazard_zones",
        "oil_well",
    )

    LEASE_COLUMNS: tuple[str, ...] = (
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
        "fire_hazard_severity",
        "fire_hazard_responsibility_area",
        "fire_hazard_rollout_phase",
        "fire_hazard_effective_date",
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
        "listed_date",
        "school_district_name",
        "nearest_high_school_mi",
        "fire_hazard_severity",
        "fire_hazard_responsibility_area",
        "fire_hazard_rollout_phase",
        "fire_hazard_effective_date",
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
            "height": "100vh",
            "margin": "0",
            "display": "block",
        },
        active_filter_items=(
            "listed_date",
            "location",
            "fire_hazard",
            "subtypes",
            "monthly_rent",
            "bedrooms",
            "bathrooms",
            "pet_policy",
        ),
        accordion_class_name="options-accordion dmc",
        map_card_class_name="d-block d-md-block sticky-top dbc",
        map_body_class_name="p-2 g-0 dbc",
    )

    @classmethod
    def get_cached_geojson_payload(cls) -> dict:
        """
        Return the cached lease GeoJSON payload for the current database version.

        Returns:
            A GeoJSON feature collection for the lease map store.
        """
        return _build_cached_geojson_payload(
            table_name=cls.CONFIG.table_name,
            page_type=cls.CONFIG.page_type,
            select_columns=cls.CONFIG.map_columns,
            db_mtime_ns=_db_cache_token(),
            categorize_lease_laundry=True,
        )

    def __init__(self) -> None:
        """
        Load lease data and assemble the top-level page cards.
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
        """
        Build the title, sidebar, and map cards for the lease page.

        Returns:
            The assembled ``PageParts`` bundle.
        """
        parts = build_page_parts(
            config=self.CONFIG,
            last_updated=self.last_updated,
            filter_items=self._build_filter_sections(),
            map_component=self._build_map_component(),
            map_overlay_children=[
                build_map_gesture_control(),
                build_school_layer_map_prompt(self.page_type),
                build_fire_hazard_layer_legend(self.page_type),
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
        """
        Build the lease map component with shared overlays and styles.

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
        """
        Build the accordion sections shown on the lease sidebar.

        Returns:
            Ordered filter-section tuples for the lease page.
        """
        return [
            ("Listed Date", self.create_listed_date_components(), "listed_date"),
            ("Location", build_location_filter_components(self.page_type), "location"),
            (
                "Fire Hazard Severity",
                self.create_fire_hazard_components(),
                "fire_hazard",
            ),
            ("Subtypes", self.create_subtype_checklist(), "subtypes"),
            ("Monthly Rent", self._build_rental_price_filter(), "monthly_rent"),
            ("Bedrooms", self._build_bedrooms_filter(), "bedrooms"),
            ("Bathrooms", self._build_bathrooms_filter(), "bathrooms"),
            ("Pet Policy", self.create_pets_radio_button(), "pet_policy"),
            (
                "Deposits",
                [
                    self._create_deposit_filter(
                        title="Key Deposit",
                        column="key_deposit",
                        slider_id="key_deposit_slider",
                        switch_id="key_deposit_missing_switch",
                        switch_label="Include properties with an unknown key deposit",
                        dynamic_index="key_deposit",
                        component_id="key_deposit_div",
                    ),
                    self._create_deposit_filter(
                        title="Other Deposit",
                        column="other_deposit",
                        slider_id="other_deposit_slider",
                        switch_id="other_deposit_missing_switch",
                        switch_label="Include properties with an unknown misc/other deposit",
                        dynamic_index="other_deposit",
                        component_id="other_deposit_div",
                    ),
                    self._create_deposit_filter(
                        title="Pet Deposit",
                        column="pet_deposit",
                        slider_id="pet_deposit_slider",
                        switch_id="pet_deposit_missing_switch",
                        switch_label="Include properties with an unknown pet deposit",
                        dynamic_index="pet_deposit",
                        component_id="pet_deposit_div",
                    ),
                    self._create_deposit_filter(
                        title="Security Deposit",
                        column="security_deposit",
                        slider_id="security_deposit_slider",
                        switch_id="security_deposit_missing_switch",
                        switch_label="Include properties with an unknown security deposit",
                        dynamic_index="security_deposit",
                        component_id="security_deposit_div",
                    ),
                ],
                "deposits",
            ),
            ("Furnished", self.create_furnished_checklist(), "furnished"),
            ("Parking Spaces", self._build_parking_spaces_filter(), "parking_spaces"),
            (
                "Internet Service Provider (ISP) Speed",
                build_isp_speed_components(
                    max_download=self._safe_speed_max("best_dn"),
                    max_upload=self._safe_speed_max("best_up"),
                ),
                "isp_speed",
            ),
            ("Laundry", self.create_laundry_checklist(), "laundry"),
            ("Price Per Sqft", self._build_ppsqft_filter(), "ppsqft"),
            ("Rental Terms", self.create_rental_terms_checklist(), "rental_terms"),
            ("Square Footage", self._build_square_footage_filter(), "square_footage"),
            ("Year Built", self.create_year_built_components(), "year_built"),
        ]

    def _build_rental_price_filter(self) -> html.Div:
        """
        Build the monthly-rent slider section.

        Returns:
            A rent filter ``Div``.
        """
        return build_range_filter(
            slider_id="rental_price_slider",
            min_value=self.df["list_price"].min(),
            max_value=self.df["list_price"].max(),
            value=[0, self.df["list_price"].max()],
            component_id="rental_price_div",
            dynamic_id=self.dynamic_output_id("rental_price"),
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
            component_id="bedrooms_div",
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
            component_id="bathrooms_div",
            dynamic_id=self.dynamic_output_id("bathrooms"),
            step=1,
        )

    def _build_parking_spaces_filter(self) -> html.Div:
        """
        Build the parking-spaces slider section.

        Returns:
            A parking filter ``Div``.
        """
        return build_range_filter(
            slider_id="garage_spaces_slider",
            min_value=0,
            max_value=self.df["parking_spaces"].max(),
            value=[0, self.df["parking_spaces"].max()],
            component_id="garage_spaces_div",
            dynamic_id=self.dynamic_output_id("garage_spaces"),
            include_missing_switch_id="garage_missing_switch",
            include_missing_switch_label="Include properties with an unknown number of garage spaces",
            container_style={"marginBottom": "10px"},
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
            switch_style={"marginTop": "15px"},
            container_style={"marginBottom": "10px"},
        )

    def _create_deposit_filter(
        self,
        *,
        title: str,
        column: str,
        slider_id: str,
        switch_id: str,
        switch_label: str,
        dynamic_index: str,
        component_id: str,
    ) -> html.Div:
        """
        Build a deposit slider section for one lease deposit field.

        Args:
            title: Visible section title.
            column: Dataframe column to inspect.
            slider_id: Dash id for the slider.
            switch_id: Dash id for the missing-values switch.
            switch_label: Label for the missing-values switch.
            dynamic_index: Pattern-matching id suffix for the content block.
            component_id: Outer container id.

        Returns:
            A deposit filter ``Div``.
        """
        return build_range_filter(
            slider_id=slider_id,
            min_value=self.df[column].min(),
            max_value=self.df[column].max(),
            value=[self.df[column].min(), self.df[column].max()],
            component_id=component_id,
            dynamic_id=self.dynamic_output_id(dynamic_index),
            tooltip_transform="formatCurrency",
            include_missing_switch_id=switch_id,
            include_missing_switch_label=switch_label,
            container_style={"marginBottom": "10px"},
            header_children=[
                html.H5(
                    title,
                    style={"display": "inline-block", "marginRight": "10px"},
                )
            ],
        )

    def create_subtype_checklist(self) -> html.Div:
        """
        Build the subtype dropdown for lease listings.

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
            placeholder="Type of home (e.g. Apartment, Single Family Residence, Townhouse)",
        )

    def create_pets_radio_button(self) -> html.Div:
        """
        Build the pet-policy radio controls.

        Returns:
            A pet-policy filter ``Div``.
        """
        return html.Div(
            [
                html.Div(
                    [
                        dcc.RadioItems(
                            id="pets_radio",
                            options=[
                                {"label": "Pets Allowed", "value": True},
                                {"label": "Pets NOT Allowed", "value": False},
                                {"label": "Both", "value": "Both"},
                            ],
                            value="Both",
                            inputStyle={"marginRight": "4px", "marginLeft": "0px"},
                            className="d-flex flex-wrap align-items-center gap-3 mb-1",
                            inline=True,
                        ),
                    ],
                    id=self.dynamic_output_id("pets"),
                ),
            ],
            id="pet_policy_div",
        )

    def create_fire_hazard_components(self) -> html.Div:
        """
        Build the CAL FIRE FHSZ filter section.

        Returns:
            A fire-hazard filter ``Div``.
        """
        values = [
            "Outside mapped zone",
            "Moderate",
            "High",
            "Very High",
            "Unknown",
        ]
        return html.Div(
            [
                html.Div(
                    "CAL FIRE zones describe long-term fire hazard for an area, not expected damage to a specific home.",
                    className="small text-muted mb-2",
                ),
                dmc.ChipGroup(
                    id="fire_hazard_severity_checklist",
                    multiple=True,
                    value=list(values),
                    children=[
                        dmc.Chip(children=value, value=value, radius="sm")
                        for value in values
                    ],
                ),
                html.Details(
                    [
                        html.Summary("What does this mean?"),
                        html.P(
                            (
                                "Fire Hazard Severity Zone maps evaluate hazard, not risk. "
                                "They are similar to flood zone maps: they describe area-level "
                                "conditions and likelihood over a 30- to 50-year period, without "
                                "accounting for mitigation such as home hardening, recent wildfire, "
                                "or fuel-reduction work."
                            ),
                            className="small text-muted mt-2 mb-0",
                        ),
                    ],
                    className="small mt-2",
                ),
            ],
            id=self.dynamic_output_id("fire_hazard"),
            className="d-flex flex-column gap-2",
        )

    def create_rental_terms_checklist(self) -> html.Div:
        """
        Build the rental-terms chip selector and unknown switch.

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
            dmc.ChipGroup(
                id="terms_checklist",
                multiple=True,
                value=list(unique_terms),
                children=[
                    dmc.Chip(
                        children=f"{terms[term]} ({term})",
                        value=term,
                        radius="sm",
                    )
                    for term in unique_terms
                ],
            ),
            id=self.dynamic_output_id("rental_terms"),
            className="d-flex flex-wrap gap-2",
        )

        return html.Div(
            [
                rental_terms_checklist,
                dmc.Switch(
                    id="terms_missing_switch",
                    label="Include properties with an unknown rental term",
                    checked=True,
                    size="sm",
                    color="teal",
                    style={"marginTop": "10px"},
                ),
            ],
            id="rental_terms_wrapper",
            style={"marginBottom": "10px"},
        )

    def create_furnished_checklist(self) -> html.Div:
        """
        Build the furnished-status chip selector.

        Returns:
            A furnished filter ``Div``.
        """
        furnished_options = [
            "Furnished Or Unfurnished",
            "Furnished",
            "Negotiable",
            "Partially",
            "Unfurnished",
            "Unknown",
        ]

        return html.Div(
            dmc.ChipGroup(
                id="furnished_checklist",
                multiple=True,
                value=furnished_options,
                children=[
                    dmc.Chip(
                        children=label,
                        value=label,
                        radius="sm",
                    )
                    for label in furnished_options
                ],
            ),
            id="furnished_div",
            className="d-flex flex-wrap gap-2",
        )

    def create_laundry_checklist(self) -> html.Div:
        """
        Build the laundry-category chip selector.

        Returns:
            A laundry filter ``Div``.
        """
        laundry_options = sorted(self.df["laundry"].fillna("Unknown").unique())

        return html.Div(
            dmc.ChipGroup(
                id="laundry_checklist",
                multiple=True,
                value=list(laundry_options),
                children=[
                    dmc.Chip(
                        children=category,
                        value=category,
                        radius="sm",
                    )
                    for category in laundry_options
                ],
            ),
            id=self.dynamic_output_id("laundry"),
            className="d-flex flex-wrap gap-2",
        )

    def create_listed_date_components(self) -> html.Div:
        """
        Build the listed-date filter section for the lease page.

        Returns:
            A listed-date filter ``Div``.
        """
        return build_listed_date_filter(
            earliest_date=self.earliest_date,
            dynamic_id=self.dynamic_output_id("listed_date"),
            datepicker_id="listed_date_datepicker_lease",
            component_id="listed_date_div_lease",
        )

    def create_year_built_components(self) -> html.Div:
        """
        Build the year-built filter section for the lease page.

        Returns:
            A year-built filter ``Div``.
        """
        return build_year_built_filter(
            min_year=int(self.df["year_built"].min()),
            max_year=int(self.df["year_built"].max()),
            dynamic_id=self.dynamic_output_id("year_built"),
            component_id="year_built_div",
        )
