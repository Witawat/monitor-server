#!/usr/bin/env bash
# ติดตั้ง agent เป็น systemd service (Linux) — รับ server url + token
set -euo pipefail

SERVER_URL="${1:?ใช้: install-agent.sh <server_url> <token> [interval]}"
TOKEN="${2:?ใช้: install-agent.sh <server_url> <token> [interval]}"
INTERVAL="${3:-15}"

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="monitor-agent"

sudo cp "${APP_DIR}/agent/service/${SERVICE}.service" "/etc/systemd/system/${SERVICE}.service"
sudo sed -i \
  -e "s|/usr/bin/python3 -m agent.agent|/usr/bin/python3 -m agent.agent --server ${SERVER_URL} --token ${TOKEN} --interval ${INTERVAL}|" \
  -e "s|WorkingDirectory=|WorkingDirectory=${APP_DIR}|" \
  "/etc/systemd/system/${SERVICE}.service"
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE}"
echo "เสร็จ — ตรวจ: systemctl status ${SERVICE}"
