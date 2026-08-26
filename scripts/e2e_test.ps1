# Integration test: agent (จริง) → server (จริง) — อยู่นอก pytest -q
param(
    [string]$ConfigPath = "config.toml"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Token = "e2e-token-" + [guid]::NewGuid().ToString("N").Substring(0, 8)

Write-Host "== e2e: start server =="
$srv = Start-Process -FilePath $Python -ArgumentList "-m","server.main","--config",$ConfigPath `
    -WorkingDirectory $Root -RedirectStandardOutput "$Root\e2e_srv.log" -RedirectStandardError "$Root\e2e_srv_err.log" -PassThru
Start-Sleep -Seconds 4

try {
    Write-Host "== e2e: run agent (interval 1s, ~3s) =="
    $ag = Start-Process -FilePath $Python -ArgumentList "-m","agent.agent","--server","http://127.0.0.1:18080","--token",$Token,"--interval","1" `
        -WorkingDirectory $Root -RedirectStandardOutput "$Root\e2e_ag.log" -RedirectStandardError "$Root\e2e_ag_err.log" -PassThru
    Start-Sleep -Seconds 3
    Stop-Process -Id $ag.Id -Force -ErrorAction SilentlyContinue

    Write-Host "== e2e: check host registered =="
    # /api/status ต้อง auth → login ก่อน (dev: admin/admin123)
    $sess = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "http://127.0.0.1:18080/api/v1/auth/login" -Method Post `
        -Body '{"username":"admin","password":"admin123"}' -ContentType "application/json" -WebSession $sess | Out-Null
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:18080/api/status" -WebSession $sess -TimeoutSec 5
    if ($resp.host_count -ge 1) {
        Write-Host "PASS: agent → server, host ขึ้นแล้ว (host_count=$($resp.host_count))"
    } else {
        Write-Host "FAIL: ไม่พบ host"
        exit 1
    }
}
finally {
    Get-Process python | Where-Object { $_.Id -eq $srv.Id } | Stop-Process -Force -ErrorAction SilentlyContinue
    Remove-Item "$Root\e2e_srv.log","$Root\e2e_srv_err.log","$Root\e2e_ag.log","$Root\e2e_ag_err.log" -Force -ErrorAction SilentlyContinue
}
Write-Host "== e2e done =="
