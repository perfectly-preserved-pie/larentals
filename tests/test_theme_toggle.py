from dash.development.base_component import Component

from app import app  # noqa: F401
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

    assert any(component.__class__.__name__ == "ColorSchemeToggle" for component in rendered_components)
    assert not any(getattr(component, "id", None) == "theme-switch-store" for component in rendered_components)
