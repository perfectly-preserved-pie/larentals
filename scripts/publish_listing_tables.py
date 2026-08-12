"""Atomically publish independently-built buy and lease SQLite tables."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3

from functions.data_paths import LARENTALS_DB_PATH


def _read_table_schema(stage_path: Path, table_name: str) -> str:
    """Return a staged table's CREATE TABLE statement after validating it."""
    if not stage_path.is_file():
        raise FileNotFoundError(f"Staging database does not exist: {stage_path}")

    stage_uri = f"file:{stage_path.resolve()}?mode=ro"
    with sqlite3.connect(stage_uri, uri=True) as connection:
        row = connection.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        if row is None or row[0] is None:
            raise ValueError(
                f"Staging database {stage_path} is missing table {table_name!r}"
            )
        row_count = connection.execute(
            f'SELECT COUNT(*) FROM "{table_name}"'
        ).fetchone()[0]
        if row_count == 0:
            raise ValueError(
                f"Staging database {stage_path} has an empty {table_name!r} table"
            )
        return row[0]


def publish_listing_tables(
    *,
    db_path: str | Path,
    buy_stage_path: str | Path,
    lease_stage_path: str | Path,
) -> None:
    """Replace buy and lease together, leaving other canonical tables intact."""
    destination = Path(db_path)
    buy_stage = Path(buy_stage_path)
    lease_stage = Path(lease_stage_path)
    schemas = {
        "buy": _read_table_schema(buy_stage, "buy"),
        "lease": _read_table_schema(lease_stage, "lease"),
    }

    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(destination, timeout=30) as connection:
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("ATTACH DATABASE ? AS buy_stage", (str(buy_stage),))
        connection.execute("ATTACH DATABASE ? AS lease_stage", (str(lease_stage),))
        try:
            connection.execute("BEGIN IMMEDIATE")
            for table_name, stage_name in (("buy", "buy_stage"), ("lease", "lease_stage")):
                connection.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                connection.execute(schemas[table_name])
                connection.execute(
                    f'INSERT INTO "{table_name}" SELECT * FROM "{stage_name}"."{table_name}"'
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute("DETACH DATABASE buy_stage")
            connection.execute("DETACH DATABASE lease_stage")


def main() -> None:
    """
    Validate staged listing tables and publish them atomically to SQLite.
    """
    parser = argparse.ArgumentParser(
        description="Atomically publish staged buy and lease listing tables."
    )
    parser.add_argument("--db-path", default=str(LARENTALS_DB_PATH))
    parser.add_argument("--buy-stage-path", required=True)
    parser.add_argument("--lease-stage-path", required=True)
    args = parser.parse_args()

    publish_listing_tables(
        db_path=args.db_path,
        buy_stage_path=args.buy_stage_path,
        lease_stage_path=args.lease_stage_path,
    )
    print(f"Published buy and lease tables to {args.db_path}")


if __name__ == "__main__":
    main()
