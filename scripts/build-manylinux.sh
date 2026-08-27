#!/usr/bin/env bash
# =====================================================================
#  Build monitor-server + monitor-agent สำหรับ Linux บน manylinux_2_28 (glibc 2.28)
#
#  ทำไม 2.28: PyInstaller binary ฝัง glibc ของเครื่อง build — build บน glibc 2.28
#  (= RHEL 8 / AlmaLinux 8 / Rocky 8) ทำให้ binary รันได้บน distro ที่ glibc >= 2.28:
#  Alma/Rocky 8-9, RHEL 8-9, Ubuntu 20.04+, Debian 11+, Fedora 32+
#
#  ทำไมต้อง build Python เอง: Python ใน /opt/python ของ manylinux image ถูก build
#  โดยไม่มี shared library → PyInstaller ล้ม — จึง build 3.11 จาก source
#  ด้วย --enable-shared (ใช้เวลา ~10-15 นาทีต่อรอบ)
#
#  Usage:  รันภายใน container quay.io/pypa/manylinux_2_28_x86_64
#          (GitHub Actions: docker run -v $PWD:/src -w /src <image> bash scripts/build-manylinux.sh)
# =====================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# กัน UnicodeEncodeError ตอน print ไทย บน locale ที่ไม่ใช่ UTF-8
export PYTHONUTF8=1

PY_VERSION="3.11.14"
PY_SRC="/opt/python-3.11"
PY_BUILD="${PY_SRC}/bin/python3.11"

# ── 1) build Python 3.11 จาก source (มี shared library) ──
if [ ! -x "$PY_BUILD" ]; then
    echo "== 1) build Python ${PY_VERSION} ด้วย --enable-shared =="
    command -v curl > /dev/null || yum install -y curl
    yum install -y gcc make zlib-devel bzip2-devel openssl-devel ncurses-devel \
        sqlite-devel readline-devel tk-devel gdbm-devel libuuid-devel libffi-devel xz-devel

    curl -fSL "https://www.python.org/ftp/python/${PY_VERSION}/Python-${PY_VERSION}.tgz" \
        -o "/tmp/Python-${PY_VERSION}.tgz"
    tar xzf "/tmp/Python-${PY_VERSION}.tgz" -C /tmp
    (
        cd "/tmp/Python-${PY_VERSION}"
        ./configure --prefix="${PY_SRC}" --enable-shared
        make -j"$(nproc)"
        make install
    )
    rm -rf "/tmp/Python-${PY_VERSION}"*
    echo "Python ${PY_VERSION} build เสร็จ: ${PY_BUILD} ($("${PY_BUILD}" --version 2>&1))"
else
    echo "== 1) Python 3.11 อยู่แล้ว — skip build =="
fi

# safety net: ชี้ LD_LIBRARY_PATH ไป libpython (ปกติ rpath ฝังมาแล้วตอน make install)
export LD_LIBRARY_PATH="${PY_SRC}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

# ── 2) venv + install deps ──
echo "== 2) venv + install deps =="
"${PY_BUILD}" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt -r requirements-build.txt pytest pytest-asyncio

# ── 3) tests (sanity) ──
echo "== 3) tests (sanity) =="
.venv/bin/python -m pytest -q

# ── 4) build monitor-server (add-data separator ':' ใช้ Linux) ──
echo "== 4) build monitor-server =="
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile \
  --name monitor-server \
  --add-data "$PWD/server/webui:server/webui" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  run.py

# ── 5) build monitor-agent ──
echo "== 5) build monitor-agent =="
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile \
  --name monitor-agent \
  agent/agent.py

# ── 6) smoke test: รัน binary ใน container glibc 2.28 (พิสูจน์รันได้บน Alma/Rocky 8) ──
echo "== 6) smoke test =="
./dist/monitor-server --help > /dev/null
./dist/monitor-agent --help > /dev/null
echo "smoke test OK (server --help, agent --help exit 0)"

# ── 7) ตรวจ glibc symbol สูงสุด (ต้อง <= 2.28) ──
echo "== 7) glibc check =="
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
