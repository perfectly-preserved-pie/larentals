"""LA City Rent Stabilization Ordinance (RSO) listing lookups.

The Los Angeles Housing Department publishes the current RSO inventory through
its public dashboard.  The inventory is property-level: it supplies the number
of covered units and an assessor unit-count range, but not a public mapping of
individual apartment numbers to RSO status.  This module deliberately keeps
that distinction visible to renters.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

import orjson
import requests

from functions.data_paths import RSO_PROPERTY_LOOKUP_PATH

logger = logging.getLogger(__name__)

# Public LAHD report configuration, obtained from the report's publish-to-web
# embed. The refresh command validates responses and fails rather than silently
# serving a partial inventory if LAHD changes this public report.
RSO_REPORT_URL = "https://housing.lacity.gov/rso"
RSO_POWERBI_API_BASE = "https://wabi-us-gov-iowa-api.analysis.usgovcloudapi.net"
RSO_POWERBI_RESOURCE_KEY = "3db255db-5477-4b7c-8624-7f37f177efac"
RSO_POWERBI_MODEL_ID = 264470
RSO_SOURCE_DESCRIPTION = "LAHD public RSO dashboard inventory"
RSO_REQUEST_TIMEOUT_SECONDS = 60

_UNIT_RE = re.compile(r"(?:\s*(?:#|APT\.?|APARTMENT|UNIT|STE|SUITE)\s*[A-Z0-9-]+)\s*$", re.IGNORECASE)
_STREET_SUFFIX_NORMALIZATION = {
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "COURT": "CT",
    "DRIVE": "DR",
    "LANE": "LN",
    "PARKWAY": "PKWY",
    "PLACE": "PL",
    "ROAD": "RD",
    "STREET": "ST",
    "TERRACE": "TER",
}


class RsoListingLookupResult(TypedDict):
    data_available: bool
    matched: bool
    coverage: str | None
    rso_units: int | None
    unit_range: str | None
    apn: str | None
    address: str | None
    rso_year: int | None


def _normalize_address(value: object) -> str:
    """
    Normalize an address for property-level RSO matching.
    """
    raw_value = str(value or "").strip().upper()
    if not raw_value:
        return ""
    street_only = raw_value.split(",", 1)[0]
    street_only = _UNIT_RE.sub("", street_only)
    street_only = re.sub(r"[^A-Z0-9/]+", " ", street_only)
    tokens = [token for token in street_only.split() if token]
    if tokens:
        tokens[-1] = _STREET_SUFFIX_NORMALIZATION.get(tokens[-1], tokens[-1])
    return " ".join(tokens)


def _parse_int(value: object) -> int | None:
    """
    Convert a non-negative numeric value to an integer.
    """
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _coverage_from_counts(rso_units: int, unit_range: str) -> str:
    """
    Derive a conservative coverage status from LAHD's public fields.
    """
    numbers = [int(value) for value in re.findall(r"\d+", unit_range)]
    if len(numbers) == 1 and rso_units >= numbers[0]:
        return "all"
    if len(numbers) >= 2 and rso_units >= max(numbers):
        return "all"
    return "some"


def _empty_result(*, data_available: bool) -> RsoListingLookupResult:
    """
    Return the default result for an unavailable or unmatched lookup.
    """
    return {
        "data_available": data_available,
        "matched": False,
        "coverage": None,
        "rso_units": None,
        "unit_range": None,
        "apn": None,
        "address": None,
        "rso_year": None,
    }


def _result_from_record(record: dict[str, Any]) -> RsoListingLookupResult:
    """
    Convert an RSO inventory record into a popup-safe result.
    """
    rso_units = _parse_int(record.get("rso_units")) or 0
    unit_range = str(record.get("unit_range") or "").strip()
    return {
        "data_available": True,
        "matched": True,
        "coverage": _coverage_from_counts(rso_units, unit_range),
        "rso_units": rso_units,
        "unit_range": unit_range or None,
        "apn": str(record.get("apn") or "") or None,
        "address": str(record.get("address") or "") or None,
        "rso_year": _parse_int(record.get("rso_year")),
    }


@lru_cache(maxsize=4)
def _load_lookup(artifact_path: str, artifact_mtime_ns: int) -> dict[str, Any]:
    """
    Load and index the local RSO inventory by normalized address.
    """
    del artifact_mtime_ns
    try:
        with gzip.open(artifact_path, "rb") as artifact_file:
            payload = orjson.loads(artifact_file.read())
    except (OSError, orjson.JSONDecodeError) as exc:
        logger.warning("Failed loading RSO lookup artifact from %s: %s", artifact_path, exc)
        return {"records": {}, "metadata": {}}

    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return {"records": {}, "metadata": {}}

    address_index: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        key = _normalize_address(record.get("address"))
        if not key:
            continue
        existing = address_index.get(key)
        if existing is None or (_parse_int(record.get("rso_year")) or 0) > (
            _parse_int(existing.get("rso_year")) or 0
        ):
            address_index[key] = record
    metadata = payload.get("metadata") if isinstance(payload, dict) else {}
    return {"records": address_index, "metadata": metadata if isinstance(metadata, dict) else {}}


def lookup_rso_property_for_listing(
    address: object,
    artifact_path: Path = RSO_PROPERTY_LOOKUP_PATH,
) -> RsoListingLookupResult:
    """
    Look up a listing's property in the local LAHD RSO inventory.
    """
    try:
        mtime_ns = artifact_path.stat().st_mtime_ns
    except OSError:
        return _empty_result(data_available=False)

    key = _normalize_address(address)
    if not key:
        return _empty_result(data_available=True)
    lookup = _load_lookup(str(artifact_path), mtime_ns)
    record = (lookup.get("records") or {}).get(key)
    return _result_from_record(record) if isinstance(record, dict) else _empty_result(data_available=True)


def add_rso_status_to_listing_geojson(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach a client-filter-friendly RSO status to each listing feature.

    Listings outside LA City and listings not found in the public inventory are
    intentionally both ``unknown``. An inventory omission is not a finding that
    a property is not rent controlled.
    """
    features = payload.get("features")
    if not isinstance(features, list):
        return payload

    try:
        mtime_ns = RSO_PROPERTY_LOOKUP_PATH.stat().st_mtime_ns
        address_index = _load_lookup(str(RSO_PROPERTY_LOOKUP_PATH), mtime_ns).get("records") or {}
    except OSError:
        address_index = {}

    for feature in features:
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict):
            continue
        record = address_index.get(_normalize_address(properties.get("full_street_address")))
        properties["rent_control_status"] = (
            _coverage_from_counts(_parse_int(record.get("rso_units")) or 0, str(record.get("unit_range") or ""))
            if isinstance(record, dict)
            else "unknown"
        )
    return payload


