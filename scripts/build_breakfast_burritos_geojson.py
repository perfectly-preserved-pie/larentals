from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from loguru import logger

SOURCE_NAME = "LABreakfastBurrito"
SOURCE_URL = "https://labreakfastburrito.com/"
SOURCE_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRtLslbRsQydGCHn7TxcPZl1682DkrpdXXRgARONtraYuxUrzII6y3Y_pviMvxjDzeryCty8WXhiQwn/"
    "pubhtml?gid=0&single=true"
)
SHEET_HTML_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRtLslbRsQydGCHn7TxcPZl1682DkrpdXXRgARONtraYuxUrzII6y3Y_pviMvxjDzeryCty8WXhiQwn/"
    "pubhtml/sheet?headers=false&gid=0"
)
DEFAULT_OUTPUT_PATH = Path("assets/datasets/breakfast_burritos.geojson")

THREED_FOURD_RE = re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)")
AT_COORDS_RE = re.compile(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
LATLONG_TEXT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a breakfast burrito GeoJSON dataset from the published LABreakfastBurrito sheet.",
    )
    parser.add_argument(
        "--sheet-html-url",
        default=SHEET_HTML_URL,
        help="Published Google Sheets HTML URL to parse.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to the GeoJSON file to write.",
    )
    return parser.parse_args()


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""

    normalized = value.replace("\xa0", " ").replace("\u200b", " ")
    return " ".join(normalized.split()).strip()


def normalize_name_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize_text(value).lower())


def extract_link_target(anchor: Tag | None) -> str | None:
    if anchor is None:
        return None

    href = normalize_text(anchor.get("href"))
    if not href:
        return None

    parsed = urlparse(href)
    query_target = parse_qs(parsed.query).get("q")
    if query_target:
        return normalize_text(unquote(query_target[0]))
    return href


def parse_numeric(value: str) -> float | None:
    cleaned = normalize_text(value)
    if not cleaned:
        return None

    try:
        return float(cleaned.replace("$", ""))
    except ValueError:
        return None


def parse_explicit_latlong(value: str) -> tuple[float, float] | None:
    match = LATLONG_TEXT_RE.match(normalize_text(value))
    if not match:
        return None

    lat = float(match.group(1))
    lon = float(match.group(2))
    return lat, lon


def extract_coordinates(latlong_text: str, maps_url: str | None) -> tuple[float, float] | None:
    explicit_coords = parse_explicit_latlong(latlong_text)
    if explicit_coords is not None:
        return explicit_coords

    if not maps_url:
        return None

    three_d_four_d_match = THREED_FOURD_RE.search(maps_url)
    if three_d_four_d_match:
        lat = float(three_d_four_d_match.group(1))
        lon = float(three_d_four_d_match.group(2))
        return lat, lon

    at_coords_match = AT_COORDS_RE.search(maps_url)
    if at_coords_match:
        lat = float(at_coords_match.group(1))
        lon = float(at_coords_match.group(2))
        return lat, lon

    return None


def parse_table_row(
    cells: list[Tag],
    *,
    review_url_map: dict[str, str],
) -> dict[str, Any] | None:
    if len(cells) != 11:
        return None

    values = [normalize_text(cell.get_text(" ", strip=True)) for cell in cells]
    restaurant_name = values[1]
    if not restaurant_name:
        return None

    maps_url = extract_link_target(cells[1].find("a"))
    picture_url = extract_link_target(cells[10].find("a"))
    coordinates = extract_coordinates(values[9], maps_url)
    if coordinates is None:
        logger.warning("Skipping {} because no usable coordinates were found.", restaurant_name)
        return None

    rating_value = parse_numeric(values[0])
    price_value = parse_numeric(values[3])
    review_status = (
        "To Be Reviewed"
        if normalize_text(values[7]).upper() == "TO BE REVIEWED" or rating_value is None
        else "Reviewed"
    )
    review_url = review_url_map.get(normalize_name_key(restaurant_name))
    lat, lon = coordinates

    properties: dict[str, Any] = {
        "name": restaurant_name,
        "rating": values[0] or None,
        "rating_value": rating_value,
        "neighborhood": values[2] or None,
        "price": values[3] or None,
        "price_value": price_value,
        "size": values[4] or None,
        "value_rating": values[5] or None,
        "whats_inside": values[6] or None,
        "overall_thoughts": values[7] or None,
        "address": values[8] or None,
        "latlong": values[9] or None,
        "picture_url": picture_url,
        "maps_url": maps_url,
        "review_status": review_status,
        "review_url": review_url,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "source_sheet_url": SOURCE_SHEET_URL,
    }

    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Point",
            "coordinates": [round(lon, 6), round(lat, 6)],
        },
    }


def build_review_url_map(rankings_html: str) -> dict[str, str]:
    soup = BeautifulSoup(rankings_html, "html.parser")
    site_host = urlparse(SOURCE_URL).netloc
    review_url_map: dict[str, str] = {}

    for anchor in soup.find_all("a", href=True):
        link_text = normalize_text(anchor.get_text(" ", strip=True))
        if not link_text:
            continue

        href = urljoin(SOURCE_URL, anchor["href"])
        parsed = urlparse(href)
        if parsed.netloc != site_host:
            continue

        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) != 1 or path_parts[0] in {"about", "editorial", "maps"}:
            continue

        review_url_map[normalize_name_key(link_text)] = href

    logger.info("Resolved {} direct LABreakfastBurrito review URLs.", len(review_url_map))
    return review_url_map


def build_feature_collection(
    sheet_html: str,
    *,
    review_url_map: dict[str, str],
) -> dict[str, Any]:
    soup = BeautifulSoup(sheet_html, "html.parser")
    table = soup.select_one("table.waffle")
    if table is None:
        raise ValueError("Could not find the published sheet table.")

    rows = table.select("tr")[2:]
    features: list[dict[str, Any]] = []
    for row in rows:
        feature = parse_table_row(
            row.find_all("td"),
            review_url_map=review_url_map,
        )
        if feature is not None:
            features.append(feature)

    logger.info("Built breakfast burrito feature collection with {} features.", len(features))
    return {
        "type": "FeatureCollection",
        "features": features,
    }


def fetch_sheet_html(sheet_html_url: str) -> str:
    response = requests.get(
        sheet_html_url,
        timeout=30,
        headers={"User-Agent": "WhereToLive.LA breakfast burrito dataset builder"},
    )
    response.raise_for_status()
    return response.text


def fetch_html(url: str) -> str:
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "WhereToLive.LA breakfast burrito dataset builder"},
    )
    response.raise_for_status()
    return response.text


def write_geojson(feature_collection: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(feature_collection, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    rankings_html = fetch_html(SOURCE_URL)
    review_url_map = build_review_url_map(rankings_html)
    sheet_html = fetch_sheet_html(args.sheet_html_url)
    feature_collection = build_feature_collection(
        sheet_html,
        review_url_map=review_url_map,
    )
    write_geojson(feature_collection, args.output)
    logger.info("Wrote breakfast burrito dataset to {}", args.output)


if __name__ == "__main__":
    main()
