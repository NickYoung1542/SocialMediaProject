param(
    [string]$Account = "animals",
    [string]$Time = "09:00"
)

# Registers a daily Windows scheduled task. Re-run to change the time; use -Remove via Unregister-ScheduledTask.
$script = Join-Path $PSScriptRoot "run_daily.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Account $Account"
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
# StartWhenAvailable runs a missed job as soon as the PC is back on.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName "reelbot-$Account" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Generate and post the daily $Account video" -Force | Out-Null
Write-Host "Registered task 'reelbot-$Account' daily at $Time. Logs: logs\"
