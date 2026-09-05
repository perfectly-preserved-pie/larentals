import unittest
from collections.abc import Iterator

import dash_mantine_components as dmc
from dash import dcc, html

from pages.component_factories import (
    build_isp_speed_components,
    build_location_filter_components,
    build_location_filter_status,
    build_location_suggestions,
    build_range_filter,
    build_subtype_filter,
    build_title_card,
    iqr_capped_range_bounds,
)
from pages.components import BuyComponents, LeaseComponents


def _collect_components(component: object) -> Iterator[object]:
    """Handle collect components.

    Args:
        component: Dash component or nested component collection to traverse.

    Yields:
        Values produced by the iterator.
    """
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _collect_components(child)
        return

    yield component
    children = getattr(component, "children", None)
    if children is not None:
        yield from _collect_components(children)


class ComponentsSmokeTest(unittest.TestCase):
    def test_location_inputs_use_associated_labels(self) -> None:
        """Verify that location inputs use associated labels.

        Returns:
            None.
        """
        for page_type in ("lease", "buy"):
            with self.subTest(page_type=page_type):
                component = build_location_filter_components(page_type)
                label, entry_row, help_text = component.children[:3]
                location_input, add_button = entry_row.children

                self.assertIsInstance(label, html.Label)
                self.assertEqual(label.htmlFor, f"{page_type}-location-input")
                self.assertIsInstance(location_input, dmc.TagsInput)
                props = location_input.to_plotly_json()["props"]
                self.assertEqual(props["value"], [])
                self.assertEqual(props["searchValue"], "")
                self.assertEqual(props["splitChars"], [";"])
                self.assertEqual(props["maxTags"], 5)
                self.assertEqual(
                    props["placeholder"],
                    "Search neighborhoods, cities, or ZIPs",
                )
                self.assertFalse(props["acceptValueOnBlur"])
                self.assertIn("Los Feliz, CA", props["data"])
                self.assertIn("Silver Lake, CA", props["data"])
                self.assertIsInstance(add_button, html.Button)
                self.assertEqual(add_button.id, f"{page_type}-location-add-button")
                desktop_help, touch_help = help_text.children
                self.assertIn("press Enter", desktop_help.children)
                self.assertIn("tap Add", touch_help.children)
                self.assertNotIn("inputProps", props)
                self.assertNotIn("aria-label", props)

                loading = component.children[3]
                self.assertIsInstance(loading, dcc.Loading)
                loading_props = loading.to_plotly_json()["props"]
                self.assertEqual(
                    loading_props["target_components"],
                    {f"{page_type}-location-status": "children"},
                )
                self.assertIn(
                    "Resolving locations",
                    "".join(
                        str(child)
                        for child in loading_props["custom_spinner"].children
                    ),
                )
                status = loading.children
                status_props = status.to_plotly_json()["props"]
                self.assertEqual(status_props["role"], "status")
                self.assertEqual(status_props["aria-live"], "polite")
                self.assertEqual(status_props["aria-atomic"], "true")

    def test_location_suggestions_include_listing_places_and_zip_codes(self) -> None:
        """Build canonical suggestions from local listing values.

        Returns:
            None.
        """
        suggestions = build_location_suggestions(
            ["SILVER LAKE", "Pasadena", "#302, LONG BEACH", "BDPK", None],
            ["90026", "91030-1234", None],
        )

        self.assertIn("Silver Lake, CA", suggestions)
        self.assertIn("Pasadena, CA", suggestions)
        self.assertIn("Los Feliz, CA", suggestions)
        self.assertNotIn("#302, Long Beach, CA", suggestions)
        self.assertNotIn("Bdpk, CA", suggestions)
        self.assertEqual(suggestions[-2:], ["90026", "91030"])

    def test_short_location_status_stays_plain_text(self) -> None:
        """Verify that short location status stays plain text.

        Returns:
            None.
        """
        status = "Filtering by ZIP codes: 90027, 90039."

        rendered = build_location_filter_status(
            {"zip_codes": ["90027", "90039"]},
            status,
        )

        self.assertEqual(rendered, status)

    def test_long_location_status_puts_additional_zips_in_popover(self) -> None:
        """Verify that long location status puts additional zips in popover.

        Returns:
            None.
        """
        zip_codes = ["90027", "90039", "90041", "90065", "91011", "91020"]
        status = (
            "Filtering by ZIP codes: 90027, 90039, 90041, 90065, 91011 "
            "+1 more. Could not find a California location matching 'Atlantis'."
        )

        rendered = build_location_filter_status(
            {"zip_codes": zip_codes},
            status,
        )

        self.assertIsInstance(rendered, list)
        popover = rendered[1]
        self.assertIsInstance(popover, dmc.Popover)
        target, dropdown = popover.children
        button = target.children
        self.assertEqual(button.children, "+1 more")
        self.assertEqual(
            button.to_plotly_json()["props"]["aria-label"],
            "Show 1 additional ZIP code",
        )
        zip_list = dropdown.children[1]
        self.assertEqual(
            [item.children for item in zip_list.children],
            ["91020"],
        )
        self.assertEqual(
            rendered[-1],
            " Could not find a California location matching 'Atlantis'.",
        )

    def test_buy_components_build_core_cards(self) -> None:
        """Verify that buy components build core cards.

        Returns:
            None.
        """
        components = BuyComponents()

        self.assertIsNotNone(components.parts)
        self.assertIsNotNone(components.title_card)
        self.assertIsNotNone(components.user_options_card)
        self.assertIsNotNone(components.map_card)

    def test_lease_components_build_core_cards(self) -> None:
        """Verify that lease components build core cards.

        Returns:
            None.
        """
        components = LeaseComponents()

        self.assertIsNotNone(components.parts)
        self.assertIsNotNone(components.title_card)
        self.assertIsNotNone(components.user_options_card)
        self.assertIsNotNone(components.map_card)

    def test_subtype_filter_defaults_to_include_all_state(self) -> None:
        """Verify that subtype filter defaults to include all state.

        Returns:
            None.
        """
        component = build_subtype_filter(
            values=["Apartment", "Townhouse", "Unknown"],
            dynamic_id="subtype-wrapper",
            placeholder="Type of home",
        )

        self.assertIsInstance(component, html.Div)
        dropdown_wrapper = next(
            child
            for child in component.children
            if getattr(child, "id", None) == "subtype-wrapper"
        )
        dropdown = dropdown_wrapper.children[0]
        self.assertIsInstance(dropdown, dcc.Dropdown)
        self.assertEqual(dropdown.value, [])

        quick = next(
            child
            for child in component.children
            if "subtype-quick" in str(getattr(child, "className", ""))
        )
        self.assertEqual([button.children for button in quick.children],
                         ["Apartment", "Condo or townhouse"])

    def test_range_filter_defers_missing_values_to_the_shared_switch(self) -> None:
        """Verify that a range filter renders no per-filter missing switch.

        One sidebar-wide switch now answers the missing-values question, so a
        range filter contributes only its slider.

        Returns:
            None.
        """
        component = build_range_filter(
            slider_id="test-slider",
            min_value=0,
            max_value=100,
            value=[0, 100],
            component_id="test-range-filter",
            dynamic_id="test-range-filter-controls",
            include_missing_switch_id="test-missing-switch",
            include_missing_switch_label="Include unknown values",
        )

        controls = next(
            child
            for child in component.children
            if getattr(child, "className", None) == "range-filter__controls"
        )
        self.assertEqual(controls.className, "range-filter__controls")
        self.assertEqual(len(controls.children), 1)
        self.assertIsInstance(controls.children[0], dcc.RangeSlider)

    def test_hybrid_range_filter_has_exact_fields_and_finite_slider(self) -> None:
        """Verify that hybrid range filter has exact fields and finite slider.

        Returns:
            None.
        """
        component = build_range_filter(
            slider_id="test_price_slider",
            min_value=0,
            max_value=10_000,
            value=[0, 10_000],
            component_id="test-price-filter",
            dynamic_id="test-price-filter-controls",
            tooltip_transform="formatCurrency",
            marks={0: "$0", 5_000: "$5k", 10_000: "$10k"},
            show_exact_inputs=True,
            input_prefix="$",
        )

        controls = next(
            child
            for child in component.children
            if getattr(child, "className", None) == "range-filter__controls"
        )
        exact_inputs, slider_wrapper = controls.children
        minimum_input, maximum_input = exact_inputs.children
        slider = slider_wrapper.children

        self.assertEqual(exact_inputs.className, "range-filter__exact-inputs")
        self.assertIsInstance(minimum_input, dmc.NumberInput)
        self.assertEqual(minimum_input.id, "test_price_minimum_input")
        self.assertEqual(getattr(minimum_input, "aria-label"), "Minimum")
        self.assertEqual(minimum_input.value, 0)
        minimum_clear_button = minimum_input.rightSection
        self.assertIsInstance(minimum_clear_button, dmc.ActionIcon)
        self.assertEqual(minimum_clear_button.id, "test_price_minimum_clear")
        self.assertEqual(minimum_clear_button.style, {"visibility": "hidden"})
        self.assertEqual(
            minimum_clear_button.buttonProps["aria-label"],
            "Reset minimum to zero",
        )
        self.assertEqual(maximum_input.id, "test_price_maximum_input")
        self.assertEqual(getattr(maximum_input, "aria-label"), "Maximum")
        self.assertIsNone(maximum_input.value)
        self.assertEqual(maximum_input.placeholder, "Unlimited")
        unlimited_button = maximum_input.rightSection
        self.assertIsInstance(unlimited_button, dmc.ActionIcon)
        self.assertEqual(unlimited_button.id, "test_price_maximum_clear")
        self.assertEqual(unlimited_button.style, {"visibility": "hidden"})
        self.assertEqual(
            unlimited_button.buttonProps["aria-label"],
            "Set maximum to unlimited",
        )
        self.assertEqual(slider_wrapper.className, "range-filter__hybrid-slider-wrap")
        self.assertEqual(slider.className, "range-filter__hybrid-slider")
        self.assertEqual(slider.max, 10_000)
        self.assertEqual(slider.updatemode, "drag")
        self.assertNotIn("tooltip", slider.to_plotly_json()["props"])

    def test_iqr_slider_cap_buckets_outliers_without_discarding_them(self) -> None:
        """Verify that iqr slider cap buckets outliers without discarding them.

        Returns:
            None.
        """
        bounds = iqr_capped_range_bounds(
            [1, 2, 2, 3] * 25 + [15],
            minimum=0,
            step=1,
        )

        self.assertTrue(bounds.is_capped)
        self.assertEqual(bounds.capped_at, 5)
        self.assertEqual(bounds.maximum, 6)
        self.assertEqual(bounds.display_maximum, 5)
        self.assertEqual(
            bounds.marks(),
            {0: "0", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6"},
        )
        self.assertEqual(
            bounds.marks(include_open_end=False, target_intervals=3),
            {0: "0", 2: "2", 4: "4", 5: "5"},
        )

    def test_iqr_slider_cap_rounds_currency_to_a_readable_endpoint(self) -> None:
        """Verify that iqr slider cap rounds currency to a readable endpoint.

        Returns:
            None.
        """
        bounds = iqr_capped_range_bounds(
            [2_250, 2_500, 3_000, 3_646] * 25 + [675_000],
            minimum=0,
            step=1,
        )

        self.assertTrue(bounds.is_capped)
        self.assertEqual(bounds.capped_at, 10_000)
        self.assertEqual(bounds.maximum, 12_000)
        self.assertEqual(bounds.display_maximum, 10_000)
        self.assertEqual(bounds.marks(currency=True)[10_000], "$10k")
        # The final stop is still open ended, but it is labelled with the real
        # maximum rather than a word that hid the number.
        self.assertEqual(bounds.marks(currency=True)[12_000], "$12k")
        self.assertEqual(
            bounds.marks(
                currency=True,
                include_open_end=False,
                target_intervals=3,
            ),
            {0: "$0", 5_000: "$5k", 10_000: "$10k"},
        )

    def test_iqr_slider_uses_observed_max_when_data_has_no_high_outlier(self) -> None:
        """Verify that iqr slider uses observed max when data has no high outlier.

        Returns:
            None.
        """
        bounds = iqr_capped_range_bounds([1, 2, 3, 3], minimum=0, step=1)

        self.assertFalse(bounds.is_capped)
        self.assertIsNone(bounds.capped_at)
        self.assertEqual(bounds.maximum, 3)
        self.assertEqual(bounds.display_maximum, 3)
        self.assertIsNone(bounds.marks())
        self.assertEqual(
            bounds.marks(include_open_end=False, target_intervals=3),
            {0: "0", 1: "1", 2: "2", 3: "3"},
        )

    def test_isp_speed_filter_renders_both_sliders(self) -> None:
        """Verify that the ISP filter renders a download and an upload range.

        The per-filter missing-values switch is gone; one sidebar-wide switch
        answers that question for every filter.

        Returns:
            None.
        """
        tiers = [0, 100, 1_000, 5_000, 10_000]
        component = build_isp_speed_components(tiers, tiers)

        download_range, upload_range = component.children

        self.assertEqual(component.className, "isp-speed-filter")
        self.assertEqual(download_range.className, "isp-speed-filter__range")
        self.assertEqual(upload_range.className, "isp-speed-filter__range")

        # The slider steps through tier indexes, not megabits, so the ladder
        # travels the same distance per tier however lopsided the speeds are.
        slider = download_range.children[1]
        self.assertEqual(slider.min, 0)
        self.assertEqual(slider.max, len(tiers) - 1)
        self.assertEqual(slider.step, 1)
        self.assertEqual(
            download_range.__dict__["data-speed-tiers"], "0,100,1000,5000,10000"
        )
        self.assertEqual(slider.marks[len(tiers) - 1], "10G")

    def test_title_card_links_to_mcp_setup_page(self) -> None:
        """Verify that title card links to mcp setup page.

        Returns:
            None.
        """
        title_card = build_title_card(
            title="WhereToLive.LA",
            last_updated=None,
            page_type="lease",
        )

        links = [
            component
            for component in _collect_components(title_card)
            if isinstance(component, html.A)
        ]
        self.assertIn("/mcp", [link.href for link in links])


if __name__ == "__main__":
    unittest.main()
