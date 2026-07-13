"""Smoke tests for the human-facing MCP documentation page."""

import unittest

from dash import dcc, html

from functions.mcp_docs_ui import MCP_ENDPOINT, build_mcp_docs_layout


def _collect_components(component: object):
  """Yield every Dash component in a layout tree.

  Lists and tuples are traversed so nested cards and copy controls are covered.
  """
  if isinstance(component, (list, tuple)):
    for child in component:
      yield from _collect_components(child)
    return

  yield component
  children = getattr(component, "children", None)
  if children is not None:
    yield from _collect_components(children)


class McpDocsUiTest(unittest.TestCase):
  def setUp(self) -> None:
    """Build one documentation layout for each isolated test case."""
    self.layout = build_mcp_docs_layout()
    self.components = list(_collect_components(self.layout))

  def test_layout_exposes_copyable_public_endpoint(self) -> None:
    """Keep the displayed and copied endpoint consistent."""
    codes = [item for item in self.components if isinstance(item, html.Code)]
    clipboards = [
      item for item in self.components if isinstance(item, dcc.Clipboard)
    ]

    self.assertIn(MCP_ENDPOINT, [code.children for code in codes])
    self.assertIn(MCP_ENDPOINT, [clipboard.content for clipboard in clipboards])

  def test_layout_covers_supported_clients_and_listing_modes(self) -> None:
    """Ensure essential setup and capability copy remains present."""
    text = str(self.layout.to_plotly_json())

    for expected in ("Claude", "Hermes", "lease", "buy", "Streamable HTTP"):
      self.assertIn(expected, text)

  def test_layout_has_navigation_and_theme_control(self) -> None:
    """Verify that users can return home and use the shared theme callback."""
    links = [item for item in self.components if isinstance(item, dcc.Link)]
    ids = [getattr(item, "id", None) for item in self.components]

    self.assertIn("/", [link.href for link in links])
    self.assertIn("color-scheme-switch", ids)


if __name__ == "__main__":
  unittest.main()
