import Foundation

public enum ActivityState: String, Codable, Sendable {
    case active
    case idle
    case locked
    case sleeping
    case paused
}

public struct ActivityContext: Codable, Hashable, Sendable {
    public let bundleId: String
    public let appName: String
    public let windowTitle: String?
    public let titleRedacted: Bool

    public init(bundleId: String, appName: String, windowTitle: String?, titleRedacted: Bool) {
        self.bundleId = bundleId
        self.appName = appName
        self.windowTitle = windowTitle
        self.titleRedacted = titleRedacted
    }
}

public struct ActivitySlice: Codable, Equatable, Sendable {
    public let state: ActivityState
    public var seconds: Int
    public let bundleId: String?
    public let appName: String?
    public let windowTitle: String?
    public let titleRedacted: Bool

    public init(state: ActivityState, seconds: Int, context: ActivityContext?) {
        self.state = state
        self.seconds = seconds
        bundleId = context?.bundleId
        appName = context?.appName
        windowTitle = context?.windowTitle
        titleRedacted = context?.titleRedacted ?? false
    }
}

public struct ActivityBucket: Codable, Equatable, Sendable {
    public let bucketStart: Date
    public let timezone: String
    public let sessionId: String?
    public let coveredSeconds: Int
    public let switchCount: Int
    public let slices: [ActivitySlice]

    public init(
        bucketStart: Date,
        timezone: String,
        sessionId: String?,
        coveredSeconds: Int,
        switchCount: Int,
        slices: [ActivitySlice]
    ) {
        self.bucketStart = bucketStart
        self.timezone = timezone
        self.sessionId = sessionId
        self.coveredSeconds = coveredSeconds
        self.switchCount = switchCount
        self.slices = slices
    }
}

public struct ActivityBatch: Codable, Sendable {
    public let schemaVersion: Int
    public let buckets: [ActivityBucket]

    public init(buckets: [ActivityBucket]) {
        schemaVersion = 1
        self.buckets = buckets
    }
}

public struct MonitorHeartbeat: Codable, Sendable {
    public let currentState: ActivityState
    public let observedAt: Date
    public let currentAppName: String?
    public let currentWindowTitle: String?
    public let appVersion: String
    public let osVersion: String
    public let accessibilityGranted: Bool
    public let paused: Bool
    public let queueDepth: Int

    public init(
        currentState: ActivityState,
        observedAt: Date,
        currentAppName: String?,
        currentWindowTitle: String?,
        appVersion: String,
        osVersion: String,
        accessibilityGranted: Bool,
        paused: Bool,
        queueDepth: Int
    ) {
        self.currentState = currentState
        self.observedAt = observedAt
        self.currentAppName = currentAppName
        self.currentWindowTitle = currentWindowTitle
        self.appVersion = appVersion
        self.osVersion = osVersion
        self.accessibilityGranted = accessibilityGranted
        self.paused = paused
        self.queueDepth = queueDepth
    }
}

public enum MonitorCoding {
    public static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }

    public static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}
