"""Generate a deterministic customer-sales fixture for analytics demonstrations."""

import argparse
import csv
import json
import random
import sqlite3
from calendar import monthrange
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Any


HEADERS = [
    "Order ID",
    "Order Date",
    "Customer ID",
    "Customer Segment",
    "Region",
    "Sales Channel",
    "Product Category",
    "Product Name",
    "Units Sold",
    "Unit Price",
    "Gross Sales",
    "Discount Pct",
    "Discount Amount",
    "Returned Units",
    "Net Sales",
    "Unit Cost",
    "Total Cost",
    "Profit",
    "Payment Status",
]

MONTHLY_SALES_FACTORS = [
    0.55, 0.63, 0.73, 0.84, 0.96, 1.11, 1.27, 1.46, 1.68, 1.93, 2.23, 2.56,
    2.30, 1.96, 1.66, 1.41, 1.20, 1.02, 0.87, 0.74, 0.63, 0.53, 0.45, 0.39,
]
PRODUCTS = {
    "Electronics": [("Wireless Headphones", 89.99, 0.56), ("Smart Speaker", 119.00, 0.59),
                    ("USB-C Dock", 74.50, 0.52)],
    "Home": [("Air Purifier", 159.00, 0.62), ("Desk Lamp", 42.00, 0.48),
             ("Coffee Maker", 94.00, 0.57)],
    "Apparel": [("Everyday Backpack", 58.00, 0.43), ("Trail Jacket", 132.00, 0.51),
                ("Cotton T-Shirt", 24.00, 0.38)],
    "Office": [("Ergonomic Chair", 279.00, 0.64), ("Monitor Stand", 68.00, 0.49),
               ("Mechanical Keyboard", 105.00, 0.55)],
}
SEGMENTS = ("Consumer", "Small Business", "Enterprise")
REGIONS = ("Northeast", "Southeast", "Midwest", "Southwest", "West")
CHANNELS = ("Web", "Retail", "Partner")
PAYMENT_STATUSES = ("Paid", "Paid", "Paid", "Pending", "Refunded")
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d")


def _format_date(value: date, rng: random.Random) -> str:
    if rng.random() < 0.008:
        return "date unavailable"
    formatted = value.strftime(rng.choice(DATE_FORMATS))
    if rng.random() < 0.04:
        return f" {formatted} "
    return formatted


