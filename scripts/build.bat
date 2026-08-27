@echo off
setlocal enabledelayedexpansion
rem =====================================================================
rem  Build monitor-server.exe + monitor-agent.exe (PyInstaller onefile)
rem  + icon (monitor+pulse) + UPX compression
rem  Usage:  scripts\build.bat     (from anywhere)
rem =====================================================================
cd /d "%~dp0.."

rem กัน UnicodeEncodeError ตอน print ไทยบน console ที่ไม่ใช่ UTF-8 (CI/codepage ต่าง)
set "PYTHONUTF8=1"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] venv not found. Create it first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements-build.txt
    exit /b 1
)

rem ---- 1) make icon (monitor + pulse) ----
echo == 1) make icon ==
"%PY%" scripts\make_icon.py
if errorlevel 1 exit /b 1

rem ---- 2) ensure UPX (download via build.ps1 if missing, then let it build) ----
if not exist "scripts\tools\upx\upx.exe" (
    echo UPX not found - downloading latest + building via build.ps1 ...
    powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\build.ps1"
    exit /b %errorlevel%
)

rem ---- 3) build monitor-server.exe ----
echo == 2) build monitor-server.exe ==
"%PY%" -m PyInstaller --noconfirm --clean --onefile ^
  --name monitor-server ^
  --icon build\monitor.ico ^
  --add-data "%CD%\server\webui;server/webui" ^
  --upx-dir "%CD%\scripts\tools\upx" ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  run.py
if errorlevel 1 exit /b 1

rem ---- 4) build monitor-agent.exe ----
echo == 3) build monitor-agent.exe ==
"%PY%" -m PyInstaller --noconfirm --clean --onefile ^
  --name monitor-agent ^
  --icon build\monitor.ico ^
  --upx-dir "%CD%\scripts\tools\upx" ^
  agent\agent.py
if errorlevel 1 exit /b 1

echo == done ==
for %%F in (dist\monitor-server.exe dist\monitor-agent.exe) do if exist "%%F" (
    for %%S in ("%%F") do echo   %%~nxF - %%~zS bytes
)
exit /b 0
