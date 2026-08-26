# ติดตั้ง monitor-server เป็น Windows service ผ่าน NSSM (delegate ไป run.py)
param(
    [string]$ConfigPath = "config.toml",
    [ValidateSet("install", "start", "stop", "remove")]
    [string]$Action = "install"
)

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Write-Error "ไม่พบ nssm ใน PATH — ลงจาก https://nssm.cc ก่อน"
    exit 1
}

python run.py --config $ConfigPath --service $Action
