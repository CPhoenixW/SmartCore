import Foundation
import Security

public struct PairingDocument: Codable, Sendable {
    public let serverUrl: String
    public let pairId: String
    public let claimCode: String

    public init(serverUrl: String, pairId: String, claimCode: String) {
        self.serverUrl = serverUrl
        self.pairId = pairId
        self.claimCode = claimCode
    }
}

public struct MonitorConfiguration: Codable, Sendable {
    public let serverUrl: String
    public let deviceId: String
    public let deviceName: String

    public init(serverUrl: String, deviceId: String, deviceName: String) {
        self.serverUrl = serverUrl
        self.deviceId = deviceId
        self.deviceName = deviceName
    }
}

public protocol TokenStorage: Sendable {
    func read(account: String) throws -> String?
    func write(_ token: String, account: String) throws
    func delete(account: String) throws
}

public enum KeychainError: Error {
    case status(OSStatus)
}

public struct KeychainTokenStorage: TokenStorage {
    private let service = "com.smartcore.monitor.device-token"

    public init() {}

    public func read(account: String) throws -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw KeychainError.status(status) }
        guard let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    public func write(_ token: String, account: String) throws {
        try? delete(account: account)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: Data(token.utf8),
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else { throw KeychainError.status(status) }
    }

    public func delete(account: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw KeychainError.status(status) }
    }
}

public struct FileTokenStorage: TokenStorage {
    private let directory: URL

    public init(directory: URL? = nil) {
        self.directory = directory ?? FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        )[0].appendingPathComponent("SmartCoreMonitor", isDirectory: true)
    }

    public func read(account: String) throws -> String? {
        let path = tokenPath(account: account)
        guard FileManager.default.fileExists(atPath: path.path) else { return nil }
        return String(data: try Data(contentsOf: path), encoding: .utf8)
    }

    public func write(_ token: String, account: String) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)
        let path = tokenPath(account: account)
        try Data(token.utf8).write(to: path, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: path.path)
    }

    public func delete(account: String) throws {
        let path = tokenPath(account: account)
        if FileManager.default.fileExists(atPath: path.path) {
            try FileManager.default.removeItem(at: path)
        }
    }

    private func tokenPath(account: String) -> URL {
        let digest = account.utf8.reduce(into: UInt64(14_695_981_039_346_656_037)) { value, byte in
            value = (value ^ UInt64(byte)) &* 1_099_511_628_211
        }
        return directory.appendingPathComponent("device-token-\(String(digest, radix: 16))")
    }
}

public final class ConfigurationStore: @unchecked Sendable {
    private let defaults: UserDefaults
    private let key = "monitorConfiguration"

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    public func load() -> MonitorConfiguration? {
        guard let data = defaults.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(MonitorConfiguration.self, from: data)
    }

    public func save(_ configuration: MonitorConfiguration) throws {
        defaults.set(try JSONEncoder().encode(configuration), forKey: key)
    }
}

public extension MonitorConfiguration {
    var keychainAccount: String { "\(serverUrl)|\(deviceId)" }
}
