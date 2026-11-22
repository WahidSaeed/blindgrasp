#!/bin/bash
# Runs on every boot (systemd unit "blindgrasp"): update code, build images, run sim server + UI + Caddy (HTTPS).
# The public address is <ip-with-dashes>.sslip.io, so Caddy can get a Let's Encrypt certificate without a domain.
set -euo pipefail
REPO=https://github.com/WahidSaeed/blindgrasp.git
DIR=/opt/blindgrasp
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" \
  http://169.254.169.254/latest/meta-data/placement/region)

# 2 GB swap so the UI build doesn't run out of memory next to the running simulation.
if [ ! -f /swapfile ]; then fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile; fi
swapon /swapfile 2>/dev/null || true

if [ -d $DIR/.git ]; then git -C $DIR pull --ff-only; else git clone --depth 1 $REPO $DIR; fi
docker build -t blindgrasp $DIR
docker build -t blindgrasp-web $DIR/web

# Secrets/config from SSM Parameter Store (the instance role may read /blindgrasp/*).
param() { aws ssm get-parameter --region "$REGION" --name "$1" --with-decryption --query Parameter.Value --output text 2>/dev/null || echo "$2"; }
TOKEN=$(param /blindgrasp/TABPFN_TOKEN "")
ORIGINS=$(param /blindgrasp/ALLOWED_ORIGINS "*")

# Public IP (Elastic IP) -> HTTPS host name.
for i in $(seq 1 30); do
  IMDS=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
  IP=$(curl -s -H "X-aws-ec2-metadata-token: $IMDS" http://169.254.169.254/latest/meta-data/public-ipv4 || true)
  [ -n "$IP" ] && break; sleep 5
done
HOST="${IP//./-}.sslip.io"

docker network inspect bg >/dev/null 2>&1 || docker network create bg
docker rm -f sim web caddy >/dev/null 2>&1 || true
docker run -d --name sim --network bg --restart unless-stopped \
  -e TABPFN_TOKEN="$TOKEN" -e ALLOWED_ORIGINS="$ORIGINS" -e WIDTH=960 -e HEIGHT=600 -e FPS=15 -e SPEED=2 blindgrasp

docker run -d --name web --network bg --restart unless-stopped blindgrasp-web

mkdir -p /etc/caddy
cat > /etc/caddy/Caddyfile <<CADDY
$HOST {
  encode {
    gzip
    match {
      not header Content-Type multipart/*
    }
  }
  @sim path /state /action /stream*
  reverse_proxy @sim sim:8000 {
    flush_interval -1
  }
  reverse_proxy web:3000
}
CADDY
docker run -d --name caddy --network bg --restart unless-stopped -p 80:80 -p 443:443 \
  -v /etc/caddy/Caddyfile:/etc/caddy/Caddyfile:ro -v caddy_data:/data caddy:2
echo "Blindgrasp: https://$HOST"