def _powerbi_headers(request_id: str) -> dict[str, str]:
    """
    Build the headers required by the public Power BI report endpoint.
    """
    return {
        "Content-Type": "application/json",
        "X-PowerBI-ResourceKey": RSO_POWERBI_RESOURCE_KEY,
        "ActivityId": "25cb3e7b-3c20-4e6f-b2c0-7074804ec8da",
        "RequestId": request_id,
    }


def _build_query(apn_min: int, apn_max: int) -> dict[str, Any]:
    """
    Build a public-dashboard query for one half-open APN range.
    """
    fields = ["APN", "BillingYear", "Address", "City", "Zip", "RSO_Units", "UnitRange"]
    select = [
        {
            "Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": field},
            "Name": f"RSO.{field}",
        }
        for field in fields
    ]
    apn_column = {"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": "APN"}}
    query = {
        "Commands": [
            {
                "SemanticQueryDataShapeCommand": {
                    "Query": {
                        "Version": 2,
                        "From": [{"Name": "r", "Entity": "RSO", "Type": 0}],
                        "Select": select,
                        "Where": [
                            {"Condition": {"Comparison": {"ComparisonKind": 2, "Left": apn_column, "Right": {"Literal": {"Value": f"{apn_min}L"}}}}},
                            {"Condition": {"Comparison": {"ComparisonKind": 4, "Left": apn_column, "Right": {"Literal": {"Value": f"{apn_max}L"}}}}},
                        ],
                        "OrderBy": [{"Direction": 1, "Expression": apn_column}],
                    },
                    "Binding": {
                        "Primary": {"Groupings": [{"Projections": list(range(len(fields)))}]},
                        "DataReduction": {"DataVolume": 6, "Primary": {"Window": {"Count": 30000}}},
                        "Version": 1,
                    },
                    "ExecutionMetricsKind": 1,
                }
            }
        ]
    }
    return {"version": "1.0.0", "queries": [{"Query": query, "CacheKey": ""}], "cancelQueries": [], "modelId": RSO_POWERBI_MODEL_ID}


