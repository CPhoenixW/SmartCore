import Foundation
import SmartCoreMonitorCore
import SQLite3
import Testing

private let oldID = "019f9cd5-cc7a-7dc0-8cc3-8a3e1291a2da"
private let currentID = "019f9cc4-c49a-79e0-9668-605298dc5736"

@Test func codexLogParserTracksTheCurrentPrimaryConversation() {
    let log = """
    thread_stream_view_activity_changed active=true conversationId=\(oldID) rendererWindowAppearance=primary
    thread_stream_view_activity_changed active=false conversationId=\(oldID) rendererWindowAppearance=primary
    thread_stream_view_activity_changed active=true conversationId=\(currentID) rendererWindowAppearance=primary
    """

    #expect(CodexConversationTitleReader.currentConversationID(fromDesktopLog: log) == currentID)
}

@Test func codexLogParserClearsAClosedConversationAndIgnoresOtherWindows() {
    let log = """
    thread_stream_view_activity_changed active=true conversationId=\(currentID) rendererWindowAppearance=avatarOverlay
    thread_stream_view_activity_changed active=true conversationId=not-a-uuid rendererWindowAppearance=primary
    thread_stream_view_activity_changed active=true conversationId=\(oldID) rendererWindowAppearance=primary
    thread_stream_view_activity_changed active=false conversationId=\(oldID) rendererWindowAppearance=primary
    """

    #expect(CodexConversationTitleReader.currentConversationID(fromDesktopLog: log) == nil)
}

@Test func codexSessionIndexUsesTheLatestMatchingTitle() {
    let index = """
    {"id":"\(currentID)","thread_name":"Old title","updated_at":"2026-07-27T00:00:00Z"}
    {"id":"\(oldID)","thread_name":"Other task","updated_at":"2026-07-27T00:01:00Z"}
    {"id":"\(currentID)","thread_name":"  SmartCore   monitor  ","updated_at":"2026-07-27T00:02:00Z"}
    """

    #expect(
        CodexConversationTitleReader.title(fromSessionIndex: index, conversationID: currentID)
            == "SmartCore monitor"
    )
}

@Test func codexReaderResolvesTitleFromLocalMetadata() throws {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("SmartCoreMonitorTests-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let logDirectory = root.appendingPathComponent("Library/Logs/com.openai.codex/2026/07/27", isDirectory: true)
    let indexDirectory = root.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: logDirectory, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: indexDirectory, withIntermediateDirectories: true)
    let log = "thread_stream_view_activity_changed active=true conversationId=\(currentID) rendererWindowAppearance=primary\n"
    try Data(log.utf8).write(to: logDirectory.appendingPathComponent("codex-desktop-test.log"))
    let index = "{\"id\":\"\(currentID)\",\"thread_name\":\"Current SmartCore task\"}\n"
    try Data(index.utf8).write(to: indexDirectory.appendingPathComponent("session_index.jsonl"))

    let reader = CodexConversationTitleReader(homeDirectory: root)
    #expect(reader.currentTitle() == "Current SmartCore task")
}

@Test func codexReaderKeepsTheSelectedConversationWhenUnrelatedLogsAreAppended() throws {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("SmartCoreMonitorTests-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let logDirectory = root.appendingPathComponent("Library/Logs/com.openai.codex/2026/07/27", isDirectory: true)
    let indexDirectory = root.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: logDirectory, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: indexDirectory, withIntermediateDirectories: true)
    let logURL = logDirectory.appendingPathComponent("codex-desktop-test.log")
    let event = "thread_stream_view_activity_changed active=true conversationId=\(currentID) rendererWindowAppearance=primary\n"
    try Data(event.utf8).write(to: logURL)
    let index = "{\"id\":\"\(currentID)\",\"thread_name\":\"Stable task title\"}\n"
    try Data(index.utf8).write(to: indexDirectory.appendingPathComponent("session_index.jsonl"))
    let reader = CodexConversationTitleReader(homeDirectory: root)
    #expect(reader.currentTitle() == "Stable task title")

    let handle = try FileHandle(forWritingTo: logURL)
    try handle.seekToEnd()
    try handle.write(contentsOf: Data("unrelated log message\n".utf8))
    try handle.close()
    #expect(reader.currentTitle() == "Stable task title")
}

@Test func codexReaderFallsBackToReadOnlyStateDatabase() throws {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("SmartCoreMonitorTests-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let logDirectory = root.appendingPathComponent("Library/Logs/com.openai.codex/2026/07/27", isDirectory: true)
    let codexDirectory = root.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: logDirectory, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: codexDirectory, withIntermediateDirectories: true)
    let log = "thread_stream_view_activity_changed active=true conversationId=\(currentID) rendererWindowAppearance=primary\n"
    try Data(log.utf8).write(to: logDirectory.appendingPathComponent("codex-desktop-test.log"))

    var database: OpaquePointer?
    let databaseURL = codexDirectory.appendingPathComponent("state_5.sqlite")
    #expect(sqlite3_open(databaseURL.path, &database) == SQLITE_OK)
    defer { sqlite3_close(database) }
    #expect(sqlite3_exec(database, "CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT NOT NULL)", nil, nil, nil) == SQLITE_OK)
    #expect(sqlite3_exec(database, "INSERT INTO threads VALUES ('\(currentID)', 'Database task title')", nil, nil, nil) == SQLITE_OK)

    let reader = CodexConversationTitleReader(homeDirectory: root)
    #expect(reader.currentTitle() == "Database task title")
}
