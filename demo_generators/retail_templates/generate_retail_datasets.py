
"""
Enterprise Synthetic Dataset Generator
---------------------------------------
Generates synthetic, illustrative datasets for:
1. Customer Sales Transactions
2. Retail Store Performance
3. Banking Transactions

Features:
- Exactly 15 columns per dataset
- CSV and SQLite exports
- JSON metadata
- Business-rule validation
- Configurable row count and random seed
- Realistic synthetic banking account balances
- Fraud-pattern simulation

For demonstration and testing only.
No real customer or banking data is used.
"""

import argparse
import csv
import json
import random
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "data" / "generated"

DEFAULT_ROWS = 5000
DEFAULT_SEED = 42

CATALOG = [
    ("Electronics", "Wireless Headphones", "ELE-100", 89.99, 0.54),
    ("Home", "Air Purifier", "HOM-210", 159.00, 0.57),
    ("Apparel", "Trail Jacket", "APP-330", 132.00, 0.48),
    ("Office", "Ergonomic Chair", "OFF-410", 279.00, 0.61),
    ("Beauty", "Skin Care Set", "BEA-520", 46.00, 0.52),
]

LOCATIONS = [
    ("New York", "North America", "USA"),
    ("Toronto", "North America", "Canada"),
    ("London", "EMEA", "UK"),
    ("Berlin", "EMEA", "Germany"),
    ("Singapore", "APAC", "Singapore"),
    ("Sydney", "APAC", "Australia"),
]

NAMES = [
    "Avery Patel",
    "Jordan Kim",
    "Riley Morgan",
    "Taylor Singh",
    "Casey Brown",
    "Morgan Lee",
    "Alex Johnson",
    "Sam Wilson",
    "Jamie Chen",
    "Robin Das",
    "Cameron Roy",
    "Drew Sharma",
]

BANKING_CITIES = [
    "Kolkata",
    "Mumbai",
    "Delhi",
    "Bangalore",
    "Chennai",
    "Hyderabad",
    "Pune",
    "Ahmedabad",
    "Jaipur",
    "Lucknow",
]

MERCHANTS = {
    "Shopping": [
        "Amazon Retail",
        "Flipkart Store",
        "Myntra Fashion",
        "Reliance Digital",
    ],
    "Grocery": [
        "BigBasket",
        "DMart",
        "Blinkit",
        "Local Grocery Store",
    ],
    "Food": [
        "Swiggy",
        "Zomato",
        "Cafe Central",
        "Food Junction",
    ],
    "Utilities": [
        "Electricity Board",
        "Water Department",
        "Internet Services",
    ],
    "Healthcare": [
        "Apollo Pharmacy",
        "City Hospital",
        "HealthPlus",
    ],
    "Travel": [
        "IRCTC",
        "MakeMyTrip",
        "Uber",
        "Ola",
    ],
    "Entertainment": [
        "Netflix",
        "Spotify",
        "BookMyShow",
    ],
    "Salary": [
        "ABC Technologies Payroll",
        "XYZ Solutions Payroll",
        "Corporate Payroll",
    ],
    "Transfer": [
        "Personal Transfer",
        "Family Transfer",
        "Business Transfer",
    ],
    "Other": [
        "Miscellaneous Merchant",
        "Local Merchant",
    ],
}


# ============================================================
# DATASET REGISTRY
# ============================================================

