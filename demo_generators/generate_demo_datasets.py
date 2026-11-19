"""Create illustrative, intentionally messy datasets for Boardroom demos only.

These generators are deliberately outside the application runtime. They produce CSV and
SQLite fixtures that demonstrate schema approval, quality scans, KPI discovery, trends,
segments, and anomaly/risk analysis across several business domains.
"""

import argparse
import csv
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path


def messy_date(value: date, rnd: random.Random, rate: float = .06) -> str:
    if rnd.random() < rate:
        return rnd.choice(["", "2025-19-42", "not recorded", "31/31/2025"])
    return rnd.choice([value.isoformat(), value.strftime("%m/%d/%Y"), value.strftime("%d-%b-%Y")])


def write_bundle(name: str, rows: list[dict], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0])
    csv_path = out / f"{name}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader(); writer.writerows(rows)
    db_path = out / f"{name}.sqlite"
    with sqlite3.connect(db_path) as connection:
        quoted = ", ".join(f'"{header}" TEXT' for header in headers)
        connection.execute(f'CREATE TABLE "{name}" ({quoted})')
        connection.executemany(
            f'INSERT INTO "{name}" VALUES ({", ".join("?" for _ in headers)})',
            [[str(row.get(header, "")) for header in headers] for row in rows],
        )
    print(f"{name}: {len(rows):,} rows -> {csv_path} and {db_path}")


def saas(rows: int, rnd: random.Random) -> list[dict]:
    plans = [("Starter", 59), ("Growth", 199), ("Enterprise", 850)]
    regions = ["North America", "EMEA", "APAC", "North America ", "emea"]
    records=[]; start=date(2024, 1, 1)
    for index in range(rows):
        plan, mrr = rnd.choices(plans, weights=[.48,.36,.16])[0]; month=start+timedelta(days=30*rnd.randrange(25))
        status=rnd.choices(["Active","Churned","Paused","active"],weights=[.77,.13,.06,.04])[0]
        expansion=round(max(0,rnd.gauss(20 if plan=="Enterprise" else 4,18)),2)
        records.append({"Subscription_ID":f"SUB-{index+1:06}","Account_ID":f"ACC-{rnd.randrange(1,rows//3):05}","Snapshot_Date":messy_date(month,rnd),"Plan":plan,"Region":rnd.choice(regions),"MRR":round(mrr+expansion,2) if rnd.random()>.04 else "","Seats":rnd.randint(1,250),"Subscription_Status":status,"Churned_Flag":int(status.lower()=="churned"),"Acquisition_Channel":rnd.choice(["Direct","Partner","Organic","Paid"]),"Support_Tickets":rnd.choice([rnd.randint(0,8),"N/A"]),"Contract_Value":round((mrr+expansion)*12,2)})
    return records


def ecommerce(rows: int, rnd: random.Random) -> list[dict]:
    catalog=[("Electronics","Headphones",89.99,.54),("Home","Air Purifier",159,.57),("Apparel","Trail Jacket",132,.48),("Office","Ergonomic Chair",279,.61)]
    records=[]; start=date(2024,1,1)
    for index in range(rows):
        category,product,price,margin=rnd.choice(catalog); units=rnd.randint(1,6); gross=round(price*units,2); discount=rnd.choice([0,.05,.10,.15,.25]); returned=rnd.choices([0,1,2],weights=[.91,.07,.02])[0]
        records.append({"Order_ID":f"ORD-{index+1:07}","Order_Date":messy_date(start+timedelta(days=rnd.randrange(730)),rnd),"Customer_ID":f"CUST-{rnd.randrange(1,rows//3):06}","Customer_Segment":rnd.choice(["Consumer","SMB","Enterprise","consumer"]),"Region":rnd.choice(["North America","EMEA","APAC","North America "]),"Sales_Channel":rnd.choice(["Web","Marketplace","Retail","Partner"]),"Product_Category":category,"Product_Name":product,"Units_Sold":units,"Unit_Price":price,"Gross_Sales":gross if rnd.random()>.03 else "","Discount_Pct":discount,"Discount_Amount":round(gross*discount,2),"Returned_Units":returned,"Net_Sales":round(gross*(1-discount),2),"Total_Cost":round(gross*(1-margin),2),"Profit":round(gross*(1-discount)-gross*(1-margin),2),"Payment_Status":rnd.choice(["Paid","Paid","Pending","paid"]),"Order_Status":rnd.choice(["Completed","Completed","Returned","Cancelled"])})
    return records


