import json
import unittest
from unittest.mock import patch

from flask import Flask, Response, request

from functions.mcp_usage_logging import _result_summary, register_mcp_usage_logging


class McpUsageLoggingTest(unittest.TestCase):
    def setUp(self) -> None:
        """Handle setUp.

        Each request runs through a fresh Flask app to isolate logging hooks.

        Returns:
            None.
        """
        app = Flask(__name__)
        register_mcp_usage_logging(app)

        @app.route("/_mcp", methods=["GET", "POST"])
        def mcp_endpoint() -> Response:
            """Handle mcp endpoint.

            The fixture endpoint exercises request hooks without constructing the full production app.

            Returns:
                An HTTP response containing the MCP endpoint.
            """
            status = 500 if request.args.get("failed") else 200
            return Response("{}", status=status, mimetype="application/json")

        @app.route("/health")
        def health() -> str:
            """Handle health.

            A simple health route verifies non-MCP requests remain routable under the test app.

            Returns:
                The health text.
            """
            return "ok"

        self.client = app.test_client()

    def test_logs_tool_invocation_with_search_filters_and_result_summary(self) -> None:
        """Verify that logs tool invocation with search filters and result summary.

        The log should capture useful tool context while keeping the result summary compact.

        Returns:
            None.
        """
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
        """Verify that suppresses non tool mcp requests.

        Discovery and other protocol traffic should not be mislabeled as tool usage.

        Returns:
            None.
        """
        with patch("functions.mcp_usage_logging.logger.info") as log_info:
            response = self.client.post(
                "/_mcp", json={"jsonrpc": "2.0", "method": "tools/list"}
            )

        self.assertEqual(response.status_code, 200)
        log_info.assert_not_called()

    def test_suppresses_failed_non_tool_mcp_requests(self) -> None:
        """Verify that suppresses failed non tool mcp requests.

        Non-tool failures should not create misleading tool failure records.

        Returns:
            None.
        """
        with patch("functions.mcp_usage_logging.logger.info") as log_info:
            response = self.client.get("/_mcp?failed=1")

        self.assertEqual(response.status_code, 500)
        log_info.assert_not_called()

    def test_logs_missing_result_payload(self) -> None:
        """Verify that logs missing result payload.

        A missing response body still needs a completed request record.

        Returns:
            None.
        """
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
        """Verify that summarizes structured tool result without listing data.

        Structured summaries must not retain individual listing records.

        Returns:
            None.
        """
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
        """Verify that ignores non mcp paths.

        The logging hook is limited to the MCP endpoint and must leave normal API traffic alone.

        Returns:
            None.
        """
        with patch("functions.mcp_usage_logging.logger.info") as log_info:
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        log_info.assert_not_called()

    def test_summarizes_stale_session_bundle(self) -> None:
        messages = [
            {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"},
            {"jsonrpc": "2.0", "method": "notifications/resources/list_changed"},
            {"jsonrpc": "2.0", "id": 7, "result": {"structuredContent": {
                "result": {"listing_type": "lease", "total_results": 0,
                           "page": 1, "page_size": 20}
            }}},
        ]
        response = Response(json.dumps(messages), mimetype="application/json")
        original_body = response.get_data()
        self.assertEqual(
            _result_summary(response, request_id=7),
            "success(listing_type=lease,total_results=0,page=1,page_size=20)",
        )
        self.assertEqual(response.get_data(), original_body)

    def test_selects_matching_bundled_reply_and_preserves_errors(self) -> None:
        for reply, expected in [
            ({"result": {"isError": True}}, "tool_error"),
            ({"error": {"code": -32602, "message": "Invalid params"}}, "rpc_error"),
        ]:
            with self.subTest(expected=expected):
                response = Response(json.dumps([
                    {"id": 1, "result": {}}, {"id": 2, **reply},
                ]), mimetype="application/json")
                self.assertEqual(_result_summary(response, request_id=2), expected)
                self.assertEqual(_result_summary(response, request_id=3), "missing")
                self.assertEqual(_result_summary(response), "missing")

    def test_notification_only_bundle_has_no_result(self) -> None:
        response = Response(json.dumps([
            {"method": "notifications/tools/list_changed"}, None, "invalid",
        ]), mimetype="application/json")
        self.assertEqual(_result_summary(response, request_id=1), "missing")


if __name__ == "__main__":
    unittest.main()