TEMPLATES = {

    # --------------------------------------------------------
    # 1. CUSTOMER SALES TRANSACTIONS
    # --------------------------------------------------------

    "customer_sales_transactions": {
        "name": "Customer Sales Transactions",

        "use_case": (
            "Analyze customer-level retail revenue, repeat "
            "purchase patterns, product mix, and regional contribution."
        ),

        "columns": [
            ("transaction_id", "String", "Unique transaction identifier"),
            ("customer_id", "String", "Synthetic customer identifier"),
            ("customer_name", "String", "Synthetic customer name"),
            ("gender", "Category", "Customer gender segment"),
            ("age", "Integer", "Customer age"),
            ("city", "Category", "Customer city"),
            ("region", "Category", "Geographic region"),
            ("product_id", "String", "Product identifier"),
            ("product_category", "Category", "Product category"),
            ("product_name", "String", "Product name"),
            ("quantity", "Integer", "Units purchased"),
            ("unit_price", "Decimal", "Price per unit"),
            ("discount_percentage", "Decimal", "Discount percentage"),
            ("transaction_date", "Date", "Transaction date"),
            ("total_amount", "Decimal", "Net transaction amount"),
        ],

        "kpis": [
            "Total Revenue",
            "Total Orders",
            "Average Order Value",
            "Repeat Purchase Rate",
            "Revenue Growth",
        ],

        "visualizations": [
            "Monthly revenue line chart",
            "Category contribution bar chart",
            "Regional sales map",
            "Customer purchase frequency chart",
            "Product performance chart",
        ],

        "questions": [
            "Which regions drove monthly growth?",
            "Which customers are repeat buyers?",
            "Which product categories generate the most revenue?",
        ],
    },

    # --------------------------------------------------------
    # 2. RETAIL STORE PERFORMANCE
    # --------------------------------------------------------

    "retail_store_performance": {
        "name": "Retail Store Performance",

        "use_case": (
            "Compare store productivity, footfall conversion, "
            "costs, and profitability."
        ),

        "columns": [
            ("sales_date", "Date", "Store reporting date"),
            ("store_id", "String", "Store identifier"),
            ("store_name", "String", "Store name"),
            ("city", "Category", "Store city"),
            ("region", "Category", "Store region"),
            ("store_format", "Category", "Store format"),
            ("manager_id", "String", "Store manager identifier"),
            ("footfall", "Integer", "Number of store visitors"),
            ("transactions", "Integer", "Completed transactions"),
            ("units_sold", "Integer", "Units sold"),
            ("gross_sales", "Decimal", "Sales before reductions"),
            ("discount_amount", "Decimal", "Total discount"),
            ("returns_amount", "Decimal", "Total returns"),
            ("net_sales", "Decimal", "Net sales"),
            ("operating_cost", "Decimal", "Operating cost"),
        ],

        "kpis": [
            "Total Net Sales",
            "Average Transaction Value",
            "Footfall Conversion Rate",
            "Sales Per Store",
            "Store Profitability",
        ],

        "visualizations": [
            "Daily store sales trend",
            "Store performance comparison",
            "Regional revenue chart",
            "Footfall conversion chart",
            "Store profitability chart",
        ],

        "questions": [
            "Which stores generate the highest revenue?",
            "Which stores have the best conversion rate?",
            "Which regions have the highest operating costs?",
        ],
    },

    # --------------------------------------------------------
    # 3. BANKING TRANSACTIONS
    # --------------------------------------------------------

    "banking_transactions": {
        "name": "Banking Transactions",

        "use_case": (
            "Analyze customer banking activity, transaction "
            "patterns, account balances, payment channels, "
            "and suspicious transactions."
        ),

        "columns": [
            ("transaction_id", "String", "Unique transaction identifier"),
            ("customer_id", "String", "Synthetic customer identifier"),
            ("account_id", "String", "Bank account identifier"),
            ("account_type", "Category", "Account classification"),
            ("transaction_date", "DateTime", "Transaction timestamp"),
            ("transaction_type", "Category", "Transaction classification"),
            ("transaction_channel", "Category", "Payment channel"),
            ("merchant_category", "Category", "Merchant classification"),
            ("merchant_name", "String", "Synthetic merchant name"),
            ("transaction_amount", "Decimal", "Transaction amount"),
            ("transaction_currency", "Category", "Currency code"),
            ("transaction_status", "Category", "Transaction status"),
            ("account_balance", "Decimal", "Balance after transaction"),
            ("transaction_location", "Category", "Transaction location"),
            ("fraud_flag", "Boolean", "Potential fraud indicator"),
        ],

        "kpis": [
            "Total Transaction Volume",
            "Total Transaction Value",
            "Average Transaction Value",
            "Transaction Success Rate",
            "Failed Transaction Rate",
            "Debit vs Credit Ratio",
            "Channel-wise Transaction Volume",
            "Monthly Transaction Growth",
            "Average Account Balance",
            "Fraud Detection Rate",
            "High-Value Transaction Count",
            "Customer Transaction Frequency",
        ],

        "visualizations": [
            "Monthly transaction volume and value line chart",
            "Debit vs Credit donut chart",
            "Transaction channel distribution bar chart",
            "Transaction status pie chart",
            "Daily transaction activity heatmap",
            "Customer transaction volume chart",
            "Transaction amount histogram",
            "Fraudulent transaction scatter plot",
            "Geographical transaction distribution map",
            "Account balance trend chart",
        ],

        "questions": [
            "What is the total transaction value?",
            "Which transaction channels have the highest volume?",
            "What percentage of transactions are successful?",
            "Which customers have the highest transaction frequency?",
            "How does transaction volume vary across weekdays?",
            "Which merchant categories account for the highest spending?",
            "Which transactions exhibit suspicious behaviour?",
            "Are there unusual high-value transactions?",
            "Which accounts have significant balance fluctuations?",
            "What is the ratio of debit transactions to credit transactions?",
            "Which locations contribute the highest transaction volume?",
        ],
    },
}


