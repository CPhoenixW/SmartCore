# SmartCoreMonitor for Windows

This is the Windows implementation of the same outbound-only Computer monitor used by the
macOS client. It records objective foreground application activity in one-minute buckets,
keeps a durable local outbox, sends a heartbeat every 30 seconds, and uploads at most 120
accepted buckets per request. Server-side ownership, work-block boundaries, Plan matching,
project investment and Daily summary behavior are unchanged.

The client never records keyboard text, clipboard contents, screenshots, browser URL paths,
document contents or full file paths. Active slices carry only a bounded application identity
and a sanitized window title. Password managers, Windows credential surfaces, banking/payment
titles and authentication domains always lose window and structured context. Structured context
is off by default; when enabled, browser/IDE labels remain bounded names only.

## Build and install

Run PowerShell 7 or Windows PowerShell with the .NET 8 SDK:

```powershell
./scripts/install.ps1
```

The installer publishes a self-contained `win-x64` executable under the user's local application
data directory and registers a per-user Task Scheduler logon task. It does not require
administrator rights. `uninstall.ps1` stops only the task and preserves the local configuration,
device token and offline queue.

Pairing is the same flow as macOS: create a Computer pair in `/work`, save the displayed JSON,
then run:

```powershell
Get-Content .\pairing.json | & "$env:LOCALAPPDATA\SmartCoreMonitor\bin\SmartCoreMonitor.exe" pair
```

Confirm the pair in SmartCore, then the client activates and stores the token. Useful commands:

```powershell
SmartCoreMonitor.exe status
SmartCoreMonitor.exe structured-context on|off|status
SmartCoreMonitor.exe accessibility status
```

Windows does not need macOS Accessibility permission; the `accessibility` command reports
`not-required` for parity with the macOS diagnostics. Set `SMARTCORE_TIMEZONE` when the Windows
timezone is not covered by the built-in Windows-to-IANA map. The Server requires an IANA timezone.

`codex-report` accepts the same JSON batch as macOS and uploads it with the paired Computer token.
The executable includes `self-test` for deterministic activity, aggregation and sanitization checks.
