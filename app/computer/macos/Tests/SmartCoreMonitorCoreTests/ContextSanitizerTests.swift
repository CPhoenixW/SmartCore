import Foundation
import SmartCoreMonitorCore
import Testing

@Test func chatGPTConversationTitlePolicyKeepsOnlyBoundedNonControlLabels() {
    #expect(ChatGPTConversationTitlePolicy.sanitize("  SmartCore   monitor  ", appName: "ChatGPT") == "SmartCore monitor")
    #expect(ChatGPTConversationTitlePolicy.sanitize("ChatGPT", appName: "ChatGPT") == nil)
    #expect(ChatGPTConversationTitlePolicy.sanitize("Send", appName: "ChatGPT") == nil)
    #expect(ChatGPTConversationTitlePolicy.sanitize("message\nbody", appName: "ChatGPT") == nil)
    #expect(ChatGPTConversationTitlePolicy.sanitize(String(repeating: "x", count: 201), appName: "ChatGPT") == nil)
}

@Test func defaultContextKeepsFilteredTitleWithoutStructuredFields() {
    let context = ActivityContextSanitizer.sanitize(
        RawActivityContext(
            bundleId: "com.google.Chrome",
            appName: "Google Chrome",
            windowTitle: "  SmartCore architecture   - Google Chrome ",
            documentReference: "https://docs.example.test/private/path?q=secret"
        ),
        includeStructuredContext: false
    )

    #expect(context.windowTitle == "SmartCore architecture")
    #expect(context.domain == nil)
    #expect(context.documentName == nil)
    #expect(context.titleRedacted == false)
}

@Test func structuredBrowserContextKeepsDomainButNeverURLPath() {
    let context = ActivityContextSanitizer.sanitize(
        RawActivityContext(
            bundleId: "com.apple.Safari",
            appName: "Safari",
            windowTitle: "Project board",
            documentReference: "https://work.example.test/projects/secret?token=value"
        ),
        includeStructuredContext: true
    )

    #expect(context.contextKind == .browser)
    #expect(context.domain == "work.example.test")
    #expect(context.documentName == nil)
    #expect(context.workspace == nil)
}

@Test func structuredIDEContextKeepsOnlyFileAndParentNames() {
    let context = ActivityContextSanitizer.sanitize(
        RawActivityContext(
            bundleId: "com.microsoft.VSCode",
            appName: "Visual Studio Code",
            windowTitle: "service.py — SmartCore",
            documentReference: "file:///Users/person/Private/SmartCore/service.py"
        ),
        includeStructuredContext: true
    )

    #expect(context.contextKind == .ide)
    #expect(context.documentName == "service.py")
    #expect(context.workspace == "SmartCore")
    #expect(context.domain == nil)
}

@Test func titleFilteringRemovesFullPathsAndURLs() {
    let file = ActivityContextSanitizer.sanitize(
        RawActivityContext(
            bundleId: "com.example.Editor",
            appName: "Editor",
            windowTitle: "/Users/person/Private/notes.txt - Editor",
            documentReference: nil
        ),
        includeStructuredContext: false
    )
    let browser = ActivityContextSanitizer.sanitize(
        RawActivityContext(
            bundleId: "com.google.Chrome",
            appName: "Google Chrome",
            windowTitle: "https://example.test/private/path?q=secret - Google Chrome",
            documentReference: nil
        ),
        includeStructuredContext: false
    )

    #expect(file.windowTitle == "notes.txt")
    #expect(browser.windowTitle == "example.test")
}

@Test func sensitiveAppsAndAuthenticationWindowsAlwaysRedactDetails() {
    let passwordManager = ActivityContextSanitizer.sanitize(
        RawActivityContext(
            bundleId: "com.1password.1password",
            appName: "1Password",
            windowTitle: "Personal vault",
            documentReference: "file:///Users/person/vault"
        ),
        includeStructuredContext: true
    )
    let authentication = ActivityContextSanitizer.sanitize(
        RawActivityContext(
            bundleId: "com.apple.Safari",
            appName: "Safari",
            windowTitle: "Enter password to sign in",
            documentReference: "https://accounts.example.test/login"
        ),
        includeStructuredContext: true
    )

    for context in [passwordManager, authentication] {
        #expect(context.titleRedacted)
        #expect(context.windowTitle == nil)
        #expect(context.contextKind == nil)
        #expect(context.domain == nil)
        #expect(context.workspace == nil)
        #expect(context.documentName == nil)
    }
}
