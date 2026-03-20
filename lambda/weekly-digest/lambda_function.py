import boto3
import json
import os
from datetime import datetime, timedelta

def lambda_handler(event, context):
    ce = boto3.client("ce", region_name="us-east-1")
    ec2 = boto3.client("ec2")
    sns = boto3.client("sns")

    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    first_of_month = today.replace(day=1)

    weekly = ce.get_cost_and_usage(
        TimePeriod={"Start": week_ago.isoformat(), "End": today.isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )

    daily_costs = []
    for day in weekly["ResultsByTime"]:
        amount = float(day["Total"]["UnblendedCost"]["Amount"])
        daily_costs.append({"date": day["TimePeriod"]["Start"], "amount": amount})

    weekly_total = sum(d["amount"] for d in daily_costs)
    avg_daily = weekly_total / 7 if daily_costs else 0

    mtd = ce.get_cost_and_usage(
        TimePeriod={"Start": first_of_month.isoformat(), "End": today.isoformat()},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    services = []
    for group in mtd["ResultsByTime"][0]["Groups"]:
        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
        if amount > 0.01:
            services.append((group["Keys"][0], amount))
    services.sort(key=lambda x: x[1], reverse=True)
    mtd_total = sum(amt for _, amt in services)

    unattached = ec2.describe_volumes(Filters=[{"Name": "status", "Values": ["available"]}])
    stopped = ec2.describe_instances(Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}])
    eips = ec2.describe_addresses()

    idle_volumes = len(unattached["Volumes"])
    idle_instances = sum(len(r["Instances"]) for r in stopped["Reservations"])
    idle_eips = sum(1 for a in eips["Addresses"] if "InstanceId" not in a and "NetworkInterfaceId" not in a)

    digest = f"""
{'=' * 60}
  FINOPS WEEKLY DIGEST — Week of {week_ago.isoformat()}
{'=' * 60}

COST SUMMARY
  Weekly Spend:         ${weekly_total:.2f}
  Average Daily:        ${avg_daily:.2f}
  Month-to-Date:        ${mtd_total:.2f}

DAILY BREAKDOWN:
"""
    for day in daily_costs:
        bar_len = int(day["amount"] / max(avg_daily, 0.01) * 20)
        bar = "█" * min(bar_len, 40)
        digest += f"  {day['date']}  ${day['amount']:>7.2f}  {bar}\n"

    digest += f"""
TOP 5 SERVICES (MTD):
"""
    for i, (svc, amt) in enumerate(services[:5], 1):
        pct = (amt / mtd_total * 100) if mtd_total > 0 else 0
        digest += f"  {i}. {svc[:35]:<35} ${amt:>8.2f}  ({pct:.1f}%)\n"

    waste = idle_volumes * 2.50 + idle_eips * 3.60 + idle_instances * 0.50
    digest += f"""
{'-' * 60}
IDLE RESOURCE FINDINGS
  Unattached EBS Volumes:   {idle_volumes}
  Stopped EC2 Instances:    {idle_instances}
  Unused Elastic IPs:       {idle_eips}
  Estimated Monthly Waste:  ~${waste:.2f}

RECOMMENDED ACTIONS:
"""
    if idle_volumes > 0:
        digest += f"  • Review and delete {idle_volumes} unattached EBS volume(s)\n"
    if idle_instances > 0:
        digest += f"  • Terminate or restart {idle_instances} stopped instance(s)\n"
    if idle_eips > 0:
        digest += f"  • Release {idle_eips} unused Elastic IP(s) (${idle_eips * 3.60:.2f}/mo)\n"
    if waste == 0:
        digest += "  • No idle resources detected — great job!\n"

    digest += f"""
{'=' * 60}
Generated at {datetime.utcnow().isoformat()}Z
"""

    topic_arn = os.environ["SNS_TOPIC_ARN"]
    sns.publish(
        TopicArn=topic_arn,
        Subject=f"FinOps Weekly Digest — ${weekly_total:.2f} this week, {idle_volumes + idle_instances + idle_eips} idle resources",
        Message=digest,
    )

    return {
        "statusCode": 200,
        "weekly_total": weekly_total,
        "mtd_total": mtd_total,
        "idle_resources": idle_volumes + idle_instances + idle_eips,
    }
