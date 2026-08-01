$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Support = Join-Path $env:LOCALAPPDATA "SmartCoreMonitor"
$Install = Join-Path $Support "bin"
$Executable = Join-Path $Install "SmartCoreMonitor.exe"
$TaskName = "SmartCoreMonitor"

function Log([string]$Message) {
    Write-Host "[smartcore-monitor] $Message"
}

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw "The .NET 8 SDK is required to build SmartCoreMonitor."
}

Log "building Windows release executable"
dotnet publish (Join-Path $Root "SmartCoreMonitor.Windows.csproj") `
    --configuration Release `
    --runtime win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    --output (Join-Path $Root "publish\win-x64")

New-Item -ItemType Directory -Force -Path $Install | Out-Null
Copy-Item (Join-Path $Root "publish\win-x64\SmartCoreMonitor.exe") $Executable -Force
$AclUser = "$env:USERDOMAIN\$env:USERNAME"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

$Action = New-ScheduledTaskAction -Execute $Executable -Argument "run"
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $AclUser
$Principal = New-ScheduledTaskPrincipal -UserId $AclUser -LogonType InteractiveToken -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

& icacls.exe $Support /inheritance:r /grant:r "${AclUser}:(OI)(CI)F" | Out-Null
Log "installed and started $Executable"
Log "pair with: Get-Content pairing.json | & '$Executable' pair"
