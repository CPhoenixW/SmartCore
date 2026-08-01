namespace SmartCoreMonitor.Windows;

public static class ActivityStateResolver
{
    public const double DefaultIdleSeconds = 120;

    public static ActivityState Resolve(
        bool paused,
        bool sleeping,
        bool locked,
        double idleSeconds,
        double idleThreshold = DefaultIdleSeconds)
    {
        if (paused) return ActivityState.paused;
        if (sleeping) return ActivityState.sleeping;
        if (locked) return ActivityState.locked;
        return idleSeconds >= idleThreshold ? ActivityState.idle : ActivityState.active;
    }
}

public sealed class SessionTracker
{
    private readonly TimeSpan idleBoundary;
    public string? SessionId { get; private set; }
    public DateTimeOffset? LastActiveAt { get; private set; }

    public SessionTracker(TimeSpan? idleBoundary = null)
    {
        this.idleBoundary = idleBoundary ?? TimeSpan.FromMinutes(10);
    }

    public string? Update(ActivityState state, DateTimeOffset at)
    {
        switch (state)
        {
            case ActivityState.locked:
            case ActivityState.sleeping:
            case ActivityState.paused:
                SessionId = null;
                break;
            case ActivityState.idle:
                if (LastActiveAt is not null && at - LastActiveAt.Value >= idleBoundary)
                    SessionId = null;
                break;
            case ActivityState.active:
                if (SessionId is null || LastActiveAt is null || at - LastActiveAt.Value >= idleBoundary)
                    SessionId = Guid.NewGuid().ToString("D").ToLowerInvariant();
                LastActiveAt = at;
                break;
        }
        return SessionId;
    }
}

public static class TimezoneMapper
{
    private static readonly IReadOnlyDictionary<string, string> WindowsToIana =
        new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["UTC"] = "UTC",
            ["China Standard Time"] = "Asia/Shanghai",
            ["Singapore Standard Time"] = "Asia/Singapore",
            ["Tokyo Standard Time"] = "Asia/Tokyo",
            ["Korea Standard Time"] = "Asia/Seoul",
            ["Taipei Standard Time"] = "Asia/Taipei",
            ["W. Australia Standard Time"] = "Australia/Perth",
            ["AUS Eastern Standard Time"] = "Australia/Sydney",
            ["New Zealand Standard Time"] = "Pacific/Auckland",
            ["India Standard Time"] = "Asia/Kolkata",
            ["SE Asia Standard Time"] = "Asia/Bangkok",
            ["Russian Standard Time"] = "Europe/Moscow",
            ["GMT Standard Time"] = "Europe/London",
            ["W. Europe Standard Time"] = "Europe/Berlin",
            ["Central Europe Standard Time"] = "Europe/Budapest",
            ["Romance Standard Time"] = "Europe/Paris",
            ["E. Europe Standard Time"] = "Europe/Bucharest",
            ["Turkey Standard Time"] = "Europe/Istanbul",
            ["Eastern Standard Time"] = "America/New_York",
            ["Central Standard Time"] = "America/Chicago",
            ["Mountain Standard Time"] = "America/Denver",
            ["Pacific Standard Time"] = "America/Los_Angeles",
            ["Alaskan Standard Time"] = "America/Anchorage",
            ["Hawaiian Standard Time"] = "Pacific/Honolulu",
            ["Atlantic Standard Time"] = "America/Halifax",
            ["Argentina Standard Time"] = "America/Argentina/Buenos_Aires",
            ["E. South America Standard Time"] = "America/Sao_Paulo",
            ["South Africa Standard Time"] = "Africa/Johannesburg",
            ["Egypt Standard Time"] = "Africa/Cairo",
        };

    public static string LocalIana(string? configured = null)
    {
        var value = string.IsNullOrWhiteSpace(configured)
            ? TimeZoneInfo.Local.Id
            : configured.Trim();
        if (value.Equals("UTC", StringComparison.OrdinalIgnoreCase)) return "UTC";
        if (WindowsToIana.TryGetValue(value, out var iana)) return iana;
        try
        {
            if (TimeZoneInfo.TryConvertWindowsIdToIanaId(value, out var converted) && !string.IsNullOrWhiteSpace(converted))
                return converted;
        }
        catch (PlatformNotSupportedException) { }
        return value.Contains('/', StringComparison.Ordinal) ? value : "UTC";
    }
}

public sealed class ActivityAggregator
{
    private sealed class PendingBucket
    {
        public DateTimeOffset Start { get; init; }
        public string Timezone { get; init; } = "UTC";
        public string? SessionId { get; set; }
        public int CoveredSeconds { get; set; }
        public int SwitchCount { get; set; }
        public string? LastBundleId { get; set; }
        public List<ActivitySlice> Slices { get; } = [];

