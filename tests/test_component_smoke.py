import unittest

import dash_mantine_components as dmc
from dash import dcc, html

from pages.component_factories import (
    build_isp_speed_components,
    build_location_filter_components,
    build_range_filter,
    build_subtype_filter,
    build_title_card,
    iqr_capped_range_bounds,
)
from pages.components import BuyComponents, LeaseComponents


def _collect_components(component):
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
        for page_type in ("lease", "buy"):
            with self.subTest(page_type=page_type):
                component = build_location_filter_components(page_type)
                label, location_input = component.children[:2]

                self.assertIsInstance(label, html.Label)
                self.assertEqual(label.htmlFor, f"{page_type}-location-input")
                self.assertIsInstance(location_input, dmc.TagsInput)
                props = location_input.to_plotly_json()["props"]
                self.assertEqual(props["value"], [])
                self.assertEqual(props["splitChars"], [";"])
                self.assertEqual(props["maxTags"], 5)
                self.assertEqual(
                    props["description"],
                    "Add up to 5 locations.",
                )
                self.assertEqual(
                    props["placeholder"],
                    "Type a location, then press Enter",
                )
                self.assertTrue(props["acceptValueOnBlur"])
                self.assertNotIn("inputProps", props)
                self.assertNotIn("aria-label", props)

    def test_buy_components_build_core_cards(self) -> None:
        components = BuyComponents()

        self.assertIsNotNone(components.parts)
        self.assertIsNotNone(components.title_card)
        self.assertIsNotNone(components.user_options_card)
        self.assertIsNotNone(components.map_card)

    def test_lease_components_build_core_cards(self) -> None:
        components = LeaseComponents()

        self.assertIsNotNone(components.parts)
        self.assertIsNotNone(components.title_card)
        self.assertIsNotNone(components.user_options_card)
        self.assertIsNotNone(components.map_card)

    def test_subtype_filter_defaults_to_include_all_state(self) -> None:
        component = build_subtype_filter(
            values=["Apartment", "Townhouse", "Unknown"],
            dynamic_id="subtype-wrapper",
            placeholder="Type of home",
        )

        self.assertIsInstance(component, html.Div)
        dropdown_wrapper = component.children[1]
        self.assertIsInstance(dropdown_wrapper, html.Div)
        dropdown = dropdown_wrapper.children[0]
        self.assertIsInstance(dropdown, dcc.Dropdown)
        self.assertEqual(dropdown.value, [])

    def test_range_filter_reserves_tooltip_space_before_switch(self) -> None:
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

        controls = component.children[1]
        slider_wrapper, missing_switch = controls.children

        self.assertEqual(controls.className, "range-filter__controls")
        self.assertEqual(
            slider_wrapper.className,
            "range-filter__slider-with-switch",
        )
        self.assertIsInstance(slider_wrapper.children, dcc.RangeSlider)
        self.assertEqual(missing_switch.id, "test-missing-switch")

    def test_hybrid_range_filter_has_exact_fields_and_finite_slider(self) -> None:
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

        controls = component.children[1]
        exact_inputs, slider_wrapper = controls.children
        minimum_input, maximum_input = exact_inputs.children
        slider = slider_wrapper.children

        self.assertEqual(exact_inputs.className, "range-filter__exact-inputs")
        self.assertIsInstance(minimum_input, dmc.NumberInput)
        self.assertEqual(minimum_input.id, "test_price_minimum_input")
        self.assertEqual(minimum_input.label, "Minimum")
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
        self.assertEqual(maximum_input.label, "Maximum")
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
            {0: "0", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "Unlimited"},
        )
        self.assertEqual(
            bounds.marks(include_open_end=False, target_intervals=3),
            {0: "0", 2: "2", 4: "4", 5: "5"},
        )

    def test_iqr_slider_cap_rounds_currency_to_a_readable_endpoint(self) -> None:
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
        self.assertEqual(bounds.marks(currency=True)[12_000], "Unlimited")
        self.assertEqual(
            bounds.marks(
                currency=True,
                include_open_end=False,
                target_intervals=3,
            ),
            {0: "$0", 5_000: "$5k", 10_000: "$10k"},
        )

    def test_iqr_slider_uses_observed_max_when_data_has_no_high_outlier(self) -> None:
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

    def test_isp_speed_filter_reserves_space_below_both_sliders(self) -> None:
        component = build_isp_speed_components(10_000, 10_000)

        download_range, upload_range, missing_switch = component.children

        self.assertEqual(component.className, "isp-speed-filter")
        self.assertEqual(download_range.className, "isp-speed-filter__range")
        self.assertEqual(upload_range.className, "isp-speed-filter__range")
        self.assertEqual(missing_switch.id, "isp_speed_missing_switch")

    def test_title_card_links_to_mcp_setup_page(self) -> None:
        title_card = build_title_card(
            title="WhereToLive.LA",
            subtitle="Interactive housing map",
            last_updated=None,
        )

        links = [
            component
            for component in _collect_components(title_card)
            if isinstance(component, html.A)
        ]
        self.assertIn("/mcp", [link.href for link in links])


if __name__ == "__main__":
    unittest.main()
