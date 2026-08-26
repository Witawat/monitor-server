# Test built EXEs end-to-end (monitor-server.exe + monitor-agent.exe)
# Checks: health, WebUI/login/static, ingest, hosts, metrics, tags, alerts CRUD, export CSV, agent exe push
param(
    [int]$Port = 18089
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$ServerExe = Join-Path $Root "dist\monitor-server.exe"
$AgentExe = Join-Path $Root "dist\monitor-agent.exe"
$BaseUrl = "http://127.0.0.1:$Port"
$Work = Join-Path $env:TEMP ("monitor-exe-test-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$DataDir = Join-Path $Work "data"
$LogDir = Join-Path $Work "logs"
New-Item -ItemType Directory -Force -Path $DataDir, $LogDir | Out-Null
# TOML: ใช้ forward slash กัน backslash กลายเป็น escape
$DataDirToml = $DataDir -replace '\\', '/'
$LogDirToml = $LogDir -replace '\\', '/'
$passCount = 0

function Pass([string]$m) { $script:passCount++; Write-Host "PASS: $m" -ForegroundColor Green }
function Fail([string]$m) { Write-Host "FAIL: $m" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $ServerExe)) { Fail "missing $ServerExe - run scripts\build.bat first" }
if (-not (Test-Path $AgentExe)) { Fail "missing $AgentExe" }

# ---- 0) temp config (isolated data_dir) ----
$hash = (& $Py -c "from server.webui.auth import hash_password; print(hash_password('testpass'))" | Select-Object -Last 1)
$cfg = @"
[server]
host = "127.0.0.1"
port = $Port
data_dir = "$DataDirToml"
log_dir = "$LogDirToml"

[webui]
admin_user = "admin"
admin_pass_hash = "$hash"
secret_key = "exe-test-secret-key-1234567890"
secure_cookie = false

[ingest]
rate_limit_per_min = 1000
max_batch_size = 200
offline_timeout_sec = 60

[storage]
retention_raw_days = 45
rollup_intervals = ["1m","5m","1h","1d"]
wal = true

[alerting]
enabled = true

[alerting.notifiers.webhook]
url = ""

[alerting.notifiers.telegram]
bot_token = ""
chat_id = ""

[auth]
allow_registration = true
"@
$cfgPath = Join-Path $Work "config.toml"
Set-Content -Path $cfgPath -Value $cfg -Encoding ascii

$srv = $null
try {
    # ---- 1) start server exe ----
    Write-Host "== start monitor-server.exe =="
    $srv = Start-Process -FilePath $ServerExe -ArgumentList "--config", $cfgPath -WorkingDirectory $Root `
        -RedirectStandardOutput (Join-Path $Work "srv.log") -RedirectStandardError (Join-Path $Work "srv_err.log") -PassThru
    $up = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        try { if ((Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 2).status -eq "ok") { $up = $true; break } } catch {}
    }
    if (-not $up) { Fail "server exe did not start (health)" }
    Pass "server exe started, /api/health ok"

    # ---- 2) WebUI: login page, static chart, login, me, SPA ----
    $rootHtml = (Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing -TimeoutSec 5).Content
    if ($rootHtml -notmatch 'loginForm' -or $rootHtml -notmatch '/static/js/login.js') { Fail "login page not shown" }
    Pass "WebUI login page + login.js (CSP-safe)"

    $chart = Invoke-WebRequest -Uri "$BaseUrl/static/js/chart.umd.min.js" -UseBasicParsing -TimeoutSec 5
    if ($chart.StatusCode -ne 200 -or $chart.Content.Length -lt 100000) { Fail "chart.umd.min.js not served" }
    Pass "static chart.umd.min.js served from exe"

    $sess = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $lr = Invoke-WebRequest -Uri "$BaseUrl/api/v1/auth/login" -Method Post -Body '{"username":"admin","password":"testpass"}' `
        -ContentType "application/json" -WebSession $sess -UseBasicParsing -TimeoutSec 5
    if ($lr.StatusCode -ne 200) { Fail "login failed" }
    Pass "login ok (admin/testpass) + cookie"

    $me = (Invoke-WebRequest -Uri "$BaseUrl/api/v1/auth/me" -WebSession $sess -UseBasicParsing -TimeoutSec 5).Content
    if ($me -notmatch 'admin') { Fail "/api/v1/auth/me did not return admin" }
    Pass "/api/v1/auth/me"

    $spa = (Invoke-WebRequest -Uri "$BaseUrl/" -WebSession $sess -UseBasicParsing -TimeoutSec 5).Content
    if ($spa -notmatch 'view-fleet') { Fail "SPA base.html has no fleet view" }
    Pass "WebUI SPA base shown after login"

    # ---- 3) ingest + API ----
    $now = [int][double]::Parse((Get-Date -UFormat %s))
    $snaps = @()
    for ($i = 0; $i -lt 5; $i++) {
        $snaps += @{ host_id = "exe-web-01"; hostname = "exe-web-01"; platform = "linux"; ts = ($now - 300 + $i * 60); cpu_percent = (30 + $i); memory = @{ total = 1000; used = 400; percent = 40.0 }; services = @(@{ name = "nginx"; up = $true }) }
    }
    $body = $snaps | ConvertTo-Json -Depth 8
    $ig = Invoke-RestMethod -Uri "$BaseUrl/api/v1/ingest" -Method Post -Body $body -ContentType "application/json" -Headers @{ "X-Agent-Token" = "exetok" } -WebSession $sess -TimeoutSec 5
    if ($ig.received -lt 1) { Fail "ingest did not accept snapshots" }
    Pass "POST /api/v1/ingest stored metrics"

    $hosts = Invoke-RestMethod -Uri "$BaseUrl/api/v1/hosts" -WebSession $sess -TimeoutSec 5
    if (-not ($hosts | Where-Object { $_.host_id -eq "exe-web-01" })) { Fail "host not in /api/v1/hosts" }
    Pass "GET /api/v1/hosts lists host"

    $tg = Invoke-WebRequest -Uri "$BaseUrl/api/v1/hosts/exe-web-01/tags" -Method Put -Body '{"tags":["env=prod","exe"]}' `
        -ContentType "application/json" -WebSession $sess -UseBasicParsing -TimeoutSec 5
    if ($tg.StatusCode -ne 200) { Fail "set tags failed" }
    if ((Invoke-RestMethod -Uri "$BaseUrl/api/v1/hosts/tags" -WebSession $sess -TimeoutSec 5) -notcontains "env=prod") { Fail "tags not listed" }
    Pass "PUT tags + GET /hosts/tags"

    $metrics = Invoke-RestMethod -Uri "$BaseUrl/api/v1/hosts/exe-web-01/metrics?range=6h" -WebSession $sess -TimeoutSec 5
    if (-not $metrics.series.cpu_percent.points) { Fail "metrics range=6h empty" }
    Pass "GET metrics range=6h returns series"

    # ---- 4) alerts CRUD ----
    $rule = Invoke-WebRequest -Uri "$BaseUrl/api/v1/alerts" -Method Post -Body '{"name":"CPU exe","host_id":"","metric":"cpu_percent","op":">","threshold":90.0,"duration":"5m"}' `
        -ContentType "application/json" -WebSession $sess -UseBasicParsing -TimeoutSec 5
    if ($rule.StatusCode -ne 201) { Fail "create alert rule failed" }
    $rid = ($rule.Content | ConvertFrom-Json).id
    $rup = Invoke-WebRequest -Uri "$BaseUrl/api/v1/alerts/$rid" -Method Put -Body '{"name":"CPU exe 2","host_id":"","metric":"cpu_percent","op":">","threshold":95.0}' `
        -ContentType "application/json" -WebSession $sess -UseBasicParsing -TimeoutSec 5
    if ($rup.StatusCode -ne 200) { Fail "update alert rule failed" }
    if ((Invoke-WebRequest -Uri "$BaseUrl/api/v1/alerts/$rid" -Method Delete -WebSession $sess -UseBasicParsing -TimeoutSec 5).StatusCode -ne 200) { Fail "delete alert rule failed" }
    Pass "alerts CRUD (create/update/delete)"

    # ---- 5) export CSV ----
    $csv = Invoke-WebRequest -Uri "$BaseUrl/api/v1/hosts/exe-web-01/export?range=1h" -WebSession $sess -UseBasicParsing -TimeoutSec 5
    if ($csv.Headers["Content-Type"] -notmatch "text/csv" -or $csv.Content -notmatch "cpu_percent") { Fail "export CSV invalid" }
    Pass "export CSV"

    # ---- 6) agent exe push ----
    Write-Host "== start monitor-agent.exe (interval 1s) =="
    $before = (Invoke-RestMethod -Uri "$BaseUrl/api/status" -WebSession $sess -TimeoutSec 5).host_count
    $ag = Start-Process -FilePath $AgentExe -ArgumentList "--server", $BaseUrl, "--token", "ag-tok-1", "--interval", "1", "--watch", "explorer" `
        -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $Work "ag.log") -RedirectStandardError (Join-Path $Work "ag_err.log") -PassThru
    Start-Sleep -Seconds 4
    Stop-Process -Id $ag.Id -Force -ErrorAction SilentlyContinue
    $after = (Invoke-RestMethod -Uri "$BaseUrl/api/status" -WebSession $sess -TimeoutSec 5).host_count
    if ($after -le $before) { Fail "agent exe did not push new host ($before -> $after)" }
    Pass "monitor-agent.exe push -> host up ($before -> $after)"

    Write-Host ""
    Write-Host "== RESULT: $passCount checks passed ==" -ForegroundColor Green
    Write-Host "PASSED"
}
finally {
    if ($srv -and -not $srv.HasExited) { Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 300
    Remove-Item $Work -Recurse -Force -ErrorAction SilentlyContinue
}