        public void Add(ActivityState state, ActivityContext? context, int seconds, string? sessionId)
        {
            var bounded = Math.Min(seconds, Math.Max(0, 60 - CoveredSeconds));
            if (bounded <= 0) return;
            var activeContext = state == ActivityState.active ? context : null;
            var existing = Slices.FirstOrDefault(item => Same(item, state, activeContext));
            if (existing is null)
                Slices.Add(ActivitySlice.From(state, bounded, activeContext));
            else
                existing.Seconds += bounded;
            CoveredSeconds += bounded;
            SessionId ??= sessionId;
            if (state == ActivityState.active && activeContext is not null)
            {
                if (LastBundleId is not null && LastBundleId != activeContext.BundleId) SwitchCount++;
                LastBundleId = activeContext.BundleId;
            }
        }

        public ActivityBucket FinalizeBucket() => new()
        {
            BucketStart = Start,
            Timezone = Timezone,
            SessionId = SessionId,
            CoveredSeconds = CoveredSeconds,
            SwitchCount = SwitchCount,
            Slices = Slices
                .OrderBy(item => item.State.ToString(), StringComparer.Ordinal)
                .ThenBy(item => item.AppName ?? "", StringComparer.Ordinal)
                .ToList(),
        };

        private static bool Same(ActivitySlice slice, ActivityState state, ActivityContext? context)
        {
            return slice.State == state
                && slice.BundleId == context?.BundleId
                && slice.AppName == context?.AppName
                && slice.WindowTitle == context?.WindowTitle
                && slice.ContextKind == context?.ContextKind
                && slice.Domain == context?.Domain
                && slice.Workspace == context?.Workspace
                && slice.DocumentName == context?.DocumentName
                && slice.TitleRedacted == (context?.TitleRedacted ?? false);
        }
    }

    private PendingBucket? pending;
    private readonly SessionTracker tracker;
    private readonly TimeZoneInfo localZone;
    private readonly string timezone;

    public ActivityAggregator(string timezone)
    {
        this.timezone = timezone;
        localZone = ResolveZone(timezone);
        tracker = new SessionTracker();
    }

    public List<ActivityBucket> Record(
        ActivityState state,
        ActivityContext? context,
        DateTimeOffset start,
        DateTimeOffset end)
    {
        if (end <= start) return [];
        var completed = new List<ActivityBucket>();
        var cursor = start;
        while (cursor < end)
        {
            var minuteStart = MinuteStart(cursor);
            var minuteEnd = minuteStart.AddMinutes(1);
            var segmentEnd = end < minuteEnd ? end : minuteEnd;
            var seconds = Math.Max(1, (int)Math.Round((segmentEnd - cursor).TotalSeconds));
            if (pending is null || pending.Start.UtcDateTime != minuteStart.UtcDateTime)
            {
                if (pending is not null && pending.CoveredSeconds > 0) completed.Add(pending.FinalizeBucket());
                pending = new PendingBucket { Start = minuteStart, Timezone = timezone };
            }
            pending!.Add(state, context, seconds, tracker.Update(state, segmentEnd));
            cursor = segmentEnd;
        }
        return completed;
    }

    public List<ActivityBucket> Flush(DateTimeOffset? before = null)
    {
        if (pending is null) return [];
        var currentMinute = MinuteStart(before ?? DateTimeOffset.UtcNow);
        if (pending.Start >= currentMinute) return [];
        var result = pending.CoveredSeconds > 0 ? [pending.FinalizeBucket()] : new List<ActivityBucket>();
        pending = null;
        return result;
    }

    private DateTimeOffset MinuteStart(DateTimeOffset value)
    {
        var local = TimeZoneInfo.ConvertTime(value, localZone);
        var localMinute = new DateTime(local.Year, local.Month, local.Day, local.Hour, local.Minute, 0, DateTimeKind.Unspecified);
        return new DateTimeOffset(localMinute, local.Offset);
    }

    private static TimeZoneInfo ResolveZone(string timezone)
    {
        try { return TimeZoneInfo.FindSystemTimeZoneById(timezone); }
        catch (TimeZoneNotFoundException) { return TimeZoneInfo.Local; }
        catch (InvalidTimeZoneException) { return TimeZoneInfo.Local; }
        catch (PlatformNotSupportedException) { return TimeZoneInfo.Local; }
    }
}

public sealed class RetryBackoff
{
    private int failures;

    public void Succeeded() => failures = 0;

    public TimeSpan Failed()
    {
        failures++;
        return TimeSpan.FromSeconds(Math.Min(300, Math.Pow(2, Math.Min(failures, 8)) * 2.5));
    }
}
