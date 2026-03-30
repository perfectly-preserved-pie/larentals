from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import requests

DEFAULT_GTFS_ROOT = Path("docker/valhalla/gtfs_feeds")
DEFAULT_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept": "application/zip,application/octet-stream,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass(frozen=True)
class GtfsFeed:
    """
    Static GTFS feed metadata used by the downloader CLI.

    Args:
        key: Stable CLI key used to select the feed.
        label: Human-readable agency label.
        url: Static GTFS ZIP download URL.
        headers: Optional per-feed HTTP headers.
    """

    key: str
    label: str
    url: str
    headers: Mapping[str, str] | None = None


GTFS_FEEDS: tuple[GtfsFeed, ...] = (
    GtfsFeed("metro_bus", "LA Metro Bus", "https://gitlab.com/LACMTA/gtfs_bus/raw/master/gtfs_bus.zip"),
    GtfsFeed("metro_rail", "LA Metro Rail", "https://gitlab.com/LACMTA/gtfs_rail/raw/master/gtfs_rail.zip"),
    GtfsFeed("culver_citybus", "Culver CityBus", "https://web.culvercity.org/gtfs/gtfsexport.zip"),
    GtfsFeed("big_blue_bus", "Big Blue Bus", "https://gtfs.bigbluebus.com/current.zip"),
    GtfsFeed(
        "metrolink",
        "Metrolink",
        "https://metrolinktrains.com/globalassets/about/gtfs/gtfs.zip",
        headers={
            "Referer": "https://metrolinktrains.com/about/gtfs/",
            "Origin": "https://metrolinktrains.com",
        },
    ),
    GtfsFeed("ladot", "LADOT Transit", "https://ladotbus.com/gtfs"),
    GtfsFeed("foothill", "Foothill Transit", "https://foothilltransit.rideralerts.com/myStop/gtfs-zip.ashx"),
    GtfsFeed("torrance", "Torrance Transit", "https://transit.torranceca.gov/home/showpublisheddocument/16673/639033196638970000"),
)

GTFS_FEEDS_BY_KEY = {feed.key: feed for feed in GTFS_FEEDS}


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments for the GTFS downloader.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Download and unzip curated LA-area static GTFS feeds for Valhalla."
    )
    parser.add_argument(
        "feeds",
        nargs="*",
        help="Feed keys to download, or `all` for the full curated set.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the currently supported feed keys and exit.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_GTFS_ROOT),
        help="Directory where feed subfolders should be written.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="HTTP timeout used for each feed download.",
    )
    return parser.parse_args()


def list_feeds() -> None:
    """
    Print the supported GTFS feed keys.

    Returns:
        None.
    """
    print("Available GTFS feed keys:")
    for feed in GTFS_FEEDS:
        print(f"  {feed.key:<16} {feed.label}")


def resolve_requested_feeds(feed_keys: list[str]) -> list[GtfsFeed]:
    """
    Normalize CLI feed selectors into concrete feed definitions.

    Args:
        feed_keys: Raw feed keys from the command line.

    Returns:
        Ordered list of feed definitions to download.

    Raises:
        ValueError: If any requested key is unknown.
    """
    if not feed_keys:
        raise ValueError("No feeds specified. Use `all` or one or more feed keys.")

    if len(feed_keys) == 1 and feed_keys[0] == "all":
        return list(GTFS_FEEDS)

    resolved: list[GtfsFeed] = []
    for key in feed_keys:
        feed = GTFS_FEEDS_BY_KEY.get(key)
        if feed is None:
            raise ValueError(f"Unknown GTFS feed key: {key}")
        resolved.append(feed)
    return resolved


def extract_zip_archive(archive_path: Path, destination_dir: Path) -> None:
    """
    Replace a destination directory with the contents of a GTFS ZIP archive.

    Args:
        archive_path: Downloaded GTFS ZIP archive path.
        destination_dir: Feed-specific output directory.

    Returns:
        None.
    """
    destination_dir.mkdir(parents=True, exist_ok=True)
    for child in destination_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(destination_dir)


def download_feed(
    *,
    feed: GtfsFeed,
    output_root: Path,
    timeout_seconds: float,
) -> None:
    """
    Download and unpack a single GTFS feed.

    Args:
        feed: Feed metadata describing what to fetch.
        output_root: Root directory for feed subfolders.
        timeout_seconds: Per-request timeout.

    Returns:
        None.
    """
    destination_dir = output_root / feed.key
    print(f"Downloading {feed.key:<16} {feed.url}")
    request_headers = {
        **DEFAULT_REQUEST_HEADERS,
        **dict(feed.headers or {}),
    }

    with tempfile.NamedTemporaryFile(prefix=f"{feed.key}.", suffix=".zip", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        with requests.get(
            feed.url,
            headers=request_headers,
            stream=True,
            timeout=timeout_seconds,
        ) as response:
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise requests.HTTPError(
                    f"{exc}. Feed={feed.key} URL={feed.url}",
                    response=response,
                ) from exc
            with temp_path.open("wb") as output_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output_file.write(chunk)

        extract_zip_archive(temp_path, destination_dir)
        (destination_dir / ".source_url").write_text(f"{feed.url}\n", encoding="utf-8")
        (destination_dir / ".agency_name").write_text(f"{feed.label}\n", encoding="utf-8")
        print(f"Saved {feed.key:<16} -> {destination_dir}")
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> None:
    """
    Run the GTFS downloader CLI.

    Returns:
        None.
    """
    args = parse_args()

    if args.list:
        list_feeds()
        return

    try:
        selected_feeds = resolve_requested_feeds(list(args.feeds))
    except ValueError as exc:
        raise SystemExit(f"{exc}\n\nUse `uv run download-gtfs-feeds --list` to see valid keys.") from exc

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        for feed in selected_feeds:
            download_feed(
                feed=feed,
                output_root=output_root,
                timeout_seconds=float(args.timeout_seconds),
            )
    except requests.RequestException as exc:
        raise SystemExit(f"Failed downloading GTFS feed: {exc}") from exc


if __name__ == "__main__":
    main()
