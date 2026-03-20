# Lab M7.10 - FinOps Automation and Reporting

## What I Did
- Built three Lambda functions: daily cost report, idle resource checker, weekly digest
- Configured EventBridge rules for automated scheduling
- Set up SNS email delivery for all reports

## Key Findings
- Daily average spend: $0.00
- Idle resources found: 0 unattached volumes, 1 stopped instance, 0 unused EIPs
- Estimated monthly waste from idle resources: $0.50

## Architecture
- EventBridge → Lambda (daily-cost-report) → SNS → Email (daily at 8 AM)
- EventBridge → Lambda (idle-resource-checker) → SNS → Email (Mondays at 9 AM)
- EventBridge → Lambda (finops-weekly-digest) → SNS → Email (Mondays at 10 AM)

## Screenshots
- `screenshots/daily-cost-email.png`
- `screenshots/idle-resource-email.png`
- `screenshots/weekly-digest-email.png`
