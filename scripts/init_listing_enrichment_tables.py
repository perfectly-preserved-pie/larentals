from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from functions.listing_enrichment_utils import (
    DEFAULT_DB_PATH,
    ensure_enrichment_table,
    rebuild_enrichment_table,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create or evolve buy_enrichment and lease_enrichment tables used for "
            "derived listing-level spatial/context fields."
        )
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help=(
            "Drop and recreate buy_enrichment and lease_enrichment from the current "
            "canonical schema. This clears existing enrichment rows and should be "
            "followed by rerunning active enrichment jobs."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        for table_name in ("buy_enrichment", "lease_enrichment"):
            if args.rebuild:
                dropped_rows, created_indexes = rebuild_enrichment_table(conn, table_name)
                print(
                    f"[{table_name}] rebuilt schema; dropped {dropped_rows} row(s); "
                    f"created {created_indexes} index(es)."
                )
            else:
                added_columns, created_indexes = ensure_enrichment_table(conn, table_name)
                print(
                    f"[{table_name}] ensured schema; added {added_columns} column(s); "
                    f"ensured {created_indexes} index(es)."
                )


if __name__ == "__main__":
    main()
