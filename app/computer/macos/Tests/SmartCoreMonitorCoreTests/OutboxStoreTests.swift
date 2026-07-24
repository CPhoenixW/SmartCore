import Foundation
import Testing
@testable import SmartCoreMonitorCore

@Suite struct OutboxStoreTests {
    @Test func persistenceAcknowledgementAndDeviceIsolation() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let path = directory.appendingPathComponent("outbox.sqlite")
        let first = makeBucket(at: Date(timeIntervalSince1970: 1_704_067_200))
        let second = makeBucket(at: Date(timeIntervalSince1970: 1_704_067_260))

        do {
            let store = try OutboxStore(path: path)
            try store.enqueue([first], deviceId: "old-device")
            try store.enqueue([second], deviceId: "new-device")
            #expect(try store.count(deviceId: "old-device") == 1)
            #expect(try store.count(deviceId: "new-device") == 1)
            #expect(try store.pending(deviceId: "new-device") == [second])
            try store.acknowledge(deviceId: "new-device", bucketStarts: [second.bucketStart])
            #expect(try store.count(deviceId: "new-device") == 0)
            #expect(try store.count(deviceId: "old-device") == 1)
        }

        let reopened = try OutboxStore(path: path)
        #expect(try reopened.pending(deviceId: "old-device") == [first])
    }

    @Test func configurationUsesDeviceScopedKeychainAccount() {
        let first = MonitorConfiguration(serverUrl: "https://smartcore.test", deviceId: "one", deviceName: "Mac")
        let second = MonitorConfiguration(serverUrl: "https://smartcore.test", deviceId: "two", deviceName: "Mac")
        #expect(first.keychainAccount != second.keychainAccount)
    }

    private func makeBucket(at date: Date) -> ActivityBucket {
        let context = ActivityContext(bundleId: "com.apple.Terminal", appName: "Terminal", windowTitle: "shell", titleRedacted: false)
        return ActivityBucket(
            bucketStart: date,
            timezone: "UTC",
            sessionId: "session",
            coveredSeconds: 60,
            switchCount: 0,
            slices: [ActivitySlice(state: .active, seconds: 60, context: context)]
        )
    }
}
