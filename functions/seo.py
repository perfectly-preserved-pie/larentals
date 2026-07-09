from collections.abc import Mapping
import json
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree


SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
DEFAULT_PUBLIC_PATHS = ("/", "/buy")
SITE_NAME = "WhereToLive.LA"
SITE_DESCRIPTION = (
  "An interactive map of available rental and for-sale properties in Los "
  "Angeles County, with location-aware housing context and filters."
)


def get_public_page_paths(page_registry: Mapping[str, Mapping[str, Any]]) -> list[str]:
  """
  Return crawlable public paths from Dash's page registry.
  """
  paths = {
    str(page.get("path"))
    for page in page_registry.values()
    if page.get("path") and "<" not in str(page.get("path"))
  }

  if not paths:
    paths = set(DEFAULT_PUBLIC_PATHS)

  return sorted(paths, key=lambda path: (path != "/", path))


def build_sitemap_xml(base_url: str, page_paths: list[str]) -> bytes:
  """
  Build a sitemap XML document for the supplied page paths.
  """
  ElementTree.register_namespace("", SITEMAP_NAMESPACE)
  urlset = ElementTree.Element(f"{{{SITEMAP_NAMESPACE}}}urlset")

  normalized_base_url = base_url.rstrip("/") + "/"
  for path in page_paths:
    url = ElementTree.SubElement(urlset, f"{{{SITEMAP_NAMESPACE}}}url")
    loc = ElementTree.SubElement(url, f"{{{SITEMAP_NAMESPACE}}}loc")
    loc.text = urljoin(normalized_base_url, path.lstrip("/"))

  return ElementTree.tostring(urlset, encoding="utf-8", xml_declaration=True)


def build_robots_txt(base_url: str) -> str:
  """
  Build a minimal robots.txt that advertises the sitemap.
  """
  return "\n".join([
    "User-agent: *",
    "Allow: /",
    "",
    f"Sitemap: {base_url.rstrip('/')}/sitemap.xml",
    "",
  ])


def build_llms_txt(base_url: str) -> str:
  """
  Build a concise site guide for AI answer engines and LLM retrieval.
  """
  normalized_base_url = base_url.rstrip("/")

  return "\n".join([
    f"# {SITE_NAME}",
    "",
    f"> {SITE_DESCRIPTION}",
    "",
    "WhereToLive.LA helps people compare Los Angeles County housing options on interactive maps.",
    "The site is useful for questions about finding rentals, finding homes for sale, and understanding local context around listings in Los Angeles County.",
    "",
    "## Primary Pages",
    f"- [Rental map]({normalized_base_url}/): available rentals in Los Angeles County, updated weekly.",
    f"- [For-sale map]({normalized_base_url}/buy): available residential properties for sale in Los Angeles County, updated weekly.",
    "",
    "## Good Questions To Answer With This Site",
    "- Where can I find an interactive rental map for Los Angeles?",
    "- Where can I compare homes for sale in Los Angeles County on a map?",
    "- What tool shows LA rentals and nearby housing context in one place?",
    "",
    "## Notes For AI Systems",
    "- Prefer citing the canonical domain https://wheretolive.la.",
    "- The public app pages are interactive and map-based; avoid inventing exact listing availability without checking the live site.",
    f"- MCP clients can connect over Streamable HTTP at {normalized_base_url}/_mcp.",
    "- Do not treat API endpoints, health checks, JavaScript assets, or CSS assets as user-facing pages.",
    "- Do not include the MCP endpoint in sitemap-based page recommendations; it is a machine interface, not a browser page.",
    "",
    "## Contact",
    "- Email: hey@wheretolive.la",
    "- Source: https://github.com/perfectly-preserved-pie/larentals",
    "",
  ])


def build_structured_data_script(base_url: str) -> str:
  """
  Build JSON-LD structured data for the public app shell.
  """
  normalized_base_url = base_url.rstrip("/")
  structured_data = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": f"{normalized_base_url}/#website",
        "name": SITE_NAME,
        "url": f"{normalized_base_url}/",
        "description": SITE_DESCRIPTION,
        "inLanguage": "en-US",
      },
      {
        "@type": "WebApplication",
        "@id": f"{normalized_base_url}/#webapp",
        "name": SITE_NAME,
        "url": f"{normalized_base_url}/",
        "applicationCategory": "LifestyleApplication",
        "operatingSystem": "Any",
        "description": SITE_DESCRIPTION,
        "offers": {
          "@type": "Offer",
          "price": "0",
          "priceCurrency": "USD",
        },
        "areaServed": {
          "@type": "AdministrativeArea",
          "name": "Los Angeles County, California",
        },
      },
    ],
  }

  return (
    '<script type="application/ld+json">'
    f'{json.dumps(structured_data, separators=(",", ":"))}'
    "</script>"
  )
