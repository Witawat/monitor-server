#!/usr/bin/env bash
# ติดตั้ง monitor-server เป็น systemd service (Linux)
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="monitor-server"
UNIT="scripts/systemd/${SERVICE}.service"

echo "ติดตั้ง unit: ${UNIT}"
sudo cp "${APP_DIR}/${UNIT}" "/etc/systemd/system/${SERVICE}.service"
sudo sed -i "s|/opt/monitor-server|${APP_DIR}|" "/etc/systemd/system/${SERVICE}.service"
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE}"
echo "เสร็จ — ตรวจ: systemctl status ${SERVICE}"
