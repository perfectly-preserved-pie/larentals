"""Populate only AC and dishwasher fields, saving each lookup for safe resume."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

import requests

from functions.data_paths import CHECKPOINT_DIR, LARENTALS_DB_PATH
from functions.webscraping_utils import (
    HostCircuitOpen,
    extract_listing_amenities,
    get_with_backoff,
)


MARKETS = ("buy", "lease")
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Tenant": "QUdZfFBST0R8Q09NUEFOWXwx",
    "Origin": "https://www.theagencyre.com",
    "Referer": "https://www.theagencyre.com/",
    "Accept": "*/*",
}


def fetch_amenities(mls_number: str, listing_url: str | None) -> dict[str, str | None]:
    """Read labeled amenities without running image or geocoding work.

    Use the board from an Agency listing URL when available, otherwise the
    pipeline's CLR default. The API can JSON-encode its detail object twice
    depending on Accept headers, so decode that wrapper before reading labels.
    HTTP errors propagate so failures remain retryable.

    Args:
        mls_number: MLS identifier from the existing listing table.
        listing_url: Existing provider URL used to identify the MLS board.

    Returns:
        AC and dishwasher statuses, including unknowns in successful responses.
    """
    match = re.search(r"theagencyre\.com/[^/]+/([a-z0-9_]+)/", listing_url or "", re.I)
    board = match.group(1).lower() if match else "clr"
    response = get_with_backoff(
        f"https://search-service.idcrealestate.com/api/property/en_US/d4/detail/{board}/{mls_number}",
        headers=HEADERS,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("Provider returned a non-object listing payload")
    details = payload.get("AddtionalPropertyInfo", payload.get("AdditionalPropertyInfo")) or {}
    fields = (details.get("Item") or []) if isinstance(details, dict) else []
    if isinstance(fields, dict):
        fields = [fields]
    if not isinstance(fields, list):
        fields = []
    return extract_listing_amenities([field for field in fields if isinstance(field, dict)])


def backfill_amenities(db_path: Path, checkpoint_path: Path, *, limit: int | None = None) -> dict[str, Any]:
    """Apply amenity-only updates and checkpoint successful provider lookups.

    Each row commits independently so a long pass can be interrupted and
    resumed. Cached outcomes are applied again, making resume safe even if a
    prior process stopped between saving the lookup and updating the listing.
    Existing confirmed statuses survive omitted provider fields. A host circuit
    stops the pass rather than rapidly marking thousands of rows as failures.

    Args:
        db_path: Existing canonical listing database to enrich in place.
        checkpoint_path: Separate SQLite file holding reusable lookup outcomes.
        limit: Optional cap on uncached lookups for a smoke run.

    Returns:
        Counts of saved, cached, unavailable, and failed listing lookups.
    """
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"processed": 0, "cached": 0, "unavailable": 0, "failed": 0, "stopped": False}
    with sqlite3.connect(db_path, timeout=30) as database, sqlite3.connect(checkpoint_path) as checkpoint:
        checkpoint.execute("""CREATE TABLE IF NOT EXISTS amenity_lookup (
            market TEXT, mls_number TEXT, listing_url TEXT, status TEXT,
            has_ac TEXT, has_dishwasher TEXT, error TEXT, updated_at TEXT,
            PRIMARY KEY (market, mls_number))""")
        checkpoint.commit()
        for market in MARKETS:
            columns = {row[1] for row in database.execute(f'PRAGMA table_info("{market}")')}
            if not columns:
                raise ValueError(f"Missing listing table: {market}")
            for column in ("has_ac", "has_dishwasher"):
                if column not in columns:
                    database.execute(f'ALTER TABLE "{market}" ADD COLUMN "{column}" TEXT')
            database.commit()
        total = sum(database.execute(f'SELECT COUNT(*) FROM "{market}"').fetchone()[0] for market in MARKETS)
        attempts = 0
        pending_rows = [
            (market, *row)
            for market in MARKETS
            for row in database.execute(f'SELECT mls_number, listing_url FROM "{market}" ORDER BY mls_number').fetchall()
        ]
        pending_rows.sort(key=lambda row: str(row[1]))
        for market, raw_mls, raw_url in pending_rows:
            mls = str(raw_mls).strip()
            url = str(raw_url or "")
            cached = checkpoint.execute(
                "SELECT status, has_ac, has_dishwasher, listing_url FROM amenity_lookup WHERE market = ? AND mls_number = ?",
                (market, mls),
            ).fetchone()
            if cached and cached[0] in {"success", "unavailable"} and cached[3] == url:
                status, ac, dishwasher, _ = cached
                summary["cached"] += 1
            else:
                if limit is not None and attempts >= limit:
                    summary["stopped"] = True
                    return summary
                attempts += 1
                status, ac, dishwasher, error = "success", None, None, None
                try:
                    amenities = fetch_amenities(mls, url)
                    ac, dishwasher = amenities["has_ac"], amenities["has_dishwasher"]
                except HostCircuitOpen as exc:
                    summary["stopped"] = True
                    print(json.dumps({"stopped": "host_circuit", "message": str(exc), **summary}), flush=True)
                    return summary
                except (requests.RequestException, ValueError) as exc:
                    code = exc.response.status_code if isinstance(exc, requests.HTTPError) and exc.response is not None else None
                    status = "unavailable" if code in {404, 410} else "failed"
                    error = str(exc)
                checkpoint.execute(
                    "INSERT OR REPLACE INTO amenity_lookup VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (market, mls, url, status, ac, dishwasher, error, datetime.now(timezone.utc).isoformat()),
                )
                checkpoint.commit()
            if status == "failed":
                summary["failed"] += 1
            else:
                database.execute(
                    f'''UPDATE "{market}" SET
                        has_ac = COALESCE(?, has_ac),
                        has_dishwasher = COALESCE(?, has_dishwasher)
                        WHERE mls_number = ?''',
                    (ac, dishwasher, raw_mls),
                )
                database.commit()
                if status == "unavailable":
                    summary["unavailable"] += 1
            summary["processed"] += 1
            print(json.dumps({"market": market, "mls_number": mls, "status": status, "has_ac": ac, "has_dishwasher": dishwasher, "total": total, **summary}), flush=True)
        summary["coverage"] = {
            market: dict(database.execute(
                f'''SELECT 'total', COUNT(*) FROM "{market}" UNION ALL
                    SELECT 'ac_reported', COUNT(*) FROM "{market}" WHERE has_ac IN ('Yes', 'No') UNION ALL
                    SELECT 'dishwasher_reported', COUNT(*) FROM "{market}" WHERE has_dishwasher IN ('Yes', 'No')'''
            ).fetchall()) for market in MARKETS
        }
    return summary


def main() -> None:
    """Run a resumable in-place backfill after creating a database backup.

    The backup is made once; later resumes keep the original pre-backfill copy.
    An interrupted pass exits unsuccessfully so operators can retry it safely.

    Returns:
        None.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=LARENTALS_DB_PATH)
    parser.add_argument("--checkpoint-path", type=Path, default=CHECKPOINT_DIR / "amenities.sqlite")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if not args.db_path.is_file():
        parser.error(f"Database does not exist: {args.db_path}")
    backup = args.checkpoint_path.with_suffix(".before.sqlite")
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        with sqlite3.connect(args.db_path) as source, sqlite3.connect(backup) as destination:
            source.backup(destination)
        print(f"Saved pre-backfill database to {backup}", flush=True)
    summary = backfill_amenities(args.db_path, args.checkpoint_path, limit=args.limit)
    print(json.dumps({"summary": summary}), flush=True)
    if summary["stopped"] or summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
