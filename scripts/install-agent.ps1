# ติดตั้ง agent เป็น Windows service ผ่าน NSSM
# ใช้ dist\monitor-agent.exe ถ้ามี (เก็บ state ข้าง exe) ไม่งั้นใช้ python -m agent.agent
param(
    [Parameter(Mandatory)][string]$ServerUrl,
    [Parameter(Mandatory)][string]$Token,
    [int]$Interval = 15,
    [string]$ExePath = ""
)

$ServiceName = "MonitorAgent"
$Root = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Write-Error "ไมพบ nssm ใน PATH - ลงจาก https://nssm.cc กอน"
    exit 1
}

if ([string]::IsNullOrEmpty($ExePath)) {
    $ExePath = Join-Path $Root "dist\monitor-agent.exe"
}

if (Test-Path $ExePath) {
    # ใช้ exe ตรงๆ - state (host_id/queue) เก็บขาง exe
    $exeResolved = (Resolve-Path $ExePath).Path
    $target = $exeResolved
    $args = "--server $ServerUrl --token $Token --interval $Interval"
    $AppDir = Split-Path $exeResolved
    Write-Output "ใช้ agent exe: $exeResolved"
} else {
    $py = (Get-Command python).Source
    $target = $py
    $args = "-m agent.agent --server $ServerUrl --token $Token --interval $Interval"
    $AppDir = Get-Location
    Write-Output "ไม่พบ agent exe ใช้ python -m agent.agent"
}

nssm install $ServiceName $target $args
nssm set $ServiceName AppDirectory $AppDir
nssm start $ServiceName
Write-Output "ติดตั้ง service '$ServiceName' แล้ว"
