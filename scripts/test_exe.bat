@echo off
rem =====================================================================
rem  Test built EXEs end-to-end (monitor-server.exe + monitor-agent.exe)
rem  Usage:  scripts\test_exe.bat [port]
rem =====================================================================
setlocal
set "PORT=%~1"
if "%PORT%"=="" set "PORT=18089"

echo Testing built EXEs on port %PORT% ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_exe.ps1" -Port %PORT%
exit /b %errorlevel%
