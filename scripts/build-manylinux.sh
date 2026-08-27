#!/usr/bin/env bash
# =====================================================================
#  Build monitor-server + monitor-agent สำหรับ Linux ให้ครอบคลุมทุก distro
#  ภายใน manylinux2014 (glibc 2.17, CentOS 7 base) + Python 3.11
#
#  ทำไม: PyInstaller binary ฝัง glibc ของเครื่อง build — การ build บน glibc เก่า
#  (2.17) ทำให้ binary รันได้บน distro ที่ glibc >= 2.17 (CentOS 7, RHEL/Alma/Rocky
#  8-9, Ubuntu 20.04+, Debian 11+, Fedora, Arch, ...) = ครอบคลุมที่สุด
#  (Python 3.11 ยังรองรับ glibc 2.17; Python 3.12+ ต้อง glibc 2.28 — ใช้ 3.11)
#
#  Usage:  รันภายใน container quay.io/pypa/manylinux2014_x86_64
#          (เรียกจาก GitHub Actions: bash scripts/build-manylinux.sh)
# =====================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# กัน UnicodeEncodeError ตอน print ไทย (make_icon.py) บน locale ที่ไม่ใช่ UTF-8
export PYTHONUTF8=1

# Python 3.11 ที่มากับ manylinux2014 image
PY="/opt/python/cp311-cp311/bin/python"
if [ ! -x "$PY" ]; then
    echo "[ERROR] cp311 python not found in manylinux image: $PY"
    exit 1
fi

echo "== 1) venv + install deps =="
"$PY" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt -r requirements-build.txt pytest pytest-asyncio

echo "== 2) tests (sanity) =="
.venv/bin/python -m pytest -q

echo "== 3) make icon =="
.venv/bin/python scripts/make_icon.py

echo "== 4) build monitor-server (add-data separator ':' ใช้ Linux) =="
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile \
  --name monitor-server \
  --add-data "$PWD/server/webui:server/webui" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  run.py

echo "== 5) build monitor-agent =="
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile \
  --name monitor-agent \
  agent/agent.py

echo "== done =="
ls -l dist/monitor-server dist/monitor-agent
