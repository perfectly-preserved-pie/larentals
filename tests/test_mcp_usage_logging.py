import unittest
from unittest.mock import patch

from flask import Flask, Response, request

from functions.mcp_usage_logging import _result_summary, register_mcp_usage_logging


class McpUsageLoggingTest(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        register_mcp_usage_logging(app)

        @app.route("/_mcp", methods=["GET", "POST"])
        def mcp_endpoint() -> Response:
            status = 500 if request.args.get("failed") else 200
            return Response("{}", status=status, mimetype="application/json")

        @app.route("/health")
        def health() -> str:
            return "ok"

        self.client = app.test_client()

    def test_logs_tool_invocation_with_search_filters_and_result_summary(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "update_lease_zip_boundary",
                "arguments": {
                    "location": "Pasadena",
                    "max_price": 2500,
                    "pet_friendly": True,
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
        self.assertIn("MCP tool call", log_output)
        self.assertIn("tool=update_lease_zip_boundary", log_output)
        self.assertIn(
            'arguments={"location": "Pasadena", "max_price": 2500, "pet_friendly": true}',
            log_output,
        )
        self.assertIn("status=200", log_output)
        self.assertIn("result=missing", log_output)
        self.assertIn("MCP test client", log_output)
        self.assertNotIn("argument_keys", log_output)

    def test_suppresses_non_tool_mcp_requests(self) -> None:
        with patch("functions.mcp_usage_logging.logger.info") as log_info:
            response = self.client.post(
                "/_mcp", json={"jsonrpc": "2.0", "method": "tools/list"}
            )

        self.assertEqual(response.status_code, 200)
        log_info.assert_not_called()

    def test_suppresses_failed_non_tool_mcp_requests(self) -> None:
        with patch("functions.mcp_usage_logging.logger.info") as log_info:
            response = self.client.get("/_mcp?failed=1")

        self.assertEqual(response.status_code, 500)
        log_info.assert_not_called()

    def test_logs_missing_result_payload(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "search_listings", "arguments": {}},
        }

        with patch("functions.mcp_usage_logging.logger.info") as log_info:
            response = self.client.post("/_mcp", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertIn("result=missing", log_info.call_args.args[0])

    def test_summarizes_structured_tool_result_without_listing_data(self) -> None:
        response = Response(
            '{"result":{"structuredContent":{"result":{'
            '"listing_type":"lease","total_results":2,"page":1,'
            '"page_size":20,"listings":[{"address":"123 Private Street"}]}}}}',
            mimetype="application/json",
        )

        summary = _result_summary(response)

        self.assertEqual(
            summary,
            "success(listing_type=lease,total_results=2,page=1,page_size=20)",
        )
        self.assertNotIn("123 Private Street", summary)

    def test_ignores_non_mcp_paths(self) -> None:
        with patch("functions.mcp_usage_logging.logger.info") as log_info:
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        log_info.assert_not_called()


if __name__ == "__main__":
    unittest.main()
