$ErrorActionPreference = "Stop"
$TaskName = "SmartCoreMonitor"
$Support = Join-Path $env:LOCALAPPDATA "SmartCoreMonitor"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Write-Host "[smartcore-monitor] stopped $TaskName; configuration, token, and outbox remain in $Support"
