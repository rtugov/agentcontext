// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "AgentContext",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(name: "AgentContext", targets: ["AgentContext"]),
    ],
    targets: [
        .executableTarget(
            name: "AgentContext",
            resources: [
                .copy("Resources/proxy.py"),
                .copy("Resources/requirements.txt"),
            ]
        ),
    ]
)
