import unittest

import dash_mantine_components as dmc
from dash import dcc, html

from pages.component_factories import (
    build_isp_speed_components,
    build_location_filter_components,
    build_range_filter,
    build_subtype_filter,
    build_title_card,
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
