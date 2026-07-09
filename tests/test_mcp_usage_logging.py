import unittest
from unittest.mock import patch

from flask import Flask, Response

from functions.mcp_usage_logging import register_mcp_usage_logging


class McpUsageLoggingTest(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        register_mcp_usage_logging(app)

        @app.route("/_mcp", methods=["GET", "POST"])
        def mcp_endpoint() -> Response:
            return Response("{}", mimetype="application/json")

        @app.route("/health")
        def health() -> str:
            return "ok"

        self.client = app.test_client()

    def test_logs_mcp_post_metadata_without_arguments(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "update_lease_zip_boundary",
                "arguments": {
                    "location": "123 Private Street",
                },
            },
        }

        with patch("functions.mcp_usage_logging.logger.info") as log_info:
            response = self.client.post(
                "/_mcp",
                json=payload,
                headers={"User-Agent": "MCP test client"},
            )

        self.assertEqual(response.status_code, 200)
        log_info.assert_called_once()
        log_output = log_info.call_args.args[0]
        self.assertIn("MCP request method=POST", log_output)
        self.assertIn("rpc_method=tools/call", log_output)
        self.assertIn("target=update_lease_zip_boundary", log_output)
        self.assertIn("status=200", log_output)
        self.assertIn("MCP test client", log_output)
        self.assertNotIn("arguments", log_output)
        self.assertNotIn("123 Private Street", log_output)

    def test_logs_mcp_get_without_rpc_payload(self) -> None:
        with patch("functions.mcp_usage_logging.logger.info") as log_info:
            response = self.client.get("/_mcp")

        self.assertEqual(response.status_code, 200)
        log_info.assert_called_once()
        log_output = log_info.call_args.args[0]
        self.assertIn("MCP request method=GET", log_output)
        self.assertIn("rpc_method=-", log_output)
        self.assertIn("target=-", log_output)

    def test_ignores_non_mcp_paths(self) -> None:
        with patch("functions.mcp_usage_logging.logger.info") as log_info:
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        log_info.assert_not_called()


if __name__ == "__main__":
    unittest.main()
