import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pages.component_base import BaseClass


class BaseClassEnrichmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "larentals-test.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_db(self, schema_sql: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(schema_sql)

    def test_select_columns_can_include_enrichment_fields(self) -> None:
        self._write_db(
            """
            CREATE TABLE buy (
              mls_number TEXT,
              latitude REAL,
              longitude REAL,
              list_price INTEGER,
              listed_date TEXT
            );

            INSERT INTO buy (
              mls_number,
              latitude,
              longitude,
              list_price,
              listed_date
            ) VALUES (
              'MLS-1',
              34.1201,
              -118.2501,
              1200000,
              '2026-03-20'
            );

            CREATE TABLE buy_provider_options (
              listing_id TEXT,
              MaxAdDn REAL,
              MaxAdUp REAL
            );

            INSERT INTO buy_provider_options (listing_id, MaxAdDn, MaxAdUp)
            VALUES ('MLS-1', 500.0, 50.0);

            CREATE TABLE buy_enrichment (
              mls_number TEXT PRIMARY KEY,
              school_district_name TEXT,
              nearest_high_school_mi REAL
            );

            INSERT INTO buy_enrichment (
              mls_number,
              school_district_name,
              nearest_high_school_mi
            ) VALUES (
              'MLS-1',
              'Los Angeles Unified',
              0.35
            );
            """
        )

        with patch("pages.component_base.DB_PATH", str(self.db_path)):
            loader = BaseClass(
                table_name="buy",
                page_type="buy",
                select_columns=(
                    "mls_number",
                    "latitude",
                    "longitude",
                    "school_district_name",
                    "nearest_high_school_mi",
                ),
                include_last_updated=False,
            )

        self.assertEqual(loader.df.loc[0, "school_district_name"], "Los Angeles Unified")
        self.assertAlmostEqual(loader.df.loc[0, "nearest_high_school_mi"], 0.35)
        self.assertAlmostEqual(loader.df.loc[0, "best_dn"], 500.0)
        self.assertAlmostEqual(loader.df.loc[0, "best_up"], 50.0)

    def test_missing_enrichment_table_is_ignored(self) -> None:
        self._write_db(
            """
            CREATE TABLE lease (
              mls_number TEXT,
              latitude REAL,
              longitude REAL,
              list_price INTEGER,
              listed_date TEXT
            );

            INSERT INTO lease (
              mls_number,
              latitude,
              longitude,
              list_price,
              listed_date
            ) VALUES (
              'LEASE-1',
              34.0501,
              -118.3001,
              3200,
              '2026-03-21'
            );

            CREATE TABLE lease_provider_options (
              listing_id TEXT,
              MaxAdDn REAL,
              MaxAdUp REAL
            );
            """
        )

        with patch("pages.component_base.DB_PATH", str(self.db_path)):
            loader = BaseClass(
                table_name="lease",
                page_type="lease",
                select_columns=("mls_number", "latitude", "longitude"),
                include_last_updated=False,
            )

        self.assertIn("mls_number", loader.df.columns)
        self.assertIn("best_dn", loader.df.columns)
        self.assertIn("best_up", loader.df.columns)
        self.assertEqual(loader.df.loc[0, "mls_number"], "LEASE-1")


if __name__ == "__main__":
    unittest.main()
