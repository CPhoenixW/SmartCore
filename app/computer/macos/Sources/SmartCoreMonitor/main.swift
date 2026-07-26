import AppKit
import ApplicationServices
import CoreGraphics
import Darwin
import SmartCoreMonitorCore

private let configurationChangedNotification = Notification.Name("com.smartcore.monitor.configurationChanged")
private let anyInputEventType = CGEventType(rawValue: UInt32.max)!
private let structuredContextPreference = "collectStructuredContext"
private let sampleInterval: TimeInterval = 20

@main
struct SmartCoreMonitorMain {
    @MainActor
    static func main() {
        switch CommandLine.arguments.dropFirst().first {
        case "pair":
            pairFromStandardInput()
        case "status":
            printStatus()
        case "migrate-token":
            migrateLegacyToken()
        case "structured-context":
            configureStructuredContext()
        case "run", nil:
            runAgent()
        default:
            fputs("Usage: SmartCoreMonitor [run|pair|status|migrate-token|structured-context on|off|status]\n", stderr)
            exit(EXIT_FAILURE)
        }
    }

    @MainActor
    private static func runAgent() {
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        let delegate = MonitorAgentDelegate()
        app.delegate = delegate
        app.run()
    }

    private static func pairFromStandardInput() -> Never {
        let data = FileHandle.standardInput.readDataToEndOfFile()
        guard let document = try? JSONDecoder().decode(PairingDocument.self, from: data) else {
            fputs("Pairing JSON must be provided on standard input.\n", stderr)
            exit(EXIT_FAILURE)
        }
        Task {
            do {
                let client = SmartCoreClient()
                try await client.claim(document, deviceName: Host.current().localizedName ?? "Mac")
                print("Pairing claimed. Confirm it in SmartCore.")
                for _ in 0 ..< 200 {
                    if try await client.pairingStatus(document) == "userConfirmed" {
                        let activated = try await client.activate(document)
                        try FileTokenStorage().write(
                            activated.token,
                            account: activated.configuration.keychainAccount
                        )
                        try ConfigurationStore().save(activated.configuration)
                        DistributedNotificationCenter.default().post(
                            name: configurationChangedNotification,
                            object: nil
                        )
                        print("Paired \(activated.configuration.deviceName).")
                        exit(EXIT_SUCCESS)
                    }
                    try await Task.sleep(for: .seconds(3))
                }
                fputs("Pairing timed out.\n", stderr)
            } catch {
                fputs("Pairing failed: \(error.localizedDescription)\n", stderr)
            }
            exit(EXIT_FAILURE)
        }
        dispatchMain()
    }

    private static func printStatus() {
        guard let configuration = ConfigurationStore().load() else {
            print("not paired")
            return
        }
        let hasToken = ((try? FileTokenStorage().read(account: configuration.keychainAccount)) ?? nil) != nil
        let structured = UserDefaults.standard.bool(forKey: structuredContextPreference)
        print("device=\(configuration.deviceName) id=\(configuration.deviceId) token=\(hasToken ? "ready" : "missing") accessibility=\(AXIsProcessTrusted() ? "granted" : "missing") structuredContext=\(structured ? "on" : "off")")
    }

    private static func configureStructuredContext() {
        let value = CommandLine.arguments.dropFirst(2).first ?? "status"
        switch value {
        case "on", "off":
            UserDefaults.standard.set(value == "on", forKey: structuredContextPreference)
            DistributedNotificationCenter.default().post(name: configurationChangedNotification, object: nil)
            print("Structured context collection is \(value).")
        case "status":
            print(UserDefaults.standard.bool(forKey: structuredContextPreference) ? "on" : "off")
        default:
            fputs("Usage: SmartCoreMonitor structured-context on|off|status\n", stderr)
            exit(EXIT_FAILURE)
        }
    }

    private static func migrateLegacyToken() {
        guard let configuration = ConfigurationStore().load() else {
            fputs("No paired device configuration was found.\n", stderr)
            exit(EXIT_FAILURE)
        }
        do {
            if try FileTokenStorage().read(account: configuration.keychainAccount) != nil {
                print("Token storage is ready.")
                return
            }
            guard let token = try KeychainTokenStorage().read(account: configuration.keychainAccount) else {
                fputs("No legacy Keychain token was found.\n", stderr)
                exit(EXIT_FAILURE)
            }
            try FileTokenStorage().write(token, account: configuration.keychainAccount)
            print("Legacy token migrated.")
        } catch {
            fputs("Token migration failed: \(error.localizedDescription)\n", stderr)
            exit(EXIT_FAILURE)
        }
    }
}