def _decode_powerbi_rows(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Decode the compact row representation returned by Power BI.
    """
    try:
        rows = dataset["PH"][0]["DM0"]
    except (KeyError, IndexError, TypeError):
        return []
    dictionaries = dataset.get("ValueDicts") or {}
    dictionary_values = {name: values for name, values in dictionaries.items() if isinstance(values, list)}
    fields = ("apn", "rso_year", "address", "city", "zip", "rso_units", "unit_range")
    values: list[Any] = [None] * len(fields)
    dictionary_names: list[str | None] = [None] * len(fields)
    output: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        if row_index == 0:
            schema = row.get("S") or []
            dictionary_names = [entry.get("DN") if isinstance(entry, dict) else None for entry in schema]
        compressed_values = iter(row.get("C") or [])
        repeat_mask = int(row.get("R") or 0)
        for column_index in range(len(fields)):
            if repeat_mask & (1 << column_index):
                continue
            value = next(compressed_values, None)
            dictionary_name = dictionary_names[column_index]
            if dictionary_name and isinstance(value, int):
                dictionary = dictionary_values.get(dictionary_name) or []
                value = dictionary[value] if 0 <= value < len(dictionary) else None
            values[column_index] = value
        record = dict(zip(fields, values, strict=True))
        if _parse_int(record["apn"]) and str(record.get("address") or "").strip():
            record["apn"] = str(_parse_int(record["apn"]))
            output.append(record)
    return output


def fetch_current_rso_records() -> tuple[list[dict[str, Any]], str]:
    """
    Fetch the complete current public LAHD RSO inventory.
    """
    records: list[dict[str, Any]] = []
    source_timestamp = ""

    def fetch_partition(apn_min: int, apn_max: int) -> None:
        """
        Fetch one APN range, splitting it if Power BI truncates the result.
        """
        nonlocal source_timestamp
        response = requests.post(
            f"{RSO_POWERBI_API_BASE}/public/reports/querydata?synchronous=true",
            headers=_powerbi_headers(f"d4a778a4-8d12-4ca7-8a14-{apn_min % 1_000_000_000:012d}"),
            json=_build_query(apn_min, apn_max),
            timeout=RSO_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        try:
            data = payload["results"][0]["result"]["data"]
            dataset = data["dsr"]["DS"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected LAHD RSO dashboard response for APN range {apn_min}-{apn_max}: {payload!r}") from exc
        partition_rows = _decode_powerbi_rows(dataset)
        if len(partition_rows) >= 30_000:
            midpoint = apn_min + ((apn_max - apn_min) // 2)
            if midpoint <= apn_min or midpoint >= apn_max:
                raise RuntimeError(f"LAHD RSO dashboard range {apn_min}-{apn_max} reached the public row limit.")
            fetch_partition(apn_min, midpoint)
            fetch_partition(midpoint, apn_max)
            return
        records.extend(partition_rows)
        source_timestamp = str(data.get("timestamp") or source_timestamp)

    # LA County APNs in the LAHD inventory currently begin with 20 through 69.
    # Keeping each two-digit prefix below Power BI's public 30,000-row limit
    # also makes a truncated response detectable. Dense prefixes are split
    # further by ``fetch_partition``.
    for prefix in range(20, 70):
        fetch_partition(prefix * 100_000_000, (prefix + 1) * 100_000_000)

    if not records:
        raise RuntimeError("LAHD RSO dashboard returned no inventory records.")
    return records, source_timestamp


def refresh_local_rso_property_lookup(output_path: Path = RSO_PROPERTY_LOOKUP_PATH) -> Path:
    """
    Fetch LAHD's public RSO inventory and write the local lookup artifact.
    """
    started_at = time.time()
    records, source_timestamp = fetch_current_rso_records()
    deduplicated: dict[str, dict[str, Any]] = {}
    for record in records:
        key = _normalize_address(record.get("address"))
        if not key:
            continue
        existing = deduplicated.get(key)
        if existing is None or (_parse_int(record.get("rso_year")) or 0) >= (_parse_int(existing.get("rso_year")) or 0):
            deduplicated[key] = record
    payload = {
        "metadata": {
            "source": RSO_SOURCE_DESCRIPTION,
            "source_url": RSO_REPORT_URL,
            "source_timestamp": source_timestamp,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "record_count": len(deduplicated),
        },
        "records": list(deduplicated.values()),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output_path, "wb") as artifact_file:
        artifact_file.write(orjson.dumps(payload))
    _load_lookup.cache_clear()
    logger.info("Wrote %s RSO lookup records to %s in %.2fs.", len(deduplicated), output_path, time.time() - started_at)
    return output_path
