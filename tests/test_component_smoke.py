import unittest

from dash import dcc, html

from pages.component_factories import build_subtype_filter, build_title_card
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
