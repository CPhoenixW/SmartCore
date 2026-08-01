using System.Text.Json;

namespace SmartCoreMonitor.Windows;

public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        try
        {
            var command = args.FirstOrDefault()?.ToLowerInvariant() ?? "run";
            return command switch
            {
                "pair" => await PairAsync(),
                "status" => Status(),
                "structured-context" => StructuredContext(args.Skip(1).FirstOrDefault()),
                "accessibility" => Accessibility(args.Skip(1).FirstOrDefault()),
                "codex-report" => await UploadCodexReportAsync(),
                "self-test" => SelfTest(),
                "run" => await RunAsync(),
                _ => Usage(),
            };
        }
        catch (Exception error)
        {
            Console.Error.WriteLine($"SmartCoreMonitor: {error.Message}");
            return 1;
        }
    }

    private static async Task<int> PairAsync()
    {
        var document = JsonSerializer.Deserialize<PairingDocument>(
            await Console.In.ReadToEndAsync(), MonitorJson.Options);
        if (document is null || string.IsNullOrWhiteSpace(document.ServerUrl)
            || string.IsNullOrWhiteSpace(document.PairId) || string.IsNullOrWhiteSpace(document.ClaimCode))
        {
            Console.Error.WriteLine("Pairing JSON must be provided on standard input.");
            return 2;
        }

        var storage = new LocalStorage();
        using var client = new SmartCoreClient();
        var deviceName = Environment.GetEnvironmentVariable("COMPUTERNAME") ?? "Windows Computer";
        await client.ClaimAsync(document, deviceName, CancellationToken.None);
        Console.WriteLine("Pairing claimed. Confirm it in SmartCore.");
        for (var attempt = 0; attempt < 200; attempt++)
        {
            if (await client.PairingStatusAsync(document, CancellationToken.None) == "userConfirmed")
            {
                var activated = await client.ActivateAsync(document, CancellationToken.None);
                storage.SavePairing(activated.Configuration, activated.Token);
                Console.WriteLine($"Paired {activated.Configuration.DeviceName}.");
                return 0;
            }
            await Task.Delay(TimeSpan.FromSeconds(3));
        }
        Console.Error.WriteLine("Pairing timed out.");
        return 1;
    }

    private static int Status()
    {
        var storage = new LocalStorage();
        var configuration = storage.LoadConfiguration();
        if (configuration is null) { Console.WriteLine("not paired"); return 0; }
        var token = storage.LoadToken();
        var structured = ReadStructuredContext();
        Console.WriteLine($"device={configuration.DeviceName} id={configuration.DeviceId} token={(string.IsNullOrWhiteSpace(token) ? "missing" : "ready")} accessibility=not-required structuredContext={(structured ? "on" : "off")} path={Environment.ProcessPath}");
        return 0;
    }

    private static int StructuredContext(string? value)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Equals("status", StringComparison.OrdinalIgnoreCase))
        {
            Console.WriteLine(ReadStructuredContext() ? "on" : "off");
            return 0;
        }
        if (!value.Equals("on", StringComparison.OrdinalIgnoreCase) && !value.Equals("off", StringComparison.OrdinalIgnoreCase)) return Usage();
        var storage = new LocalStorage();
        LocalStorage.AtomicWrite(Path.Combine(storage.Root, "structured-context"), value.Equals("on", StringComparison.OrdinalIgnoreCase) ? "on\n" : "off\n");
        Console.WriteLine($"Structured context collection is {value.ToLowerInvariant()}.");
        return 0;
    }

    private static int Accessibility(string? value)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Equals("status", StringComparison.OrdinalIgnoreCase))
        {
            Console.WriteLine("accessibility=not-required platform=Windows");
            return 0;
        }
        Console.Error.WriteLine("Windows does not require macOS Accessibility permission for Computer monitoring.");
        return value.Equals("open", StringComparison.OrdinalIgnoreCase) ? 0 : 2;
    }

    private static async Task<int> UploadCodexReportAsync()
    {
        var storage = new LocalStorage();
        var configuration = storage.LoadConfiguration();
        var token = storage.LoadToken();
        if (configuration is null || string.IsNullOrWhiteSpace(token))
        {
            Console.Error.WriteLine("The paired computer token is unavailable.");
            return 1;
        }
        var batch = JsonSerializer.Deserialize<CodexWorkReportBatch>(await Console.In.ReadToEndAsync(), MonitorJson.Options);
        if (batch is null || batch.Reports.Count == 0)
        {
            Console.Error.WriteLine("Codex report batch JSON must be provided on standard input.");
            return 2;
        }
        using var client = new SmartCoreClient();
        var accepted = await client.UploadCodexReportsAsync(configuration.ServerUrl, token, batch, CancellationToken.None);
        Console.WriteLine($"Uploaded {accepted.Count} Codex work report(s).");
        return 0;
    }

    private static async Task<int> RunAsync()
    {
        using var cancellation = new CancellationTokenSource();
        Console.CancelKeyPress += (_, args) => { args.Cancel = true; cancellation.Cancel(); };
        using var runtime = new MonitorRuntime(new LocalStorage(), ReadStructuredContext());
        try { await runtime.RunAsync(cancellation.Token); }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
        return 0;
    }

    private static bool ReadStructuredContext()
    {
        var path = Path.Combine(new LocalStorage().Root, "structured-context");
        try { return File.Exists(path) && File.ReadAllText(path).Trim().Equals("on", StringComparison.OrdinalIgnoreCase); }
        catch (IOException) { return false; }
    }

    private static int SelfTest()
    {
        if (ActivityStateResolver.Resolve(false, false, false, 120) != ActivityState.idle) throw new Exception("idle threshold failed");
        var start = DateTimeOffset.Parse("2026-01-01T00:00:00+00:00");
        var context = new ActivityContext { BundleId = "a", AppName = "A" };
        var aggregator = new ActivityAggregator("UTC");
        var buckets = aggregator.Record(ActivityState.active, context, start, start.AddSeconds(65));
        buckets.AddRange(aggregator.Flush(start.AddSeconds(122)));
        if (buckets.Sum(item => item.CoveredSeconds) != 65 || buckets.Any(item => item.CoveredSeconds > 60)) throw new Exception("aggregation failed");
        var encoded = JsonSerializer.Serialize(new ActivityBatch { Buckets = buckets }, MonitorJson.Options);
        if (!encoded.Contains("\"schemaVersion\":1", StringComparison.Ordinal)
            || !encoded.Contains("\"bucketStart\"", StringComparison.Ordinal)
            || encoded.Contains("\"BucketStart\"", StringComparison.Ordinal)) throw new Exception("protocol encoding failed");
        var sanitized = ActivityContextSanitizer.Sanitize(new RawActivityContext { BundleId = "chrome.exe", AppName = "Chrome", WindowTitle = "https://example.test/private - Chrome" }, false);
        if (sanitized.WindowTitle != "example.test") throw new Exception("sanitization failed");
        var sensitive = ActivityContextSanitizer.Sanitize(new RawActivityContext { BundleId = "1password.exe", AppName = "1Password", WindowTitle = "Personal vault" }, true);
        if (!sensitive.TitleRedacted || sensitive.WindowTitle is not null || sensitive.ContextKind is not null) throw new Exception("sensitive redaction failed");
        Console.WriteLine("self-test passed");
        return 0;
    }

    private static int Usage()
    {
        Console.Error.WriteLine("Usage: SmartCoreMonitor [run|pair|status|structured-context on|off|status|accessibility status|codex-report|self-test]");
        return 2;
    }
}
