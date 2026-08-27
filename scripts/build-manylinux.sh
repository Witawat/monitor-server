#!/usr/bin/env bash
# =====================================================================
#  Build monitor-server + monitor-agent สำหรับ Linux บน manylinux_2_28 (glibc 2.28)
#
#  ทำไม 2.28: PyInstaller binary ฝัง glibc ของเครื่อง build — build บน glibc 2.28
#  (= RHEL 8 / AlmaLinux 8 / Rocky 8) ทำให้ binary รันได้บน distro ที่ glibc >= 2.28:
#  Alma/Rocky 8-9, RHEL 8-9, Ubuntu 20.04+, Debian 11+, Fedora 32+ (Python 3.11 ใช้ได้)
#
#  Usage:  รันภายใน container quay.io/pypa/manylinux_2_28_x86_64
#          (GitHub Actions: docker run -v $PWD:/src -w /src <image> bash scripts/build-manylinux.sh)
# =====================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# กัน UnicodeEncodeError ตอน print ไทย บน locale ที่ไม่ใช่ UTF-8
export PYTHONUTF8=1

# Python 3.11 ที่มากับ manylinux image
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

echo "== 3) build monitor-server (add-data separator ':' ใช้ Linux) =="
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile \
  --name monitor-server \
  --add-data "$PWD/server/webui:server/webui" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  run.py

echo "== 4) build monitor-agent =="
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile \
  --name monitor-agent \
  agent/agent.py

echo "== 5) smoke test: รัน binary ใน container glibc 2.28 (พิสูจน์รันได้บน Alma/Rocky 8) =="
./dist/monitor-server --help > /dev/null
./dist/monitor-agent --help > /dev/null
echo "smoke test OK (server --help, agent --help exit 0)"

echo "== 6) ตรวจ glibc symbol สูงสุด (ต้อง <= 2.28) =="
command -v objdump > /dev/null || { echo "[ERROR] objdump not found"; exit 1; }
MAX_GLIBC=$(objdump -T dist/monitor-server | grep -oE 'GLIBC_[0-9]+(\.[0-9]+)+' | sort -uV | tail -1 || true)
if [ -n "$MAX_GLIBC" ]; then
  if [ "$(printf '2.28\n%s\n' "${MAX_GLIBC#GLIBC_}" | sort -uV | tail -1)" != "2.28" ]; then
    echo "[ERROR] binary ต้องการ ${MAX_GLIBC} ซึ่ง > glibc 2.28 — จะรันไม่ได้บน Alma/Rocky 8"
    exit 1
  fi
  echo "glibc check OK (สูงสุด: ${MAX_GLIBC})"
else
  echo "glibc check: ไม่พบ GLIBC_ symbol (static) — OK"
fi

echo "== done =="
ls -l dist/monitor-server dist/monitor-agent
