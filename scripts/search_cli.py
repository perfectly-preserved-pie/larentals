"""A dependency-free command-line client for the WhereToLive.LA public API."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main(argv: list[str] | None = None) -> int:
    """Fetch a bounded listing page and print JSON for shell workflows.

    Args:
        argv: Optional command arguments, otherwise read from the process.

    Returns:
        Zero on success, one on HTTP/connection/JSON failure.
    """
    parser = argparse.ArgumentParser(description="Search WhereToLive.LA public listings (no API key required).")
    parser.add_argument("--listing-type", required=True, choices=["lease", "buy"])
    parser.add_argument("--location")
    parser.add_argument("--max-price", type=int)
    parser.add_argument("--min-bedrooms", type=int)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--base-url", default="https://wheretolive.la", help="API origin; override for local development.")
    args = vars(parser.parse_args(argv))
    base_url = args.pop("base_url").rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        parser.error("--base-url must use http:// or https://")
    query = urlencode({key: value for key, value in args.items() if value is not None})
    request = Request(f"{base_url}/api/listings?{query}", headers={"Accept": "application/json", "User-Agent": "WhereToLive.LA-CLI/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}", file=sys.stderr)
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"Search failed: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
