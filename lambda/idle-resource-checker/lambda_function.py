import boto3
import os
from datetime import datetime, timedelta, timezone

def lambda_handler(event, context):
    ec2 = boto3.client("ec2")
    sns = boto3.client("sns")

    findings = {"unattached_volumes": [], "stopped_instances": [], "unused_eips": []}

    volumes = ec2.describe_volumes(
        Filters=[{"Name": "status", "Values": ["available"]}]
    )
    for vol in volumes["Volumes"]:
        size_gb = vol["Size"]
        vol_type = vol["VolumeType"]
        created = vol["CreateTime"]
        findings["unattached_volumes"].append({
            "id": vol["VolumeId"],
            "size": f"{size_gb} GB",
            "type": vol_type,
            "created": created.strftime("%Y-%m-%d"),
        })

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    instances = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
    )
    for reservation in instances["Reservations"]:
        for inst in reservation["Instances"]:
            launch_time = inst["LaunchTime"]
            state_reason = inst.get("StateTransitionReason", "Unknown")
            name_tag = next(
                (t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"),
                "No Name",
            )
            findings["stopped_instances"].append({
                "id": inst["InstanceId"],
                "name": name_tag,
                "type": inst["InstanceType"],
                "stopped_reason": state_reason[:60],
            })

    addresses = ec2.describe_addresses()
    for addr in addresses["Addresses"]:
        if "InstanceId" not in addr and "NetworkInterfaceId" not in addr:
            findings["unused_eips"].append({
                "ip": addr["PublicIp"],
                "allocation_id": addr["AllocationId"],
            })

    total_findings = (
        len(findings["unattached_volumes"])
        + len(findings["stopped_instances"])
        + len(findings["unused_eips"])
    )

    report = f"""
=== Idle Resource Report — {datetime.utcnow().date().isoformat()} ===
Total findings: {total_findings}

--- Unattached EBS Volumes ({len(findings['unattached_volumes'])}) ---
"""
    if findings["unattached_volumes"]:
        for vol in findings["unattached_volumes"]:
            report += f"  {vol['id']}  {vol['size']:>8}  {vol['type']:<6}  created {vol['created']}\n"
    else:
        report += "  None found.\n"

    report += f"\n--- Stopped EC2 Instances ({len(findings['stopped_instances'])}) ---\n"
    if findings["stopped_instances"]:
        for inst in findings["stopped_instances"]:
            report += f"  {inst['id']}  {inst['name']:<20}  {inst['type']:<12}  {inst['stopped_reason']}\n"
    else:
        report += "  None found.\n"

    report += f"\n--- Unused Elastic IPs ({len(findings['unused_eips'])}) ---\n"
    if findings["unused_eips"]:
        for eip in findings["unused_eips"]:
            report += f"  {eip['ip']:<16}  Allocation: {eip['allocation_id']}\n"
    else:
        report += "  None found.\n"

    estimated_monthly_waste = (
        len(findings["unattached_volumes"]) * 2.50
        + len(findings["unused_eips"]) * 3.60
        + len(findings["stopped_instances"]) * 0.50
    )
    report += f"\nEstimated monthly waste: ~${estimated_monthly_waste:.2f}\n"
    report += f"{'=' * 55}\nGenerated at {datetime.utcnow().isoformat()}Z\n"

    topic_arn = os.environ["SNS_TOPIC_ARN"]
    sns.publish(
        TopicArn=topic_arn,
        Subject=f"Idle Resource Report — {total_findings} findings",
        Message=report,
    )

    return {
        "statusCode": 200,
        "total_findings": total_findings,
        "unattached_volumes": len(findings["unattached_volumes"]),
        "stopped_instances": len(findings["stopped_instances"]),
        "unused_eips": len(findings["unused_eips"]),
        "estimated_monthly_waste": estimated_monthly_waste,
    }
