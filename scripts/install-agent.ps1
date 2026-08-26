# ติดตั้ง agent เป็น Windows service ผ่าน NSSM
param(
    [Parameter(Mandatory)][string]$ServerUrl,
    [Parameter(Mandatory)][string]$Token,
    [int]$Interval = 15
)

$ServiceName = "MonitorAgent"

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Write-Error "ไม่พบ nssm ใน PATH — ลงจาก https://nssm.cc ก่อน"
    exit 1
}

$py = (Get-Command python).Source
$cmd = "-m agent.agent --server $ServerUrl --token $Token --interval $Interval"

nssm install $ServiceName $py $cmd
nssm set $ServiceName AppDirectory (Get-Location)
nssm start $ServiceName
Write-Output "ติดตั้ง service '$ServiceName' แล้ว"
