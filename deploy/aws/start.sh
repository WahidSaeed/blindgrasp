#!/bin/bash
# Runs on every boot (systemd unit "blindgrasp"): update code, build the image, run it on port 80.
# One container serves both the UI and the sim API, at the instance's default AWS address (plain HTTP).
set -euo pipefail
REPO=https://github.com/WahidSaeed/blindgrasp.git
DIR=/opt/blindgrasp
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" \
  http://169.254.169.254/latest/meta-data/placement/region)

# 2 GB swap so the image build (UI + Python) doesn't run out of memory next to the running simulation.
if [ ! -f /swapfile ]; then fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile; fi
swapon /swapfile 2>/dev/null || true

if [ -d $DIR/.git ]; then git -C $DIR pull --ff-only; else git clone --depth 1 $REPO $DIR; fi
docker build -t blindgrasp $DIR

# Secrets/config from SSM Parameter Store (the instance role may read /blindgrasp/*).
param() { aws ssm get-parameter --region "$REGION" --name "$1" --with-decryption --query Parameter.Value --output text 2>/dev/null || echo "$2"; }
TOKEN=$(param /blindgrasp/TABPFN_TOKEN "")
ORIGINS=$(param /blindgrasp/ALLOWED_ORIGINS "*")

docker rm -f sim web caddy >/dev/null 2>&1 || true
docker run -d --name sim --restart unless-stopped -p 80:8000 \
  -e TABPFN_TOKEN="$TOKEN" -e ALLOWED_ORIGINS="$ORIGINS" -e WIDTH=960 -e HEIGHT=600 -e FPS=15 -e SPEED=2 blindgrasp

IMDS=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
echo "Blindgrasp: http://$(curl -s -H "X-aws-ec2-metadata-token: $IMDS" http://169.254.169.254/latest/meta-data/public-hostname)"
