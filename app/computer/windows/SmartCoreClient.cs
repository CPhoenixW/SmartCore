using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace SmartCoreMonitor.Windows;

public sealed class SmartCoreClientException : Exception
{
    public SmartCoreClientException(string message) : base(message) { }
}

public sealed class SmartCoreClient : IDisposable
{
    private sealed class Envelope<T>
    {
        public bool Ok { get; init; }
        public T Data { get; init; } = default!;
    }

    private readonly HttpClient http;

    public SmartCoreClient()
    {
        http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false })
        {
            Timeout = TimeSpan.FromSeconds(20),
        };
    }

    public async Task ClaimAsync(PairingDocument document, string deviceName, CancellationToken cancellationToken)
    {
        await RequestAsync<PairStatusPayload>(
            document.ServerUrl,
            $"/api/device/pair/{Uri.EscapeDataString(document.PairId)}/claim",
            HttpMethod.Post,
            new { claimCode = document.ClaimCode, deviceName },
            null,
            cancellationToken);
    }

    public async Task<string> PairingStatusAsync(PairingDocument document, CancellationToken cancellationToken)
    {
        return (await RequestAsync<PairStatusPayload>(
            document.ServerUrl,
            $"/api/device/pair/{Uri.EscapeDataString(document.PairId)}/status?claimCode={Uri.EscapeDataString(document.ClaimCode)}",
            HttpMethod.Get,
            null,
            null,
            cancellationToken)).Stat;
    }

    public async Task<(MonitorConfiguration Configuration, string Token)> ActivateAsync(
        PairingDocument document,
        CancellationToken cancellationToken)
    {
        var data = await RequestAsync<ActivationPayload>(
            document.ServerUrl,
            $"/api/device/pair/{Uri.EscapeDataString(document.PairId)}/activate",
            HttpMethod.Post,
            new { claimCode = document.ClaimCode },
            null,
            cancellationToken);
        return (
            new MonitorConfiguration
            {
                ServerUrl = document.ServerUrl,
                DeviceId = data.Device.DeviceId,
                DeviceName = data.Device.DeviceName,
            },
            data.DeviceToken);
    }

    public async Task<List<DateTimeOffset>> UploadAsync(
        string serverUrl,
        string token,
        IEnumerable<ActivityBucket> buckets,
        CancellationToken cancellationToken)
    {
        var data = await RequestAsync<AcceptedPayload>(
            serverUrl,
            "/api/computer/activity/batch",
            HttpMethod.Post,
            new ActivityBatch { Buckets = buckets.ToList() },
            token,
            cancellationToken);
        return data.AcceptedBucketStarts;
    }

    public async Task HeartbeatAsync(
        string serverUrl,
        string token,
        MonitorHeartbeat heartbeat,
        CancellationToken cancellationToken)
    {
        await RequestAsync<Dictionary<string, object>>(
            serverUrl, "/api/computer/heartbeat", HttpMethod.Post, heartbeat, token, cancellationToken);
    }

    public async Task<List<AcceptedCodexWorkReport>> UploadCodexReportsAsync(
        string serverUrl,
        string token,
        CodexWorkReportBatch batch,
        CancellationToken cancellationToken)
    {
        var data = await RequestAsync<AcceptedCodexWorkReportsPayload>(
            serverUrl, "/api/computer/codex-reports/batch", HttpMethod.Post, batch, token, cancellationToken);
        return data.AcceptedReports;
    }

    public void Dispose() => http.Dispose();

    private async Task<T> RequestAsync<T>(
        string baseUrl,
        string path,
        HttpMethod method,
        object? body,
        string? token,
        CancellationToken cancellationToken)
    {
        if (!Uri.TryCreate(baseUrl, UriKind.Absolute, out var baseUri)
            || (baseUri.Scheme != Uri.UriSchemeHttp && baseUri.Scheme != Uri.UriSchemeHttps)
            || !Uri.TryCreate(baseUri, path, out var uri)
            || uri is null
            || !string.Equals(uri.Host, baseUri.Host, StringComparison.OrdinalIgnoreCase))
            throw new SmartCoreClientException("Invalid SmartCore server URL");

        using var request = new HttpRequestMessage(method, uri);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (!string.IsNullOrWhiteSpace(token)) request.Headers.Add("X-SmartCore-Device-Token", token);
        if (body is not null)
            request.Content = new StringContent(JsonSerializer.Serialize(body, MonitorJson.Options), Encoding.UTF8, "application/json");

        using var response = await http.SendAsync(request, cancellationToken);
        var text = await response.Content.ReadAsStringAsync(cancellationToken);
        if (response.StatusCode is < HttpStatusCode.OK or >= HttpStatusCode.MultipleChoices)
        {
            var detail = "request failed";
            try
            {
                using var error = JsonDocument.Parse(text);
                if (error.RootElement.TryGetProperty("detail", out var detailProperty)) detail = detailProperty.GetString() ?? detail;
            }
            catch (JsonException) { }
            throw new SmartCoreClientException($"SmartCore rejected the request ({(int)response.StatusCode}): {detail}");
        }
        try
        {
            var envelope = JsonSerializer.Deserialize<Envelope<T>>(text, MonitorJson.Options);
            if (envelope is null || !envelope.Ok) throw new JsonException();
            return envelope.Data;
        }
        catch (JsonException ex)
        {
            throw new SmartCoreClientException($"SmartCore returned an invalid response: {ex.Message}");
        }
    }
}
