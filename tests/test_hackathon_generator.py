import csv
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.generate_hackathon_data import HEADERS, generate_rows, write_dataset


class HackathonDataGeneratorTests(unittest.TestCase):
    def test_outputs_are_reproducible_and_csv_sqlite_match(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_csv, first_sqlite, first_manifest = write_dataset(
                Path(first_dir), row_count=1200, seed=7
            )
            second_csv, _, _ = write_dataset(Path(second_dir), row_count=1200, seed=7)

            with first_csv.open(encoding="utf-8-sig", newline="") as handle:
                first_rows = list(csv.DictReader(handle))
            with second_csv.open(encoding="utf-8-sig", newline="") as handle:
                second_rows = list(csv.DictReader(handle))
            self.assertEqual(len(first_rows), 1200)
            self.assertEqual(first_rows, second_rows)
            self.assertGreaterEqual(len(HEADERS), 12)
            self.assertEqual(list(first_rows[0]), HEADERS)

            with closing(sqlite3.connect(first_sqlite)) as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM customer_sales").fetchone()[0],
                    1200,
                )
                sqlite_columns = [
                    row[1] for row in connection.execute("PRAGMA table_info(customer_sales)")
                ]
                self.assertEqual(sqlite_columns, HEADERS)
                self.assertEqual(
                    connection.execute('SELECT "Order ID" FROM customer_sales ORDER BY rowid LIMIT 1').fetchone()[0],
                    first_rows[0]["Order ID"],
                )

            manifest = json.loads(first_manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["rows"], 1200)
            self.assertEqual(set(manifest["monthly_net_sales"]), {
                f"{year}-{month:02d}" for year in (2024, 2025) for month in range(1, 13)
            })

    def test_fixture_has_messy_values_and_clear_annual_sales_direction(self):
        with tempfile.TemporaryDirectory() as output_dir:
            _, _, manifest_path = write_dataset(Path(output_dir), row_count=1200, seed=2026)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        monthly_sales = manifest["monthly_net_sales"]

        self.assertTrue(any(not row["Customer Segment"] for row in generate_rows(1200, seed=2026)))
        self.assertTrue(any(row["Region"] is None for row in generate_rows(1200, seed=2026)))
        self.assertIn("date unavailable", {row["Order Date"] for row in generate_rows(1200, seed=2026)})
        self.assertTrue(any(
            str(row["Region"]).strip() != row["Region"]
            for row in generate_rows(1200, seed=2026)
            if row["Region"]
        ))

        first_year = sum(value for month, value in monthly_sales.items() if month.startswith("2024"))
        second_year = sum(value for month, value in monthly_sales.items() if month.startswith("2025"))
        growth = [monthly_sales[f"2024-{month:02d}"] for month in range(1, 13)]
        contraction = [monthly_sales[f"2025-{month:02d}"] for month in range(1, 13)]
        self.assertGreater(growth[-1], growth[0])
        self.assertLess(contraction[-1], contraction[0])
        self.assertGreaterEqual(sum(left < right for left, right in zip(growth, growth[1:])), 8)
        self.assertGreaterEqual(sum(left > right for left, right in zip(contraction, contraction[1:])), 8)
        self.assertLess(second_year, first_year)

    def test_rejects_invalid_row_count(self):
        with self.assertRaises(ValueError):
            generate_rows(0, seed=1)


if __name__ == "__main__":
    unittest.main()
