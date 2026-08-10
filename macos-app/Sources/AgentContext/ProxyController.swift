import AppKit
import Darwin
import Foundation

@MainActor
final class ProxyController: ObservableObject {
    private enum State: Equatable {
        case stopped
        case preparing
        case running
        case external
        case failed(String)
    }

    @Published private var state: State = .stopped

    private let fileManager = FileManager.default
    private let port = 8090
    private let upstreamURL = "https://chatgpt.com/backend-api/codex"
    private var proxyProcess: Process?
    private var healthTimer: Timer?

    private lazy var supportDirectory: URL = {
        let root = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return root.appendingPathComponent("AgentContext", isDirectory: true)
    }()

    private lazy var logsDirectory: URL = {
        let library = fileManager.urls(for: .libraryDirectory, in: .userDomainMask)[0]
        return library
            .appendingPathComponent("Logs", isDirectory: true)
            .appendingPathComponent("AgentContext", isDirectory: true)
    }()

    private var proxySourceURL: URL {
        supportDirectory.appendingPathComponent("ac-proxy.py")
    }

    private var requirementsURL: URL {
        supportDirectory.appendingPathComponent("requirements.txt")
    }

    private var venvPythonURL: URL {
        supportDirectory.appendingPathComponent("venv/bin/python")
    }

    private var requestLogURL: URL {
        logsDirectory.appendingPathComponent("requests.jsonl")
    }

    private var applicationLogURL: URL {
        logsDirectory.appendingPathComponent("application.log")
    }

    var statusText: String {
        switch state {
        case .stopped:
            return "Proxy is stopped"
        case .preparing:
            return "Preparing proxy"
        case .running:
            return "Proxy is running"
        case .external:
            return "Port 8090 is already active"
        case .failed:
            return "Proxy failed"
        }
    }

    var detailText: String {
        switch state {
        case .stopped:
            return "Requests are not being audited."
        case .preparing:
            return "Creating the Python environment and installing dependencies."
        case .running:
            return "Listening on 127.0.0.1:\(port). Request bodies are written to requests.jsonl."
        case .external:
            return "Another process owns 127.0.0.1:\(port). This app will not stop it."
        case .failed(let message):
            return message
        }
    }

    var menuBarSymbol: String {
        switch state {
        case .running:
            return "arrow.left.arrow.right.circle.fill"
        case .preparing:
            return "hourglass.circle"
        case .external:
            return "exclamationmark.arrow.circlepath"
        case .failed:
            return "exclamationmark.triangle.fill"
        case .stopped:
            return "arrow.left.arrow.right.circle"
        }
    }

    var isPreparing: Bool {
        state == .preparing
    }

    var canStart: Bool {
        switch state {
        case .stopped, .failed:
            return true
        case .preparing, .running, .external:
            return false
        }
    }

    var canStop: Bool {
        state == .running && proxyProcess != nil
    }

