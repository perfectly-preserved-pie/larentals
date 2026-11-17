"""Download complete LAHD datasets offline and index the committed snapshot by APN."""

from datetime import datetime, timezone
from functools import lru_cache
import gzip
from pathlib import Path
import re
import tempfile
from typing import Any

import orjson
import requests

from functions.data_paths import LAHD_RECORDS_SNAPSHOT_PATH

DATASETS = {"cases": "eagk-wq48", "violations": "cr8f-uc4j"}
PAGE_SIZE = 50000


def source_metadata(dataset: str) -> dict[str, Any]:
    """Read the source's data revision independently of descriptive metadata.

    Socrata's rowsUpdatedAt changes when records change; a description edit
    should not cause the quarterly job to download and commit identical rows.

    Args:
        dataset: Socrata dataset identifier.

    Returns:
        Dataset identifier and source record revision.
    """
    response = requests.get(f"https://data.lacity.org/api/views/{dataset}.json", timeout=60)
    response.raise_for_status()
    revision = response.json().get("rowsUpdatedAt")
    if not revision:
        raise ValueError(f"Missing data revision for LAHD dataset {dataset}")
    return {"dataset": dataset, "rows_updated_at": revision}


def refresh_records_snapshot(output: Path = LAHD_RECORDS_SNAPSHOT_PATH) -> bool:
    """Download both complete datasets when either source revision changes.

    Paginate raw rows rather than bounded property aggregates. Verify source
    counts and revisions before atomically replacing the previous snapshot;
    an interrupted download or source edit must leave the last good file intact.

    Args:
        output: Committed gzip snapshot included in the Docker build context.

    Returns:
        Whether a new snapshot was written.
    """
    revisions = {kind: source_metadata(dataset) for kind, dataset in DATASETS.items()}
    if output.exists():
        with gzip.open(output, "rb") as source:
            previous = orjson.loads(source.read())
        if previous.get("version") == 1 and previous.get("sources") == revisions:
            return False
    snapshot: dict[str, Any] = {"version": 1, "sources": revisions}
    for kind, dataset in DATASETS.items():
        url = f"https://data.lacity.org/resource/{dataset}.json"
        count_response = requests.get(url, params={"$select": "count(*) AS count"}, timeout=180)
        count_response.raise_for_status()
        expected = int(count_response.json()[0]["count"])
        if expected <= 0:
            raise ValueError(f"LAHD dataset {dataset} unexpectedly contains no rows")
        rows = []
        while len(rows) < expected:
            response = requests.get(url, params={"$limit": PAGE_SIZE, "$offset": len(rows), "$order": ":id"}, timeout=180)
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, list) or not page or not all(isinstance(row, dict) for row in page):
                raise ValueError(f"Incomplete LAHD dataset {dataset} at offset {len(rows)}")
            rows.extend(page)
        if len(rows) != expected or source_metadata(dataset) != revisions[kind]:
            raise ValueError(f"LAHD dataset {dataset} changed during download; retry the refresh")
        snapshot[kind] = rows
    # Recheck both sources after all downloads so they describe one stable pair.
    if any(source_metadata(dataset) != revisions[kind] for kind, dataset in DATASETS.items()):
        raise ValueError("LAHD source revisions changed during the snapshot build")
    snapshot["generated_at"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".tmp", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with temporary_path.open("wb") as destination:
            with gzip.GzipFile(fileobj=destination, mode="wb", mtime=0, filename="") as compressed:
                compressed.write(orjson.dumps(snapshot, option=orjson.OPT_SORT_KEYS))
        temporary_path.replace(output)
    finally:
        temporary_path.unlink(missing_ok=True)
    return True


@lru_cache(maxsize=1)
def _load_snapshot(path: str, mtime_ns: int) -> dict[str, Any]:
    """Index a snapshot once and reuse its raw rows across property requests.

    The file revision invalidates the index after replacement. Gunicorn preload
    builds this index before forking so workers can share the read-only pages.

    Args:
        path: Gzipped snapshot file.
        mtime_ns: Modification timestamp invalidating the process cache.

    Returns:
        APN indexes and snapshot metadata.
    """
    with gzip.open(path, "rb") as source:
        payload = orjson.loads(source.read())
    if payload.get("version") != 1:
        raise ValueError("Unsupported LAHD records snapshot version")
    indexes = {}
    for kind in DATASETS:
        rows = payload.get(kind)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"Missing LAHD {kind} dataset")
        index: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            apn = re.sub(r"\D", "", str(row.get("apn") or ""))
            if apn:
                index.setdefault(apn, []).append(row)
        order_field = "case_filed_date" if kind == "cases" else "violations_cited"
        for records in index.values():
            records.sort(key=lambda row: str(row.get(order_field) or ""), reverse=True)
        indexes[kind] = index
    return {**indexes, "generated_at": payload["generated_at"], "sources": payload["sources"]}


def read_records_snapshot(path: Path = LAHD_RECORDS_SNAPSHOT_PATH) -> dict[str, Any]:
    """Load local record indexes without making any source requests.

    Missing or corrupt snapshots raise so callers can mark records unavailable
    instead of treating a deployment problem as a property with no cases.

    Args:
        path: Committed snapshot copied into the application image.

    Returns:
        Cached APN indexes with download and source revision metadata.
    """
    return _load_snapshot(str(path), path.stat().st_mtime_ns)
