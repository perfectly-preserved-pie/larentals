"""HTTP content negotiation, server-rendered content, and strict page routing."""

from html import escape
import re
from typing import Any

from dash import Dash
from flask import Response, abort, request
from werkzeug.exceptions import MethodNotAllowed

from api.public import api_error_response
from functions.public_content import BASE_URL, PAGES, page_html, page_markdown
from functions.seo import build_structured_data_script

STATIC_PATHS = {"/developers", "/about", "/contact", "/privacy"}


def page_metadata(path: str) -> str:
    """Create canonical and social metadata from the known page registry.

    Args:
        path: Canonical public path, without query parameters.

    Returns:
        Escaped head tags with a stable canonical origin.
    """
    title, sections = PAGES[path]
    description = sections[0][1][0]
    url = BASE_URL + path
    return (f'<link rel="canonical" href="{url}">'
            f'<meta name="description" content="{escape(description, quote=True)}">'
            f'<meta property="og:title" content="{escape(title, quote=True)}">'
            f'<meta property="og:url" content="{url}">'
            '<meta property="og:type" content="website">'
            f'<meta property="og:image" content="{BASE_URL}/assets/social-card.png">'
            '<meta property="og:image:width" content="1200">'
            '<meta property="og:image:height" content="630">'
            '<meta property="og:image:alt" content="WhereToLive.LA — Los Angeles rental and for-sale maps">'
            '<link rel="alternate" type="application/json" href="/openapi.json" title="OpenAPI">'
            f'<link rel="alternate" type="text/markdown" href="{url}" title="Markdown">')


def register_public_pages(app: Dash) -> None:
    """Add raw page content and intercept only Dash's catch-all for unknown URLs.

    Args:
        app: Dash app whose map and MCP pages must retain their client behavior.

    Returns:
        None.
    """
    server = app.server
    original_interpolate = app.interpolate_index

    def interpolate_index(**kwargs: Any) -> str:
        """Place readable fallback content inside the React mount point.

        Args:
            **kwargs: Index fragments supplied by Dash.

        Returns:
            Original app shell with content that React replaces when mounted.
        """
        path = request.path
        if path in PAGES:
            kwargs["title"] = escape(PAGES[path][0])
            kwargs["app_entry"] = '<div id="react-entry-point">' + page_html(path) + '</div>'
            # Dash emits empty og:image and page metadata before this hook.
            # Replace overlapping tags so crawlers never pick a stale first value.
            kwargs["metas"] = re.sub(
                r'<meta\b[^>]*(?:name|property)="(?:description|og:(?:title|url|type|image))"[^>]*>\s*',
                "", kwargs["metas"],
            ) + page_metadata(path)
        return original_interpolate(**kwargs)

    app.interpolate_index = interpolate_index

    @server.before_request
    def public_page_request() -> Response | None:
        """Negotiate known pages and reject unknown paths captured by Dash.

        Returns:
            Markdown/static HTML/404, or None for the normal Dash handler.
        """
        if request.path in PAGES:
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                raise MethodNotAllowed(valid_methods=["GET", "HEAD", "OPTIONS"])
            if request.method == "OPTIONS":
                response = Response(status=204)
                response.headers["Allow"] = "GET, HEAD, OPTIONS"
                return response
            best = request.accept_mimetypes.best_match(["text/html", "text/markdown"]) if request.headers.get("Accept") else "text/html"
            if best is None:
                return Response("Supported representations: text/html, text/markdown\n", status=406, mimetype="text/plain")
            if best == "text/markdown":
                return Response(page_markdown(request.path), mimetype="text/markdown")
            if request.path in STATIC_PATHS:
                return Response('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
                                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                                f'<title>{escape(PAGES[request.path][0])}</title>' + page_metadata(request.path)
                                + build_structured_data_script(BASE_URL)
                                + '<link rel="stylesheet" href="/assets/css/public-content.css"></head><body>'
                                + page_html(request.path) + '</body></html>', mimetype="text/html")
        # Exact Flask routes, Dash callbacks, asset routes and MCP stay under their owners.
        # Flask may choose the GET catch-all when a path exists for another method.
        if request.url_rule and request.url_rule.rule == "/<path:path>" and request.path not in PAGES:
            adapter = server.url_map.bind_to_environ(request.environ)
            allowed = set(adapter.allowed_methods(request.path)) - {"GET", "HEAD", "OPTIONS"}
            if allowed:
                raise MethodNotAllowed(valid_methods=sorted(allowed | {"OPTIONS"}))
            abort(404)
        return None

    @server.errorhandler(404)
    def page_not_found(error: Any) -> Response:
        """Provide a real Markdown 404 with paths for recovery.

        Args:
            error: Flask's not-found exception, delegated for API paths.

        Returns:
            JSON for unknown APIs, otherwise short Markdown navigation.
        """
        if request.path.startswith("/api/") or request.path == "/api":
            return api_error_response(error)
        return Response('# Not found\n\nThis URL does not exist on WhereToLive.LA.\n\n'
                        '- [Sitemap](https://wheretolive.la/sitemap.xml)\n'
                        '- [Agent instructions](https://wheretolive.la/llms.txt)\n'
                        '- [Developer guide](https://wheretolive.la/developers)\n', status=404, mimetype="text/markdown")

    @server.after_request
    def vary_page_content(response: Response) -> Response:
        """Keep negotiated page variants separate in downstream caches.

        Args:
            response: Page response before Flask-Compress adds its own Vary value.

        Returns:
            Response with Accept appended without erasing other variations.
        """
        if request.path in PAGES:
            response.vary.add("Accept")
        return response
