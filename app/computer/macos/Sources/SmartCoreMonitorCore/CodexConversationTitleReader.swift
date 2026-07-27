import Foundation
import SQLite3

private let codexSQLiteTransient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

/// Reads only Codex desktop task-selection metadata. It never opens rollout files
/// or reads conversation messages.
public final class CodexConversationTitleReader: @unchecked Sendable {
    private let homeDirectory: URL
    private let initialLogBytes: Int
    private let maxIndexBytes: Int
    private let lock = NSLock()
    private var trackedLogURL: URL?
    private var trackedLogSize: Int?
    private var trackedModificationDate: Date?
    private var hasReadLog = false
    private var cachedConversationID: String?

    public init(
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser,
        initialLogBytes: Int = 16 * 1024 * 1024,
        maxIndexBytes: Int = 4 * 1024 * 1024
    ) {
        self.homeDirectory = homeDirectory
        self.initialLogBytes = initialLogBytes
        self.maxIndexBytes = maxIndexBytes
    }

    public func currentTitle(appName: String = "ChatGPT") -> String? {
        guard let conversationID = currentConversationID() else { return nil }

        let indexURL = homeDirectory.appendingPathComponent(".codex/session_index.jsonl")
        if let indexText = readTail(of: indexURL, maximumBytes: maxIndexBytes),
           let title = Self.title(
               fromSessionIndex: indexText,
               conversationID: conversationID,
               appName: appName
           ) {
            return title
        }

        return titleFromDatabase(conversationID: conversationID, appName: appName)
    }

    public static func currentConversationID(fromDesktopLog text: String) -> String? {
        applyingConversationEvents(fromDesktopLog: text, startingWith: nil)
    }

    private static func applyingConversationEvents(
        fromDesktopLog text: String,
        startingWith initialID: String?
    ) -> String? {
        let pattern = #"thread_stream_view_activity_changed active=(true|false) conversationId=([0-9a-fA-F-]{36}).*rendererWindowAppearance=primary"#
        guard let expression = try? NSRegularExpression(pattern: pattern) else { return nil }
        var currentID = initialID

        for line in text.split(whereSeparator: \Character.isNewline) {
            let line = String(line)
            let range = NSRange(line.startIndex ..< line.endIndex, in: line)
            guard let match = expression.firstMatch(in: line, range: range),
                  let activeRange = Range(match.range(at: 1), in: line),
                  let idRange = Range(match.range(at: 2), in: line) else { continue }
            let conversationID = String(line[idRange]).lowercased()
            guard UUID(uuidString: conversationID) != nil else { continue }

            if line[activeRange] == "true" {
                currentID = conversationID
            } else if currentID == conversationID {
                currentID = nil
            }
        }
        return currentID
    }

    public static func title(
        fromSessionIndex text: String,
        conversationID: String,
        appName: String = "ChatGPT"
    ) -> String? {
        guard UUID(uuidString: conversationID) != nil else { return nil }
        var result: String?
        for line in text.split(whereSeparator: \Character.isNewline) {
            guard let data = String(line).data(using: .utf8),
                  let entry = try? JSONDecoder().decode(SessionIndexEntry.self, from: data),
                  entry.id.caseInsensitiveCompare(conversationID) == .orderedSame else { continue }
            result = ChatGPTConversationTitlePolicy.sanitize(entry.threadName, appName: appName)
        }
        return result
    }

    private func currentConversationID() -> String? {
        lock.lock()
        defer { lock.unlock() }
        guard let log = latestDesktopLog() else { return nil }
        if hasReadLog,
           trackedLogURL == log.url,
           trackedLogSize == log.size,
           trackedModificationDate == log.modifiedAt {
            return cachedConversationID
        }

        let sameLog = hasReadLog && trackedLogURL == log.url
        let bytesToRead = sameLog ? min(initialLogBytes, 2 * 1024 * 1024) : initialLogBytes
        guard let logText = readTail(of: log.url, maximumBytes: bytesToRead) else {
            return cachedConversationID
        }
        cachedConversationID = Self.applyingConversationEvents(
            fromDesktopLog: logText,
            startingWith: hasReadLog ? cachedConversationID : nil
        )
        trackedLogURL = log.url
        trackedLogSize = log.size
        trackedModificationDate = log.modifiedAt
        hasReadLog = true
        return cachedConversationID
    }

    private func latestDesktopLog() -> (url: URL, modifiedAt: Date, size: Int)? {
        let root = homeDirectory.appendingPathComponent("Library/Logs/com.openai.codex", isDirectory: true)
        let keys: [URLResourceKey] = [.isRegularFileKey, .contentModificationDateKey, .fileSizeKey]
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: keys,
            options: [.skipsHiddenFiles]
        ) else { return nil }

        var latest: (url: URL, modifiedAt: Date, size: Int)?
        for case let url as URL in enumerator {
            guard url.pathExtension == "log",
                  url.lastPathComponent.hasPrefix("codex-desktop-"),
                  let values = try? url.resourceValues(forKeys: Set(keys)),
                  values.isRegularFile == true,
                  let modifiedAt = values.contentModificationDate,
                  let size = values.fileSize else { continue }
            if latest == nil || modifiedAt > latest!.modifiedAt {
                latest = (url, modifiedAt, size)
            }
        }
        return latest
    }

    private func readTail(of url: URL, maximumBytes: Int) -> String? {
        guard maximumBytes > 0, let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }
        guard let endOffset = try? handle.seekToEnd() else { return nil }
        let byteCount = UInt64(maximumBytes)
        let startOffset = endOffset > byteCount ? endOffset - byteCount : 0
        do {
            try handle.seek(toOffset: startOffset)
            guard var data = try handle.readToEnd(), !data.isEmpty else { return nil }
            if startOffset > 0, let newline = data.firstIndex(of: 0x0A) {
                data.removeSubrange(data.startIndex ... newline)
            }
            return String(data: data, encoding: .utf8)
        } catch {
            return nil
        }
    }

    private func titleFromDatabase(conversationID: String, appName: String) -> String? {
        guard UUID(uuidString: conversationID) != nil else { return nil }
        let databaseURL = homeDirectory.appendingPathComponent(".codex/state_5.sqlite")
        var database: OpaquePointer?
        guard sqlite3_open_v2(
            databaseURL.path,
            &database,
            SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX,
            nil
        ) == SQLITE_OK else {
            if database != nil { sqlite3_close(database) }
            return nil
        }
        defer { sqlite3_close(database) }

        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(
            database,
            "SELECT title FROM threads WHERE id=? LIMIT 1",
            -1,
            &statement,
            nil
        ) == SQLITE_OK else { return nil }
        defer { sqlite3_finalize(statement) }
        sqlite3_bind_text(statement, 1, conversationID, -1, codexSQLiteTransient)
        guard sqlite3_step(statement) == SQLITE_ROW,
              let value = sqlite3_column_text(statement, 0) else { return nil }
        return ChatGPTConversationTitlePolicy.sanitize(String(cString: value), appName: appName)
    }
}

private struct SessionIndexEntry: Decodable {
    let id: String
    let threadName: String

    private enum CodingKeys: String, CodingKey {
        case id
        case threadName = "thread_name"
    }
}
