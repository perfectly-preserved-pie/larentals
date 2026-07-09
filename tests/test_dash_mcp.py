import ast
import json
import unittest
from pathlib import Path

from dash import Dash, html


class DashMcpTest(unittest.TestCase):
    def test_app_constructor_opts_into_dash_mcp(self) -> None:
        app_source = Path("app.py").read_text(encoding="utf-8")
        module = ast.parse(app_source)

        dash_calls = [
            node
            for node in ast.walk(module)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Dash"
        ]
        self.assertEqual(len(dash_calls), 1)

        enable_mcp_keywords = [
            keyword
            for keyword in dash_calls[0].keywords
            if keyword.arg == "enable_mcp"
        ]
        self.assertEqual(len(enable_mcp_keywords), 1)
        self.assertIsInstance(enable_mcp_keywords[0].value, ast.Constant)
        self.assertIs(enable_mcp_keywords[0].value.value, True)

    def test_dash_mcp_endpoint_initializes_over_http(self) -> None:
        app = Dash(__name__, enable_mcp=True)
        app.layout = html.Div("MCP smoke test")
        client = app.server.test_client()

        get_response = client.get("/_mcp")
        self.assertEqual(get_response.status_code, 200)
        self.assertIn("text/event-stream", get_response.content_type)
        self.assertTrue(get_response.headers.get("Mcp-Session-Id"))

        initialize_response = client.post(
            "/_mcp",
            data=json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {},
            }),
            content_type="application/json",
        )
        payload = initialize_response.get_json()

        self.assertEqual(initialize_response.status_code, 200)
        self.assertEqual(payload["jsonrpc"], "2.0")
        self.assertEqual(payload["id"], 1)
        self.assertEqual(payload["result"]["serverInfo"]["name"], "Plotly Dash")
        self.assertIn("tools", payload["result"]["capabilities"])
        self.assertIn("resources", payload["result"]["capabilities"])


if __name__ == "__main__":
    unittest.main()
