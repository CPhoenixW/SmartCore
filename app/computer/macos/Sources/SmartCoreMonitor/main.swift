import AppKit
import ApplicationServices
import SmartCoreMonitorCore

@main
struct SmartCoreMonitorMain {
    @MainActor
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let delegate = MonitorAppDelegate()
        app.delegate = delegate
        app.run()
    }
}

@MainActor
final class MonitorAppDelegate: NSObject, NSApplicationDelegate {
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    private let configurationStore = ConfigurationStore()
    private let tokenStore = KeychainTokenStorage()
    private let client = SmartCoreClient()
    private let privacy = PrivacyFilter()
    private var outbox: OutboxStore?
    private var configuration: MonitorConfiguration?
    private var token: String?
    private var aggregator = ActivityAggregator()
    private var timer: Timer?
    private var lastSampleAt = Date()
    private var lastSyncAt = Date.distantPast
    private var nextSyncAt = Date.distantPast
    private var retryBackoff = RetryBackoff()
    private var paused = false
    private var locked = false
    private var sleepingSince: Date?
    private var currentState: ActivityState = .idle
    private var currentContext: ActivityContext?
    private var syncMessage = "Not paired"
    private var syncing = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("SmartCoreMonitor", isDirectory: true)
            outbox = try OutboxStore(path: directory.appendingPathComponent("outbox.sqlite"))
            try outbox?.prune()
        } catch {
            syncMessage = "Local queue unavailable"
        }
        configuration = configurationStore.load()
        if let configuration {
            token = try? tokenStore.read(account: configuration.keychainAccount)
            syncMessage = token == nil ? "Token missing" : "Ready"
        }
        installObservers()
        buildMenu()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.sample() }
        }
        sample()
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
    }

    private func sample() {
        guard configuration != nil, token != nil else { buildMenu(); return }
        let now = Date()
        let state: ActivityState
        let context: ActivityContext?
        if paused {
            state = .paused; context = nil
        } else if sleepingSince != nil {
            state = .sleeping; context = nil
        } else if locked {
            state = .locked; context = nil
        } else if CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .null) >= 300 {
            state = .idle; context = nil
        } else {
            state = .active; context = frontmostContext()
        }
        capture(state: state, context: context, to: now)
        if now >= nextSyncAt { Task { await synchronize() } }
        buildMenu()
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
    }

    private func beginLock() {
        guard !locked else { return }
        let now = Date()
        capture(state: currentState, context: currentContext, to: now)
        locked = true
    }

    private func endLock() {
        guard locked else { return }
        let now = Date()
        capture(state: .locked, context: nil, to: now)
        locked = false
    }

    private func frontmostContext() -> ActivityContext? {
        guard let app = NSWorkspace.shared.frontmostApplication else { return nil }
        let bundle = app.bundleIdentifier ?? "unknown.\(app.processIdentifier)"
        let name = app.localizedName ?? "Unknown"
        return privacy.context(bundleId: bundle, appName: name, title: windowTitle(pid: app.processIdentifier))
    }

    private func windowTitle(pid: pid_t) -> String? {
        guard AXIsProcessTrusted() else { return nil }
        let application = AXUIElementCreateApplication(pid)
        var window: CFTypeRef?
        guard AXUIElementCopyAttributeValue(application, kAXFocusedWindowAttribute as CFString, &window) == .success,
              let window else { return nil }
        var title: CFTypeRef?
        guard AXUIElementCopyAttributeValue(window as! AXUIElement, kAXTitleAttribute as CFString, &title) == .success else { return nil }
        return title as? String
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
            let heartbeat = MonitorHeartbeat(
                currentState: currentState,
                observedAt: Date(),
                currentAppName: currentContext?.appName,
                currentWindowTitle: currentContext?.windowTitle,
                appVersion: "0.1.0",
                osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
                accessibilityGranted: AXIsProcessTrusted(),
                paused: paused,
                queueDepth: try outbox.count(deviceId: configuration.deviceId)
            )
            try await client.heartbeat(heartbeat, configuration: configuration, token: token)
            retryBackoff.succeeded()
            lastSyncAt = Date()
            nextSyncAt = lastSyncAt.addingTimeInterval(60)
            syncMessage = "Synced"
        } catch {
            lastSyncAt = Date()
            nextSyncAt = lastSyncAt.addingTimeInterval(retryBackoff.failed())
            syncMessage = "Sync pending"
        }
        buildMenu()
    }

    private func buildMenu() {
        statusItem.button?.title = currentState == .active ? "SC Active" : "SC \(currentState.rawValue.capitalized)"
        let menu = NSMenu()
        let status = NSMenuItem(title: configuration?.deviceName ?? "SmartCore Monitor", action: nil, keyEquivalent: "")
        status.isEnabled = false
        menu.addItem(status)
        let context = NSMenuItem(title: currentContext?.appName ?? currentState.rawValue.capitalized, action: nil, keyEquivalent: "")
        context.isEnabled = false
        menu.addItem(context)
        let sync = NSMenuItem(title: syncMessage, action: nil, keyEquivalent: "")
        sync.isEnabled = false
        menu.addItem(sync)
        menu.addItem(.separator())
        menu.addItem(withTitle: paused ? "Resume" : "Pause", action: #selector(togglePause), keyEquivalent: "p").target = self
        menu.addItem(withTitle: "Pair Device...", action: #selector(pairDevice), keyEquivalent: "").target = self
        menu.addItem(withTitle: "Request Accessibility", action: #selector(requestAccessibility), keyEquivalent: "").target = self
        menu.addItem(withTitle: "Sync Now", action: #selector(syncNow), keyEquivalent: "s").target = self
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit", action: #selector(quit), keyEquivalent: "q").target = self
        statusItem.menu = menu
    }

    @objc private func togglePause() {
        let now = Date()
        capture(state: paused ? .paused : currentState, context: paused ? nil : currentContext, to: now)
        paused.toggle()
        sample()
    }
    @objc private func syncNow() {
        nextSyncAt = .distantPast
        Task { await synchronize() }
    }
    @objc private func requestAccessibility() {
        let options = ["AXTrustedCheckOptionPrompt": true] as CFDictionary
        AXIsProcessTrustedWithOptions(options)
    }

    @objc private func pairDevice() {
        let alert = NSAlert()
        alert.messageText = "Pair with SmartCore"
        alert.informativeText = "Paste the pairing JSON from the SmartCore device page."
        let input = NSTextField(frame: NSRect(x: 0, y: 0, width: 420, height: 24))
        input.placeholderString = "{\"serverUrl\":\"http://...\",\"pairId\":\"...\",\"claimCode\":\"...\"}"
        alert.accessoryView = input
        alert.addButton(withTitle: "Pair")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn,
              let data = input.stringValue.data(using: .utf8),
              let document = try? JSONDecoder().decode(PairingDocument.self, from: data)
        else { return }
        syncMessage = "Awaiting confirmation"
        buildMenu()
        Task { await completePairing(document) }
    }

    private func completePairing(_ document: PairingDocument) async {
        do {
            try await client.claim(document, deviceName: Host.current().localizedName ?? "Mac")
            for _ in 0 ..< 200 {
                if try await client.pairingStatus(document) == "userConfirmed" {
                    let activated = try await client.activate(document)
                    try tokenStore.write(activated.token, account: activated.configuration.keychainAccount)
                    try configurationStore.save(activated.configuration)
                    configuration = activated.configuration
                    token = activated.token
                    syncMessage = "Paired"
                    lastSampleAt = Date()
                    sample()
                    return
                }
                try await Task.sleep(for: .seconds(3))
            }
            syncMessage = "Pairing timed out"
        } catch {
            syncMessage = "Pairing failed"
        }
        buildMenu()
    }

    @objc private func quit() { NSApplication.shared.terminate(nil) }
}
