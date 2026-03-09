import dash_mantine_components as dmc
from dash.development.base_component import Component

from app import app
from pages.buy_page import components


def _walk(component):
    if isinstance(component, Component):
        yield component
        children = getattr(component, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from _walk(child)
        elif children is not None:
            yield from _walk(children)


def test_layout_uses_color_scheme_toggle_without_theme_store():
    rendered_components = list(_walk(components.title_card))

    assert any(
        isinstance(component, dmc.ColorSchemeToggle) and getattr(component, "id", None) == "color-scheme-toggle"
        for component in rendered_components
    )
    assert not any(getattr(component, "id", None) == "color-scheme-switch" for component in rendered_components)
    assert not any(getattr(component, "id", None) == "theme-switch-store" for component in rendered_components)


def test_index_string_syncs_bootstrap_theme_with_mantine_color_scheme():
    assert "mantine-color-scheme-value" in app.index_string
    assert 'data-bs-theme' in app.index_string
