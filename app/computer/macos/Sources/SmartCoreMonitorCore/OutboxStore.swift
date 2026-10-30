import Foundation
import SQLite3

private let sqliteTransient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

public enum OutboxError: Error {
    case sqlite(String)
}

public final class OutboxStore: @unchecked Sendable {
    private var database: OpaquePointer?
    private let lock = NSLock()

    public init(path: URL) throws {
        try FileManager.default.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true)
        guard sqlite3_open(path.path, &database) == SQLITE_OK else { throw OutboxError.sqlite("open failed") }
        try execute("PRAGMA journal_mode=WAL")
        try execute("PRAGMA busy_timeout=3000")
        try execute("""
            CREATE TABLE IF NOT EXISTS outbox (
                deviceId TEXT NOT NULL,
                bucketStart TEXT NOT NULL,
                payload BLOB NOT NULL,
                createdAt TEXT NOT NULL,
                PRIMARY KEY (deviceId, bucketStart)
            )
            """)
        try execute("CREATE INDEX IF NOT EXISTS idx_outbox_device_created ON outbox(deviceId, createdAt)")
    }

    deinit { sqlite3_close(database) }

    private func execute(_ sql: String) throws {
        guard sqlite3_exec(database, sql, nil, nil, nil) == SQLITE_OK else {
            throw OutboxError.sqlite(String(cString: sqlite3_errmsg(database)))
        }
    }

    public func enqueue(_ buckets: [ActivityBucket], deviceId: String) throws {
        lock.lock(); defer { lock.unlock() }
        let encoder = MonitorCoding.encoder()
        for bucket in buckets {
            let payload = try encoder.encode(bucket)
            var statement: OpaquePointer?
            let sql = "INSERT OR REPLACE INTO outbox(deviceId,bucketStart,payload,createdAt) VALUES(?,?,?,?)"
            guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK else { throw error() }
            defer { sqlite3_finalize(statement) }
            sqlite3_bind_text(statement, 1, deviceId, -1, sqliteTransient)
            sqlite3_bind_text(statement, 2, ISO8601DateFormatter().string(from: bucket.bucketStart), -1, sqliteTransient)
            _ = payload.withUnsafeBytes { bytes in
                sqlite3_bind_blob(statement, 3, bytes.baseAddress, Int32(payload.count), sqliteTransient)
            }
            sqlite3_bind_text(statement, 4, ISO8601DateFormatter().string(from: Date()), -1, sqliteTransient)
            guard sqlite3_step(statement) == SQLITE_DONE else { throw error() }
        }
    }

    public func pending(deviceId: String, limit: Int = 120) throws -> [ActivityBucket] {
        lock.lock(); defer { lock.unlock() }
        var statement: OpaquePointer?
        let sql = "SELECT payload FROM outbox WHERE deviceId=? ORDER BY bucketStart LIMIT ?"
        guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK else { throw error() }
        defer { sqlite3_finalize(statement) }
        sqlite3_bind_text(statement, 1, deviceId, -1, sqliteTransient)
        sqlite3_bind_int(statement, 2, Int32(limit))
        var result: [ActivityBucket] = []
        while sqlite3_step(statement) == SQLITE_ROW {
            guard let bytes = sqlite3_column_blob(statement, 0) else { continue }
            let data = Data(bytes: bytes, count: Int(sqlite3_column_bytes(statement, 0)))
            result.append(try MonitorCoding.decoder().decode(ActivityBucket.self, from: data).sanitizedForUpload())
        }
        return result
    }

    public func acknowledge(deviceId: String, bucketStarts: [Date]) throws {
        lock.lock(); defer { lock.unlock() }
        for date in bucketStarts {
            var statement: OpaquePointer?
            guard sqlite3_prepare_v2(database, "DELETE FROM outbox WHERE deviceId=? AND bucketStart=?", -1, &statement, nil) == SQLITE_OK else { throw error() }
            defer { sqlite3_finalize(statement) }
            sqlite3_bind_text(statement, 1, deviceId, -1, sqliteTransient)
            sqlite3_bind_text(statement, 2, ISO8601DateFormatter().string(from: date), -1, sqliteTransient)
            guard sqlite3_step(statement) == SQLITE_DONE else { throw error() }
        }
    }

    public func count(deviceId: String) throws -> Int {
        lock.lock(); defer { lock.unlock() }
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(database, "SELECT COUNT(*) FROM outbox WHERE deviceId=?", -1, &statement, nil) == SQLITE_OK else { throw error() }
        defer { sqlite3_finalize(statement) }
        sqlite3_bind_text(statement, 1, deviceId, -1, sqliteTransient)
        return sqlite3_step(statement) == SQLITE_ROW ? Int(sqlite3_column_int(statement, 0)) : 0
    }

    public func prune(maxAgeDays: Int = 90, maxBytes: Int = 50 * 1024 * 1024) throws {
        lock.lock(); defer { lock.unlock() }
        let cutoff = ISO8601DateFormatter().string(from: Date().addingTimeInterval(-Double(maxAgeDays) * 86_400))
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(database, "DELETE FROM outbox WHERE createdAt < ?", -1, &statement, nil) == SQLITE_OK else { throw error() }
        sqlite3_bind_text(statement, 1, cutoff, -1, sqliteTransient)
        guard sqlite3_step(statement) == SQLITE_DONE else { sqlite3_finalize(statement); throw error() }
        sqlite3_finalize(statement)
        while payloadSize() > maxBytes {
            let before = sqlite3_total_changes(database)
            try execute("DELETE FROM outbox WHERE rowid IN (SELECT rowid FROM outbox ORDER BY createdAt LIMIT 100)")
            if sqlite3_total_changes(database) == before { break }
        }
    }

    private func payloadSize() -> Int {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(database, "SELECT COALESCE(SUM(length(payload)), 0) FROM outbox", -1, &statement, nil) == SQLITE_OK else {
            return 0
        }
        defer { sqlite3_finalize(statement) }
        return sqlite3_step(statement) == SQLITE_ROW ? Int(sqlite3_column_int64(statement, 0)) : 0
    }

    private func error() -> OutboxError { .sqlite(String(cString: sqlite3_errmsg(database))) }
}
