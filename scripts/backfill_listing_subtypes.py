"""Fill missing buy and lease subtypes from The Agency without other enrichment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import requests

from functions.data_paths import CHECKPOINT_DIR, LARENTALS_DB_PATH
from functions.webscraping_utils import (
    HostCircuitOpen,
    extract_agency_subtype,
    fetch_agency_detail,
)


MARKETS = ("buy", "lease")
MISSING_SUBTYPE_SQL = "LOWER(TRIM(COALESCE(subtype, ''))) IN ('', 'unknown', 'none', 'null', 'nan', 'n/a')"


def backfill_subtypes(db_path: Path, checkpoint_path: Path, *, limit: int | None = None) -> dict:
    """Update only missing subtypes, committing each lookup for safe resume.

    Successful lookups, including absent types and HTTP 404/410, are cached by
    market, MLS, and listing URL. Transport and decoding failures stay retryable.
    Save each outcome before applying it so a crash between commits can replay
    the update. The SQL guard also preserves a subtype filled by another process
    while the API request was running. A host circuit ends the pass immediately.

    Args:
        db_path: Existing listing database containing buy and lease tables.
        checkpoint_path: Separate SQLite file for subtype-only lookup outcomes.
        limit: Maximum uncached requests; cached outcomes do not use this budget.

    Returns:
        Counts of requests, cached outcomes, updates, missing types, and failures,
        plus a stop reason when limited or interrupted by the host circuit.
    """
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    if db_path.resolve() == checkpoint_path.resolve():
        raise ValueError("Listing and checkpoint databases must be separate")
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    summary = dict(requested=0, cached=0, updated=0, not_found=0, unavailable=0, failed=0, stopped=None)
    with sqlite3.connect(db_path, timeout=30) as database, sqlite3.connect(checkpoint_path) as checkpoint:
        for market in MARKETS:
            columns = {row[1] for row in database.execute(f'PRAGMA table_info("{market}")')}
            if not {"mls_number", "listing_url", "subtype"} <= columns:
                raise ValueError(f"Missing required listing columns in {market}")
        checkpoint.execute("""CREATE TABLE IF NOT EXISTS subtype_lookup (
            market TEXT, mls_number TEXT, listing_url TEXT, status TEXT,
            subtype TEXT, error TEXT, updated_at TEXT,
            PRIMARY KEY (market, mls_number))""")
        checkpoint.commit()
        pending = [
            (market, *row)
            for market in MARKETS
            for row in database.execute(
                f'SELECT mls_number, listing_url FROM "{market}" WHERE {MISSING_SUBTYPE_SQL} ORDER BY mls_number'
            ).fetchall()
        ]
        for market, raw_mls, raw_url in pending:
            mls, url = str(raw_mls).strip(), str(raw_url or "")
            cached = checkpoint.execute(
                "SELECT status, subtype, listing_url FROM subtype_lookup WHERE market = ? AND mls_number = ?",
                (market, mls),
            ).fetchone()
            if cached and cached[0] in {"success", "not_found", "unavailable"} and cached[2] == url:
                status, subtype, _ = cached
                summary["cached"] += 1
            else:
                if limit is not None and summary["requested"] >= limit:
                    summary["stopped"] = "limit"
                    break
                summary["requested"] += 1
                subtype, error = None, None
                try:
                    subtype = extract_agency_subtype(fetch_agency_detail(mls, url))
                    status = "success" if subtype else "not_found"
                except HostCircuitOpen:
                    summary["stopped"] = "host_circuit"
                    break
                except (requests.RequestException, ValueError) as exc:
                    code = exc.response.status_code if isinstance(exc, requests.HTTPError) and exc.response is not None else None
                    status = "unavailable" if code in {404, 410} else "failed"
                    error = str(exc)
                checkpoint.execute(
                    "INSERT OR REPLACE INTO subtype_lookup VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (market, mls, url, status, subtype, error, datetime.now(timezone.utc).isoformat()),
                )
                checkpoint.commit()
            if subtype:
                cursor = database.execute(
                    f'UPDATE "{market}" SET subtype = ? WHERE mls_number = ? AND {MISSING_SUBTYPE_SQL}',
                    (subtype, raw_mls),
                )
                database.commit()
                summary["updated"] += cursor.rowcount
            elif status in {"not_found", "unavailable", "failed"}:
                summary[status] += 1
            print(json.dumps({"market": market, "mls_number": mls, "status": status, "subtype": subtype, **summary}), flush=True)
    return summary


def main() -> None:
    """Back up the listing database once before a resumable subtype-only pass.

    A request limit permits short API smoke runs. Reusing the checkpoint skips
    completed lookups, and the original backup remains intact across resumes.
    Failures or a host circuit produce an unsuccessful exit for retry tooling;
    reaching an explicitly requested limit is a normal completion.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=LARENTALS_DB_PATH)
    parser.add_argument("--checkpoint-path", type=Path, default=CHECKPOINT_DIR / "subtypes.sqlite")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if not args.db_path.is_file():
        parser.error(f"Database does not exist: {args.db_path}")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.db_path.resolve() == args.checkpoint_path.resolve():
        parser.error("Listing and checkpoint databases must be separate")
    backup = args.checkpoint_path.with_suffix(".before.sqlite")
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        with sqlite3.connect(args.db_path) as source, sqlite3.connect(backup) as destination:
            source.backup(destination)
        print(f"Saved pre-backfill database to {backup}", flush=True)
    summary = backfill_subtypes(args.db_path, args.checkpoint_path, limit=args.limit)
    print(json.dumps({"summary": summary}), flush=True)
    if summary["failed"] or summary["stopped"] == "host_circuit":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
