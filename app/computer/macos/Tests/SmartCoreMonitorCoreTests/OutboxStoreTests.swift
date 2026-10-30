import Foundation
import Testing
@testable import SmartCoreMonitorCore

@Suite struct OutboxStoreTests {
    @Test func legacyQueuedSlicesDecodeWithNewContextFieldsEmpty() throws {
        let json = #"{"state":"active","seconds":5,"bundleId":"com.example.Editor","appName":"Editor"}"#.data(using: .utf8)!
        let slice = try MonitorCoding.decoder().decode(ActivitySlice.self, from: json)

        #expect(slice.windowTitle == nil)
        #expect(slice.contextKind == nil)
        #expect(slice.titleRedacted == false)
    }

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

    @Test func pendingSanitizesLegacyPathMetadataWithoutDroppingTime() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let path = directory.appendingPathComponent("outbox.sqlite")
        let context = ActivityContext(
            bundleId: "com.apple.Terminal",
            appName: "Terminal",
            contextKind: .document,
            workspace: "/",
            documentName: "/Users/person/SmartCore/service.py"
        )
        let bucket = ActivityBucket(
            bucketStart: Date(timeIntervalSince1970: 1_704_067_200),
            timezone: "UTC",
            sessionId: "session",
            coveredSeconds: 60,
            switchCount: 0,
            slices: [ActivitySlice(state: .active, seconds: 60, context: context)]
        )

        let store = try OutboxStore(path: path)
        try store.enqueue([bucket], deviceId: "device")
        let pending = try store.pending(deviceId: "device")

        #expect(pending[0].coveredSeconds == 60)
        #expect(pending[0].slices[0].workspace == nil)
        #expect(pending[0].slices[0].documentName == "service.py")
    }

    @Test func pendingRemovesAllRedactedStructuredMetadata() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let context = ActivityContext(
            bundleId: "com.example.Auth",
            appName: "Auth",
            windowTitle: "sign in",
            contextKind: .application,
            domain: "accounts.example.test",
            workspace: "vault",
            documentName: "secret.txt",
            titleRedacted: true
        )
        let bucket = ActivityBucket(
            bucketStart: Date(timeIntervalSince1970: 1_704_067_200),
            timezone: "UTC",
            sessionId: "session",
            coveredSeconds: 60,
            switchCount: 0,
            slices: [ActivitySlice(state: .active, seconds: 60, context: context)]
        )

        let store = try OutboxStore(path: directory.appendingPathComponent("outbox.sqlite"))
        try store.enqueue([bucket], deviceId: "device")
        let slice = try #require(try store.pending(deviceId: "device").first?.slices.first)

        #expect(slice.titleRedacted)
        #expect(slice.windowTitle == nil)
        #expect(slice.contextKind == nil)
        #expect(slice.domain == nil)
        #expect(slice.workspace == nil)
        #expect(slice.documentName == nil)
    }

    @Test func configurationUsesDeviceScopedKeychainAccount() {
        let first = MonitorConfiguration(serverUrl: "https://smartcore.test", deviceId: "one", deviceName: "Mac")
        let second = MonitorConfiguration(serverUrl: "https://smartcore.test", deviceId: "two", deviceName: "Mac")
        #expect(first.keychainAccount != second.keychainAccount)
    }

    @Test func fileTokenStorageUsesOwnerOnlyPermissions() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let storage = FileTokenStorage(directory: directory)
        try storage.write("secret", account: "device")
        #expect(try storage.read(account: "device") == "secret")
        let files = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        let attributes = try FileManager.default.attributesOfItem(atPath: try #require(files.first).path)
        #expect(attributes[.posixPermissions] as? Int == 0o600)
    }

    private func makeBucket(at date: Date) -> ActivityBucket {
        let context = ActivityContext(bundleId: "com.apple.Terminal", appName: "Terminal")
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
