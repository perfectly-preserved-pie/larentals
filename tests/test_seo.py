import unittest
from xml.etree import ElementTree

from functions.seo import (
  build_llms_txt,
  build_robots_txt,
  build_sitemap_xml,
  build_structured_data_script,
  get_public_page_paths,
)


class SeoTest(unittest.TestCase):
  def test_get_public_page_paths_uses_dash_registry_paths(self) -> None:
    page_registry = {
      "pages.lease_page": {"path": "/"},
      "pages.buy_page": {"path": "/buy"},
      "pages.mcp_page": {"path": "/mcp"},
      "pages.details_page": {"path": "/listing/<listing_id>"},
    }

    self.assertEqual(get_public_page_paths(page_registry), ["/", "/buy", "/mcp"])

  def test_build_sitemap_xml_contains_canonical_public_urls(self) -> None:
    sitemap = build_sitemap_xml("https://wheretolive.la", ["/", "/buy", "/mcp"])
    sitemap_text = sitemap.decode("utf-8")
    root = ElementTree.fromstring(sitemap)
    namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls = [
      loc.text
      for loc in root.findall("sitemap:url/sitemap:loc", namespace)
    ]

    self.assertEqual(
      urls,
      [
        "https://wheretolive.la/",
        "https://wheretolive.la/buy",
        "https://wheretolive.la/mcp",
      ],
    )
    self.assertNotIn("_mcp", sitemap_text)

  def test_build_robots_txt_points_to_sitemap(self) -> None:
    robots_txt = build_robots_txt("https://wheretolive.la/")

    self.assertIn("User-agent: *", robots_txt)
    self.assertIn("Allow: /", robots_txt)
    self.assertIn("Sitemap: https://wheretolive.la/sitemap.xml", robots_txt)

  def test_build_llms_txt_describes_primary_ai_search_context(self) -> None:
    llms_txt = build_llms_txt("https://wheretolive.la/")

    self.assertIn("# WhereToLive.LA", llms_txt)
    self.assertIn("[Rental map](https://wheretolive.la/)", llms_txt)
    self.assertIn("[For-sale map](https://wheretolive.la/buy)", llms_txt)
    self.assertIn("[MCP setup](https://wheretolive.la/mcp)", llms_txt)
    self.assertIn("https://wheretolive.la/_mcp", llms_txt)
    self.assertIn("avoid inventing exact listing availability", llms_txt)
    self.assertIn("machine interface, not a browser page", llms_txt)

  def test_build_structured_data_script_contains_web_app_schema(self) -> None:
    script = build_structured_data_script("https://wheretolive.la/")

    self.assertIn('type="application/ld+json"', script)
    self.assertIn('"@type":"WebSite"', script)
    self.assertIn('"@type":"WebApplication"', script)
    self.assertIn('"areaServed":{"@type":"AdministrativeArea"', script)


if __name__ == "__main__":
  unittest.main()
