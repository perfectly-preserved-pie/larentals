from flask import Flask

from functions.security_headers import register_security_headers


def test_csp_covers_documents_api_and_errors() -> None:
    """Apply the CSP to documents, API responses, health checks, and 404s.

    Check for a single enforced policy so inherited or duplicate headers cannot conflict.

    Returns:
        None.
    """
    server = Flask(__name__)
    register_security_headers(server)
    server.add_url_rule("/", endpoint="index", view_func=lambda: "<html></html>")
    server.add_url_rule("/api", endpoint="api", view_func=lambda: {"ok": True})
    server.add_url_rule("/health", endpoint="health", view_func=lambda: "ok")

    with server.test_client() as client:
        for path in ("/", "/api", "/health", "/missing"):
            response = client.get(path)
            policies = response.headers.getlist("Content-Security-Policy")
            assert len(policies) == 1
            directives = dict(part.split(" ", 1) for part in policies[0].split("; "))
            assert directives["default-src"] == "'none'"
            assert directives["object-src"] == "'none'"
            assert directives["frame-ancestors"] == "'none'"
            assert "https:" not in directives["script-src"].split()
            assert "https:" not in directives["connect-src"].split()
            assert "https:" not in directives["img-src"].split()
            assert "'unsafe-inline'" not in directives["script-src"]
            assert "'unsafe-eval'" not in directives["script-src"]
            assert directives["script-src-attr"] == "'none'"
            assert "Content-Security-Policy-Report-Only" not in response.headers


def test_hashes_are_resolved_after_request_setup() -> None:
    """Include script hashes registered during request setup.

    This models Dash initializing page callbacks on its first request.

    Returns:
        None.
    """
    server = Flask(__name__)
    hashes = []
    register_security_headers(server, lambda: hashes)

    @server.before_request
    def register_lazy_callback() -> None:
        """Add a script hash during request setup.

        The response hook must see the hash even though it was absent at registration time.

        Returns:
            None.
        """
        hashes.append("'sha256-lazy-callback'")

    with server.test_client() as client:
        response = client.get("/")
        assert "'sha256-lazy-callback'" in response.headers["Content-Security-Policy"]
