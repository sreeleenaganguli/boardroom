# Boardroom Analytics Copilot

## Start the application

After installing backend and frontend dependencies, start both services from the repository root:

```powershell
.\start-boardroom.ps1
```

The script starts the API on `http://localhost:8000` and the UI on `http://localhost:5173`. Use `-BackendPort` or `-FrontendPort` to override either port. The seeded local login is `admin@boardroom.local` / `admin123`.

The application is focused on the hackathon use case: upload raw CSV/SQLite data, inspect schema and data health, ask questions through validated read-only SQL, review generated bar/line/scatter charts and IQR outlier callouts, then save and export an executive report as Markdown or PDF.

## Generate the hackathon fixture

Synthetic test data is generated separately from the application. From the repository root:

```powershell
py -3 scripts\generate_hackathon_data.py
```

By default this writes a deterministic, intentionally messy 1,200-row customer-sales fixture to `data\customer_sales.csv` and `data\customer_sales.sqlite` (SQLite table `customer_sales`), plus `data\customer_sales_ground_truth.json`. The fixture has 19 business columns, mixed/invalid dates, missing or inconsistent categorical values, discounts, returns, costs, and profit. Monthly net sales are designed to rise through 2024 and contract through 2025, making trend questions and visualizations meaningful. Override its output directory, row count, or seed with `--out-dir`, `--rows`, and `--seed`.

Upload either data file through **Data Workspace**; the application does not generate synthetic datasets or expose a synthetic-data module. The ground-truth JSON is for validating the intended trend, not an application input.

## AI query generation

Without a provider key, Ask Analytics uses a limited schema-aware query planner for row counts, sums, averages, category breakdowns, and date trends. Set `OPENAI_API_KEY` to enable model-generated SQL and one constrained error-correction retry. All generated SQL remains subject to the read-only SQL sandbox and dataset table allowlist. Conversations and their question/answer evidence are persisted. Administrator and Data Analyst roles can select a configured model to generate executive reports from a saved analytics result; provider credentials/endpoints must be configured in the backend environment.

## Verification

```powershell
py -3 -m unittest tests.test_hackathon_generator
cd frontend
npm run build
```
