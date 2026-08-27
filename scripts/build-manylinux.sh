#!/usr/bin/env bash
# =====================================================================
#  Build monitor-server + monitor-agent สำหรับ Linux บน manylinux_2_28 (glibc 2.28)
#
#  ทำไม 2.28: PyInstaller binary ฝัง glibc ของเครื่อง build — build บน glibc 2.28
#  (= RHEL 8 / AlmaLinux 8 / Rocky 8) ทำให้ binary รันได้บน distro ที่ glibc >= 2.28:
#  Alma/Rocky 8-9, RHEL 8-9, Ubuntu 20.04+, Debian 11+, Fedora 32+ (Python 3.11 ใช้ได้)
#
#  หมายเหตุ: Python ใน /opt/python ของ manylinux_image ถูก build โดยไมมมี shared library
#  (จำเป็นตอง build Python เองพรอม --enable-shared เพื่อใหPyInstaller ใชงานได)
#
#  Usage:  รันภายใน container quay.io/pypa/manylinux_2_28_x86_64
#          (GitHub Actions: docker run -v $PWD:/src -w /src <image> bash scripts/build-manylinux.sh)
# =====================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# กัน UnicodeEncodeError ตอน print ไทย บน locale ที่ไมใช UTF-8
export PYTHONUTF8=1

# ── 1) build Python 3.11 from source with shared library ──
PY_SRC="/opt/python-3.11"
PY_BUILD="${PY_SRC}/bin/python3.11"

if [ ! -x "$PY_BUILD" ]; then
    echo "== 1) build Python 3.11 with --enable-shared =="
    PKG="gcc make zlib-devel bzip2-devel openssl-devel ncurses-devel sqlite-devel readline-devel tk-devel gdbm-devel libuuid-devel libffi-devel xz-devel"
    yum install -y $PKG

    curl -fSL "https://www.python.org/ftp/python/3.11.11/Python-3.11.11.tgz" -o /tmp/Python-3.11.11.tgz
    tar xzf /tmp/Python-3.11.11.tgz -C /tmp
    mkdir -p "${PY_SRC}"
    cd /tmp/Python-3.11.11
    ./configure --prefix="${PY_SRC}" --enable-shared --enable-optimizations --with-lto --enable-framework
    make -j$(nproc || grep -c processor /proc/cpuinfo || echo 2)
    make install
    cd - > /dev/null
    rm -rf /tmp/Python-3.11.11*
    echo "Python 3.11 built: ${PY_BUILD} ($(PY_BUILD --version 2>&1))"
else
    echo "== 1) Python 3.11 already built — skip =="
fi

PY="${PY_BUILD}"

# ── 2) venv + install deps ──
echo "== 2) venv + install deps =="
"$PY" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt -r requirements-build.txt pytest pytest-asyncio

# ── 3) tests (sanity) ──
echo "== 3) tests (sanity) =="
.venv/bin/python -m pytest -q

# ── 4) make icon (required for some PyInstaller hooks) ──
echo "== 4) make icon =="
.venv/bin/python scripts/make_icon.py

# ── 5) build monitor-server ──
echo "== 5) build monitor-server (add-data separator ':' ใช Linux) =="
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile \
  --name monitor-server \
  --add-data "$PWD/server/webui:server/webui" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  run.py

# ── 6) build monitor-agent ──
echo "== 6) build monitor-agent =="
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile \
  --name monitor-agent \
  agent/agent.py

# ── 7) smoke test: รัน binary ใน container glibc 2.28 ──
echo "== 7) smoke test =="
./dist/monitor-server --help > /dev/null
./dist/monitor-agent --help > /dev/null
echo "smoke test OK (server --help, agent --help exit 0)"

# ── 8) ตรวจ glibc symbol สูงสุด (ตอง <= 2.28) ──
echo "== 8) glibc check =="
command -v objdump > /dev/null || { echo "[ERROR] objdump not found"; exit 1; }
MAX_GLIBC=$(objdump -T dist/monitor-server | grep -oE 'GLIBC_[0-9]+(\.[0-9]+)+' | sort -uV | tail -1 || true)
if [ -n "$MAX_GLIBC" ]; then
  if [ "$(printf '2.28\n%s\n' "${MAX_GLIBC#GLIBC_}" | sort -uV | tail -1)" != "2.28" ]; then
    echo "[ERROR] binary ตองการ ${MAX_GLIBC} ซึ่ง > glibc 2.28 — จะรันไมไดบน Alma/Rocky 8"
    exit 1
  fi
  echo "glibc check OK (สุงสุด: ${MAX_GLIBC})"
else
  echo "glibc check: ไมพบ GLIBC_ symbol (static) — OK"
fi

echo "== done =="
ls -l dist/monitor-server dist/monitor-agent