# ============================================================
# COMMON UTILITIES
# ============================================================

def random_date(start_date, end_date):
    """Generate a random date within a date range."""

    delta = (end_date - start_date).days

    return start_date + timedelta(
        days=random.randint(0, max(delta, 0))
    )


def random_datetime(start_date, end_date):
    """Generate a random timestamp within a date range."""

    day = random_date(start_date, end_date)

    hour = random.randint(0, 23)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)

    return datetime(
        day.year,
        day.month,
        day.day,
        hour,
        minute,
        second,
    )


def round_money(value):
    return round(float(value), 2)


def generate_customer_name():
    return random.choice(NAMES)


# ============================================================
# CUSTOMER SALES GENERATOR
# ============================================================

def generate_customer_sales(rows, start_date, end_date):

    customers = {}

    for i in range(1, max(101, rows // 5) + 1):

        city, region, country = random.choice(LOCATIONS)

        customers[f"CUS-{i:05d}"] = {
            "name": generate_customer_name(),
            "gender": random.choice(["Male", "Female", "Other"]),
            "age": random.randint(18, 70),
            "city": city,
            "region": region,
        }

    records = []

    for i in range(1, rows + 1):

        customer_id = random.choice(list(customers.keys()))
        customer = customers[customer_id]

        category, product, product_id, price, margin = random.choice(CATALOG)

        quantity = random.choices(
            [1, 2, 3, 4, 5],
            weights=[40, 30, 15, 10, 5],
        )[0]

        discount = random.choice([
            0.00, 0.05, 0.10, 0.15, 0.25
        ])

        total = round_money(
            quantity * price * (1 - discount)
        )

        records.append({
            "transaction_id": f"TXN-{i:08d}",
            "customer_id": customer_id,
            "customer_name": customer["name"],
            "gender": customer["gender"],
            "age": customer["age"],
            "city": customer["city"],
            "region": customer["region"],
            "product_id": product_id,
            "product_category": category,
            "product_name": product,
            "quantity": quantity,
            "unit_price": price,
            "discount_percentage": discount,
            "transaction_date": random_date(
                start_date, end_date
            ).isoformat(),
            "total_amount": total,
        })

    return records


# ============================================================
# RETAIL STORE GENERATOR
# ============================================================

def generate_retail_store_performance(
    rows, start_date, end_date
):

    stores = []

    for i, (city, region, country) in enumerate(
        LOCATIONS, start=1
    ):

        stores.append({
            "store_id": f"STR-{i:03d}",
            "store_name": f"{city} Central",
            "city": city,
            "region": region,
            "store_format": random.choice([
                "Flagship", "Mall", "Outlet", "Standard"
            ]),
            "manager_id": f"MGR-{i:03d}",
        })

    records = []

    for i in range(rows):

        store = random.choice(stores)

        footfall = random.randint(100, 1000)

        conversion_rate = random.uniform(0.12, 0.35)

        transactions = min(
            footfall,
            max(1, int(footfall * conversion_rate))
        )

        units_sold = transactions * random.randint(1, 3)

        gross_sales = round_money(
            units_sold * random.uniform(30, 180)
        )

        discount_amount = round_money(
            gross_sales * random.uniform(0.02, 0.12)
        )

        returns_amount = round_money(
            gross_sales * random.uniform(0.00, 0.04)
        )

        net_sales = round_money(
            gross_sales - discount_amount - returns_amount
        )

        operating_cost = round_money(
            random.uniform(1000, 8000)
        )

        records.append({
            "sales_date": random_date(
                start_date, end_date
            ).isoformat(),
            "store_id": store["store_id"],
            "store_name": store["store_name"],
            "city": store["city"],
            "region": store["region"],
            "store_format": store["store_format"],
            "manager_id": store["manager_id"],
            "footfall": footfall,
            "transactions": transactions,
            "units_sold": units_sold,
            "gross_sales": gross_sales,
            "discount_amount": discount_amount,
            "returns_amount": returns_amount,
            "net_sales": net_sales,
            "operating_cost": operating_cost,
        })

    return records


# ============================================================
# BANKING DATA GENERATOR
# ============================================================

def generate_banking_transactions(
    rows, start_date, end_date
):
    """
    Generate realistic synthetic banking transactions.

    Account balances are maintained independently per account
    and transactions are processed chronologically.

    Outgoing and incoming transfers are represented as
    Transfer transactions. In this single-account dataset,
    each transfer represents the movement from the perspective
    of the account represented by account_id.
    """

    # --------------------------------------------------------
    # STEP 1: CREATE CUSTOMERS AND ACCOUNTS
    # --------------------------------------------------------

    number_of_customers = max(
        100,
        min(2000, rows // 5)
    )

    customers = {}
    accounts = {}

    account_types = [
        "Savings",
        "Current",
        "Salary",
        "Fixed Deposit",
    ]

    for i in range(1, number_of_customers + 1):

        customer_id = f"CUS-{i:05d}"

        customers[customer_id] = {
            "name": generate_customer_name(),
            "city": random.choice(BANKING_CITIES),
        }

        number_of_accounts = random.choices(
            [1, 2, 3],
            weights=[70, 25, 5],
        )[0]

        for j in range(number_of_accounts):

            account_id = f"ACC-{len(accounts) + 1:07d}"

            account_type = random.choice(account_types)

            # Opening balance differs by account type.
            if account_type == "Savings":
                opening_balance = random.uniform(5000, 100000)

            elif account_type == "Current":
                opening_balance = random.uniform(20000, 300000)

            elif account_type == "Salary":
                opening_balance = random.uniform(10000, 80000)

            else:
                opening_balance = random.uniform(50000, 500000)

            accounts[account_id] = {
                "customer_id": customer_id,
                "account_type": account_type,
                "opening_balance": round_money(opening_balance),
                "balance": round_money(opening_balance),
            }

    # --------------------------------------------------------
    # STEP 2: GENERATE TRANSACTION EVENTS
    # --------------------------------------------------------

    events = []

    account_ids = list(accounts.keys())

    transaction_types = [
        "Debit",
        "Credit",
        "Transfer",
        "Withdrawal",
        "Deposit",
    ]

    transaction_type_weights = [
        0.42,
        0.25,
        0.13,
        0.12,
        0.08,
    ]

    channels = [
        "UPI",
        "ATM",
        "POS",
        "NEFT",
        "RTGS",
        "IMPS",
        "Mobile Banking",
        "Internet Banking",
    ]

    channel_weights = [
        0.35,
        0.10,
        0.15,
        0.10,
        0.03,
        0.12,
        0.10,
        0.05,
    ]

    for i in range(1, rows + 1):

        account_id = random.choice(account_ids)
        account = accounts[account_id]

        transaction_type = random.choices(
            transaction_types,
            weights=transaction_type_weights,
        )[0]

        channel = random.choices(
            channels,
            weights=channel_weights,
        )[0]

        # ----------------------------------------------------
        # TRANSACTION AMOUNT
        # ----------------------------------------------------

        # Log-normal distribution creates realistic skew:
        # many small transactions and fewer large transactions.

        amount = round_money(
            random.lognormvariate(6.0, 1.0)
        )

        amount = min(amount, 250000)

        # Salary credits have a predictable monthly pattern.
        if transaction_type == "Credit":

            if random.random() < 0.30:

                salary_day = random.randint(1, 7)

                transaction_date = random_datetime(
                    start_date, end_date
                ).replace(day=salary_day)

                merchant_category = "Salary"

                merchant_name = random.choice(
                    MERCHANTS["Salary"]
                )

                amount = round_money(
                    random.uniform(20000, 150000)
                )

            else:

                transaction_date = random_datetime(
                    start_date, end_date
                )

                merchant_category = "Transfer"

                merchant_name = random.choice(
                    MERCHANTS["Transfer"]
                )

        else:

            transaction_date = random_datetime(
                start_date, end_date
            )

            if transaction_type in ("Transfer", "Deposit"):
                merchant_category = "Transfer"

            elif transaction_type == "Withdrawal":
                merchant_category = "Other"

            else:
                merchant_category = random.choices(
                    list(MERCHANTS.keys())[:8],
                    weights=[20, 20, 20, 10, 8, 10, 7, 5],
                )[0]

            merchant_name = random.choice(
                MERCHANTS[merchant_category]
            )

        # ----------------------------------------------------
        # CHANNEL-SPECIFIC RULES
        # ----------------------------------------------------

        if channel == "ATM":
            transaction_type = "Withdrawal"
            merchant_category = "Other"
            merchant_name = "ATM Cash Withdrawal"

        elif channel == "POS":
            if transaction_type not in ("Debit",):
                transaction_type = "Debit"

        elif channel == "UPI":
            if transaction_type not in ("Debit", "Credit"):
                transaction_type = "Debit"

        # ----------------------------------------------------
        # FRAUD PATTERN GENERATION
        # ----------------------------------------------------

        fraud_flag = random.random() < 0.01

        if fraud_flag:

            # Suspicious transactions tend to be larger.
            amount = round_money(
                random.uniform(20000, 100000)
            )

            # Occasionally simulate an unusual location.
            location = random.choice([
                "Mumbai",
                "Delhi",
                "Kolkata",
                "Bangalore",
                "Chennai",
                "Hyderabad",
                "International",
            ])

        else:

            location = customers[
                account["customer_id"]
            ]["city"]

        # ----------------------------------------------------
        # TRANSACTION STATUS
        # ----------------------------------------------------

        transaction_status = random.choices(
            ["Success", "Failed", "Reversed"],
            weights=[0.955, 0.035, 0.010],
        )[0]

        # ----------------------------------------------------
        # INTERNAL TRANSACTION DIRECTION
        # ----------------------------------------------------

        # Direction is internal metadata and is not included
        # in the final 15-column dataset.

        if transaction_type in ("Debit", "Withdrawal"):
            direction = "OUT"

        elif transaction_type in ("Credit", "Deposit"):
            direction = "IN"

        else:
            direction = random.choice(["IN", "OUT"])

        # ----------------------------------------------------
        # INSUFFICIENT BALANCE VALIDATION
        # ----------------------------------------------------

        current_balance = account["balance"]

        if (
            transaction_status == "Success"
            and direction == "OUT"
            and amount > current_balance
        ):

            transaction_status = "Failed"

        events.append({
            "transaction_id": f"BNK-TXN-{i:08d}",
            "account_id": account_id,
            "transaction_date": transaction_date,
            "transaction_type": transaction_type,
            "transaction_channel": channel,
            "merchant_category": merchant_category,
            "merchant_name": merchant_name,
            "transaction_amount": amount,
            "transaction_status": transaction_status,
            "transaction_location": location,
            "fraud_flag": fraud_flag,
            "_direction": direction,
        })

    # --------------------------------------------------------
    # STEP 3: SORT TRANSACTIONS CHRONOLOGICALLY
    # --------------------------------------------------------

    events.sort(
        key=lambda x: (
            x["account_id"],
            x["transaction_date"],
            x["transaction_id"],
        )
    )

    # --------------------------------------------------------
    # STEP 4: CALCULATE ACCOUNT BALANCES
    # --------------------------------------------------------

    records = []

    for event in events:

        account = accounts[event["account_id"]]

        amount = event["transaction_amount"]

        if event["transaction_status"] == "Success":

            if event["_direction"] == "OUT":
                account["balance"] -= amount

            else:
                account["balance"] += amount

        account["balance"] = round_money(
            account["balance"]
        )

        customer_id = account["customer_id"]

        records.append({
            "transaction_id": event["transaction_id"],
            "customer_id": customer_id,
            "account_id": event["account_id"],
            "account_type": account["account_type"],
            "transaction_date": event[
                "transaction_date"
            ].strftime("%Y-%m-%d %H:%M:%S"),
            "transaction_type": event["transaction_type"],
            "transaction_channel": event[
                "transaction_channel"
            ],
            "merchant_category": event["merchant_category"],
            "merchant_name": event["merchant_name"],
            "transaction_amount": amount,
            "transaction_currency": "INR",
            "transaction_status": event[
                "transaction_status"
            ],
            "account_balance": account["balance"],
            "transaction_location": event[
                "transaction_location"
            ],
            "fraud_flag": event["fraud_flag"],
        })

    return records


# ============================================================
# GENERATOR REGISTRY
# ============================================================

GENERATORS = {
    "customer_sales_transactions": generate_customer_sales,
    "retail_store_performance": generate_retail_store_performance,
    "banking_transactions": generate_banking_transactions,
}


# ============================================================
# DATA VALIDATION
# ============================================================

def validate_dataset(dataset_name, records):

    if dataset_name not in TEMPLATES:
        raise ValueError(
            f"Unknown dataset: {dataset_name}"
        )

    expected_columns = [
        column[0]
        for column in TEMPLATES[dataset_name]["columns"]
    ]

    errors = []

    # Validate number of columns.
    if len(expected_columns) != 15:
        errors.append(
            f"Schema has {len(expected_columns)} columns instead of 15."
        )

    for index, record in enumerate(records):

        if len(record) != 15:
            errors.append(
                f"Record {index} does not contain 15 columns."
            )

        if list(record.keys()) != expected_columns:
            errors.append(
                f"Record {index} has incorrect column order."
            )

    if dataset_name == "banking_transactions":

        transaction_ids = [
            record["transaction_id"]
            for record in records
        ]

        if len(transaction_ids) != len(set(transaction_ids)):
            errors.append(
                "Duplicate banking transaction IDs found."
            )

        # Validate chronological account balances.
        previous_balances = {}

        for record in records:

            account_id = record["account_id"]

            amount = record["transaction_amount"]

            balance = record["account_balance"]

            status = record["transaction_status"]

            if amount <= 0:
                errors.append(
                    f"Invalid transaction amount: {account_id}"
                )

            if account_id not in previous_balances:
                previous_balances[account_id] = None

            previous = previous_balances[account_id]

            if previous is not None and status != "Success":
                if balance != previous:
                    errors.append(
                        f"Failed/reversed transaction changed balance: {account_id}"
                    )

            previous_balances[account_id] = balance

    if errors:
        raise ValueError(
            "Dataset validation failed:\n"
            + "\n".join(errors[:20])
        )

    return {
        "valid": True,
        "total_records": len(records),
        "total_columns": 15,
        "validation_errors": 0,
    }


# ============================================================
# DATA QUALITY SUMMARY
# ============================================================

def generate_quality_report(records):

    if not records:
        return {
            "total_records": 0,
            "total_columns": 15,
        }

    columns = list(records[0].keys())

    column_summary = {}

    for column in columns:

        values = [
            record[column]
            for record in records
        ]

        null_count = sum(
            value is None or value == ""
            for value in values
        )

        column_summary[column] = {
            "null_count": null_count,
            "unique_count": len(set(values)),
            "null_percentage": round(
                null_count / len(values) * 100, 2
            ),
        }

    return {
        "total_records": len(records),
        "total_columns": len(columns),
        "total_null_values": sum(
            item["null_count"]
            for item in column_summary.values()
        ),
        "column_summary": column_summary,
    }


# ============================================================
# CSV EXPORT
# ============================================================

def export_csv(records, output_path):

    if not records:
        raise ValueError("Cannot export an empty dataset.")

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_path,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(records[0].keys())
        )

        writer.writeheader()
        writer.writerows(records)


# ============================================================
# SQLITE EXPORT
# ============================================================

def export_sqlite(
    records,
    output_path,
    table_name
):

    if not records:
        raise ValueError("Cannot export an empty dataset.")

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    connection = sqlite3.connect(output_path)

    try:

        cursor = connection.cursor()

        columns = list(records[0].keys())

        column_definitions = []

        for column in columns:

            if column in (
                "transaction_id",
                "customer_id",
                "account_id",
                "store_id",
                "product_id",
            ):
                sql_type = "TEXT"

            elif column in (
                "age",
                "quantity",
                "footfall",
                "transactions",
                "units_sold",
            ):
                sql_type = "INTEGER"

            elif column == "fraud_flag":
                sql_type = "INTEGER"

            elif column.endswith("_date"):
                sql_type = "TEXT"

            else:
                sql_type = "REAL"

            column_definitions.append(
                f'"{column}" {sql_type}'
            )

        create_query = (
            f'CREATE TABLE IF NOT EXISTS "{table_name}" '
            f'({", ".join(column_definitions)})'
        )

        cursor.execute(create_query)

        cursor.execute(
            f'DELETE FROM "{table_name}"'
        )

        placeholders = ", ".join(
            ["?"] * len(columns)
        )

        insert_query = (
            f'INSERT INTO "{table_name}" '
            f'({", ".join([f"{column}" for column in columns])}) '
            f'VALUES ({placeholders})'
        )

        values = []

        for record in records:

            row = []

            for column in columns:

                value = record[column]

                if isinstance(value, bool):
                    value = int(value)

                row.append(value)

            values.append(tuple(row))

        cursor.executemany(
            insert_query,
            values
        )

        connection.commit()

    finally:
        connection.close()


# ============================================================
# METADATA GENERATOR
# ============================================================

def generate_metadata(
    dataset_name,
    records,
    start_date,
    end_date,
    seed,
    validation_report,
    quality_report,
):

    template = TEMPLATES[dataset_name]

    return {
        "dataset_name": template["name"],
        "dataset_key": dataset_name,
        "description": template["use_case"],
        "record_count": len(records),
        "column_count": 15,
        "columns": [
            {
                "name": column[0],
                "data_type": column[1],
                "description": column[2],
            }
            for column in template["columns"]
        ],
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "random_seed": seed,
        "generation_timestamp": datetime.now().isoformat(),
        "kpis": template["kpis"],
        "visualizations": template["visualizations"],
        "analytical_questions": template["questions"],
        "validation": validation_report,
        "data_quality": quality_report,
    }


# ============================================================
# MAIN DATASET GENERATION
# ============================================================

def generate_dataset(
    dataset_name,
    rows,
    start_date,
    end_date,
    seed,
    formats,
):

    if dataset_name not in GENERATORS:
        raise ValueError(
            f"Unsupported dataset: {dataset_name}"
        )

    if rows <= 0:
        raise ValueError(
            "Number of rows must be greater than zero."
        )

    if start_date > end_date:
        raise ValueError(
            "Start date cannot be after end date."
        )

    random.seed(seed)

    print("\n" + "=" * 60)
    print(f"Generating: {TEMPLATES[dataset_name]['name']}")
    print(f"Records: {rows}")
    print(f"Seed: {seed}")
    print("=" * 60)

    generator = GENERATORS[dataset_name]

    records = generator(
        rows,
        start_date,
        end_date
    )

    validation_report = validate_dataset(
        dataset_name,
        records
    )

    quality_report = generate_quality_report(
        records
    )

    output_folder = OUTPUT_DIR / dataset_name

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # EXPORT FILES
    # --------------------------------------------------------

    for output_format in formats:

        if output_format == "csv":

            output_path = (
                output_folder /
                f"{dataset_name}_{rows}.csv"
            )

            export_csv(records, output_path)

            print(f"CSV exported: {output_path}")

        elif output_format == "sqlite":

            output_path = (
                output_folder /
                f"{dataset_name}.db"
            )

            export_sqlite(
                records,
                output_path,
                dataset_name
            )

            print(f"SQLite exported: {output_path}")

        else:
            raise ValueError(
                f"Unsupported output format: {output_format}"
            )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    metadata = generate_metadata(
        dataset_name,
        records,
        start_date,
        end_date,
        seed,
        validation_report,
        quality_report,
    )

    metadata_path = output_folder / "metadata.json"

    with open(
        metadata_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            metadata,
            file,
            indent=4,
            default=str,
        )

    # --------------------------------------------------------
    # QUALITY REPORT
    # --------------------------------------------------------

    quality_path = (
        output_folder /
        "data_quality_report.json"
    )

    with open(
        quality_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            quality_report,
            file,
            indent=4,
        )

    print(f"Metadata: {metadata_path}")
    print(f"Quality report: {quality_path}")

    print("\nDataset generated successfully.")
    print(f"Total records: {len(records)}")
    print(f"Total columns: {len(records[0])}")
    print(f"Validation: {validation_report['valid']}")

    return records


# ============================================================
# CLI
# ============================================================

def parse_arguments():

    parser = argparse.ArgumentParser(
        description=(
            "Enterprise Synthetic Dataset Generator"
        )
    )

    parser.add_argument(
        "--dataset",
        type=str,
        choices=list(TEMPLATES.keys()),
        help="Dataset template to generate.",
    )

    parser.add_argument(
        "--rows",
        type=int,
        default=DEFAULT_ROWS,
        help="Number of records to generate.",
    )

    parser.add_argument(
        "--start-date",
        type=lambda x: date.fromisoformat(x),
        default=date(2025, 1, 1),
        help="Start date in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--end-date",
        type=lambda x: date.fromisoformat(x),
        default=date(2025, 12, 31),
        help="End date in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Random seed for reproducibility.",
    )

    parser.add_argument(
        "--format",
        type=str,
        default="csv",
        help="Output formats: csv,sqlite or csv,sqlite.",
    )

    parser.add_argument(
        "--list-datasets",
        action="store_true",
        help="Display available dataset templates.",
    )

    return parser.parse_args()


# ============================================================
# APPLICATION ENTRY POINT
# ============================================================

def main():

    args = parse_arguments()

    if args.list_datasets:

        print("\nAVAILABLE DATASET TEMPLATES\n")

        for key, template in TEMPLATES.items():

            print(f"Dataset ID: {key}")
            print(f"Name: {template['name']}")
            print(f"Use case: {template['use_case']}")
            print("Columns: 15")
            print("-" * 60)

        return

    if not args.dataset:

        print(
            "Please provide --dataset or use --list-datasets."
        )

        return

    formats = [
        item.strip().lower()
        for item in args.format.split(",")
        if item.strip()
    ]

    supported_formats = {"csv", "sqlite"}

    if not formats or not set(formats).issubset(
        supported_formats
    ):
        raise ValueError(
            "Supported formats are csv and sqlite."
        )

    generate_dataset(
        dataset_name=args.dataset,
        rows=args.rows,
        start_date=args.start_date,
        end_date=args.end_date,
        seed=args.seed,
        formats=formats,
    )


if __name__ == "__main__":
    main()
