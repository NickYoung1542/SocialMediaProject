param([string]$Account = "animals")

# Runs one daily cycle. Invoked by the scheduled task; also safe to run by hand.
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PATH = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$env:PYTHONPATH = "src"
$env:PYTHONUNBUFFERED = "1"

New-Item -ItemType Directory -Force logs | Out-Null
$log = "logs\daily_$(Get-Date -Format yyyyMMdd).log"
"=== $(Get-Date -Format s) account=$Account ===" | Out-File -Append -Encoding utf8 $log
& .\.venv\Scripts\python.exe -m reelbot daily --account $Account *>&1 | Out-File -Append -Encoding utf8 $log
"exit code $LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
exit $LASTEXITCODE
