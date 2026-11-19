# Demo data generators

These scripts are separate from the product runtime and only create illustrative data for demos.

Generate all domains:

```powershell
py -3 demo_generators\generate_demo_datasets.py --out-dir demo_data
```

Generate one large SaaS fixture:

```powershell
py -3 demo_generators\generate_demo_datasets.py --domain saas --rows 15000 --out-dir demo_data\saas_large
```

Generated domains: e-commerce orders, SaaS subscriptions, customer churn, finance, and operational performance. For the stated use case, use the e-commerce, SaaS, and churn fixtures. Each has deliberate missing values, invalid/mixed dates, inconsistent category labels, and outlier-like values. They are explicitly illustrative, not application inputs or production data.
