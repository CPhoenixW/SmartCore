using System.Text.RegularExpressions;

namespace SmartCoreMonitor.Windows;

public sealed class RawActivityContext
{
    public string BundleId { get; init; } = "unknown";
    public string AppName { get; init; } = "Unknown";
    public string? WindowTitle { get; init; }
    public string? DocumentReference { get; init; }
}

public static class ActivityContextSanitizer
{
    private static readonly string[] SensitiveAppFragments =
    [
        "1password", "bitwarden", "dashlane", "lastpass", "keeper", "keepass", "passwords",
        "credentialui", "securityagent", "logonui", "lockapp", "keychain",
    ];

    private static readonly string[] SensitiveTitleFragments =
    [
        "password", "passcode", "one-time code", "two-factor", "sign in", "banking", "payment",
        "密码", "验证码", "登录", "认证", "银行", "支付",
    ];

    private static readonly string[] SensitiveDomainFragments =
    ["bank", "paypal.", "alipay.", "stripe.", "1password.", "bitwarden.", "account.microsoft."];

    private static readonly string[] BrowserFragments = ["chrome", "firefox", "msedge", "edge", "brave", "opera", "arc"];
    private static readonly string[] IdeFragments = ["devenv", "code", "rider", "idea", "clion", "pycharm", "cursor", "zed", "sublime"];

    public static ActivityContext Sanitize(RawActivityContext raw, bool includeStructuredContext)
    {
        var bundleId = Bounded(Normalized(raw.BundleId) ?? "unknown", 300);
        var appName = Bounded(Normalized(raw.AppName) ?? "Unknown", 200);
        var title = BoundedOptional(FilterTitle(raw.WindowTitle, appName), 300);
        var domain = NormalizeDomain(raw.DocumentReference);
        var sensitive = Contains(bundleId, SensitiveAppFragments)
            || Contains(appName, SensitiveAppFragments)
            || Contains(title, SensitiveTitleFragments)
            || Contains(domain, SensitiveDomainFragments);
        if (sensitive)
            return new ActivityContext { BundleId = bundleId, AppName = appName, TitleRedacted = true };

        if (!includeStructuredContext)
            return new ActivityContext { BundleId = bundleId, AppName = appName, WindowTitle = title };

        var lowerBundle = bundleId.ToLowerInvariant();
        var browser = BrowserFragments.Any(fragment => lowerBundle.Contains(fragment, StringComparison.Ordinal));
        var ide = IdeFragments.Any(fragment => lowerBundle.Contains(fragment, StringComparison.Ordinal));
        var kind = browser ? ActivityContextKind.browser : ide ? ActivityContextKind.ide : ActivityContextKind.application;
        string? document = null;
        string? workspace = null;
        if (ide && title is not null)
        {
            var pieces = title.Split(" - ", StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
            if (pieces.Length >= 2)
            {
                document = SafeName(pieces[0]);
                workspace = SafeName(pieces[^1]);
            }
        }
        return new ActivityContext
        {
            BundleId = bundleId,
            AppName = appName,
            WindowTitle = title,
            ContextKind = kind,
            Domain = browser ? domain : null,
            Workspace = workspace,
            DocumentName = document,
        };
    }

    private static string? FilterTitle(string? value, string appName)
    {
        var title = Normalized(value);
        if (title is null) return null;
        foreach (var separator in new[] { " — ", " - ", " | " })
        {
            var suffix = separator + appName;
            if (!title.Equals(appName, StringComparison.OrdinalIgnoreCase)
                && title.EndsWith(suffix, StringComparison.OrdinalIgnoreCase))
            {
                title = title[..^suffix.Length];
                break;
            }
        }
        return Normalized(string.Join(" — ", title.Split(" — ").Select(FilterPathOrUrl)));
    }

    private static string FilterPathOrUrl(string value)
    {
        if (Uri.TryCreate(value, UriKind.Absolute, out var uri) && !string.IsNullOrEmpty(uri.Host))
            return uri.Host.ToLowerInvariant();
        if (Regex.IsMatch(value, "^[A-Za-z]:\\\\") || value.StartsWith("/"))
            return Path.GetFileName(value.TrimEnd('\\', '/'));
        return value;
    }

    private static string? NormalizeDomain(string? value)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri) || string.IsNullOrEmpty(uri.Host)) return null;
        return Bounded(uri.Host.Trim('.').ToLowerInvariant(), 253);
    }

    private static string? SafeName(string value)
    {
        var normalized = Normalized(value);
        if (normalized is null || normalized.Contains('\\') || normalized.Contains('/')) return null;
        return Bounded(normalized, 300);
    }

    private static string? Normalized(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        var result = Regex.Replace(value, @"\s+", " ").Trim();
        return result.Length == 0 ? null : result;
    }

    private static string Bounded(string value, int length) => value[..Math.Min(value.Length, length)];
    private static string? BoundedOptional(string? value, int length) => value is null ? null : Bounded(value, length);
    private static bool Contains(string? value, IEnumerable<string> fragments) => value is not null
        && fragments.Any(fragment => value.Contains(fragment, StringComparison.OrdinalIgnoreCase));
}
