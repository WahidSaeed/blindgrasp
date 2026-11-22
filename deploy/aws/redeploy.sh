#!/bin/bash
# Run on your Mac after pushing to main: tells the EC2 instance (via SSM, no SSH) to pull, rebuild and restart.
set -euo pipefail
REGION=${AWS_REGION:-eu-central-1}
IID=$(aws ec2 describe-instances --region "$REGION" --filters Name=tag:Name,Values=blindgrasp-sim Name=instance-state-name,Values=running \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
[ "$IID" = "None" ] && { echo "no running blindgrasp-sim instance in $REGION"; exit 1; }
echo "Redeploying on $IID (pull, build, restart; a few minutes)..."
CID=$(aws ssm send-command --region "$REGION" --instance-ids "$IID" --document-name AWS-RunShellScript --timeout-seconds 1500 \
  --parameters 'commands=["systemctl restart blindgrasp","journalctl -u blindgrasp -n 1 --no-pager -o cat"]' \
  --query Command.CommandId --output text)
until s=$(aws ssm get-command-invocation --region "$REGION" --command-id "$CID" --instance-id "$IID" --query Status --output text 2>/dev/null) \
  && [ "$s" != "Pending" ] && [ "$s" != "InProgress" ]; do sleep 5; done
aws ssm get-command-invocation --region "$REGION" --command-id "$CID" --instance-id "$IID" --query StandardOutputContent --output text
echo "Status: $s"
