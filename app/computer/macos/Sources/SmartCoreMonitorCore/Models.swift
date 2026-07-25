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

    public init(bundleId: String, appName: String) {
        self.bundleId = bundleId
        self.appName = appName
    }
}

public struct ActivitySlice: Codable, Equatable, Sendable {
    public let state: ActivityState
    public var seconds: Int
    public let bundleId: String?
    public let appName: String?

    public init(state: ActivityState, seconds: Int, context: ActivityContext?) {
        self.state = state
        self.seconds = seconds
        bundleId = context?.bundleId
        appName = context?.appName
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
    public let appVersion: String
    public let osVersion: String
    public let queueDepth: Int

    public init(
        currentState: ActivityState,
        observedAt: Date,
        currentAppName: String?,
        appVersion: String,
        osVersion: String,
        queueDepth: Int
    ) {
        self.currentState = currentState
        self.observedAt = observedAt
        self.currentAppName = currentAppName
        self.appVersion = appVersion
        self.osVersion = osVersion
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
