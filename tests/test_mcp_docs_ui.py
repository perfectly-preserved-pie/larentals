"""Smoke tests for the human-facing MCP documentation page."""

import unittest
from collections.abc import Iterator

from dash import dcc, html

from functions.mcp_docs_ui import MCP_ENDPOINT, build_mcp_docs_layout


def _collect_components(component: object) -> Iterator[object]:
  """Yield every Dash component in a layout tree.

  Lists and tuples are traversed so nested sections and copy buttons are covered.

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


class McpDocsUiTest(unittest.TestCase):
  def setUp(self) -> None:
    """Build one documentation layout for each isolated test case.

    Each test gets a fresh docs layout so IDs and callback state do not leak between cases.

    Returns:
        None.
    """
    self.layout = build_mcp_docs_layout()
    self.components = list(_collect_components(self.layout))

  def test_layout_exposes_copyable_public_endpoint(self) -> None:
    """Keep the displayed and copied endpoint consistent.

    The copy handler resolves the code element by ID and copies its text.

    Returns:
        None.
    """
    components_by_id = {
      item.id: item for item in self.components if hasattr(item, "id")
    }
    button = components_by_id["mcp-endpoint-copy"]
    code = components_by_id[getattr(button, "data-mcp-copy")]

    self.assertIsInstance(button, html.Button)
    self.assertIsInstance(code, html.Code)
    self.assertEqual(code.children, MCP_ENDPOINT)

  def test_layout_covers_supported_clients_and_listing_modes(self) -> None:
    """Ensure essential setup and capability copy remains present.

    The setup page must explain both protocol clients and listing modes the tool supports.

    Returns:
        None.
    """
    text = str(self.layout.to_plotly_json())

    for expected in ("Claude", "Hermes", "lease", "buy", "Streamable HTTP"):
      self.assertIn(expected, text)

  def test_layout_has_navigation_and_theme_control(self) -> None:
    """Verify that users can return home and use the shared theme callback.

    The docs page should remain reachable and use the application-wide theme behavior.

    Returns:
        None.
    """
    links = [item for item in self.components if isinstance(item, dcc.Link)]
    ids = [getattr(item, "id", None) for item in self.components]

    self.assertIn("/", [link.href for link in links])
    self.assertIn("color-scheme-switch", ids)


if __name__ == "__main__":
  unittest.main()
