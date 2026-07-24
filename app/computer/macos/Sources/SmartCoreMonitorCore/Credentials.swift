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
