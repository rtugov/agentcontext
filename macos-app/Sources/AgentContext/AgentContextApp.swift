import AppKit
import SwiftUI

@main
struct AgentContextApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var controller = ProxyController()

    var body: some Scene {
        MenuBarExtra {
            VStack(alignment: .leading, spacing: 6) {
                Text(controller.statusText)
                    .font(.headline)

                Text(controller.detailText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }
            .frame(width: 300, alignment: .leading)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            Divider()

            if controller.canStop {
                Button("Stop proxy") {
                    controller.stop()
                }
                .keyboardShortcut("s")
            } else {
                Button(controller.isPreparing ? "Preparing…" : "Start proxy") {
                    controller.start()
                }
                .keyboardShortcut("s")
                .disabled(!controller.canStart)
            }

            Button("Open request log") {
                controller.openRequestLog()
            }

            Button("Open logs folder") {
                controller.openLogsFolder()
            }

            Button("Copy Codex configuration") {
                controller.copyCodexConfiguration()
            }

            Divider()

            Button("Quit") {
                controller.stop()
                NSApplication.shared.terminate(nil)
            }
            .keyboardShortcut("q")
        } label: {
            Label("AgentContext", systemImage: controller.menuBarSymbol)
        }
        .menuBarExtraStyle(.menu)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApplication.shared.setActivationPolicy(.accessory)
    }
}
