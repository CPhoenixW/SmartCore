import Foundation

public struct RawActivityContext: Sendable {
    public let bundleId: String
    public let appName: String
    public let windowTitle: String?
    public let documentReference: String?

    public init(bundleId: String, appName: String, windowTitle: String?, documentReference: String?) {
        self.bundleId = bundleId
        self.appName = appName
        self.windowTitle = windowTitle
        self.documentReference = documentReference
    }
}

public enum ChatGPTConversationTitlePolicy {
    private static let ignoredLabels: Set<String> = [
        "chatgpt", "new chat", "search", "settings", "send", "stop generating",
        "attach files", "voice mode", "start a new chat", "close", "back",
    ]

    public static func sanitize(_ value: String?, appName: String) -> String? {
        guard let value else { return nil }
        guard !value.contains("\n"), !value.contains("\r") else { return nil }
        let normalized = value.split(whereSeparator: \Character.isWhitespace).joined(separator: " ")
        guard !normalized.isEmpty,
              normalized.count <= 200,
              normalized.localizedCaseInsensitiveCompare(appName) != .orderedSame,
              !ignoredLabels.contains(normalized.lowercased()) else { return nil }
        return normalized
    }
}

public enum ActivityContextSanitizer {
    private static let sensitiveAppFragments = [
        "1password", "bitwarden", "dashlane", "lastpass", "keeper", "keepass",
        "passwords", "keychain", "securityagent", "authorizationhost", "loginwindow",
    ]
    private static let sensitiveTitleFragments = [
        "password", "passcode", "one-time code", "two-factor", "sign in", "banking",
        "payment", "密码", "验证码", "登录", "认证", "银行", "支付",
    ]
    private static let sensitiveDomainFragments = [
        "bank", "paypal.", "alipay.", "stripe.", "1password.", "bitwarden.", "account.apple.",
    ]
    private static let browserBundleFragments = ["safari", "chrome", "firefox", "edge", "arc", "brave", "opera"]
    private static let ideBundleFragments = ["xcode", "vscode", "jetbrains", "cursor", "zed", "sublimetext"]

    public static func sanitize(_ raw: RawActivityContext, includeStructuredContext: Bool) -> ActivityContext {
        let bundleId = bounded(normalized(raw.bundleId) ?? "unknown", length: 300)
        let appName = bounded(normalized(raw.appName) ?? "Unknown", length: 200)
        let rawTitle = boundedOptional(filteredTitle(raw.windowTitle, appName: appName), length: 300)
        let documentURL = raw.documentReference.flatMap(URL.init(string:))
        let domain = normalizedDomain(documentURL)
        let sensitive = containsFragment(bundleId, sensitiveAppFragments)
            || containsFragment(appName, sensitiveAppFragments)
            || containsFragment(rawTitle, sensitiveTitleFragments)
            || containsFragment(domain, sensitiveDomainFragments)

        if sensitive {
            return ActivityContext(bundleId: bundleId, appName: appName, titleRedacted: true)
        }

        guard includeStructuredContext else {
            return ActivityContext(bundleId: bundleId, appName: appName, windowTitle: rawTitle)
        }

        let bundle = bundleId.lowercased()
        let isBrowser = browserBundleFragments.contains(where: bundle.contains)
        let isIDE = ideBundleFragments.contains(where: bundle.contains)
        var kind: ActivityContextKind = .application
        var workspace: String?
        var documentName: String?
        if isBrowser {
            kind = .browser
        } else if documentURL?.isFileURL == true {
            kind = isIDE ? .ide : .document
            documentName = boundedOptional(normalized(documentURL?.lastPathComponent), length: 300)
            workspace = boundedOptional(normalized(documentURL?.deletingLastPathComponent().lastPathComponent), length: 300)
        } else if isIDE {
            kind = .ide
        }
        return ActivityContext(
            bundleId: bundleId,
            appName: appName,
            windowTitle: rawTitle,
            contextKind: kind,
            domain: isBrowser ? domain : nil,
            workspace: workspace,
            documentName: documentName
        )
    }

    private static func normalized(_ value: String?) -> String? {
        guard let value else { return nil }
        let result = value.split(whereSeparator: \Character.isWhitespace).joined(separator: " ")
        return result.isEmpty ? nil : result
    }

    private static func bounded(_ value: String, length: Int) -> String {
        String(value.prefix(length))
    }

    private static func boundedOptional(_ value: String?, length: Int) -> String? {
        value.map { bounded($0, length: length) }
    }

    private static func filteredTitle(_ value: String?, appName: String) -> String? {
        guard var title = normalized(value) else { return nil }
        for separator in [" — ", " - ", " | "] {
            let suffix = separator + appName
            if title.localizedCaseInsensitiveCompare(appName) != .orderedSame,
               title.lowercased().hasSuffix(suffix.lowercased()) {
                title.removeLast(suffix.count)
                break
            }
        }
        let pieces = title.components(separatedBy: " — ").map(filterPathOrURL)
        return normalized(pieces.joined(separator: " — "))
    }

    private static func filterPathOrURL(_ value: String) -> String {
        if let url = URL(string: value), let host = url.host(percentEncoded: false) {
            return host.lowercased()
        }
        if value.hasPrefix("/") || value.range(of: #"^[A-Za-z]:\\"#, options: .regularExpression) != nil {
            return URL(fileURLWithPath: value).lastPathComponent
        }
        return value
    }

    private static func normalizedDomain(_ url: URL?) -> String? {
        guard let host = url?.host(percentEncoded: false)?.lowercased() else { return nil }
        return bounded(host.trimmingCharacters(in: CharacterSet(charactersIn: ".")), length: 253)
    }

    private static func containsFragment(_ value: String?, _ fragments: [String]) -> Bool {
        guard let value = value?.lowercased() else { return false }
        return fragments.contains(where: value.contains)
    }
}
