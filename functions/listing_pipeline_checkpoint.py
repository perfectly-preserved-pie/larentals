"""Save paid listing work so an interrupted pipeline can safely resume.

Google Maps lookups, listing-page scrapes, and ImageKit uploads cost time or
money. This module records each completed step in a small SQLite database. When
S3 is configured, it also uploads the database after every completed step so a
replacement EC2 instance can continue from the latest saved result.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, BinaryIO, Literal, Protocol

import boto3
from botocore.exceptions import ClientError
import pandas as pd

from functions.listing_report_utils import normalize_mls_number


ListingType = Literal["buy", "lease"]
JsonScalar = str | int | float | bool | None
SUCCESS_STATUSES = frozenset({"success", "cached", "reused"})
TERMINAL_SCRAPE_STATUSES = frozenset({"success", "not_found"})

CHECKPOINT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("listing_type", "TEXT NOT NULL"),
    ("mls_number", "TEXT NOT NULL"),
    ("listing_input_hash", "TEXT"),
    ("scrape_status", "TEXT"),
    ("scrape_error", "TEXT"),
    ("listed_date", "TEXT"),
    ("listing_url", "TEXT"),
    ("source_photo_url", "TEXT"),
    ("image_status", "TEXT"),
    ("image_error", "TEXT"),
    ("image_source_hash", "TEXT"),
    ("mls_photo", "TEXT"),
    ("location_status", "TEXT"),
    ("location_error", "TEXT"),
    ("location_query_hash", "TEXT"),
    ("resolved_city", "TEXT"),
    ("resolved_zip_code", "TEXT"),
    ("geocode_status", "TEXT"),
    ("geocode_error", "TEXT"),
    ("geocode_provider", "TEXT"),
    ("geocode_address_hash", "TEXT"),
    ("latitude", "REAL"),
    ("longitude", "REAL"),
    ("inactive_check_input_hash", "TEXT"),
    ("inactive_check_status", "TEXT"),
    ("inactive_check_provider", "TEXT"),
    ("inactive_check_is_inactive", "INTEGER"),
    ("updated_at", "TEXT NOT NULL"),
)

_MUTABLE_COLUMNS = {name for name, _ in CHECKPOINT_COLUMNS} - {
    "listing_type",
    "mls_number",
    "updated_at",
}

_INPUT_HASH_EXCLUDED_COLUMNS = {
    "date_processed",
    "geocode_address_hash",
    "geocode_error",
    "geocode_provider",
    "geocode_status",
    "image_error",
    "image_source_hash",
    "image_status",
    "inactive_check_input_hash",
    "inactive_check_is_inactive",
    "inactive_check_provider",
    "inactive_check_status",
    "latitude",
    "listed_date",
    "listing_input_hash",
    "listing_url",
    "longitude",
    "location_status",
    "mls_photo",
    "scrape_error",
    "scrape_status",
    "source_photo_url",
}


class CheckpointPersistenceError(RuntimeError):
    """The pipeline completed a step but could not save its result safely."""


class S3CheckpointClient(Protocol):
    """Small portion of the S3 client used by the checkpoint store."""

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        """Download the current version of a checkpoint object."""
        ...

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: BinaryIO,
        ContentType: str,
    ) -> dict[str, Any]:
        """Upload the latest complete checkpoint database."""
        ...


def _utc_now() -> str:
    """Return the current UTC time in a format SQLite can store as text."""
    return datetime.now(timezone.utc).isoformat()


def _json_scalar(value: object) -> JsonScalar:
    """Turn common pandas values into plain values SQLite and JSON understand."""
    if value is None or value is pd.NA:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if hasattr(value, "item"):
        try:
            return _json_scalar(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, (str, int, bool)):
        return value
    return str(value)


def stable_fingerprint(value: object) -> str | None:
    """Create a repeatable identifier used to tell whether a value changed.

    Text is trimmed, lowercased, and normalized before hashing so harmless
    whitespace differences do not cause another paid operation. Empty values
    return ``None`` because there is nothing useful to compare.
    """
    normalized = _json_scalar(value)
    if normalized is None:
        return None
    if isinstance(normalized, str):
        normalized = " ".join(normalized.strip().lower().split())
        if not normalized:
            return None
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def file_fingerprint(path: str | Path) -> str:
    """Identify the exact source spreadsheet used by a pipeline run.

    The sample and full runs receive the same identifier when they read the
    same file, allowing work completed by the sample run to be reused.
    """
    digest = sha256()
    with Path(path).open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def listing_input_fingerprint(
    row: Mapping[str, Any] | pd.Series,
    *,
    source_file_hash: str,
) -> str:
    """Identify the input data that controls scraping for one listing.

    Generated enrichment columns are deliberately left out. The result changes
    when the source file or meaningful source fields change, which tells the
    pipeline that the listing page should be checked again.
    """
    values = {
        str(key): _json_scalar(value)
        for key, value in row.items()
        if str(key) not in _INPUT_HASH_EXCLUDED_COLUMNS
        and not str(key).startswith("_")
    }
    payload = {
        "source_file_hash": source_file_hash,
        "row": values,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def address_fingerprint(address: object) -> str | None:
    """Identify an address so coordinates are reused only while it is unchanged."""
    normalized = _json_scalar(address)
    if not isinstance(normalized, str):
        return stable_fingerprint(normalized)
    normalized = re.sub(r"\b(\d+)\.0\b", r"\1", normalized)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    return stable_fingerprint(normalized)


def photo_fingerprint(source_photo_url: object) -> str | None:
    """Identify the source photo so ImageKit is called only when it changes."""
    return stable_fingerprint(source_photo_url)


def inactive_check_fingerprint(
    listing_url: object,
    *,
    source_file_hash: str,
) -> str:
    """Identify a completed inactive-listing check for one source revision.

    A new source file deliberately invalidates prior results, so a listing can
    transition to inactive between weekly pipeline runs. Reusing the source
    file fingerprint lets a restarted run (and the full run after its sample
    run) skip checks already completed for that exact input.
    """
    url = _json_scalar(listing_url)
    normalized_url = " ".join(url.strip().split()) if isinstance(url, str) else url
    payload = {
        "source_file_hash": source_file_hash,
        "listing_url": normalized_url,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


class ListingCheckpointStore:
    """Keep completed listing work in SQLite and optionally mirror it to S3.

    Local SQLite commits protect progress while the current process is running.
    The optional S3 copy protects that same progress if the EC2 instance stops
    or is replaced. A new instance downloads the latest checkpoint before doing
    any paid work.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        listing_type: ListingType,
        s3_bucket: str | None = None,
        s3_key: str | None = None,
        s3_client: S3CheckpointClient | None = None,
        restore_remote: bool = True,
    ) -> None:
        """Open a checkpoint database and optionally restore its S3 copy.

        ``path`` is the local SQLite file used by this process. ``listing_type``
        keeps buy and lease records separate. Supplying both ``s3_bucket`` and
        ``s3_key`` enables write-through durability; ``s3_client`` can provide a
        compatible client for tests or custom AWS configuration. When
        ``restore_remote`` is true, an existing S3 checkpoint is downloaded only
        if the local file does not already exist.
        """
        if listing_type not in {"buy", "lease"}:
            raise ValueError(f"Unsupported listing type: {listing_type!r}")
        if bool(s3_bucket) != bool(s3_key):
            raise ValueError("s3_bucket and s3_key must be supplied together")

        self.path = Path(path)
        self.listing_type = listing_type
        self.s3_bucket = s3_bucket
        self.s3_key = s3_key
        self.s3_client: S3CheckpointClient | None = (
            s3_client
            if s3_client is not None
            else boto3.client("s3") if s3_bucket else None
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if restore_remote and self.s3_client is not None and not self.path.exists():
            self._restore_from_s3()
        self._ensure_schema()

    @property
    def remote_enabled(self) -> bool:
        """Report whether completed steps will also be saved to S3."""
        return self.s3_client is not None

    def _connect(self) -> sqlite3.Connection:
        """Open SQLite with settings that favor durable commits over speed."""
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _restore_from_s3(self) -> None:
        """Download the latest remote checkpoint without exposing a partial file.

        The download is written to a temporary file and then renamed into
        place. A missing S3 object is expected on a brand-new pipeline run and
        simply results in a new local checkpoint.
        """
        assert self.s3_client is not None
        assert self.s3_bucket is not None
        assert self.s3_key is not None

        try:
            response = self.s3_client.get_object(
                Bucket=self.s3_bucket,
                Key=self.s3_key,
            )
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return
            raise

        temporary_path = self.path.with_name(f".{self.path.name}.download")
        body = response["Body"]
        try:
            with temporary_path.open("wb") as output_file:
                while chunk := body.read(1024 * 1024):
                    output_file.write(chunk)
                output_file.flush()
                os.fsync(output_file.fileno())
            os.replace(temporary_path, self.path)
        finally:
            body.close()
            temporary_path.unlink(missing_ok=True)

    def _ensure_schema(self) -> None:
        """Create the checkpoint table and add columns introduced by upgrades."""
        definitions = ",\n          ".join(
            f'"{name}" {column_type}' for name, column_type in CHECKPOINT_COLUMNS
        )
        with self._connect() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS listing_checkpoint (
                  {definitions},
                  PRIMARY KEY (listing_type, mls_number)
                )
                """
            )
            existing = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(listing_checkpoint)"
                ).fetchall()
            }
            for name, column_type in CHECKPOINT_COLUMNS:
                if name in existing or "PRIMARY KEY" in column_type:
                    continue
                connection.execute(
                    f'ALTER TABLE listing_checkpoint ADD COLUMN "{name}" {column_type}'
                )

    def get(self, mls_number: object) -> dict[str, Any] | None:
        """Return the saved work for one MLS number, if it has been processed."""
        normalized_mls = normalize_mls_number(mls_number)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM listing_checkpoint
                WHERE listing_type = ? AND mls_number = ?
                """,
                (self.listing_type, normalized_mls),
            ).fetchone()
        return dict(row) if row is not None else None

    def upsert(self, mls_number: object, **values: object) -> None:
        """Save selected fields locally while leaving other saved fields intact.

        A listing is inserted the first time it is seen. Later pipeline stages
        update only the values they provide, so scraping, image, and geocoding
        results can be committed independently.
        """
        unexpected = set(values) - _MUTABLE_COLUMNS
        if unexpected:
            raise ValueError(f"Unsupported checkpoint columns: {sorted(unexpected)}")

        normalized_mls = normalize_mls_number(mls_number)
        cleaned = {key: _json_scalar(value) for key, value in values.items()}
        cleaned["updated_at"] = _utc_now()

        insert_columns = ["listing_type", "mls_number", *cleaned]
        placeholders = ", ".join("?" for _ in insert_columns)
        quoted_columns = ", ".join(f'"{column}"' for column in insert_columns)
        update_columns = [column for column in cleaned]
        update_clause = ", ".join(
            f'"{column}" = excluded."{column}"' for column in update_columns
        )
        parameters = [
            self.listing_type,
            normalized_mls,
            *(cleaned[column] for column in cleaned),
        ]

        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO listing_checkpoint ({quoted_columns})
                VALUES ({placeholders})
                ON CONFLICT(listing_type, mls_number) DO UPDATE SET
                  {update_clause}
                """,
                parameters,
            )

    def sync_remote(self) -> None:
        """Upload the complete, committed SQLite file as the latest checkpoint."""
        if self.s3_client is None:
            return
        assert self.s3_bucket is not None
        assert self.s3_key is not None

        with self.path.open("rb") as checkpoint_file:
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=self.s3_key,
                Body=checkpoint_file,
                ContentType="application/vnd.sqlite3",
            )

    def checkpoint(self, mls_number: object, **values: object) -> None:
        """Save one completed stage locally and then copy it to S3.

        Failure is deliberately fatal: once a paid operation succeeds, the
        pipeline must not continue unless that result is durable. Otherwise a
        later crash could repeat paid Google Maps or ImageKit work.
        """
        try:
            self.upsert(mls_number, **values)
            self.sync_remote()
        except Exception as error:
            raise CheckpointPersistenceError(
                f"Could not persist checkpoint for {self.listing_type} "
                f"MLS {normalize_mls_number(mls_number)}"
            ) from error
