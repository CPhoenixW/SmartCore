namespace SmartCoreMonitor.Windows;

public sealed class MonitorRuntime : IDisposable
{
    private const int SampleSeconds = 20;
    private const int HeartbeatSeconds = 30;
    private readonly LocalStorage storage;
    private readonly OutboxStore outbox;
    private readonly SmartCoreClient client;
    private readonly RetryBackoff retryBackoff = new();
    private WindowsPlatform platform;
    private ActivityAggregator aggregator;
    private MonitorConfiguration? configuration;
    private string? token;
    private string? loadedDeviceId;
    private ActivityState currentState = ActivityState.idle;
    private ActivityContext? currentContext;
    private DateTimeOffset lastSampleAt = DateTimeOffset.UtcNow;
    private DateTimeOffset nextSyncAt = DateTimeOffset.MinValue;
    private DateTime structuredContextModifiedAt;
    private bool syncing;

    public MonitorRuntime(LocalStorage storage, bool structuredContext)
    {
        this.storage = storage;
        outbox = new OutboxStore(storage.OutboxPath);
        outbox.Prune();
        client = new SmartCoreClient();
        var timezone = TimezoneMapper.LocalIana(Environment.GetEnvironmentVariable("SMARTCORE_TIMEZONE"));
        aggregator = new ActivityAggregator(timezone);
        platform = new WindowsPlatform(structuredContext);
        platform.StateChanged += () => nextSyncAt = DateTimeOffset.MinValue;
    }

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(SampleSeconds));
        Sample(DateTimeOffset.UtcNow);
        while (await timer.WaitForNextTickAsync(cancellationToken))
        {
            Sample(DateTimeOffset.UtcNow);
            if (DateTimeOffset.UtcNow >= nextSyncAt) await SynchronizeAsync(cancellationToken);
        }
    }

    private void Sample(DateTimeOffset now)
    {
        ReloadConfigurationIfNeeded();
        RefreshStructuredContext();
        if (configuration is null || string.IsNullOrWhiteSpace(token)) return;
        var resolvedState = ActivityStateResolver.Resolve(
            platform.Paused,
            platform.Sleeping,
            platform.IsLocked(),
            platform.IdleSeconds());
        var context = resolvedState == ActivityState.active ? platform.CurrentContext() : null;
        var changed = resolvedState != currentState || !Equals(context, currentContext);
        // The state observed at this sample covers the interval since the previous sample,
        // matching the macOS monitor and avoiding a one-sample delay in activity reports.
        var buckets = aggregator.Record(resolvedState, context, lastSampleAt, now);
        if (buckets.Count > 0) outbox.Enqueue(configuration.DeviceId, buckets);
        lastSampleAt = now;
        currentState = resolvedState;
        currentContext = context;
        if (changed) nextSyncAt = DateTimeOffset.MinValue;
    }

    private async Task SynchronizeAsync(CancellationToken cancellationToken)
    {
        if (syncing || configuration is null || string.IsNullOrWhiteSpace(token)) return;
        syncing = true;
        try
        {
            var buckets = outbox.Pending(configuration.DeviceId);
            if (buckets.Count > 0)
            {
                var accepted = await client.UploadAsync(configuration.ServerUrl, token, buckets, cancellationToken);
                outbox.Acknowledge(configuration.DeviceId, accepted);
            }
            await client.HeartbeatAsync(
                configuration.ServerUrl,
                token,
                new MonitorHeartbeat
                {
                    CurrentState = currentState,
                    ObservedAt = DateTimeOffset.UtcNow,
                    CurrentAppName = currentContext?.AppName,
                    CurrentWindowTitle = currentContext?.WindowTitle,
                    AppVersion = "0.1.0",
                    OsVersion = Environment.OSVersion.VersionString,
                    AccessibilityGranted = true,
                    Paused = platform.Paused,
                    QueueDepth = outbox.Count(configuration.DeviceId),
                },
                cancellationToken);
            retryBackoff.Succeeded();
            nextSyncAt = DateTimeOffset.UtcNow.AddSeconds(HeartbeatSeconds);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (Exception error)
        {
            nextSyncAt = DateTimeOffset.UtcNow.Add(retryBackoff.Failed());
            Console.Error.WriteLine($"SmartCoreMonitor: synchronization pending: {error.Message}");
        }
        finally { syncing = false; }
    }

    private void ReloadConfigurationIfNeeded()
    {
        var nextConfiguration = storage.LoadConfiguration();
        var nextToken = storage.LoadToken();
        var sameConfiguration = nextConfiguration is null
            ? configuration is null
            : nextConfiguration.DeviceId == loadedDeviceId
                && configuration?.ServerUrl == nextConfiguration.ServerUrl;
        if (sameConfiguration && token == nextToken) return;
        configuration = nextConfiguration;
        token = nextToken;
        loadedDeviceId = nextConfiguration?.DeviceId;
        if (nextConfiguration is not null)
        {
            var timezone = TimezoneMapper.LocalIana(Environment.GetEnvironmentVariable("SMARTCORE_TIMEZONE"));
            aggregator = new ActivityAggregator(timezone);
            lastSampleAt = DateTimeOffset.UtcNow;
            nextSyncAt = DateTimeOffset.MinValue;
        }
    }

    private void RefreshStructuredContext()
    {
        var path = Path.Combine(storage.Root, "structured-context");
        DateTime modified;
        try { modified = File.GetLastWriteTimeUtc(path); }
        catch (IOException) { modified = DateTime.MinValue; }
        if (modified == structuredContextModifiedAt) return;
        structuredContextModifiedAt = modified;
        var enabled = false;
        try { enabled = File.Exists(path) && File.ReadAllText(path).Trim().Equals("on", StringComparison.OrdinalIgnoreCase); }
        catch (IOException) { }
        platform.SetStructuredContext(enabled);
    }

    public void Dispose()
    {
        platform.Dispose();
        client.Dispose();
    }
}
