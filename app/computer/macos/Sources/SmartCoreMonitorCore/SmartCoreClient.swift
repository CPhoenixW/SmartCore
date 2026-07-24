import Foundation

public enum SmartCoreClientError: Error, LocalizedError {
    case invalidServerURL
    case unexpectedResponse
    case rejected(Int, String)

    public var errorDescription: String? {
        switch self {
        case .invalidServerURL: "Invalid SmartCore server URL"
        case .unexpectedResponse: "SmartCore returned an invalid response"
        case let .rejected(status, detail): "SmartCore rejected the request (\(status)): \(detail)"
        }
    }
}

private struct Envelope<T: Decodable>: Decodable {
    let ok: Bool
    let data: T
}

private struct PairPayload: Decodable {
    let stat: String
}

private struct DevicePayload: Decodable {
    let deviceId: String
    let deviceName: String
}

private struct ActivationPayload: Decodable {
    let device: DevicePayload
    let deviceToken: String
}

private struct AcceptedPayload: Decodable {
    let acceptedBucketStarts: [Date]
}

public struct ActivatedDevice: Sendable {
    public let configuration: MonitorConfiguration
    public let token: String
}

private final class OriginRedirectDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    private func origin(_ url: URL?) -> (String, String, Int?)? {
        guard let url, let scheme = url.scheme?.lowercased(), let host = url.host?.lowercased() else { return nil }
        return (scheme, host, url.port)
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping (URLRequest?) -> Void
    ) {
        guard let destination = origin(request.url), let source = origin(task.originalRequest?.url) else {
            completionHandler(nil)
            return
        }
        completionHandler(destination == source ? request : nil)
    }
}

public final class SmartCoreClient: @unchecked Sendable {
    private let session: URLSession

    public init() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 10
        configuration.timeoutIntervalForResource = 20
        session = URLSession(configuration: configuration, delegate: OriginRedirectDelegate(), delegateQueue: nil)
    }

    public func claim(_ document: PairingDocument, deviceName: String) async throws {
        let _: Envelope<PairPayload> = try await request(
            base: document.serverUrl,
            path: "/api/device/pair/\(document.pairId)/claim",
            method: "POST",
            body: ["claimCode": document.claimCode, "deviceName": deviceName]
        )
    }

    public func pairingStatus(_ document: PairingDocument) async throws -> String {
        let code = document.claimCode.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        let envelope: Envelope<PairPayload> = try await request(
            base: document.serverUrl,
            path: "/api/device/pair/\(document.pairId)/status?claimCode=\(code)",
            method: "GET",
            body: Optional<String>.none
        )
        return envelope.data.stat
    }

    public func activate(_ document: PairingDocument) async throws -> ActivatedDevice {
        let envelope: Envelope<ActivationPayload> = try await request(
            base: document.serverUrl,
            path: "/api/device/pair/\(document.pairId)/activate",
            method: "POST",
            body: ["claimCode": document.claimCode]
        )
        return ActivatedDevice(
            configuration: MonitorConfiguration(
                serverUrl: document.serverUrl,
                deviceId: envelope.data.device.deviceId,
                deviceName: envelope.data.device.deviceName
            ),
            token: envelope.data.deviceToken
        )
    }

    public func upload(
        buckets: [ActivityBucket],
        configuration: MonitorConfiguration,
        token: String
    ) async throws -> [Date] {
        let envelope: Envelope<AcceptedPayload> = try await request(
            base: configuration.serverUrl,
            path: "/api/computer/activity/batch",
            method: "POST",
            body: ActivityBatch(buckets: buckets),
            token: token
        )
        return envelope.data.acceptedBucketStarts
    }

    public func heartbeat(
        _ heartbeat: MonitorHeartbeat,
        configuration: MonitorConfiguration,
        token: String
    ) async throws {
        let _: Envelope<EmptyPayload> = try await request(
            base: configuration.serverUrl,
            path: "/api/computer/heartbeat",
            method: "POST",
            body: heartbeat,
            token: token
        )
    }

    private struct EmptyPayload: Decodable {}

    private func request<T: Decodable, B: Encodable>(
        base: String,
        path: String,
        method: String,
        body: B?,
        token: String? = nil
    ) async throws -> T {
        guard let baseURL = URL(string: base), ["http", "https"].contains(baseURL.scheme?.lowercased() ?? ""),
              let url = URL(string: path, relativeTo: baseURL)?.absoluteURL,
              url.host == baseURL.host
        else { throw SmartCoreClientError.invalidServerURL }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token { request.setValue(token, forHTTPHeaderField: "X-SmartCore-Device-Token") }
        if let body { request.httpBody = try MonitorCoding.encoder().encode(body) }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw SmartCoreClientError.unexpectedResponse }
        guard (200 ..< 300).contains(http.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String ?? "request failed"
            throw SmartCoreClientError.rejected(http.statusCode, detail)
        }
        do { return try MonitorCoding.decoder().decode(T.self, from: data) }
        catch { throw SmartCoreClientError.unexpectedResponse }
    }
}
