"""Serve saved property facts while a separate job refreshes official sources."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import time
from typing import Any, Callable
from loguru import logger

from functions.data_paths import PROPERTY_CONTEXT_CACHE_PATH
from functions import property_context as sources

DAY_SECONDS = 24 * 60 * 60
# These are our refresh targets, not promises about agency publication times.
REFRESH_SECONDS = {"fire": 7 * DAY_SECONDS, "flood": DAY_SECONDS,
                   "zimas": DAY_SECONDS, "permits": 7 * DAY_SECONDS,
                   "housing": 7 * DAY_SECONDS}
RETRY_SECONDS = 60 * 60


def property_identity_key(listing: dict[str, Any]) -> str:
    """Share snapshots between relistings without losing address corrections.

    Keep the same identity fields as the older cache so existing successful
    records can be reused immediately without issuing an HTTP-time lookup.
    """
    identity = json.dumps([listing.get(field) for field in ("full_street_address", "zip_code", "city", "latitude", "longitude")], default=str)
    return "v1:" + hashlib.sha256(identity.encode()).hexdigest()


def _read_saved(key: str) -> dict[str, Any] | None:
    """Read a durable snapshot, including an older successful refresh.

    Retention is independent of refresh eligibility. An agency outage should
    not delete property information that was already downloaded successfully.
    """
    if not PROPERTY_CONTEXT_CACHE_PATH.exists():
        return None
    try:
        with sqlite3.connect(f"file:{PROPERTY_CONTEXT_CACHE_PATH}?mode=ro", uri=True, timeout=0.1) as conn:
            row = conn.execute("SELECT payload FROM property_snapshots WHERE cache_key = ?", (key,)).fetchone()
        payload = json.loads(row[0]) if row else None
        return payload if isinstance(payload, dict) else None
    except (sqlite3.Error, OSError, ValueError):
        return None


def _write_saved(key: str, payload: dict[str, Any]) -> None:
    """Publish one complete snapshot atomically for all app workers.

    Writers run only in the refresh command. SQLite transactions keep readers
    from observing a half-written report while a source is being refreshed.
    """
    PROPERTY_CONTEXT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(PROPERTY_CONTEXT_CACHE_PATH, timeout=5) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS property_snapshots (cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at REAL NOT NULL)")
        conn.execute("INSERT OR REPLACE INTO property_snapshots VALUES (?, ?, ?)", (key, json.dumps(payload), time.time()))


def empty_property_snapshot(listing: dict[str, Any]) -> dict[str, Any]:
    """Distinguish an unwarmed server snapshot from a negative agency finding.

    The page stays usable on a cache miss. In particular, no missing snapshot
    is interpreted as a low hazard designation or an absence of permits.
    """
    return {"address": listing.get("full_street_address"), "checked_at": None,
            "fire": {"status": "not_cached", "source_url": sources.FIRE_SOURCE, "zones": []},
            "flood": {"status": "not_cached", "source_url": sources.FLOOD_SOURCE, "zones": []},
            "zimas": {"status": "not_cached", "source_url": sources.ZIMAS_ORIGIN, "planning": [], "hazards": [], "housing": [], "cases": [], "apns": [], "pin": None},
            "permits": {"status": "not_cached", "source_url": sources.PERMIT_SOURCE, "records": [], "has_more": False}}


def read_property_snapshot(listing: dict[str, Any]) -> dict[str, Any]:
    """Return saved property records without contacting any official service.

    A still-fresh snapshot from the previous implementation is also readable
    during migration. Neither a missing nor an expired snapshot triggers work
    from an HTTP request; only the refresh command may fetch agency records.
    """
    key = property_identity_key(listing)
    saved = _read_saved(key)
    if saved is None:
        saved = sources._read_cached_context(key, time.time())
    if saved is None:
        return empty_property_snapshot(listing)
    for name in ("fire", "flood", "zimas", "permits"):
        section = saved[name]
        section.setdefault("checked_at", saved.get("checked_at"))
        section["stale"] = _age(section.get("checked_at")) >= REFRESH_SECONDS[name]
    return saved


def read_housing_snapshot(listing: dict[str, Any]) -> dict[str, Any]:
    """Read saved LAHD counts independently of the basic listing fields.

    Unknown counts remain unavailable until the refresh command publishes a
    summary. The existing LAHD records drawer still uses its normal APN path.
    """
    return _read_saved("housing:" + property_identity_key(listing)) or {"data_available": False, "matched": False, "snapshot_status": "not_cached"}


def _age(timestamp: object) -> float:
    """Convert a source check timestamp into elapsed seconds for scheduling.

    Unknown or malformed timestamps are due immediately, rather than being
    assigned an invented recent check time.
    """
    try:
        return max(0, time.time() - datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError, OverflowError):
        return float("inf")


def section_due(name: str, section: dict[str, Any]) -> bool:
    """Refresh missing sections or those older than our source-specific target.

    Failed attempts wait an hour to avoid repeatedly hitting an unavailable
    agency during a large backfill, while successful facts remain readable.
    """
    if section.get("last_attempt_at") and section.get("refresh_failed"):
        if _age(section["last_attempt_at"]) < RETRY_SECONDS:
            return False
    if section.get("status") in {"not_cached", "unavailable"} or section.get("snapshot_status") == "not_cached":
        return True
    return _age(section.get("checked_at")) >= REFRESH_SECONDS[name]


def _refresh_section(name: str, previous: dict[str, Any], fetcher: Callable[[], dict[str, Any]], force: bool) -> dict[str, Any]:
    """Replace one source only when its refresh succeeds.

    A failure preserves the previous check timestamp and records. Failed
    refreshes are marked separately so the UI cannot present old facts as a
    fresh agency response.
    """
    if not force and not section_due(name, previous):
        return deepcopy(previous)
    attempted = datetime.now(timezone.utc).isoformat()
    try:
        current = fetcher()
        failed = current.get("status") == "unavailable" or current.get("data_available") is False
    except Exception as exc:
        logger.warning("Property snapshot {} refresh failed: {}", name, type(exc).__name__)
        current = {"status": "unavailable"} if name != "housing" else {"data_available": False, "matched": False}
        failed = True
    if failed:
        retained = deepcopy(previous)
        if retained.get("status") == "not_cached":
            retained["status"] = "unavailable"
        retained.update(refresh_failed=True, last_attempt_at=attempted)
        return retained
    return {**current, "checked_at": attempted, "last_attempt_at": attempted, "refresh_failed": False}


def refresh_property_snapshot(listing: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    """Refresh due official property sections in the offline server job.

    Independent sources can run concurrently, but permit matching still needs
    a verified ZIMAS PIN. Source-specific check times survive partial failures;
    the last successful sections are retained rather than expiring on the page.
    """
    previous = read_property_snapshot(listing)
    # Legacy snapshots have a single check time. Promote it into each section
    # so the first scheduled run does not discard existing successful work.
    for name in ("fire", "flood", "zimas", "permits"):
        previous[name].setdefault("checked_at", previous.get("checked_at"))
    with ThreadPoolExecutor(max_workers=3) as pool:
        fire = pool.submit(_refresh_section, "fire", previous["fire"], lambda: sources.fetch_fire_context(listing), force)
        flood = pool.submit(_refresh_section, "flood", previous["flood"], lambda: sources.fetch_flood_context(listing), force)
        zimas = _refresh_section("zimas", previous["zimas"], lambda: sources.fetch_zimas_context(listing), force)
        permits = _refresh_section("permits", previous["permits"], lambda: sources.fetch_permit_context(zimas), force)
        sections = {"fire": fire.result(), "flood": flood.result(), "zimas": zimas, "permits": permits}
    checked = [section["checked_at"] for section in sections.values() if section.get("checked_at")]
    snapshot = {"address": listing.get("full_street_address"), "checked_at": min(checked) if checked else None, **sections}
    _write_saved(property_identity_key(listing), snapshot)
    return snapshot


def refresh_housing_snapshot(listing: dict[str, Any], fetcher: Callable[[dict[str, Any]], dict[str, Any]], *, force: bool = False) -> dict[str, Any]:
    """Save LAHD summary counts on the refresh job's weekly check schedule.

    The city currently publishes these feeds quarterly. A weekly check also
    discovers occasional out-of-cycle changes without fetching on popup opens.
    """
    previous = read_housing_snapshot(listing)
    snapshot = _refresh_section("housing", previous, lambda: fetcher(listing), force)
    _write_saved("housing:" + property_identity_key(listing), snapshot)
    return snapshot
