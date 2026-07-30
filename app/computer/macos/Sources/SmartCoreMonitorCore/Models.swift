import Foundation

public enum ActivityState: String, Codable, Sendable {
    case active
    case idle
    case locked
    case sleeping
    case paused
}

public enum ActivityContextKind: String, Codable, Sendable {
    case application
    case browser
    case ide
    case document
}

public struct ActivityContext: Codable, Hashable, Sendable {
    public let bundleId: String
    public let appName: String
    public let windowTitle: String?
    public let contextKind: ActivityContextKind?
    public let domain: String?
    public let workspace: String?
    public let documentName: String?
    public let titleRedacted: Bool

    public init(
        bundleId: String,
        appName: String,
        windowTitle: String? = nil,
        contextKind: ActivityContextKind? = nil,
        domain: String? = nil,
        workspace: String? = nil,
        documentName: String? = nil,
        titleRedacted: Bool = false
    ) {
        self.bundleId = bundleId
        self.appName = appName
        self.windowTitle = windowTitle
        self.contextKind = contextKind
        self.domain = domain
        self.workspace = workspace
        self.documentName = documentName
        self.titleRedacted = titleRedacted
    }
}

public struct ActivitySlice: Codable, Equatable, Sendable {
    public let state: ActivityState
    public var seconds: Int
    public let bundleId: String?
    public let appName: String?
    public let windowTitle: String?
    public let contextKind: ActivityContextKind?
    public let domain: String?
    public let workspace: String?
    public let documentName: String?
    public let titleRedacted: Bool

    public init(state: ActivityState, seconds: Int, context: ActivityContext?) {
        self.state = state
        self.seconds = seconds
        bundleId = context?.bundleId
        appName = context?.appName
        windowTitle = context?.windowTitle
        contextKind = context?.contextKind
        domain = context?.domain
        workspace = context?.workspace
        documentName = context?.documentName
        titleRedacted = context?.titleRedacted ?? false
    }

    private enum CodingKeys: String, CodingKey {
        case state, seconds, bundleId, appName, windowTitle, contextKind, domain, workspace, documentName, titleRedacted
    }

    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        state = try values.decode(ActivityState.self, forKey: .state)
        seconds = try values.decode(Int.self, forKey: .seconds)
        bundleId = try values.decodeIfPresent(String.self, forKey: .bundleId)
        appName = try values.decodeIfPresent(String.self, forKey: .appName)
        windowTitle = try values.decodeIfPresent(String.self, forKey: .windowTitle)
        contextKind = try values.decodeIfPresent(ActivityContextKind.self, forKey: .contextKind)
        domain = try values.decodeIfPresent(String.self, forKey: .domain)
        workspace = try values.decodeIfPresent(String.self, forKey: .workspace)
        documentName = try values.decodeIfPresent(String.self, forKey: .documentName)
        titleRedacted = try values.decodeIfPresent(Bool.self, forKey: .titleRedacted) ?? false
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
    public let queueDepth: Int

    public init(
        currentState: ActivityState,
        observedAt: Date,
        currentAppName: String?,
        currentWindowTitle: String?,
        appVersion: String,
        osVersion: String,
        accessibilityGranted: Bool,
        queueDepth: Int
    ) {
        self.currentState = currentState
        self.observedAt = observedAt
        self.currentAppName = currentAppName
        self.currentWindowTitle = currentWindowTitle
        self.appVersion = appVersion
        self.osVersion = osVersion
        self.accessibilityGranted = accessibilityGranted
        self.queueDepth = queueDepth
    }
}

public enum CodexWorkStatus: String, Codable, Sendable {
    case completed
    case partial
    case inProgress = "in_progress"
}

public struct CodexWorkEvidence: Codable, Equatable, Sendable {
    public let commits: [String]
    public let pullRequests: [String]
    public let tests: [String]

    public init(
        commits: [String] = [],
        pullRequests: [String] = [],
        tests: [String] = []
    ) {
        self.commits = commits
        self.pullRequests = pullRequests
        self.tests = tests
    }
}

public struct CodexWorkReport: Codable, Equatable, Sendable {
    public let sourceTaskId: String
    public let reportDate: String
    public let timezone: String
    public let projectKey: String
    public let projectName: String
    public let title: String
    public let summary: String
    public let status: CodexWorkStatus
    public let startedAt: String?
    public let endedAt: String?
    public let evidence: CodexWorkEvidence

    public init(
        sourceTaskId: String,
        reportDate: String,
        timezone: String,
        projectKey: String,
        projectName: String,
        title: String,
        summary: String,
        status: CodexWorkStatus,
        startedAt: String? = nil,
        endedAt: String? = nil,
        evidence: CodexWorkEvidence = .init()
    ) {
        self.sourceTaskId = sourceTaskId
        self.reportDate = reportDate
        self.timezone = timezone
        self.projectKey = projectKey
        self.projectName = projectName
        self.title = title
        self.summary = summary
        self.status = status
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.evidence = evidence
    }
}

public struct CodexWorkReportBatch: Codable, Equatable, Sendable {
    public let reports: [CodexWorkReport]

    public init(reports: [CodexWorkReport]) {
        self.reports = reports
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
