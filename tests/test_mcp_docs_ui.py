"""Smoke tests for the standalone MCP documentation response."""

from bs4 import BeautifulSoup

from app import server
from functions.mcp_guide import MCP_ENDPOINT


def test_mcp_docs_exposes_setup_and_copy_controls() -> None:
  """Verify that the MCP guide sends its complete content as HTML.

  The clipboard handler resolves snippets by ID, so the endpoint button must
  keep its association when the page is served without the Dash renderer.

  Returns:
      None.
  """
  response = server.test_client().get("/mcp")
  assert response.status_code == 200
  assert len(response.data) < 18_000
  document = BeautifulSoup(response.data, "html.parser")
  assert document.select_one("#react-entry-point, #_dash-config") is None
  button = document.select_one("button#mcp-endpoint-copy")
  assert document.find("code", id=button["data-mcp-copy"]).get_text() == MCP_ENDPOINT
  assert document.select_one('nav a[href="/"]')
  assert document.select_one('input#color-scheme-switch[role="switch"]')
  text = document.select_one("main").get_text()
  for expected in ("Claude", "Hermes", "lease", "buy", "Streamable HTTP", "Long Beach"):
    assert expected in text
