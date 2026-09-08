"""Discoverable REST search and schemas for the existing public API."""

from collections.abc import Mapping
from types import UnionType
from typing import Any, Literal, get_args, get_origin, get_type_hints, is_typeddict
import sqlite3
import re

from flask import Flask, Response, abort, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

from functions.mcp_listings import ListingSearchResult, search_listings_in_database

PARAMETERS: dict[str, dict[str, Any]] = {
    "listing_type": {"type": "string", "enum": ["lease", "buy"], "description": "Required market: rentals or homes for sale."},
    "location": {"type": "string", "maxLength": 100, "description": "Text fragment matched against city, ZIP code, or address; not a radius search."},
    "property_type": {"type": "string", "maxLength": 100, "description": "Property subtype text filter."},
    "min_price": {"type": "integer", "minimum": 0, "description": "Minimum USD monthly rent (lease) or asking price (buy)."},
    "max_price": {"type": "integer", "minimum": 0, "description": "Maximum USD monthly rent (lease) or asking price (buy)."},
    "min_bedrooms": {"type": "integer", "minimum": 0, "description": "Minimum bedrooms."},
    "min_bathrooms": {"type": "integer", "minimum": 0, "description": "Minimum bathrooms, in whole-number increments."},
    "min_square_feet": {"type": "integer", "minimum": 0, "description": "Minimum interior square feet."},
    "pet_friendly": {"type": "boolean", "description": "Filter by the dataset's pet policy classification."},
    "furnished": {"type": "boolean", "description": "Furnished classification; lease only."},
    "min_lot_size": {"type": "integer", "minimum": 0, "description": "Minimum lot square feet; buy only."},
    "max_hoa_fee": {"type": "integer", "minimum": 0, "description": "Maximum recorded HOA fee in USD; buy only. Check fee frequency in results."},
    "senior_community": {"type": "boolean", "description": "Senior community classification; buy only."},
    "listed_after": {"type": "string", "format": "date", "description": "Include listings on or after this YYYY-MM-DD date."},
    "sort": {"type": "string", "enum": ["newest", "price_low_to_high", "price_high_to_low", "most_bedrooms", "largest"], "default": "newest", "description": "Result ordering with stable MLS-number tie breaking."},
    "page": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 1, "description": "One-based result page."},
    "page_size": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10, "description": "Maximum listings per response."},
}
ERROR_SCHEMA = {
    "type": "object", "required": ["status", "message", "error"],
    "properties": {
        "status": {"type": "string", "const": "error"},
        "message": {"type": "string"},
        "error": {"type": "object", "required": ["code", "message", "hint"], "properties": {
            "code": {"type": "string"}, "message": {"type": "string"}, "hint": {"type": "string"},
        }},
    },
}


