// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "SmartCoreMonitor",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "SmartCoreMonitorCore", targets: ["SmartCoreMonitorCore"]),
        .executable(name: "SmartCoreMonitor", targets: ["SmartCoreMonitor"]),
    ],
    dependencies: [
        .package(url: "https://github.com/swiftlang/swift-testing.git", exact: "6.3.2"),
    ],
    targets: [
        .target(
            name: "SmartCoreMonitorCore",
            linkerSettings: [.linkedLibrary("sqlite3"), .linkedFramework("Security")]
        ),
        .executableTarget(
            name: "SmartCoreMonitor",
            dependencies: ["SmartCoreMonitorCore"],
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("ApplicationServices"),
            ]
        ),
        .testTarget(
            name: "SmartCoreMonitorCoreTests",
            dependencies: [
                "SmartCoreMonitorCore",
                .product(name: "Testing", package: "swift-testing"),
            ]
        ),
    ]
)
