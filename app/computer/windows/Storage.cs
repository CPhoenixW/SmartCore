using System.Text;
using System.Text.Json;

namespace SmartCoreMonitor.Windows;

public sealed class LocalStorage
{
    public string Root { get; }
    public string ConfigurationPath => Path.Combine(Root, "configuration.json");
    public string TokenPath => Path.Combine(Root, "device-token.txt");
    public string OutboxPath => Path.Combine(Root, "outbox.json");

    public LocalStorage(string? root = null)
    {
        Root = root ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "SmartCoreMonitor");
        Directory.CreateDirectory(Root);
    }

    public MonitorConfiguration? LoadConfiguration()
    {
        if (!File.Exists(ConfigurationPath)) return null;
        try
        {
            return JsonSerializer.Deserialize<MonitorConfiguration>(File.ReadAllText(ConfigurationPath), MonitorJson.Options);
        }
        catch (JsonException) { return null; }
        catch (IOException) { return null; }
    }

    public string? LoadToken()
    {
        try { return File.Exists(TokenPath) ? File.ReadAllText(TokenPath).Trim() : null; }
        catch (IOException) { return null; }
    }

    public void SavePairing(MonitorConfiguration configuration, string token)
    {
        AtomicWrite(ConfigurationPath, JsonSerializer.Serialize(configuration, MonitorJson.Options));
        AtomicWrite(TokenPath, token.Trim() + Environment.NewLine);
        TryRestrictToCurrentUser(ConfigurationPath);
        TryRestrictToCurrentUser(TokenPath);
    }

    public static void AtomicWrite(string path, string content)
    {
        var temp = path + ".tmp-" + Guid.NewGuid().ToString("N");
        File.WriteAllText(temp, content, new UTF8Encoding(false));
        File.Move(temp, path, true);
    }

    private static void TryRestrictToCurrentUser(string path)
    {
        if (!OperatingSystem.IsWindows()) return;
        try
        {
            using var process = new System.Diagnostics.Process
            {
                StartInfo = new System.Diagnostics.ProcessStartInfo
                {
                    FileName = "icacls.exe",
                    Arguments = $"\"{path}\" /inheritance:r /grant:r \"{CurrentUserPrincipal()}\":F",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                },
            };
            process.Start();
            process.WaitForExit(3_000);
        }
        catch (Exception) { /* LocalApplicationData already inherits user-only defaults. */ }
    }

    private static string CurrentUserPrincipal()
    {
        var domain = Environment.UserDomainName;
        return string.IsNullOrWhiteSpace(domain) ? Environment.UserName : $"{domain}\\{Environment.UserName}";
    }
}

public sealed class OutboxStore
{
    private readonly string path;
    private readonly object gate = new();
    private Dictionary<string, string> records = new(StringComparer.Ordinal);

    public OutboxStore(string path)
    {
        this.path = path;
        Load();
    }

    public void Enqueue(string deviceId, IEnumerable<ActivityBucket> buckets)
    {
        lock (gate)
        {
            foreach (var bucket in buckets)
            {
                var key = Key(deviceId, bucket.BucketStart);
                records[key] = JsonSerializer.Serialize(bucket, MonitorJson.Options);
            }
            Persist();
        }
    }

    public List<ActivityBucket> Pending(string deviceId, int limit = 120)
    {
        lock (gate)
        {
            return records
                .Where(item => item.Key.StartsWith(deviceId + "|", StringComparison.Ordinal))
                .OrderBy(item => item.Key, StringComparer.Ordinal)
                .Take(limit)
                .Select(item => JsonSerializer.Deserialize<ActivityBucket>(item.Value, MonitorJson.Options))
                .Where(item => item is not null)
                .Cast<ActivityBucket>()
                .ToList();
        }
    }

    public void Acknowledge(string deviceId, IEnumerable<DateTimeOffset> bucketStarts)
    {
        lock (gate)
        {
            foreach (var start in bucketStarts) records.Remove(Key(deviceId, start));
            Persist();
        }
    }

    public int Count(string deviceId)
    {
        lock (gate) return records.Keys.Count(key => key.StartsWith(deviceId + "|", StringComparison.Ordinal));
    }

    public void Prune(TimeSpan? maxAge = null, long maxBytes = 50 * 1024 * 1024)
    {
        lock (gate)
        {
            var cutoff = DateTimeOffset.UtcNow - (maxAge ?? TimeSpan.FromDays(90));
            foreach (var key in records.Keys.ToList())
            {
                var separator = key.IndexOf('|');
                if (separator > 0 && DateTimeOffset.TryParse(key[(separator + 1)..], out var start) && start < cutoff)
                    records.Remove(key);
            }
            while (SerializedSize() > maxBytes && records.Count > 0)
                records.Remove(records.Keys.OrderBy(key => key, StringComparer.Ordinal).First());
            Persist();
        }
    }

    private void Load()
    {
        lock (gate)
        {
            if (!File.Exists(path)) return;
            try
            {
                records = JsonSerializer.Deserialize<Dictionary<string, string>>(File.ReadAllText(path), MonitorJson.Options)
                    ?? new(StringComparer.Ordinal);
            }
            catch (Exception) { records = new(StringComparer.Ordinal); }
        }
    }

    private void Persist()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        LocalStorage.AtomicWrite(path, JsonSerializer.Serialize(records, MonitorJson.Options));
    }

    private long SerializedSize() => Encoding.UTF8.GetByteCount(JsonSerializer.Serialize(records, MonitorJson.Options));
    private static string Key(string deviceId, DateTimeOffset start) => $"{deviceId}|{start.ToUniversalTime():O}";
}