    init() {
        createDirectories()
        installBundledFiles()
        refreshHealth()
        healthTimer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.refreshHealth()
            }
        }
    }

    deinit {
        healthTimer?.invalidate()
        if let process = proxyProcess, process.isRunning {
            process.terminate()
        }
    }

    func start() {
        guard canStart else { return }
        state = .preparing
        createDirectories()
        installBundledFiles()
        guard state == .preparing else { return }

        let supportDirectory = supportDirectory
        let logsDirectory = logsDirectory
        let venvPythonURL = venvPythonURL
        let requirementsURL = requirementsURL
        let applicationLogURL = applicationLogURL

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            do {
                try Self.prepareEnvironment(
                    supportDirectory: supportDirectory,
                    logsDirectory: logsDirectory,
                    venvPythonURL: venvPythonURL,
                    requirementsURL: requirementsURL,
                    applicationLogURL: applicationLogURL
                )
                Task { @MainActor in
                    guard let self else { return }
                    guard self.state == .preparing else { return }
                    self.launchPreparedProxy()
                }
            } catch {
                Task { @MainActor in
                    self?.state = .failed(error.localizedDescription)
                }
            }
        }
    }

    private func launchPreparedProxy() {
        do {
            guard fileManager.fileExists(atPath: proxySourceURL.path) else {
                throw ProxyError.setup("Bundled ac-proxy.py could not be installed.")
            }

            let process = Process()
            process.executableURL = venvPythonURL
            process.arguments = [
                "-m", "uvicorn", "ac-proxy:app",
                "--host", "127.0.0.1",
                "--port", String(port),
                "--no-access-log",
            ]
            process.currentDirectoryURL = supportDirectory

            var environment = ProcessInfo.processInfo.environment
            environment["UPSTREAM_URL"] = upstreamURL
            environment["LLM_LOG_FILE"] = requestLogURL.path
            environment["PYTHONUNBUFFERED"] = "1"
            process.environment = environment

            let output = try Self.appendHandle(for: applicationLogURL)
            process.standardOutput = output
            process.standardError = output
            process.terminationHandler = { [weak self] finished in
                try? output.close()
                Task { @MainActor in
                    guard let self else { return }
                    self.proxyProcess = nil
                    if self.state == .running || self.state == .preparing {
                        self.state = finished.terminationStatus == 0
                            ? .stopped
                            : .failed("Proxy exited with status \(finished.terminationStatus). See application.log.")
                    }
                }
            }

            try process.run()
            proxyProcess = process
            waitForStartup(attemptsRemaining: 15)
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    func stop() {
        guard let process = proxyProcess else {
            if state != .external {
                state = .stopped
            }
            return
        }

        proxyProcess = nil
        state = .stopped
        guard process.isRunning else { return }

        process.terminate()
        let processIdentifier = process.processIdentifier
        DispatchQueue.global().asyncAfter(deadline: .now() + 3) {
            if process.isRunning {
                kill(processIdentifier, SIGKILL)
            }
        }
    }

    func openLogsFolder() {
        createDirectories()
        NSWorkspace.shared.open(logsDirectory)
    }

    func openRequestLog() {
        createDirectories()
        if !fileManager.fileExists(atPath: requestLogURL.path) {
            fileManager.createFile(atPath: requestLogURL.path, contents: nil)
            try? fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: requestLogURL.path)
        }
        NSWorkspace.shared.open(requestLogURL)
    }

    func copyCodexConfiguration() {
        let configuration = """
        model_provider = "agentcontext"

        [model_providers.agentcontext]
        name = "AgentContext ac-proxy"
        base_url = "http://127.0.0.1:8090"
        wire_api = "responses"
        requires_openai_auth = true
        """

        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(configuration, forType: .string)
    }

    private func createDirectories() {
        do {
            try fileManager.createDirectory(at: supportDirectory, withIntermediateDirectories: true)
            try fileManager.createDirectory(at: logsDirectory, withIntermediateDirectories: true)
            try fileManager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: supportDirectory.path)
            try fileManager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: logsDirectory.path)
        } catch {
            state = .failed("Could not create app directories: \(error.localizedDescription)")
        }
    }

    private func installBundledFiles() {
        do {
            try installBundledFile(name: "ac-proxy", extension: "py", destination: proxySourceURL)
            try installBundledFile(name: "requirements", extension: "txt", destination: requirementsURL)
        } catch {
            state = .failed("Could not install bundled proxy files: \(error.localizedDescription)")
        }
    }

    private func installBundledFile(name: String, extension fileExtension: String, destination: URL) throws {
        guard let bundled = Bundle.module.url(forResource: name, withExtension: fileExtension) else {
            throw ProxyError.setup("Missing bundled \(name).\(fileExtension).")
        }

        let bundledData = try Data(contentsOf: bundled)
        let installedData = try? Data(contentsOf: destination)
        if installedData != bundledData {
            try bundledData.write(to: destination, options: .atomic)
        }
        try fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: destination.path)
    }

    private func refreshHealth() {
        guard proxyProcess == nil else { return }
        Self.checkHealth(port: port) { [weak self] healthy in
            Task { @MainActor in
                guard let self, self.proxyProcess == nil else { return }
                if healthy {
                    self.state = .external
                } else if self.state == .external {
                    self.state = .stopped
                }
            }
        }
    }

    private func waitForStartup(attemptsRemaining: Int) {
        guard let process = proxyProcess, process.isRunning else {
            state = .failed("Proxy exited during startup. See application.log.")
            return
        }

        Self.checkHealth(port: port) { [weak self] healthy in
            Task { @MainActor in
                guard let self else { return }
                if healthy {
                    self.state = .running
                } else if attemptsRemaining > 1 {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                        self.waitForStartup(attemptsRemaining: attemptsRemaining - 1)
                    }
                } else {
                    let process = self.proxyProcess
                    self.proxyProcess = nil
                    process?.terminate()
                    self.state = .failed("Proxy did not become healthy. See application.log.")
                }
            }
        }
    }

    nonisolated private static func checkHealth(port: Int, completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "http://127.0.0.1:\(port)/_audit/healthz") else {
            completion(false)
            return
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { data, response, _ in
            let status = (response as? HTTPURLResponse)?.statusCode
            completion(status == 200 && data != nil)
        }.resume()
    }

    nonisolated private static func prepareEnvironment(
        supportDirectory: URL,
        logsDirectory: URL,
        venvPythonURL: URL,
        requirementsURL: URL,
        applicationLogURL: URL
    ) throws {
        try FileManager.default.createDirectory(at: supportDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: logsDirectory, withIntermediateDirectories: true)
        rotateOperationalLogIfNeeded(applicationLogURL)

        if !FileManager.default.isExecutableFile(atPath: venvPythonURL.path) {
            guard let systemPython = findPython() else {
                throw ProxyError.setup("Python 3 was not found. Install it with `brew install python` and try again.")
            }
            try run(
                executable: systemPython,
                arguments: ["-m", "venv", supportDirectory.appendingPathComponent("venv").path],
                logURL: applicationLogURL
            )
        }

        try run(
            executable: venvPythonURL,
            arguments: ["-m", "pip", "install", "--disable-pip-version-check", "-r", requirementsURL.path],
            logURL: applicationLogURL
        )
    }

    nonisolated private static func findPython() -> URL? {
        let candidates = [
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
        ]

        return candidates
            .map(URL.init(fileURLWithPath:))
            .first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }

    nonisolated private static func run(executable: URL, arguments: [String], logURL: URL) throws {
        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        let output = try appendHandle(for: logURL)
        process.standardOutput = output
        process.standardError = output
        try process.run()
        process.waitUntilExit()
        try output.close()

        guard process.terminationStatus == 0 else {
            throw ProxyError.setup("Setup command failed with status \(process.terminationStatus). See application.log.")
        }
    }

    nonisolated private static func appendHandle(for url: URL) throws -> FileHandle {
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
        let handle = try FileHandle(forWritingTo: url)
        try handle.seekToEnd()
        return handle
    }

    nonisolated private static func rotateOperationalLogIfNeeded(_ url: URL) {
        guard
            let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
            let size = attributes[.size] as? NSNumber,
            size.intValue > 5 * 1_024 * 1_024
        else { return }

        let backup = url.appendingPathExtension("1")
        try? FileManager.default.removeItem(at: backup)
        try? FileManager.default.moveItem(at: url, to: backup)
    }
}

private enum ProxyError: LocalizedError {
    case setup(String)

    var errorDescription: String? {
        switch self {
        case .setup(let message):
            return message
        }
    }
}
