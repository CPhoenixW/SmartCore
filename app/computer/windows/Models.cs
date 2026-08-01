using System.Text.Json;
using System.Text.Json.Serialization;

namespace SmartCoreMonitor.Windows;

public enum ActivityState
{
    active,
    idle,
    locked,
    sleeping,
    paused,
}

public enum ActivityContextKind
{
    application,
    browser,
    ide,
    document,
}

public sealed class ActivityContext : IEquatable<ActivityContext>
{
    public string BundleId { get; init; } = "unknown";
    public string AppName { get; init; } = "Unknown";
    public string? WindowTitle { get; init; }
    public ActivityContextKind? ContextKind { get; init; }
    public string? Domain { get; init; }
    public string? Workspace { get; init; }
    public string? DocumentName { get; init; }
    public bool TitleRedacted { get; init; }

    public bool Equals(ActivityContext? other) => other is not null
        && BundleId == other.BundleId
        && AppName == other.AppName
        && WindowTitle == other.WindowTitle
        && ContextKind == other.ContextKind
        && Domain == other.Domain
        && Workspace == other.Workspace
        && DocumentName == other.DocumentName
        && TitleRedacted == other.TitleRedacted;

    public override bool Equals(object? obj) => Equals(obj as ActivityContext);

    public override int GetHashCode() => HashCode.Combine(
        BundleId, AppName, WindowTitle, ContextKind, Domain, Workspace, DocumentName, TitleRedacted);
}

public sealed class ActivitySlice
{
    public ActivityState State { get; init; }
    public int Seconds { get; set; }
    public string? BundleId { get; init; }
    public string? AppName { get; init; }
    public string? WindowTitle { get; init; }
    public ActivityContextKind? ContextKind { get; init; }
    public string? Domain { get; init; }
    public string? Workspace { get; init; }
    public string? DocumentName { get; init; }
    public bool TitleRedacted { get; init; }

    public static ActivitySlice From(ActivityState state, int seconds, ActivityContext? context)
    {
        return new ActivitySlice
        {
            State = state,
            Seconds = seconds,
            BundleId = context?.BundleId,
            AppName = context?.AppName,
            WindowTitle = context?.WindowTitle,
            ContextKind = context?.ContextKind,
            Domain = context?.Domain,
            Workspace = context?.Workspace,
            DocumentName = context?.DocumentName,
            TitleRedacted = context?.TitleRedacted ?? false,
        };
    }
}

public sealed class ActivityBucket
{
    public DateTimeOffset BucketStart { get; init; }
    public string Timezone { get; init; } = "UTC";
    public string? SessionId { get; init; }
    public int CoveredSeconds { get; init; }
    public int SwitchCount { get; init; }
    public List<ActivitySlice> Slices { get; init; } = [];
}

public sealed class ActivityBatch
{
    public int SchemaVersion { get; init; } = 1;
    public List<ActivityBucket> Buckets { get; init; } = [];
}

public sealed class MonitorHeartbeat
{
    public ActivityState CurrentState { get; init; }
    public DateTimeOffset ObservedAt { get; init; }
    public string? CurrentAppName { get; init; }
    public string? CurrentWindowTitle { get; init; }
    public string AppVersion { get; init; } = "0.1.0";
    public string OsVersion { get; init; } = "Windows";
    public bool AccessibilityGranted { get; init; } = true;
    public bool Paused { get; init; }
    public int QueueDepth { get; init; }
}

public sealed class PairingDocument
{
    public string ServerUrl { get; init; } = "";
    public string PairId { get; init; } = "";
    public string ClaimCode { get; init; } = "";
}

public sealed class MonitorConfiguration
{
    public string ServerUrl { get; init; } = "";
    public string DeviceId { get; init; } = "";
    public string DeviceName { get; init; } = "";
}

public sealed class PairStatusPayload
{
    public string Stat { get; init; } = "";
}

public sealed class DevicePayload
{
    public string DeviceId { get; init; } = "";
    public string DeviceName { get; init; } = "";
}

public sealed class ActivationPayload
{
    public DevicePayload Device { get; init; } = new();
    public string DeviceToken { get; init; } = "";
}

public sealed class AcceptedPayload
{
    public List<DateTimeOffset> AcceptedBucketStarts { get; init; } = [];
}

public sealed class AcceptedCodexWorkReport
{
    public string ReportId { get; init; } = "";
    public string SourceTaskId { get; init; } = "";
    public string ReportDate { get; init; } = "";
    public bool Created { get; init; }
}

public sealed class AcceptedCodexWorkReportsPayload
{
    public List<AcceptedCodexWorkReport> AcceptedReports { get; init; } = [];
}

public enum CodexWorkStatus
{
    completed,
    partial,
    in_progress,
}

public sealed class CodexWorkEvidence
{
    public List<string> Commits { get; init; } = [];
    public List<string> PullRequests { get; init; } = [];
    public List<string> Tests { get; init; } = [];
}

public sealed class CodexWorkReport
{
    public string SourceTaskId { get; init; } = "";
    public string ReportDate { get; init; } = "";
    public string Timezone { get; init; } = "";
    public string ProjectKey { get; init; } = "";
    public string ProjectName { get; init; } = "";
    public string Title { get; init; } = "";
    public string Summary { get; init; } = "";
    public CodexWorkStatus Status { get; init; }
    public string? StartedAt { get; init; }
    public string? EndedAt { get; init; }
    public CodexWorkEvidence Evidence { get; init; } = new();
}

public sealed class CodexWorkReportBatch
{
    public List<CodexWorkReport> Reports { get; init; } = [];
}

public static class MonitorJson
{
    public static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DictionaryKeyPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = false,
    };

    static MonitorJson()
    {
        Options.Converters.Add(new JsonStringEnumConverter(JsonNamingPolicy.CamelCase));
    }
}