@MainActor
final class MonitorAgentDelegate: NSObject, NSApplicationDelegate {
    private let configurationStore = ConfigurationStore()
    private let tokenStore = FileTokenStorage()
    private let client = SmartCoreClient()
    private var outbox: OutboxStore?
    private var configuration: MonitorConfiguration?
    private var token: String?
    private var aggregator = ActivityAggregator()
    private var timer: Timer?
    private var lastSampleAt = Date()
    private var nextSyncAt = Date.distantPast
    private var retryBackoff = RetryBackoff()
    private var locked = false
    private var sleepingSince: Date?
    private var currentState: ActivityState = .idle
    private var currentContext: ActivityContext?
    private var syncing = false
    private var accessibilityGranted = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("SmartCoreMonitor", isDirectory: true)
            outbox = try OutboxStore(path: directory.appendingPathComponent("outbox.sqlite"))
            try outbox?.prune()
        } catch {
            fputs("SmartCoreMonitor: local queue unavailable: \(error.localizedDescription)\n", stderr)
        }
        reloadConfiguration()
        let accessibilityOptions = [
            "AXTrustedCheckOptionPrompt": true,
        ] as CFDictionary
        accessibilityGranted = AXIsProcessTrustedWithOptions(accessibilityOptions)
        installObservers()
        timer = Timer.scheduledTimer(withTimeInterval: sampleInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.sample() }
        }
        sample()
    }

    private func reloadConfiguration() {
        configuration = configurationStore.load()
        token = configuration.flatMap { try? tokenStore.read(account: $0.keychainAccount) }
        lastSampleAt = Date()
        nextSyncAt = .distantPast
    }

    private func installObservers() {
        let workspace = NSWorkspace.shared.notificationCenter
        workspace.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.beginSleep() }
        }
        workspace.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.endSleep() }
        }
        DistributedNotificationCenter.default().addObserver(
            forName: .init("com.apple.screenIsLocked"), object: nil, queue: .main
        ) { [weak self] _ in Task { @MainActor in self?.beginLock() } }
        DistributedNotificationCenter.default().addObserver(
            forName: .init("com.apple.screenIsUnlocked"), object: nil, queue: .main
        ) { [weak self] _ in Task { @MainActor in self?.endLock() } }
        DistributedNotificationCenter.default().addObserver(
            forName: configurationChangedNotification, object: nil, queue: .main
        ) { [weak self] _ in Task { @MainActor in self?.reloadConfiguration() } }
    }

    private func sample() {
        guard configuration != nil, token != nil else { return }
        let now = Date()
        let idleSeconds = CGEventSource.secondsSinceLastEventType(
            .combinedSessionState,
            eventType: anyInputEventType
        )
        let state = ActivityStateResolver.resolve(
            paused: false,
            sleeping: sleepingSince != nil,
            locked: locked,
            idleSeconds: idleSeconds
        )
        let context = state == .active ? frontmostContext() : nil
        let changed = state != currentState || context != currentContext
        capture(state: state, context: context, to: now)
        if changed { nextSyncAt = .distantPast }
        if now >= nextSyncAt { Task { await synchronize() } }
    }

    private func capture(state: ActivityState, context: ActivityContext?, to date: Date) {
        guard let configuration, let outbox else { lastSampleAt = date; return }
        let buckets = aggregator.record(state: state, context: context, from: lastSampleAt, to: date)
        if !buckets.isEmpty { try? outbox.enqueue(buckets, deviceId: configuration.deviceId) }
        lastSampleAt = date
        currentState = state
        currentContext = context
    }

    private func beginSleep() {
        let now = Date()
        capture(state: currentState, context: currentContext, to: now)
        sleepingSince = now
    }

    private func endSleep() {
        let now = Date()
        capture(state: .sleeping, context: nil, to: now)
        sleepingSince = nil
        nextSyncAt = .distantPast
    }

    private func beginLock() {
        guard !locked else { return }
        let now = Date()
        capture(state: currentState, context: currentContext, to: now)
        locked = true
        nextSyncAt = .distantPast
    }

    private func endLock() {
        guard locked else { return }
        let now = Date()
        capture(state: .locked, context: nil, to: now)
        locked = false
        nextSyncAt = .distantPast
    }

    private func frontmostContext() -> ActivityContext? {
        guard let app = NSWorkspace.shared.frontmostApplication else { return nil }
        let bundle = String((app.bundleIdentifier ?? "unknown.\(app.processIdentifier)").prefix(300))
        let name = String((app.localizedName ?? "Unknown").prefix(200))
        accessibilityGranted = AXIsProcessTrusted()
        var title: String?
        var documentReference: String?
        if accessibilityGranted {
            let application = AXUIElementCreateApplication(app.processIdentifier)
            var focusedValue: CFTypeRef?
            if AXUIElementCopyAttributeValue(
                application,
                kAXFocusedWindowAttribute as CFString,
                &focusedValue
            ) == .success, let focusedValue {
                let window = focusedValue as! AXUIElement
                title = accessibilityString(window, attribute: kAXTitleAttribute)
                documentReference = accessibilityString(window, attribute: kAXDocumentAttribute)
            }
        }
        return ActivityContextSanitizer.sanitize(
            RawActivityContext(
                bundleId: bundle,
                appName: name,
                windowTitle: title,
                documentReference: documentReference
            ),
            includeStructuredContext: UserDefaults.standard.bool(forKey: structuredContextPreference)
        )
    }

    private func accessibilityString(_ element: AXUIElement, attribute: String) -> String? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success else {
            return nil
        }
        return value as? String
    }

    private func synchronize() async {
        guard !syncing, let configuration, let token, let outbox else { return }
        syncing = true
        defer { syncing = false }
        do {
            let buckets = try outbox.pending(deviceId: configuration.deviceId)
            if !buckets.isEmpty {
                let accepted = try await client.upload(buckets: buckets, configuration: configuration, token: token)
                try outbox.acknowledge(deviceId: configuration.deviceId, bucketStarts: accepted)
            }
            try await client.heartbeat(
                MonitorHeartbeat(
                    currentState: currentState,
                    observedAt: Date(),
                    currentAppName: currentContext?.appName,
                    currentWindowTitle: currentContext?.windowTitle,
                    appVersion: "0.3.0",
                    osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
                    accessibilityGranted: accessibilityGranted,
                    queueDepth: try outbox.count(deviceId: configuration.deviceId)
                ),
                configuration: configuration,
                token: token
            )
            retryBackoff.succeeded()
            nextSyncAt = Date().addingTimeInterval(30)
        } catch {
            nextSyncAt = Date().addingTimeInterval(retryBackoff.failed())
            fputs("SmartCoreMonitor: synchronization pending: \(error.localizedDescription)\n", stderr)
        }
    }
}
