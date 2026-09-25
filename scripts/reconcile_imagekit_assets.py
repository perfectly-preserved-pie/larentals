"""Keep ImageKit media storage aligned with active listing photo references."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

import boto3
from dotenv import find_dotenv, load_dotenv
import requests

from functions.aws_functions import load_ssm_parameters
from functions.data_paths import CHECKPOINT_DIR, LARENTALS_DB_PATH


IMAGEKIT_FILES_API = "https://api.imagekit.io/v1/files"
NULL_TEXT = frozenset({"", "none", "nan", "null", "nat", "<na>"})
DELETE_GUARD_EXIT_CODE = 3


class DeletionGuardExceeded(RuntimeError):
    """Signal that a reviewable cleanup proposal exceeded the automatic limit.

    The distinct exit code lets bootstrap publish the validated database while
    leaving remote media untouched for review.
    """


@dataclass(frozen=True)
class DatabasePhotoState:
    """Database references that determine which ImageKit files may survive."""

    active_paths: frozenset[str]
    active_rows: int
    inactive_rows: int


def _usable(value: object) -> bool:
    """Return whether a database value contains a real URL.

    Placeholder database values are ignored so only real delivery URLs enter the cleanup set.

    Args:
        value: Candidate value read from a photo URL column.

    Returns:
        Whether the value is nonempty and not a serialized null marker.
    """
    return value is not None and str(value).strip().lower() not in NULL_TEXT


def _asset_path(url: object, *, endpoint_prefix: str) -> str:
    """Convert an ImageKit delivery URL into its Media Library path.

    The Media Library path is needed because delivery URLs include transformation and host details.

    Args:
        url: ImageKit delivery URL stored in the listings database.
        endpoint_prefix: URL path identifying the ImageKit account endpoint.

    Returns:
        The decoded absolute path used by the ImageKit Media Library API.
    """
    path = unquote(urlparse(str(url).strip()).path)
    if endpoint_prefix and path.startswith(f"{endpoint_prefix}/"):
        return path[len(endpoint_prefix) :]
    return path


def load_database_photo_state(
    db_path: str | Path,
    *,
    endpoint_prefix: str,
) -> DatabasePhotoState:
    """Load the exact allowlist of photo paths used by unflagged listings.

    Only active listing references protect remote assets from deletion. Count
    inactive rows separately so the reconciliation manifest explains what was
    excluded.

    Args:
        db_path: SQLite database containing the canonical buy and lease tables.
        endpoint_prefix: URL path identifying the ImageKit account endpoint.

    Returns:
        Counts and unique paths for database rows considered active.
    """
    active_paths: set[str] = set()
    active_rows = 0
    inactive_rows = 0
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        for table_name in ("buy", "lease"):
            rows = connection.execute(
                f"""
                SELECT mls_photo, COALESCE(reported_as_inactive, 0) AS inactive
                FROM {table_name}
                """
            )
            for row in rows:
                if bool(row["inactive"]):
                    inactive_rows += 1
                    continue
                active_rows += 1
                if _usable(row["mls_photo"]):
                    active_paths.add(
                        _asset_path(
                            row["mls_photo"],
                            endpoint_prefix=endpoint_prefix,
                        )
                    )
    return DatabasePhotoState(
        active_paths=frozenset(active_paths),
        active_rows=active_rows,
        inactive_rows=inactive_rows,
    )


class ImageKitMediaClient:
    """Small retrying client for the ImageKit operations used by reconciliation."""

    def __init__(self, private_key: str) -> None:
        """Create an authenticated persistent HTTP session.

        Persistent authentication and connection settings are shared across paginated API requests.

        Args:
            private_key: Server-side ImageKit API credential.

        Returns:
            None.
        """
        self.session = requests.Session()
        self.session.auth = (private_key, "")
        self.session.headers.update({"Accept": "application/json"})

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Send a request with bounded retries for transport and rate failures.

        Bounded retries handle transient transport and rate failures without hanging the reconciliation job.

        Args:
            method: HTTP method accepted by ``requests.Session.request``.
            url: Absolute ImageKit API endpoint.
            **kwargs: Additional request options such as query parameters or JSON.

        Returns:
            The final HTTP response, including non-rate-limit error responses.
        """
        last_response: requests.Response | None = None
        for attempt in range(8):
            try:
                response = self.session.request(method, url, timeout=90, **kwargs)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 7:
                    raise
                time.sleep(min(60, 2**attempt))
                continue
            last_response = response
            if response.status_code != 429:
                return response
            time.sleep(min(60, 2**attempt))
        assert last_response is not None
        return last_response

    def list_assets(self, asset_type: str) -> list[dict[str, Any]]:
        """Return every current file or historical version, with de-duplication.

        De-duplication prevents current files and their historical versions from being processed twice.

        Args:
            asset_type: ImageKit asset type, either ``file`` or ``file-version``.

        Returns:
            Asset response objects keyed internally by file and version identity.
        """
        assets: dict[tuple[str, str], dict[str, Any]] = {}
        skip = 0
        while True:
            response = self._request(
                "GET",
                IMAGEKIT_FILES_API,
                params={
                    "type": asset_type,
                    "limit": 1000,
                    "skip": skip,
                    "sort": "ASC_NAME",
                },
            )
            response.raise_for_status()
            page = response.json()
            for asset in page:
                version_id = str((asset.get("versionInfo") or {}).get("id", ""))
                assets[(str(asset["fileId"]), version_id)] = asset
            if len(page) < 1000:
                break
            skip += len(page)
        return list(assets.values())

    def list_version_page(self) -> list[dict[str, Any]]:
        """Return the first version page so deletions cannot shift later offsets.

        Fetching a page before deletion avoids offset shifts that could skip later versions.

        Returns:
            Up to one thousand non-current file version objects.
        """
        response = self._request(
            "GET",
            IMAGEKIT_FILES_API,
            params={"type": "file-version", "limit": 1000, "skip": 0},
        )
        response.raise_for_status()
        return response.json()

    def delete_files(self, file_ids: Iterable[str]) -> int:
        """Delete current files in ImageKit's maximum batch size of 100.

        The API caps batch size at 100, so larger cleanup sets are split into valid requests.

        Args:
            file_ids: Current ImageKit file identifiers selected for deletion.

        Returns:
            Number of files deleted or already absent during a resumed run.
        """
        ids = list(file_ids)
        deleted = 0
        for offset in range(0, len(ids), 100):
            pending = ids[offset : offset + 100]
            for _ in range(8):
                response = self._request(
                    "POST",
                    f"{IMAGEKIT_FILES_API}/batch/deleteByFileIds",
                    json={"fileIds": pending},
                )
                if response.status_code == 404:
                    deleted += len(pending)
                    pending = []
                    break
                if response.status_code not in {200, 207}:
                    response.raise_for_status()
                completed = set(
                    response.json().get("successfullyDeletedFileIds") or []
                )
                deleted += len(completed)
                pending = [file_id for file_id in pending if file_id not in completed]
                if not pending:
                    break
                time.sleep(1)
            if pending:
                raise RuntimeError(
                    f"ImageKit did not delete {len(pending)} files in batch"
                )
        return deleted

    def delete_file_version(self, file_id: str, version_id: str) -> None:
        """Permanently delete one non-current file version.

        Historical versions are removed only when they are not the active file.

        Args:
            file_id: Parent ImageKit file identifier.
            version_id: Unique identifier for the non-current version.

        Returns:
            None.
        """
        response = self._request(
            "DELETE",
            f"{IMAGEKIT_FILES_API}/{file_id}/versions/{version_id}",
        )
        if response.status_code not in {204, 404}:
            response.raise_for_status()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a deterministic audit manifest.

    Stable ordering makes the audit manifest easy to diff and review before cleanup.

    Args:
        path: Destination CSV path.
        rows: Uniform dictionaries to serialize as manifest rows.

    Returns:
        None.
    """
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _reconcile_database(
    db_path: Path,
    *,
    live_paths: set[str],
    endpoint_prefix: str,
) -> dict[str, dict[str, int]]:
    """Clear inactive, placeholder, and missing ImageKit references atomically.

    Use one SQLite transaction for both listing tables so the database cannot
    be left with only half the photo references repaired.

    Args:
        db_path: Canonical SQLite listings database to update.
        live_paths: Exact set of paths still present in ImageKit.
        endpoint_prefix: URL path identifying the ImageKit account endpoint.

    Returns:
        Per-market counts of each database repair performed.
    """
    result: dict[str, dict[str, int]] = {}
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        for table_name in ("buy", "lease"):
            inactive = connection.execute(
                f"""
                UPDATE {table_name}
                SET mls_photo = NULL, image_status = 'inactive'
                WHERE COALESCE(reported_as_inactive, 0) <> 0
                  AND (mls_photo IS NOT NULL OR image_status IS NOT 'inactive')
                """
            ).rowcount
            placeholders = connection.execute(
                f"""
                UPDATE {table_name}
                SET mls_photo = NULL
                WHERE mls_photo IS NOT NULL
                  AND lower(trim(CAST(mls_photo AS TEXT)))
                      IN ('none', 'nan', 'null', 'nat', '<na>')
                """
            ).rowcount
            missing_mls: list[str] = []
            rows = connection.execute(
                f"""
                SELECT mls_number, mls_photo
                FROM {table_name}
                WHERE COALESCE(reported_as_inactive, 0) = 0
                  AND mls_photo IS NOT NULL
                """
            )
            for row in rows:
                if _usable(row["mls_photo"]) and _asset_path(
                    row["mls_photo"], endpoint_prefix=endpoint_prefix
                ) not in live_paths:
                    missing_mls.append(str(row["mls_number"]))
            connection.executemany(
                f"""
                UPDATE {table_name}
                SET mls_photo = NULL, image_status = 'failed'
                WHERE mls_number = ?
                """,
                ((mls_number,) for mls_number in missing_mls),
            )
            result[table_name] = {
                "inactive_rows_cleared": inactive,
                "placeholder_urls_cleared": placeholders,
                "missing_active_urls_cleared": len(missing_mls),
            }
    return result


def _clear_stale_checkpoint_urls(
    checkpoint_path: Path,
    *,
    listing_type: str,
    live_paths: set[str],
    endpoint_prefix: str,
) -> int:
    """Prevent a future run from reusing a URL whose asset was deleted.

    A pipeline checkpoint can outlive its ImageKit photo. Clear stale photo
    URLs there after cleanup so the next pipeline run uploads a valid asset.

    Args:
        checkpoint_path: Local pipeline checkpoint SQLite database.
        listing_type: Listing market stored in the checkpoint.
        live_paths: Exact set of paths still present in ImageKit.
        endpoint_prefix: URL path identifying the ImageKit account endpoint.

    Returns:
        Number of stale checkpoint photo URLs cleared.
    """
    if not checkpoint_path.is_file():
        return 0
    stale: list[str] = []
    with sqlite3.connect(checkpoint_path) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute(
            """
            SELECT mls_number, mls_photo
            FROM listing_checkpoint
            WHERE listing_type = ? AND mls_photo IS NOT NULL
            """,
            (listing_type,),
        ):
            if not _usable(row["mls_photo"]) or _asset_path(
                row["mls_photo"], endpoint_prefix=endpoint_prefix
            ) not in live_paths:
                stale.append(str(row["mls_number"]))
        connection.executemany(
            """
            UPDATE listing_checkpoint
            SET mls_photo = NULL,
                image_status = 'failed',
                image_error = 'ImageKit asset removed by reconciliation'
            WHERE listing_type = ? AND mls_number = ?
            """,
            ((listing_type, mls_number) for mls_number in stale),
        )
    return len(stale)


def _sync_checkpoint(
    path: Path,
    *,
    bucket: str | None,
    key: str | None,
) -> None:
    """Replace the remote checkpoint after stale URL cleanup.

    Replacing the remote checkpoint after cleanup keeps future imports from restoring stale URLs.

    Args:
        path: Local checkpoint database to upload.
        bucket: Optional S3 bucket holding durable checkpoints.
        key: Optional S3 object key for this listing market.

    Returns:
        None.
    """
    if not bucket or not key or not path.is_file():
        return
    boto3.client("s3").upload_file(str(path), bucket, key)


def reconcile(
    *,
    db_path: Path,
    audit_dir: Path,
    private_key: str,
    url_endpoint: str,
    apply: bool,
    force: bool,
    max_delete_fraction: float,
    min_active_references: int,
    buy_checkpoint_path: Path | None = None,
    lease_checkpoint_path: Path | None = None,
    checkpoint_s3_bucket: str | None = None,
    checkpoint_s3_prefix: str | None = None,
) -> dict[str, Any]:
    """Reconcile ImageKit with active SQLite listing photo references.

    Write a deletion manifest before any mutation and refuse a suspiciously
    large cleanup unless forced. After applying changes, re-list assets to
    catch items missed by paginated results.

    Args:
        db_path: Canonical SQLite database containing listing tables.
        audit_dir: Directory receiving manifests and the reconciliation summary.
        private_key: Server-side ImageKit API credential.
        url_endpoint: ImageKit delivery endpoint used to normalize stored URLs.
        apply: Whether to perform mutations instead of a dry-run audit.
        force: Whether to override the maximum deletion-fraction guard.
        max_delete_fraction: Largest automatic current-file deletion ratio.
        min_active_references: Minimum allowlisted paths required to proceed.
        buy_checkpoint_path: Optional local buy pipeline checkpoint database.
        lease_checkpoint_path: Optional local lease pipeline checkpoint database.
        checkpoint_s3_bucket: Optional bucket receiving updated checkpoints.
        checkpoint_s3_prefix: Optional key prefix for updated checkpoints.

    Returns:
        Reconciliation counts suitable for logs and audit records.
    """
    endpoint_prefix = urlparse(url_endpoint).path.rstrip("/")
    state = load_database_photo_state(db_path, endpoint_prefix=endpoint_prefix)
    if len(state.active_paths) < min_active_references:
        raise RuntimeError(
            f"Refusing cleanup with only {len(state.active_paths)} active photo paths"
        )

    client = ImageKitMediaClient(private_key)
    current = client.list_assets("file")
    delete_rows = [
        {
            "file_id": str(asset["fileId"]),
            "file_path": unquote(str(asset["filePath"])),
            "size": int(asset.get("size") or 0),
        }
        for asset in current
        if unquote(str(asset["filePath"])) not in state.active_paths
    ]
    delete_fraction = len(delete_rows) / len(current) if current else 0.0
    audit_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(audit_dir / "delete_current.csv", delete_rows)
    summary: dict[str, Any] = {
        "apply": apply,
        "active_database_rows": state.active_rows,
        "inactive_database_rows": state.inactive_rows,
        "active_reference_paths": len(state.active_paths),
        "current_assets_before": len(current),
        "current_assets_to_delete": len(delete_rows),
        "current_bytes_to_delete": sum(row["size"] for row in delete_rows),
        "delete_fraction": delete_fraction,
        "max_delete_fraction": max_delete_fraction,
    }
    guarded = delete_fraction > max_delete_fraction and not force
    summary["status"] = "review_required" if guarded else "ready"
    (audit_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if guarded and apply:
        raise DeletionGuardExceeded(
            f"Refusing to delete {delete_fraction:.1%} of current ImageKit files; "
            f"review {audit_dir / 'delete_current.csv'} before using --force"
        )
    if not apply:
        return summary

    summary["current_assets_deleted"] = client.delete_files(
        row["file_id"] for row in delete_rows
    )
    # Re-list after mutation. This also catches any item skipped at an unstable
    # offset boundary in a large account-wide listing.
    for _ in range(5):
        current = client.list_assets("file")
        extras = [
            asset
            for asset in current
            if unquote(str(asset["filePath"])) not in state.active_paths
        ]
        if not extras:
            break
        summary["current_assets_deleted"] += client.delete_files(
            str(asset["fileId"]) for asset in extras
        )
    else:
        raise RuntimeError("ImageKit still contains unreferenced current assets")

    versions_deleted = 0
    while versions := client.list_version_page():
        for version in versions:
            client.delete_file_version(
                str(version["fileId"]),
                str((version.get("versionInfo") or {})["id"]),
            )
            versions_deleted += 1
    summary["historical_versions_deleted"] = versions_deleted

    current = client.list_assets("file")
    live_paths = {unquote(str(asset["filePath"])) for asset in current}
    summary["database_updates"] = _reconcile_database(
        db_path,
        live_paths=live_paths,
        endpoint_prefix=endpoint_prefix,
    )
    checkpoints = {
        "buy": buy_checkpoint_path,
        "lease": lease_checkpoint_path,
    }
    summary["checkpoint_urls_cleared"] = {}
    for listing_type, checkpoint_path in checkpoints.items():
        if checkpoint_path is None:
            continue
        cleared = _clear_stale_checkpoint_urls(
            checkpoint_path,
            listing_type=listing_type,
            live_paths=live_paths,
            endpoint_prefix=endpoint_prefix,
        )
        summary["checkpoint_urls_cleared"][listing_type] = cleared
        key = (
            f"{checkpoint_s3_prefix.rstrip('/')}/{listing_type}.sqlite"
            if checkpoint_s3_prefix
            else None
        )
        _sync_checkpoint(
            checkpoint_path,
            bucket=checkpoint_s3_bucket,
            key=key,
        )

    final_state = load_database_photo_state(
        db_path,
        endpoint_prefix=endpoint_prefix,
    )
    if live_paths != set(final_state.active_paths):
        raise RuntimeError(
            "Post-cleanup verification failed: live ImageKit paths do not equal "
            "active database photo paths"
        )
    if client.list_version_page():
        raise RuntimeError("Post-cleanup verification found historical versions")
    summary["status"] = "completed"
    summary["current_assets_after"] = len(current)
    summary["historical_versions_after"] = 0
    (audit_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    """Run a dry-run audit or apply a guarded ImageKit reconciliation.

    The command writes a manifest before deletion and requires explicit apply
    flags for mutation, making the proposed cleanup reviewable.

    Returns:
        None.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(LARENTALS_DB_PATH))
    parser.add_argument("--audit-dir", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-delete-fraction", type=float, default=0.10)
    parser.add_argument("--min-active-references", type=int, default=1000)
    parser.add_argument(
        "--buy-checkpoint-path",
        default=str(CHECKPOINT_DIR / "buy.sqlite"),
    )
    parser.add_argument(
        "--lease-checkpoint-path",
        default=str(CHECKPOINT_DIR / "lease.sqlite"),
    )
    parser.add_argument("--checkpoint-s3-bucket", default=None)
    parser.add_argument("--checkpoint-s3-prefix", default=None)
    parser.add_argument("--use-env", action="store_true")
    parser.add_argument("--ssm-prefix", default="/wheretolivedotla/")
    args = parser.parse_args()

    if args.use_env:
        load_dotenv(find_dotenv())
    else:
        os.environ.update(load_ssm_parameters(args.ssm_prefix))
    private_key = os.environ.get("IMAGEKIT_PRIVATE_KEY")
    url_endpoint = os.environ.get("IMAGEKIT_URL_ENDPOINT")
    if not private_key or not url_endpoint:
        raise SystemExit("IMAGEKIT_PRIVATE_KEY and IMAGEKIT_URL_ENDPOINT are required")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audit_dir = Path(args.audit_dir or f"data/audits/imagekit_reconcile_{timestamp}")
    try:
        result = reconcile(
            db_path=Path(args.db_path),
            audit_dir=audit_dir,
            private_key=private_key,
            url_endpoint=url_endpoint,
            apply=args.apply,
            force=args.force,
            max_delete_fraction=args.max_delete_fraction,
            min_active_references=args.min_active_references,
            buy_checkpoint_path=Path(args.buy_checkpoint_path),
            lease_checkpoint_path=Path(args.lease_checkpoint_path),
            checkpoint_s3_bucket=args.checkpoint_s3_bucket,
            checkpoint_s3_prefix=args.checkpoint_s3_prefix,
        )
    except DeletionGuardExceeded as error:
        print(error, file=sys.stderr)
        raise SystemExit(DELETE_GUARD_EXIT_CODE) from None
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