def generate_rows(row_count: int = 1200, seed: int = 2026) -> list[dict[str, Any]]:
    if not 24 <= row_count <= 100_000:
        raise ValueError("row_count must be between 24 and 100000")

    rng = random.Random(seed)
    products = [
        (category, name, price, cost_ratio)
        for category, items in PRODUCTS.items()
        for name, price, cost_ratio in items
    ]
    rows = []
    start_year, start_month = 2024, 1

    for order_index in range(row_count):
        month_index = min(23, order_index * 24 // row_count)
        year = start_year + (start_month - 1 + month_index) // 12
        month = (start_month - 1 + month_index) % 12 + 1
        order_date = date(year, month, rng.randint(1, monthrange(year, month)[1]))
        factor = MONTHLY_SALES_FACTORS[month_index]
        category, product, unit_price, cost_ratio = rng.choice(products)
        unit_price = round(unit_price * rng.uniform(0.94, 1.06), 2)

        base_units = rng.choices((1, 2, 3, 4, 5, 6), weights=(14, 25, 26, 18, 11, 6))[0]
        units_sold = max(1, round(base_units * factor * rng.uniform(0.88, 1.12)))
        gross_sales = round(unit_price * units_sold, 2)
        discount_pct = rng.choices((0.0, 0.05, 0.10, 0.15, 0.20), weights=(36, 24, 21, 13, 6))[0]
        discount_amount = round(gross_sales * discount_pct, 2)
        returned_units = 1 if units_sold > 1 and rng.random() < 0.035 else 0
        net_sales = round(gross_sales - discount_amount - returned_units * unit_price * (1 - discount_pct), 2)
        unit_cost = round(unit_price * cost_ratio, 2)
        total_cost = round(unit_cost * (units_sold - returned_units), 2)

        customer_number = rng.randint(1, min(320, max(24, row_count // 3)))
        segment = SEGMENTS[(customer_number - 1) % len(SEGMENTS)]
        region = rng.choice(REGIONS)
        channel = rng.choices(CHANNELS, weights=(57, 28, 15))[0]
        if rng.random() < 0.018:
            segment = ""
        if rng.random() < 0.012:
            region = None
        elif rng.random() < 0.03:
            region = f" {region.lower()} "
        if rng.random() < 0.01:
            channel = ""

        rows.append({
            "Order ID": f"SO-{order_index + 1:07d}",
            "Order Date": _format_date(order_date, rng),
            "Customer ID": f"C-{customer_number:05d}",
            "Customer Segment": segment,
            "Region": region,
            "Sales Channel": channel,
            "Product Category": category,
            "Product Name": product,
            "Units Sold": units_sold,
            "Unit Price": unit_price,
            "Gross Sales": gross_sales,
            "Discount Pct": discount_pct,
            "Discount Amount": discount_amount,
            "Returned Units": returned_units,
            "Net Sales": net_sales,
            "Unit Cost": unit_cost,
            "Total Cost": total_cost,
            "Profit": round(net_sales - total_cost, 2),
            "Payment Status": rng.choice(PAYMENT_STATUSES),
        })
    return rows


def _monthly_ground_truth(rows: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        raw_date = row["Order Date"].strip()
        parsed_date = None
        for date_format in DATE_FORMATS:
            try:
                parsed_date = date.fromisoformat(raw_date) if date_format == "%Y-%m-%d" else None
                if parsed_date is None:
                    parsed_date = datetime.strptime(raw_date, date_format).date()
                break
            except ValueError:
                continue
        if parsed_date is None:
            continue
        month_key = parsed_date.strftime("%Y-%m")
        totals[month_key] = round(totals.get(month_key, 0.0) + row["Net Sales"], 2)
    return dict(sorted(totals.items()))


def write_dataset(
    output_dir: Path,
    row_count: int = 1200,
    seed: int = 2026,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = generate_rows(row_count, seed)
    csv_path = output_dir / "customer_sales.csv"
    sqlite_path = output_dir / "customer_sales.sqlite"
    manifest_path = output_dir / "customer_sales_ground_truth.json"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    column_types = {
        "Order ID": "TEXT PRIMARY KEY", "Order Date": "TEXT", "Customer ID": "TEXT",
        "Customer Segment": "TEXT", "Region": "TEXT", "Sales Channel": "TEXT",
        "Product Category": "TEXT", "Product Name": "TEXT", "Units Sold": "INTEGER",
        "Unit Price": "REAL", "Gross Sales": "REAL", "Discount Pct": "REAL",
        "Discount Amount": "REAL", "Returned Units": "INTEGER", "Net Sales": "REAL",
        "Unit Cost": "REAL", "Total Cost": "REAL", "Profit": "REAL",
        "Payment Status": "TEXT",
    }
    definitions = ", ".join(
        f'"{name}" {column_types[name]}' for name in HEADERS
    )
    placeholders = ", ".join("?" for _ in HEADERS)
    with closing(sqlite3.connect(sqlite_path)) as connection:
        with connection:
            connection.execute("DROP TABLE IF EXISTS customer_sales")
            connection.execute(f"CREATE TABLE customer_sales ({definitions})")
            connection.executemany(
                f"INSERT INTO customer_sales VALUES ({placeholders})",
                [[row[name] for name in HEADERS] for row in rows],
            )

    monthly_sales = _monthly_ground_truth(rows)
    manifest = {
        "rows": row_count,
        "seed": seed,
        "columns": HEADERS,
        "monthly_net_sales": monthly_sales,
        "expected_direction": {
            "growth_period": ["2024-01", "2024-12"],
            "contraction_period": ["2025-01", "2025-12"],
            "description": "Net sales have a clear upward trend across 2024 and a clear downward trend through 2025, with realistic order-level variation.",
        },
        "data_quality_notes": [
            "Order dates use four common formats with a small number of unparseable entries.",
            "A small fraction of customer segment, region, and channel values are blank or inconsistently cased.",
            "Orders include discounts, partial returns, variable costs, and occasional pending/refunded payments.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return csv_path, sqlite_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("data"))
    parser.add_argument("--rows", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    csv_path, sqlite_path, manifest_path = write_dataset(args.out_dir, args.rows, args.seed)
    print(f"Generated {args.rows} realistic, seeded customer-sales transactions.")
    print(f"CSV: {csv_path.resolve()}")
    print(f"SQLite: {sqlite_path.resolve()} (table: customer_sales)")
    print(f"Ground truth: {manifest_path.resolve()}")


if __name__ == "__main__":
    main()
