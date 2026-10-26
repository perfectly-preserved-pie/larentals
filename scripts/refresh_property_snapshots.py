"""Refresh saved property records separately from web requests."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
from typing import Sequence

from loguru import logger

from api.listings import build_lahd_listing_summary
from functions.data_paths import LARENTALS_DB_PATH
from functions.property_snapshots import (
    _read_saved,
    property_identity_key,
    refresh_housing_snapshot,
    refresh_property_snapshot,
)


def load_snapshot_listings(db_path: Path, markets: Sequence[str], mls_numbers: Sequence[str] = ()) -> list[dict]:
    """Load stored identities, prioritizing uncached and newer properties.

    A property listed in both markets needs only one snapshot. Match explicit
    MLS selections before deduplicating; do not rebuild or modify the MLS tables.
    """
    identities = {}
    with sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        for market in markets:
            if market not in {"buy", "lease"}:
                raise ValueError("Unknown listing market")
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({market})")}
            if not columns:
                continue
            selected = [name for name in ("mls_number", "full_street_address", "zip_code", "city", "latitude", "longitude", "listed_date") if name in columns]
            where = " WHERE mls_number IN (" + ",".join("?" for _ in mls_numbers) + ")" if mls_numbers else ""
            for row in conn.execute(f"SELECT {', '.join(selected)} FROM {market}{where}", tuple(mls_numbers)):
                listing = dict(row)
                identities.setdefault(property_identity_key(listing), listing)
    listings = sorted(identities.values(), key=lambda listing: str(listing.get("listed_date") or ""), reverse=True)
    # A limited backfill progresses to uncached homes before revisiting existing
    # reports, rather than refreshing the same first batch on every invocation.
    return sorted(listings, key=lambda listing: _read_saved(property_identity_key(listing)) is not None)


def refresh_snapshots(listings: Sequence[dict], *, workers: int = 2, force: bool = False) -> dict[str, int]:
    """Refresh property and housing snapshots with bounded source concurrency.

    Each property commits independently, so a stopped backfill can resume and
    an individual source outage cannot roll back previously successful homes.
    """
    counts = {"processed": 0, "partial": 0, "failed": 0}

    def refresh(listing: dict) -> str:
        """Publish one property's due sources and preserve its prior facts.

        Errors are counted per property so later addresses can still refresh.
        """
        try:
            snapshot = refresh_property_snapshot(listing, force=force)
            housing = refresh_housing_snapshot(listing, build_lahd_listing_summary, force=force)
            partial = any(snapshot[name].get("refresh_failed") for name in ("fire", "flood", "zimas", "permits")) or housing.get("refresh_failed")
            logger.info("Saved property snapshot for MLS {}", listing.get("mls_number"))
            return "partial" if partial else "complete"
        except Exception:
            logger.exception("Property snapshot refresh failed for MLS {}", listing.get("mls_number"))
            return "failed"

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as pool:
        for status in pool.map(refresh, listings):
            counts["processed"] += 1
            if status in counts:
                counts[status] += 1
    return counts


def main() -> None:
    """Build server snapshots manually or from a scheduled maintenance job.

    Source-specific refresh intervals make daily invocations inexpensive for
    unchanged sections. Use MLS selections for targeted recovery or a limit
    for resumable backfills; ordinary popup requests never invoke this command.
    """
    parser = argparse.ArgumentParser(description="Refresh cached property records without slowing listing requests.")
    parser.add_argument("--db-path", type=Path, default=LARENTALS_DB_PATH)
    parser.add_argument("--market", choices=("buy", "lease", "all"), default="all")
    parser.add_argument("--mls", action="append", default=[], help="Refresh only these MLS IDs; repeat for multiple listings.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum unique properties to process this run.")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--force", action="store_true", help="Refresh even sections still within their scheduled age.")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    markets = ("buy", "lease") if args.market == "all" else (args.market,)
    listings = load_snapshot_listings(args.db_path, markets, args.mls)
    if args.mls and not listings:
        parser.error("No matching listing IDs were found")
    if args.limit is not None:
        listings = listings[:args.limit]
    counts = refresh_snapshots(listings, workers=args.workers, force=args.force)
    print(json.dumps(counts))
    if counts["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
