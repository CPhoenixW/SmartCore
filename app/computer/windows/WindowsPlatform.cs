using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Text;
using Microsoft.Win32;

namespace SmartCoreMonitor.Windows;

public sealed class WindowsPlatform : IDisposable
{
    private bool structuredContext;
    private readonly CodexConversationTitleReader codexTitleReader = new();
    private bool locked;
    private bool sleeping;

    public event Action? StateChanged;

    public WindowsPlatform(bool structuredContext)
    {
        this.structuredContext = structuredContext;
        if (!OperatingSystem.IsWindows()) return;
        SystemEvents.SessionSwitch += OnSessionSwitch;
        SystemEvents.PowerModeChanged += OnPowerModeChanged;
    }

    public bool Paused => false;
    public bool Sleeping => sleeping;

    public void SetStructuredContext(bool enabled) => structuredContext = enabled;

    public double IdleSeconds()
    {
        if (!OperatingSystem.IsWindows()) return 0;
        var info = new LastInputInfo { cbSize = (uint)Marshal.SizeOf<LastInputInfo>() };
        if (!GetLastInputInfo(ref info)) return 0;
        var now = unchecked((uint)GetTickCount());
        var elapsedMilliseconds = unchecked(now - info.dwTime);
        return elapsedMilliseconds / 1000.0;
    }

    public bool IsLocked()
    {
        if (locked) return true;
        if (!OperatingSystem.IsWindows()) return false;
        var desktop = OpenInputDesktop(0, false, DesktopSwitchDesktop);
        if (desktop == IntPtr.Zero) return true;
        CloseDesktop(desktop);
        return false;
    }

    public ActivityContext CurrentContext()
    {
        if (!OperatingSystem.IsWindows())
            return new ActivityContext { BundleId = "windows.unknown", AppName = "Unknown" };
        var window = GetForegroundWindow();
        if (window == IntPtr.Zero)
            return new ActivityContext { BundleId = "windows.unknown", AppName = "Unknown" };
        var title = ReadWindowTitle(window);
        GetWindowThreadProcessId(window, out var processId);
        var processName = "Unknown";
        var processPath = "";
        try
        {
            using var process = Process.GetProcessById((int)processId);
            processName = process.ProcessName;
            try { processPath = process.MainModule?.FileName ?? ""; } catch (Exception) { }
        }
        catch (Exception) { }

        var appName = processName;
        if (!string.IsNullOrWhiteSpace(processPath))
        {
            try
            {
                var product = FileVersionInfo.GetVersionInfo(processPath).ProductName;
                if (!string.IsNullOrWhiteSpace(product)) appName = product.Trim();
            }
            catch (Exception) { }
        }
        var bundleId = Path.GetFileName(processPath);
        if (string.IsNullOrWhiteSpace(bundleId)) bundleId = processName + ".exe";
        if (bundleId.Contains("codex", StringComparison.OrdinalIgnoreCase)
            || appName.Contains("codex", StringComparison.OrdinalIgnoreCase))
        {
            title = codexTitleReader.CurrentTitle(appName) ?? title;
        }
        return ActivityContextSanitizer.Sanitize(
            new RawActivityContext
            {
                BundleId = bundleId,
                AppName = appName,
                WindowTitle = title,
            },
            structuredContext);
    }

    public void Dispose()
    {
        if (!OperatingSystem.IsWindows()) return;
        SystemEvents.SessionSwitch -= OnSessionSwitch;
        SystemEvents.PowerModeChanged -= OnPowerModeChanged;
    }

    [SupportedOSPlatform("windows")]
    private void OnSessionSwitch(object? sender, SessionSwitchEventArgs args)
    {
        switch (args.Reason)
        {
            case SessionSwitchReason.SessionLock:
                locked = true;
                StateChanged?.Invoke();
                break;
            case SessionSwitchReason.SessionUnlock:
                locked = false;
                StateChanged?.Invoke();
                break;
        }
    }

    [SupportedOSPlatform("windows")]
    private void OnPowerModeChanged(object? sender, PowerModeChangedEventArgs args)
    {
        switch (args.Mode)
        {
            case PowerModes.Suspend:
                sleeping = true;
                StateChanged?.Invoke();
                break;
            case PowerModes.Resume:
                sleeping = false;
                StateChanged?.Invoke();
                break;
        }
    }

    private static string ReadWindowTitle(IntPtr window)
    {
        var length = GetWindowTextLength(window);
        if (length <= 0) return "";
        var builder = new StringBuilder(length + 1);
        _ = GetWindowText(window, builder, builder.Capacity);
        return builder.ToString();
    }

    private const uint DesktopSwitchDesktop = 0x0100;

    [StructLayout(LayoutKind.Sequential)]
    private struct LastInputInfo
    {
        public uint cbSize;
        public uint dwTime;
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", SetLastError = true)]
    private static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool GetLastInputInfo(ref LastInputInfo plii);

    [DllImport("kernel32.dll")]
    private static extern uint GetTickCount();

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint desiredAccess);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool CloseDesktop(IntPtr desktop);
}
