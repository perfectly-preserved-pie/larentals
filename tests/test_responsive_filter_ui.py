import unittest
from collections.abc import Iterator
from typing import Any

from dash import html

from pages.buy_components import BuyComponents
from pages.lease_components import LeaseComponents
from pages.responsive_filter_ui import (
    FILTER_UI_BREAKPOINT,
    build_filter_ui_stores,
    build_map_filter_toolbar,
    build_responsive_listing_shell,
)


def _collect_components(component: Any) -> Iterator[Any]:
    """
    Yield every component and text node in a Dash component tree.

    Lists and tuples are traversed recursively so tests can inspect deeply
    nested controls without depending on their exact layout structure.
    """
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _collect_components(child)
        return

    yield component
    children = getattr(component, "children", None)
    if children is not None:
        yield from _collect_components(children)


class ResponsiveFilterUiTest(unittest.TestCase):
    def test_filter_shell_keeps_one_filter_tree_and_map_main(self) -> None:
        """
        Verify the responsive shell does not duplicate the filter controls.
        """
        shell = build_responsive_listing_shell(
            page_type="lease",
            title_card=html.Div("Title", id="test-title"),
            user_options_card=html.Div("Filters", id="test-filter-tree"),
            map_card=html.Div("Map", id="test-map"),
        )

        components = list(_collect_components(shell))
        component_ids = [getattr(component, "id", None) for component in components]

        self.assertEqual(component_ids.count("test-filter-tree"), 1)
        self.assertIn("lease-filter-panel", component_ids)
        self.assertIn("lease-filter-backdrop", component_ids)
        self.assertIn("lease-map-main", component_ids)

        panel = next(
            component
            for component in components
            if getattr(component, "id", None) == "lease-filter-panel"
        )
        self.assertEqual(panel.role, "complementary")
        self.assertEqual(
            panel.to_plotly_json()["props"]["data-filter-panel"],
            "lease",
        )

    def test_toolbar_has_accessible_open_trigger_and_quick_filters(self) -> None:
        """
        Verify the compact toolbar exposes its controls and current mode.
        """
        toolbar = build_map_filter_toolbar("buy")
        components = list(_collect_components(toolbar))
        component_ids = {getattr(component, "id", None) for component in components}

        self.assertIn("buy-filter-open-button", component_ids)
        self.assertIn("buy-quick-location", component_ids)
        self.assertIn("buy-quick-price", component_ids)
        self.assertIn("buy-quick-bedrooms", component_ids)
        self.assertIn("buy-quick-bathrooms", component_ids)
        self.assertIn("buy-quick-more", component_ids)

        open_button = next(
            component
            for component in components
            if getattr(component, "id", None) == "buy-filter-open-button"
        )
        props = open_button.to_plotly_json()["props"]
        self.assertEqual(props["aria-controls"], "buy-filter-panel")
        self.assertEqual(props["aria-haspopup"], "dialog")
        self.assertEqual(props["aria-expanded"], "false")

        mode_nav = next(
            component
            for component in components
            if getattr(component, "className", None) == "map-filter-toolbar__mode"
        )
        self.assertEqual(mode_nav.to_plotly_json()["props"]["aria-label"], "Listing type")

        current_modes = [
            component
            for component in components
            if hasattr(component, "to_plotly_json")
            and component.to_plotly_json()["props"].get("aria-current") == "page"
        ]
        self.assertEqual(len(current_modes), 1)
        self.assertEqual(current_modes[0].href, "/buy")
        self.assertIn("is-selected", current_modes[0].className)

    def test_page_filter_stores_are_scoped(self) -> None:
        """
        Verify each listing page receives its own filter state stores.
        """
        stores = build_filter_ui_stores("lease")
        self.assertEqual(
            [store.id for store in stores],
            [
                "lease-filter-draft-store",
                "lease-filter-applied-store",
                "lease-filter-preview-store",
            ],
        )
        self.assertEqual(stores[-1].data, {"count": None})

    def test_desktop_sections_are_expanded_initially(self) -> None:
        """
        Verify the persistent desktop sidebar opens its primary filter sections.
        """
        self.assertEqual(
            LeaseComponents.CONFIG.active_filter_items,
            (
                "listed_date",
                "location",
                "subtypes",
                "monthly_rent",
                "bedrooms",
                "bathrooms",
            ),
        )
        self.assertEqual(
            BuyComponents.CONFIG.active_filter_items,
            (
                "listed_date",
                "location",
                "subtypes",
                "list_price",
                "bedrooms",
                "bathrooms",
            ),
        )
        self.assertEqual(FILTER_UI_BREAKPOINT, 1100)


if __name__ == "__main__":
    unittest.main()
