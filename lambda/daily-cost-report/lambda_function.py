import boto3
import json
import os
from datetime import datetime, timedelta

def lambda_handler(event, context):
    ce = boto3.client("ce", region_name="us-east-1")
    sns = boto3.client("sns")

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)
    first_of_month = today.replace(day=1)

    daily = ce.get_cost_and_usage(
        TimePeriod={"Start": yesterday.isoformat(), "End": today.isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    mtd = ce.get_cost_and_usage(
        TimePeriod={"Start": first_of_month.isoformat(), "End": today.isoformat()},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )

    prev_daily = ce.get_cost_and_usage(
        TimePeriod={"Start": two_days_ago.isoformat(), "End": yesterday.isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )

    services = []
    for group in daily["ResultsByTime"][0]["Groups"]:
        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
        if amount > 0.01:
            services.append({"name": group["Keys"][0], "amount": amount})

    services.sort(key=lambda x: x["amount"], reverse=True)
    top_5 = services[:5]

    daily_total = sum(s["amount"] for s in services)
    mtd_total = float(mtd["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"])
    prev_total = float(prev_daily["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"])

    if prev_total > 0:
        day_over_day = ((daily_total - prev_total) / prev_total) * 100
    else:
        day_over_day = 0.0

    change_indicator = "↑" if day_over_day > 0 else "↓" if day_over_day < 0 else "→"

    report = f"""
=== Daily Cost Report — {yesterday.isoformat()} ===

DAILY TOTAL:       ${daily_total:.2f}
MONTH-TO-DATE:     ${mtd_total:.2f}
DAY-OVER-DAY:      {change_indicator} {abs(day_over_day):.1f}%

TOP 5 SERVICES:
"""
    for i, svc in enumerate(top_5, 1):
        pct = (svc["amount"] / daily_total * 100) if daily_total > 0 else 0
        report += f"  {i}. {svc['name'][:40]:<40} ${svc['amount']:>8.2f}  ({pct:.1f}%)\n"

    report += f"\n{'=' * 55}\nGenerated at {datetime.utcnow().isoformat()}Z\n"

    topic_arn = os.environ["SNS_TOPIC_ARN"]
    sns.publish(
        TopicArn=topic_arn,
        Subject=f"Daily Cost Report — {yesterday.isoformat()} — ${daily_total:.2f}",
        Message=report,
    )

    return {
        "statusCode": 200,
        "daily_total": daily_total,
        "mtd_total": mtd_total,
        "day_over_day_pct": round(day_over_day, 1),
        "top_service": top_5[0]["name"] if top_5 else "N/A",
    }
