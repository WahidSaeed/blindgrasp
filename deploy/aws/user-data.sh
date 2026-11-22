#!/bin/bash
# EC2 user data (Amazon Linux 2023): install Docker + git, register start.sh as a boot service, run it.
set -euxo pipefail
dnf install -y docker git
systemctl enable --now docker
curl -fsSL https://raw.githubusercontent.com/WahidSaeed/blindgrasp/main/deploy/aws/start.sh -o /usr/local/bin/blindgrasp-start
chmod +x /usr/local/bin/blindgrasp-start
cat > /etc/systemd/system/blindgrasp.service <<'UNIT'
[Unit]
Description=Blindgrasp sim server (build + run)
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/blindgrasp-start

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now blindgrasp