def parse_search_arguments(arguments: Mapping[str, str]) -> dict[str, Any]:
    """Parse query strings using the same types published in OpenAPI.

    Args:
        arguments: Single-valued query parameters supplied by the caller.

    Returns:
        Typed keyword arguments for the existing database search.

    Raises:
        ValueError: If a parameter is unknown, missing, or incorrectly typed.
    """
    if "listing_type" not in arguments:
        raise ValueError("listing_type is required (lease or buy)")
    parsed: dict[str, Any] = {}
    for name, raw in arguments.items():
        if name not in PARAMETERS:
            raise ValueError(f"Unknown query parameter: {name}")
        schema = PARAMETERS[name]
        value: Any = raw
        if schema["type"] == "integer":
            if not raw.isascii() or not raw.isdecimal():
                raise ValueError(f"{name} must be a nonnegative integer")
            value = int(raw)
        elif schema["type"] == "boolean":
            if raw not in {"true", "false"}:
                raise ValueError(f"{name} must be true or false")
            value = raw == "true"
        if schema.get("format") == "date" and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
            raise ValueError(f"{name} must use YYYY-MM-DD format")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"{name} must be one of: {', '.join(schema['enum'])}")
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{name} must be at least {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{name} must be at most {schema['maximum']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{name} must be at most {schema['maxLength']} characters")
        parsed[name] = value
    return parsed


def type_schema(annotation: Any) -> dict[str, Any]:
    """Translate the search result's Python types to JSON Schema 2020-12.

    Args:
        annotation: A supported primitive, container, union, literal, or TypedDict.

    Returns:
        An inline schema without external references.
    """
    origin = get_origin(annotation)
    args = get_args(annotation)
    if is_typeddict(annotation):
        return {"type": "object", "required": list(get_type_hints(annotation)),
                "properties": {key: type_schema(value) for key, value in get_type_hints(annotation).items()}}
    if origin is UnionType:
        return {"anyOf": [type_schema(arg) for arg in args]}
    if origin is Literal:
        return {"type": "string", "enum": list(args)}
    if origin is list:
        return {"type": "array", "items": type_schema(args[0])}
    if origin is dict:
        return {"type": "object", "additionalProperties": type_schema(args[1])}
    if annotation is Any:
        return {}
    return {"type": {str: "string", int: "integer", float: "number", bool: "boolean", type(None): "null"}[annotation]}


def json_response_schema(description: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Wrap a schema in an OpenAPI JSON response object.

    Args:
        description: Human-readable response meaning.
        schema: JSON Schema for the response body.

    Returns:
        A response object with media type and schema.
    """
    return {"description": description, "content": {"application/json": {"schema": schema}}}


def build_openapi(base_url: str) -> dict[str, Any]:
    """Describe all product REST endpoints, including existing UI endpoints.

    Args:
        base_url: Canonical server origin to publish in the document.

    Returns:
        A self-contained OpenAPI 3.1 document.
    """
    errors = {code: json_response_schema(description, {"$ref": "#/components/schemas/Error"})
              for code, description in {"400": "Invalid request; correct fields using error.hint.", "404": "Endpoint or listing not found.",
                                        "405": "Method not allowed; inspect Allow.", "500": "Unexpected server failure; retry later.",
                                        "503": "Listing data unavailable; retry later."}.items()}
    paths: dict[str, Any] = {
        "/api": {"get": {"operationId": "discoverApi", "description": "Discover public WhereToLive.LA REST and MCP interfaces without authentication.",
                           "responses": {"200": json_response_schema("Discovery links.", {"type": "object", "additionalProperties": {"type": "string"}}), **errors}}},
        "/api/listings": {"get": {"operationId": "searchListings", "description": "Search current Los Angeles County listing data with bounded pagination. Prices are USD rent per month for lease or asking price for buy. Inclusion does not guarantee availability. Return source links and data_as_of to users.",
            "parameters": [{"name": name, "in": "query", "required": name == "listing_type", "description": schema["description"], "schema": schema} for name, schema in PARAMETERS.items()],
            "responses": {"200": json_response_schema("Matching listings, data date, and pagination.", {"$ref": "#/components/schemas/ListingSearchResult"}), **errors}}},
    }
    for market in ("lease", "buy"):
        for suffix, operation, description, schema in (
            ("listing-details", "ListingDetails", "Get listing fields and available LA housing record summaries. Missing listings return 404; null fields are unknown.",
             {"type": "object", "properties": {"mls_number": {"type": ["string", "null"]}, "lahd_property_summary": {"type": "object"}},
              "additionalProperties": {"type": ["string", "number", "boolean", "object", "null"]}}),
            ("isp-options", "IspOptions", "Get broadband provider context. An empty array means no recorded options and does not establish service availability.",
             {"type": "array", "items": {"type": "object", "properties": {"dba": {"type": ["string", "null"]}},
                                          "additionalProperties": {"type": ["string", "number", "null"]}}}),
        ):
            paths[f"/api/{market}/{suffix}/{{listing_id}}"] = {"get": {
                "operationId": f"get{market.title()}{operation}", "description": description,
                "parameters": [{"name": "listing_id", "in": "path", "required": True, "description": "MLS number returned by search.", "schema": {"type": "string"}}],
                "responses": {"200": json_response_schema("Listing data.", schema), **errors},
            }}
    paths["/report_listing"] = {"post": {"operationId": "reportListingIssue", "description": "Write a correction report for an actual issue identified by a person. This does not contact the listing representative or edit source data.",
        "requestBody": {"required": True, "content": {"application/json": {"schema": {
            "type": "object", "required": ["mls_number", "option"], "properties": {
                "mls_number": {"type": "string", "minLength": 1, "maxLength": 64},
                "option": {"type": "string", "enum": ["Wrong Location", "Unavailable/Sold/Rented", "Wrong Details", "Incorrect Price", "Other"]},
                "text": {"type": "string", "maxLength": 2000},
                "page_path": {"type": "string", "default": "/", "description": "Originating map path: / for rentals or /buy for sales."},
            }}}}},
        "responses": {"200": json_response_schema("Report stored.", {"type": "object", "required": ["status"], "properties": {"status": {"type": "string", "const": "success"}}}), **errors}}}
    return {"openapi": "3.1.1", "info": {"title": "WhereToLive.LA public API", "version": "1.0.0",
            "description": "Public listing search and property context. No API key required. Bounded read-only search; no REST request quota or SLA is promised.",
            "contact": {"email": "hey@wheretolive.la", "url": f"{base_url}/contact"}},
            "servers": [{"url": base_url}], "security": [], "paths": paths,
            "externalDocs": {"description": "WhereToLive.LA developer guide", "url": f"{base_url}/developers"},
            "components": {"schemas": {"Error": ERROR_SCHEMA, "ListingSearchResult": type_schema(ListingSearchResult)}}}


def register_public_api(server: Flask, db_path: str, base_url: str) -> None:
    """Register discovery, OpenAPI, and read-only listing search routes.

    Args:
        server: Flask app serving the API.
        db_path: Existing listing database, opened read-only by search.
        base_url: Canonical public origin used in links.

    Returns:
        None.
    """
    @server.get("/openapi.json")
    def openapi() -> Response:
        """Return a self-contained OpenAPI document.

        Returns:
            JSON schema document.
        """
        return jsonify(build_openapi(base_url))

    @server.get("/api")
    def api_discovery() -> Response:
        """Return predictable entry points for API clients.

        Returns:
            Public API identity and links.
        """
        return jsonify(name="WhereToLive.LA", documentation=f"{base_url}/developers",
                       openapi=f"{base_url}/openapi.json", listings=f"{base_url}/api/listings",
                       mcp=f"{base_url}/_mcp", authentication="none")

    @server.get("/api/listings")
    def search() -> Response:
        """Search the existing listing dataset with typed query validation.

        Returns:
            A bounded search result as JSON.
        """
        try:
            if any(len(values) != 1 for _, values in request.args.lists()):
                raise ValueError("Query parameters must not be repeated")
            arguments = parse_search_arguments(request.args)
            result = search_listings_in_database(db_path, **arguments)
        except ValueError as exc:
            abort(400, str(exc))
        return jsonify(result)


def api_error_response(error: Exception) -> Response:
    """Return structured API errors and preserve normal non-API handling.

    Args:
        error: HTTP or unexpected exception raised during request processing.

    Returns:
        JSON for API failures; native HTTP response for other routes.
    """
    if not (request.path == "/api" or request.path.startswith("/api/") or request.path == "/report_listing"):
        if isinstance(error, HTTPException):
            return error.get_response()
        raise error
    status = error.code if isinstance(error, HTTPException) else (503 if isinstance(error, sqlite3.Error) else 500)
    message = error.description if isinstance(error, HTTPException) and status < 500 else "The service could not complete this request."
    hint = {400: "Correct the request using /openapi.json and /developers.", 404: "Check the endpoint or MLS number; start at /api/listings?listing_type=lease.",
            405: "Use the method documented in /openapi.json and the Allow header.",
            503: "Listing data is temporarily unavailable. Retry later."}.get(status, "Retry later; contact hey@wheretolive.la if the problem persists.")
    code = {400: "invalid_request", 404: "not_found", 405: "method_not_allowed", 503: "data_unavailable"}.get(status, "internal_error")
    response = error.get_response() if isinstance(error, HTTPException) else Response(status=status)
    response.set_data(current_app.json.dumps({"status": "error", "message": message,
                                        "error": {"code": code, "message": message, "hint": hint}}))
    response.content_type = "application/json"
    if status >= 500:
        current_app.logger.error("API request failed", exc_info=error)
    return response


def register_api_errors(server: Flask) -> None:
    """Normalize API errors without changing successful responses or MCP errors.

    Args:
        server: Flask application owning existing and new API routes.

    Returns:
        None.
    """
    server.register_error_handler(Exception, api_error_response)
