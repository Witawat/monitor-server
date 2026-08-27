#!/usr/bin/env bash
# =====================================================================
#  Build monitor-server + monitor-agent (PyInstaller onefile) บน Linux + icon
#
#  ⚠️  DEV เท่านั้น: glibc ของผลลัพธ์ = glibc ของเครื่องที่ build
#  (build บน Ubuntu 24.04 = ต้อง glibc 2.39+ — ไม่ได้รองรับ distro เก่า)
#  Binary สำหรับกระจาย/release ใช้ `scripts/build-manylinux.sh` (CI)
#  ซึ่ง build บน manylinux_2_28 → glibc 2.28+
#
#  Usage:  scripts/build.sh     (จากที่ไหนก็ได้)
# =====================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "[ERROR] venv not found. Create it first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/pip install -r requirements.txt -r requirements-build.txt"
    exit 1
fi

# ---- 1) make icon (monitor + pulse) ----
echo "== 1) make icon =="
"$PY" scripts/make_icon.py

# ---- 2) build monitor-server (add-data separator ':' ใช้ Linux) ----
echo "== 2) build monitor-server =="
"$PY" -m PyInstaller --noconfirm --clean --onefile \
  --name monitor-server \
  --add-data "$PWD/server/webui:server/webui" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  run.py

# ---- 3) build monitor-agent ----
echo "== 3) build monitor-agent =="
"$PY" -m PyInstaller --noconfirm --clean --onefile \
  --name monitor-agent \
  agent/agent.py

echo "== done =="
ls -l dist/monitor-server dist/monitor-agent 2>/dev/null || true
