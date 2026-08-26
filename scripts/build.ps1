# build exe: server + agent (PyInstaller onefile) + icon + UPX
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$UpxDir = Join-Path $Root "scripts\tools\upx"
$UpxExe = Join-Path $UpxDir "upx.exe"
$Icon = Join-Path $Root "build\monitor.ico"

# ดาวน์โหลด UPX ล่าสุดถ้ายังไม่มี (build tool — ไม่อยู่ใน repo)
if (-not (Test-Path $UpxExe)) {
    Write-Host "== 0) download UPX =="
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/upx/upx/releases/latest" -Headers @{ "User-Agent" = "opencode" }
    $asset = $rel.assets | Where-Object { $_.name -like "*win64*.zip" } | Select-Object -First 1
    New-Item -ItemType Directory -Force -Path $UpxDir | Out-Null
    $zip = Join-Path $env:TEMP "upx.zip"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath (Join-Path $env:TEMP "upx") -Force
    Get-ChildItem -Recurse (Join-Path $env:TEMP "upx") -Filter upx.exe | ForEach-Object { Copy-Item $_.FullName $UpxExe -Force }
    Write-Host "   UPX: $(& $UpxExe --version | Select-Object -First 1)"
}

Write-Host "== 1) make icon =="
& $Py (Join-Path $Root "scripts\make_icon.py")

Write-Host "== 2) build monitor-server.exe =="
& $Py -m PyInstaller --noconfirm --clean --onefile `
  --name monitor-server `
  --icon $Icon `
  --add-data "$Root\server\webui;server/webui" `
  --upx-dir $UpxDir `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import uvicorn.lifespan.on `
  (Join-Path $Root "run.py")

Write-Host "== 3) build monitor-agent.exe =="
& $Py -m PyInstaller --noconfirm --clean --onefile `
  --name monitor-agent `
  --icon $Icon `
  --upx-dir $UpxDir `
  (Join-Path $Root "agent\agent.py")

Write-Host "== 4) results =="
Get-ChildItem (Join-Path $Root "dist") -Filter *.exe | ForEach-Object {
    $mb = [math]::Round($_.Length / 1MB, 2)
    Write-Host ("  {0}  ->  {1} MB" -f $_.Name, $mb)
}
Write-Host "done - exe in dist/"
