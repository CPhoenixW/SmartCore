using System.Text.Json;
using System.Text.RegularExpressions;

namespace SmartCoreMonitor.Windows;

/// <summary>
/// Reads only Codex desktop selection metadata. It never opens rollout files or conversation text.
/// </summary>
public sealed class CodexConversationTitleReader
{
    private const int InitialLogBytes = 16 * 1024 * 1024;
    private const int IncrementalLogBytes = 2 * 1024 * 1024;
    private const int MaxIndexBytes = 4 * 1024 * 1024;
    private readonly string home;
    private readonly object gate = new();
    private LogMetadata? trackedLog;
    private bool hasReadLog;
    private string? cachedConversationId;
    private LogMetadata? trackedIndex;
    private string? trackedIndexConversationId;
    private string? cachedTitle;

    private sealed record LogMetadata(string Path, long Length, DateTime LastWriteTimeUtc);

    public CodexConversationTitleReader(string? home = null)
    {
        this.home = home ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
    }

    public string? CurrentTitle(string appName)
    {
        var conversationId = CurrentConversationId();
        if (conversationId is null) return null;
        var indexPath = Path.Combine(home, ".codex", "session_index.jsonl");
        if (!File.Exists(indexPath)) return null;
        try
        {
            var index = new FileInfo(indexPath);
            lock (gate)
            {
                if (trackedIndex is not null
                    && trackedIndex.Path == index.FullName
                    && trackedIndex.Length == index.Length
                    && trackedIndex.LastWriteTimeUtc == index.LastWriteTimeUtc
                    && string.Equals(trackedIndexConversationId, conversationId, StringComparison.OrdinalIgnoreCase))
                    return cachedTitle;

                string? title = null;
                foreach (var line in ReadTail(indexPath, MaxIndexBytes).Split('\n', StringSplitOptions.RemoveEmptyEntries))
                {
                    try
                    {
                        using var json = JsonDocument.Parse(line);
                        var root = json.RootElement;
                        if (!root.TryGetProperty("id", out var id)
                            || !string.Equals(id.GetString(), conversationId, StringComparison.OrdinalIgnoreCase)
                            || !root.TryGetProperty("thread_name", out var name)) continue;
                        title = ChatTitlePolicy.Sanitize(name.GetString(), appName);
                    }
                    catch (JsonException) { }
                }
                trackedIndex = new LogMetadata(index.FullName, index.Length, index.LastWriteTimeUtc);
                trackedIndexConversationId = conversationId;
                cachedTitle = title;
                return title;
            }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
        return null;
    }

    private string? CurrentConversationId()
    {
        try
        {
            var roots = new[]
            {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "OpenAI", "Codex", "logs"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "OpenAI", "Codex", "logs"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Codex", "logs"),
                Path.Combine(home, ".codex", "logs"),
            };
            var latest = roots
                .Where(Directory.Exists)
                .SelectMany(root => Directory.EnumerateFiles(root, "*.log", SearchOption.AllDirectories))
                .Select(path => new FileInfo(path))
                .Where(file => file.Name.StartsWith("codex-desktop-", StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(file => file.LastWriteTimeUtc)
                .FirstOrDefault();
            if (latest is null) return null;
            var metadata = new LogMetadata(latest.FullName, latest.Length, latest.LastWriteTimeUtc);
            lock (gate)
            {
                if (hasReadLog
                    && trackedLog is not null
                    && trackedLog.Path == metadata.Path
                    && trackedLog.Length == metadata.Length
                    && trackedLog.LastWriteTimeUtc == metadata.LastWriteTimeUtc)
                    return cachedConversationId;

                var bytes = hasReadLog && trackedLog?.Path == metadata.Path
                    ? IncrementalLogBytes
                    : InitialLogBytes;
                var current = cachedConversationId;
                foreach (Match match in Regex.Matches(
                    ReadTail(latest.FullName, bytes),
                    @"thread_stream_view_activity_changed active=(true|false) conversationId=([0-9a-fA-F-]{36}).*rendererWindowAppearance=primary"))
                {
                    var id = match.Groups[2].Value.ToLowerInvariant();
                    if (!Guid.TryParse(id, out _)) continue;
                    if (match.Groups[1].Value == "true") current = id;
                    else if (current == id) current = null;
                }
                trackedLog = metadata;
                hasReadLog = true;
                cachedConversationId = current;
                return current;
            }
        }
        catch (IOException)
        {
            return cachedConversationId;
        }
        catch (UnauthorizedAccessException)
        {
            return cachedConversationId;
        }
    }

    private static string ReadTail(string path, int maximumBytes)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        var start = Math.Max(0, stream.Length - maximumBytes);
        stream.Seek(start, SeekOrigin.Begin);
        using var reader = new StreamReader(stream);
        var text = reader.ReadToEnd();
        return start > 0 && text.IndexOf('\n') >= 0 ? text[(text.IndexOf('\n') + 1)..] : text;
    }
}

public static class ChatTitlePolicy
{
    private static readonly HashSet<string> Ignored = new(StringComparer.OrdinalIgnoreCase)
    {
        "codex", "new chat", "search", "settings", "send", "stop generating", "attach files", "close", "back",
    };

    public static string? Sanitize(string? value, string appName)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Contains('\n') || value.Contains('\r')) return null;
        var normalized = string.Join(' ', value.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
        if (normalized.Length == 0 || normalized.Length > 200 || normalized.Equals(appName, StringComparison.OrdinalIgnoreCase) || Ignored.Contains(normalized)) return null;
        return normalized;
    }
}
