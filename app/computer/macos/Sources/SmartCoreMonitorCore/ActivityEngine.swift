import Foundation

public enum ActivityStateResolver {
    public static let defaultIdleThreshold: TimeInterval = 120

    public static func resolve(
        paused: Bool,
        sleeping: Bool,
        locked: Bool,
        idleSeconds: TimeInterval,
        idleThreshold: TimeInterval = defaultIdleThreshold
    ) -> ActivityState {
        if paused { return .paused }
        if sleeping { return .sleeping }
        if locked { return .locked }
        if idleSeconds >= idleThreshold { return .idle }
        return .active
    }
}

public struct SessionTracker: Sendable {
    public let idleBoundary: TimeInterval
    public private(set) var sessionId: String?
    public private(set) var lastActiveAt: Date?

    public init(idleBoundary: TimeInterval = 600) {
        self.idleBoundary = idleBoundary
    }

    public mutating func update(state: ActivityState, at date: Date) -> String? {
        switch state {
        case .locked, .sleeping, .paused:
            sessionId = nil
        case .idle:
            if let lastActiveAt, date.timeIntervalSince(lastActiveAt) >= idleBoundary {
                sessionId = nil
            }
        case .active:
            if sessionId == nil || lastActiveAt.map({ date.timeIntervalSince($0) >= idleBoundary }) == true {
                sessionId = UUID().uuidString.lowercased()
            }
            lastActiveAt = date
        }
        return sessionId
    }
}

private struct SliceKey: Hashable {
    let state: ActivityState
    let context: ActivityContext?
}

private struct PendingBucket {
    let start: Date
    let timezone: String
    var sessionId: String?
    var slices: [SliceKey: Int] = [:]
    var coveredSeconds = 0
    var switchCount = 0
    var lastBundleId: String?

    mutating func add(state: ActivityState, context: ActivityContext?, seconds: Int, sessionId: String?) {
        let boundedSeconds = min(seconds, max(0, 60 - coveredSeconds))
        guard boundedSeconds > 0 else { return }
        let activeContext = state == .active ? context : nil
        slices[SliceKey(state: state, context: activeContext), default: 0] += boundedSeconds
        coveredSeconds += boundedSeconds
        self.sessionId = sessionId ?? self.sessionId
        if state == .active, let activeContext {
            if let lastBundleId, lastBundleId != activeContext.bundleId {
                switchCount += 1
            }
            lastBundleId = activeContext.bundleId
        }
    }

    func finalized() -> ActivityBucket {
        let values = slices.map { ActivitySlice(state: $0.key.state, seconds: $0.value, context: $0.key.context) }
            .sorted { lhs, rhs in
                if lhs.state.rawValue == rhs.state.rawValue { return (lhs.appName ?? "") < (rhs.appName ?? "") }
                return lhs.state.rawValue < rhs.state.rawValue
            }
        return ActivityBucket(
            bucketStart: start,
            timezone: timezone,
            sessionId: sessionId,
            coveredSeconds: coveredSeconds,
            switchCount: switchCount,
            slices: values
        )
    }
}

public struct ActivityAggregator: Sendable {
    private var pending: PendingBucket?
    private var tracker: SessionTracker
    private let calendar: Calendar

    public init(timeZone: TimeZone = .current, idleBoundary: TimeInterval = 600) {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        self.calendar = calendar
        tracker = SessionTracker(idleBoundary: idleBoundary)
    }

    public mutating func record(
        state: ActivityState,
        context: ActivityContext?,
        from start: Date,
        to end: Date
    ) -> [ActivityBucket] {
        guard end > start else { return [] }
        var completed: [ActivityBucket] = []
        var cursor = start
        while cursor < end {
            let minuteStart = calendar.dateInterval(of: .minute, for: cursor)!.start
            let minuteEnd = calendar.date(byAdding: .minute, value: 1, to: minuteStart)!
            let segmentEnd = min(end, minuteEnd)
            let seconds = max(1, Int(segmentEnd.timeIntervalSince(cursor).rounded()))
            if pending?.start != minuteStart {
                if let pending, pending.coveredSeconds > 0 { completed.append(pending.finalized()) }
                pending = PendingBucket(start: minuteStart, timezone: calendar.timeZone.identifier)
            }
            let session = tracker.update(state: state, at: segmentEnd)
            pending?.add(state: state, context: context, seconds: seconds, sessionId: session)
            cursor = segmentEnd
        }
        return completed
    }

    public mutating func flush(before date: Date = Date()) -> [ActivityBucket] {
        guard let pending else { return [] }
        let currentMinute = calendar.dateInterval(of: .minute, for: date)!.start
        guard pending.start < currentMinute else { return [] }
        self.pending = nil
        return pending.coveredSeconds > 0 ? [pending.finalized()] : []
    }
}

public struct RetryBackoff: Sendable {
    private var failures = 0

    public init() {}

    public mutating func succeeded() { failures = 0 }

    public mutating func failed() -> TimeInterval {
        failures += 1
        return min(300, pow(2, Double(min(failures, 8))) * 2.5)
    }
}