def churn(rows: int, rnd: random.Random) -> list[dict]:
    records=[]; start=date(2023,1,1)
    for index in range(rows):
        tenure=rnd.randint(0,72); risk=rnd.random(); churned=int(risk>.76 or (tenure<4 and risk>.60))
        records.append({"Customer_ID":f"CUS-{index+1:06}","Snapshot_Date":messy_date(start+timedelta(days=rnd.randrange(900)),rnd),"Customer_Segment":rnd.choice(["SMB","Mid-Market","Enterprise","SMB "]),"Region":rnd.choice(["North","South","East","West",""]),"Tenure_Months":tenure,"Monthly_Charges":round(rnd.uniform(25,650),2),"Lifetime_Value":round(rnd.uniform(300,24000),2) if rnd.random()>.08 else "","Support_Cases":rnd.randint(0,15),"NPS_Score":rnd.choice([rnd.randint(0,10),"unknown"]),"Payment_Status":rnd.choice(["Current","Late","Overdue"]),"Churned":churned,"Cancellation_Reason":rnd.choice(["Price","Product fit","Service","",None]) if churned else ""})
    return records


def finance(rows: int, rnd: random.Random) -> list[dict]:
    departments=["Sales","Engineering","Operations","Marketing","Finance"]
    records=[]; start=date(2024,1,1)
    for index in range(rows):
        dept=rnd.choice(departments); revenue=rnd.uniform(2000,25000) if dept=="Sales" else 0; expense=rnd.uniform(900,18000)
        records.append({"Transaction_ID":f"FIN-{index+1:06}","Posting_Date":messy_date(start+timedelta(days=rnd.randrange(730)),rnd),"Department":dept,"Cost_Center":f"CC-{rnd.randrange(100,140)}","Region":rnd.choice(["Americas","EMEA","APAC","EMEA "]),"Revenue":round(revenue,2),"Expense":round(expense,2) if rnd.random()>.03 else "","Budget":round(expense*rnd.uniform(.82,1.13),2),"Profit":round(revenue-expense,2),"Transaction_Type":rnd.choice(["Actual","Actual","Actual","Forecast"]),"Approval_Status":rnd.choice(["Approved","Approved","Pending","approved"])})
    return records


def operations(rows: int, rnd: random.Random) -> list[dict]:
    records=[]; start=date(2024,1,1)
    for index in range(rows):
        plant=rnd.choice(["Plant A","Plant B","Plant C","plant a"]); throughput=max(5,int(rnd.gauss(120 if plant=="Plant A" else 88,22))); delay=max(0,round(rnd.gauss(12,9),1))
        records.append({"Work_Order_ID":f"WO-{index+1:06}","Completion_Date":messy_date(start+timedelta(days=rnd.randrange(720)),rnd),"Plant":plant,"Production_Line":rnd.choice(["Line 1","Line 2","Line 3"]),"Shift":rnd.choice(["Day","Night","Swing"]),"Units_Produced":throughput,"Target_Units":rnd.choice([100,120,140]),"Processing_Hours":round(rnd.uniform(1.5,12),2),"Delay_Hours":delay if rnd.random()>.04 else "","Defect_Count":rnd.choice([rnd.randint(0,12),"unknown"]),"Downtime_Minutes":rnd.randint(0,180),"Work_Order_Status":rnd.choice(["Complete","Complete","Delayed","complete"])})
    return records


GENERATORS={"ecommerce":ecommerce,"saas":saas,"churn":churn,"finance":finance,"operations":operations}


def main() -> None:
    parser=argparse.ArgumentParser(description="Generate illustrative messy multi-domain Boardroom demo datasets.")
    parser.add_argument("--domain",choices=[*GENERATORS,"all"],default="all")
    parser.add_argument("--rows",type=int,default=1800)
    parser.add_argument("--out-dir",default="demo_data")
    parser.add_argument("--seed",type=int,default=2026)
    args=parser.parse_args(); rnd=random.Random(args.seed); out=Path(args.out_dir)
    domains=GENERATORS if args.domain=="all" else {args.domain:GENERATORS[args.domain]}
    for name,generator in domains.items(): write_bundle(name,generator(args.rows,rnd),out)


if __name__ == "__main__":
    main()
