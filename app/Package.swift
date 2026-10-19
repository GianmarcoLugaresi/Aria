// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "Aria",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(name: "Aria", path: "Sources/Aria"),
    ],
    swiftLanguageModes: [.v5]
)
