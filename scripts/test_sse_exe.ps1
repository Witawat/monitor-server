# Test SSE realtime from built exe (monitor-server.exe)
param(
    [int]$Port = 18091
)
$ErrorActionPreference = "Stop"
$Root = "D:\MyCode\monitor-server"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$ServerExe = Join-Path $Root "dist\monitor-server.exe"
$BaseUrl = "http://127.0.0.1:$Port"
$Work = Join-Path $env:TEMP ("monitor-sse-test-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$DataDir = Join-Path $Work "data"
$LogDir = Join-Path $Work "logs"
New-Item -ItemType Directory -Force -Path $DataDir, $LogDir | Out-Null
$DataDirToml = $DataDir -replace '\\', '/'
$LogDirToml = $LogDir -replace '\\', '/'

function Pass([string]$m) { Write-Host "PASS: $m" -ForegroundColor Green }
function Fail([string]$m) { Write-Host "FAIL: $m" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $ServerExe)) { Fail "missing $ServerExe" }

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
secret_key = "sse-test-secret-key-1234567890"
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
    Write-Host "== start monitor-server.exe (SSE test, port $Port) =="
    $srv = Start-Process -FilePath $ServerExe -ArgumentList "--config", $cfgPath -WorkingDirectory $Root `
        -RedirectStandardOutput (Join-Path $Work "srv.log") -RedirectStandardError (Join-Path $Work "srv_err.log") -PassThru
    $up = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        try { if ((Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 2).status -eq "ok") { $up = $true; break } } catch {}
    }
    if (-not $up) { Fail "server exe did not start (health)" }
    Pass "server exe started, /api/health ok"

    $sess = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $lr = Invoke-WebRequest -Uri "$BaseUrl/api/v1/auth/login" -Method Post -Body '{"username":"admin","password":"testpass"}' `
        -ContentType "application/json" -WebSession $sess -UseBasicParsing -TimeoutSec 5
    if ($lr.StatusCode -ne 200) { Fail "login failed" }
    Pass "login ok"

    # ---- SSE auth guard: no session -> 401 ----
    $anon = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    try {
        Invoke-WebRequest -Uri "$BaseUrl/api/v1/stream" -WebSession $anon -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop | Out-Null
        Fail "stream without session should be 401"
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode.value__ -eq 401) { Pass "SSE unauthenticated -> 401" }
        else { Fail "expected 401 for unauthenticated stream, got $($_.Exception.Response.StatusCode)" }
    }

    # ---- open SSE connection, then ingest -> expect hosts/alerts events ----
    # PowerShell 5.1 lacks native SSE; use a background job with HttpWebRequest streaming read.
    $cookieStr = $sess.Cookies.GetCookies([uri]$BaseUrl).GetEnumerator() | ForEach-Object { "$($_.Name)=$($_.Value)" }
    Write-Host "DEBUG cookie: [$cookieStr]"
    $sseJob = Start-Job -ScriptBlock {
        param($url, $cookie)
        $req = [System.Net.HttpWebRequest]::Create($url)
        if ($cookie) { $req.Headers.Add("Cookie", $cookie) }
        $req.Timeout = 20000
        $resp = $req.GetResponse()
        $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $lines = New-Object System.Collections.ArrayList
        $deadline = [DateTime]::Now.AddSeconds(15)
        while ([DateTime]::Now -lt $deadline -and $lines.Count -lt 10) {
            $line = $sr.ReadLine()
            if ($line) { [void]$lines.Add($line) }
            if ($line -eq 'data: hosts' -or $line -eq 'data: alerts') { break }
        }
        $sr.Close(); $resp.Close()
        return ($lines -join "`n")
    } -ArgumentList "$BaseUrl/api/v1/stream", $cookieStr

    Start-Sleep -Seconds 2

    $now = [int][double]::Parse((Get-Date -UFormat %s))
    $snaps = @()
    $snaps += @{ host_id = "sse-host-01"; hostname = "sse-host-01"; platform = "linux"; ts = $now; cpu_percent = 55.0; memory = @{ total = 1000; used = 500; percent = 50.0 } }
    $snaps += @{ host_id = "sse-host-01"; hostname = "sse-host-01"; platform = "linux"; ts = ($now + 1); cpu_percent = 56.0; memory = @{ total = 1000; used = 510; percent = 51.0 } }
    $body = $snaps | ConvertTo-Json -Depth 8
    $ig = Invoke-RestMethod -Uri "$BaseUrl/api/v1/ingest" -Method Post -Body $body -ContentType "application/json" -Headers @{ "X-Agent-Token" = "ssetok" } -WebSession $sess -TimeoutSec 5
    if ($ig.received -lt 1) { Fail "ingest did not accept snapshots" }
    Pass "POST /api/v1/ingest (trigger SSE)"

    $result = (Wait-Job $sseJob -Timeout 20 | Receive-Job) 
    Remove-Job $sseJob -Force -ErrorAction SilentlyContinue

    if ($result -match 'event: hosts' -and $result -match 'data: hosts') {
        Pass "SSE received 'hosts' event after ingest"
    } else {
        Fail "SSE did not receive 'hosts' event. Got: [$result]"
    }

    Write-Host "== RESULT: SSE test passed =="
}
finally {
    if ($srv -and -not $srv.HasExited) { Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
