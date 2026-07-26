import Foundation
import Testing
@testable import SmartCoreMonitorCore

@Suite struct ActivityEngineTests {
    private let utc = TimeZone(secondsFromGMT: 0)!

    @Test func objectiveStateUsesAnyInputIdleDurationAndPriority() {
        #expect(ActivityStateResolver.resolve(paused: false, sleeping: false, locked: false, idleSeconds: 119) == .active)
        #expect(ActivityStateResolver.resolve(paused: false, sleeping: false, locked: false, idleSeconds: 120) == .idle)
        #expect(ActivityStateResolver.resolve(paused: false, sleeping: false, locked: true, idleSeconds: 0) == .locked)
        #expect(ActivityStateResolver.resolve(paused: false, sleeping: true, locked: true, idleSeconds: 0) == .sleeping)
        #expect(ActivityStateResolver.resolve(paused: true, sleeping: true, locked: true, idleSeconds: 0) == .paused)
    }

    @Test func sessionContinuesThroughShortIdleAndEndsAtBoundary() {
        var tracker = SessionTracker()
        let start = Date(timeIntervalSince1970: 1_700_000_000)
        let first = tracker.update(state: .active, at: start)
        #expect(first != nil)
        #expect(tracker.update(state: .idle, at: start.addingTimeInterval(599)) == first)
        #expect(tracker.update(state: .idle, at: start.addingTimeInterval(600)) == nil)

        let second = tracker.update(state: .active, at: start.addingTimeInterval(601))
        #expect(second != nil)
        #expect(second != first)
        #expect(tracker.update(state: .locked, at: start.addingTimeInterval(602)) == nil)
    }

    @Test func aggregatorSplitsMinutesAndCapsCoverage() throws {
        var aggregator = ActivityAggregator(timeZone: utc)
        let start = Date(timeIntervalSince1970: 1_704_067_258)
        let context = ActivityContext(bundleId: "com.apple.Terminal", appName: "Terminal")
        let completed = aggregator.record(state: .active, context: context, from: start, to: start.addingTimeInterval(65))
        #expect(completed.count == 2)
        #expect(try #require(completed.first).coveredSeconds == 2)
        #expect(try #require(completed.last).coveredSeconds == 60)

        let flushed = aggregator.flush(before: start.addingTimeInterval(122))
        #expect(flushed.count == 1)
        let bucket = try #require(flushed.first)
        #expect(bucket.coveredSeconds == 3)
        #expect((completed + flushed).map(\.coveredSeconds).reduce(0, +) == 65)
        #expect((completed + flushed).allSatisfy { $0.slices.map(\.seconds).reduce(0, +) <= 60 })
    }

    @Test func aggregatorCountsContextSwitches() throws {
        var aggregator = ActivityAggregator(timeZone: utc)
        let start = Date(timeIntervalSince1970: 1_704_067_200)
        let first = ActivityContext(bundleId: "a", appName: "A")
        let sameApp = ActivityContext(bundleId: "a", appName: "A")
        let second = ActivityContext(bundleId: "b", appName: "B")
        #expect(aggregator.record(state: .active, context: first, from: start, to: start.addingTimeInterval(5)).isEmpty)
        #expect(aggregator.record(state: .active, context: sameApp, from: start.addingTimeInterval(5), to: start.addingTimeInterval(10)).isEmpty)
        #expect(aggregator.record(state: .active, context: second, from: start.addingTimeInterval(10), to: start.addingTimeInterval(15)).isEmpty)
        let bucket = try #require(aggregator.flush(before: start.addingTimeInterval(61)).first)
        #expect(bucket.switchCount == 1)
    }

    @Test func nonActiveSlicesDoNotCarryWindowContext() throws {
        var aggregator = ActivityAggregator(timeZone: utc)
        let start = Date(timeIntervalSince1970: 1_704_067_200)
        let context = ActivityContext(bundleId: "com.example.Reader", appName: "Reader", windowTitle: "Notes")

        #expect(aggregator.record(state: .idle, context: context, from: start, to: start.addingTimeInterval(10)).isEmpty)
        let bucket = try #require(aggregator.flush(before: start.addingTimeInterval(61)).first)
        let slice = try #require(bucket.slices.first)
        #expect(slice.state == .idle)
        #expect(slice.appName == nil)
        #expect(slice.windowTitle == nil)
    }

    @Test func retryBackoffResetsAfterSuccess() {
        var backoff = RetryBackoff()
        #expect(backoff.failed() == 5)
        #expect(backoff.failed() == 10)
        backoff.succeeded()
        #expect(backoff.failed() == 5)
    }
}
