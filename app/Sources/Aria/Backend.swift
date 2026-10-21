import Foundation

/// Avvia il "cervello" Python come processo figlio, lo riavvia se cade e ne raccoglie i log.
final class BackendManager {
    private var process: Process?
    private var prefetchProcess: Process?
    private var stopping = false
    private(set) var lastProblem: String?
    var onProblem: ((String?) -> Void)?

    private var failures = 0

    /// Toglie di mezzo eventuali backend rimasti da una chiusura forzata (tengono occupata la porta 8765).
    private func killStale() {
        let k = Process()
        k.executableURL = URL(fileURLWithPath: "/usr/bin/pkill")
        k.arguments = ["-f", "aria.main --config .*Application Support/Aria/config.yaml"]       // solo il backend: non il programma delle Impostazioni (aria.models), che usa la stessa configurazione
        try? k.run()
        k.waitUntilExit()
        Thread.sleep(forTimeInterval: 0.4)
    }

    func start() {
        if ProcessInfo.processInfo.environment["ARIA_NO_BACKEND"] != nil { return }
        if process == nil && prefetchProcess == nil { killStale() }
        Paths.bootstrap()
        let py = Paths.python
        guard FileManager.default.isExecutableFile(atPath: py) else {
            report(Paths.isBundled ? tr("L'app è danneggiata (manca Python): scaricala di nuovo.", "The app is damaged (Python is missing): download it again.")
                                   : tr("Python non trovato (\(py)). Esegui l'installer.", "Python not found (\(py)). Run the installer."))
            return
        }
        guard FileManager.default.fileExists(atPath: Paths.configFile) else {
            report(tr("Configurazione mancante: \(Paths.configFile)", "Configuration missing: \(Paths.configFile)"))
            return
        }
        try? FileManager.default.createDirectory(at: Paths.logs, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: Paths.backendLog.path) {
            FileManager.default.createFile(atPath: Paths.backendLog.path, contents: nil)
        }
        if Paths.isBundled && !FileManager.default.fileExists(atPath: Paths.modelsMarker.path) {
            downloadModels(then: { [weak self] in self?.launch() })              // app scaricata, primo avvio: prima i modelli
            return
        }
        launch()
    }

    /// Primo avvio dell'app scaricata: scarica i modelli (Whisper, chatbot, voce: circa 3,5 GB) con `aria.main --prefetch`, poi parte il cervello.
    private func downloadModels(then done: @escaping () -> Void) {
        if prefetchProcess != nil { return }
        report(tr("Primo avvio: sto scaricando i modelli (circa 3,5 GB), ci vuole un po'…", "First launch: downloading the models (about 3.5 GB), this takes a while…"))
        let p = Process()
        p.executableURL = URL(fileURLWithPath: Paths.python)
        p.arguments = ["-m", "aria.main", "--prefetch", "--config", Paths.configFile]
        p.currentDirectoryURL = URL(fileURLWithPath: Paths.software)
        var env = Paths.pythonEnvironment()
        env["HF_HUB_DISABLE_XET"] = "1"
        env["TOKENIZERS_PARALLELISM"] = "false"
        p.environment = env
        if let fh = try? FileHandle(forWritingTo: Paths.backendLog) {
            fh.seekToEndOfFile()
            p.standardOutput = fh
            p.standardError = fh
        }
        p.terminationHandler = { [weak self] proc in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.prefetchProcess = nil
                if self.stopping { return }
                if proc.terminationStatus == 0 {
                    try? "ok\n".write(to: Paths.modelsMarker, atomically: true, encoding: .utf8)
                    self.report(nil)
                    done()
                } else {
                    Paths.log(tr("scaricamento modelli non riuscito (codice \(proc.terminationStatus)): riprovo tra 60 s", "model download failed (code \(proc.terminationStatus)): retrying in 60 s"))
                    self.report(tr("Non riesco a scaricare i modelli: controlla la connessione (riprovo da solo).", "I can't download the models: check your connection (I'll retry on my own)."))
                    DispatchQueue.main.asyncAfter(deadline: .now() + 60) { [weak self] in self?.downloadModels(then: done) }
                }
            }
        }
        do {
            try p.run()
            prefetchProcess = p
            Paths.log(tr("scaricamento modelli avviato (pid \(p.processIdentifier))", "model download started (pid \(p.processIdentifier))"))
        } catch {
            report(tr("Impossibile avviare il download dei modelli: \(error.localizedDescription)", "Unable to start the model download: \(error.localizedDescription)"))
        }
    }

    private func launch() {
        let py = Paths.python
        let p = Process()
        p.executableURL = URL(fileURLWithPath: py)
        p.arguments = ["-m", "aria.main", "--config", Paths.configFile]
        p.currentDirectoryURL = URL(fileURLWithPath: Paths.software)
        var env = Paths.pythonEnvironment()
        env["TOKENIZERS_PARALLELISM"] = "false"
        env["ARIA_PARENT_WATCH"] = "1"
        p.environment = env
        if let fh = try? FileHandle(forWritingTo: Paths.backendLog) {
            fh.seekToEndOfFile()
            p.standardOutput = fh
            p.standardError = fh
        }
        p.terminationHandler = { [weak self] proc in
            guard let self = self, !self.stopping else { return }
            self.failures += 1
            let wait = min(30.0, 3.0 * Double(self.failures))              // se continua a cadere, aspetta sempre di piu'
            Paths.log(tr("backend terminato (codice \(proc.terminationStatus)): riavvio tra \(Int(wait)) s", "backend ended (code \(proc.terminationStatus)): restarting in \(Int(wait)) s"))
            DispatchQueue.main.asyncAfter(deadline: .now() + wait) { self.start() }
        }
        do {
            try p.run()
            process = p
            report(nil)
            DispatchQueue.main.asyncAfter(deadline: .now() + 60) { [weak self] in if self?.process === p, p.isRunning { self?.failures = 0 } }
            Paths.log(tr("backend avviato (pid \(p.processIdentifier))", "backend started (pid \(p.processIdentifier))"))
        } catch {
            report(tr("Impossibile avviare il backend: \(error.localizedDescription)", "Unable to start the backend: \(error.localizedDescription)"))
        }
    }

    func stop() {
        stopping = true
        process?.terminate()
        prefetchProcess?.terminate()
    }

    /// Riavvia il cervello (dopo aver cambiato versione o chatbot dalle Impostazioni): aspetta che il vecchio finisca e libera la porta.
    func restart() {
        guard let p = process, p.isRunning else { failures = 0; start(); return }
        stopping = true                                        // il vecchio non deve ripartire da solo
        p.terminate()
        DispatchQueue.global().async { [weak self] in
            let deadline = Date().addingTimeInterval(6)
            while p.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.1) }
            if p.isRunning { kill(p.processIdentifier, SIGKILL) }
            DispatchQueue.main.async {
                self?.stopping = false
                self?.process = nil
                self?.failures = 0
                self?.start()
            }
        }
    }

    private func report(_ msg: String?) {
        lastProblem = msg
        if let m = msg { Paths.log(m) }
        DispatchQueue.main.async { self.onProblem?(msg) }
    }
}

/// WebSocket verso il backend: riceve stato/livello/sottotitoli, manda comandi (wake, stop, mute, voice).
final class BackendClient {
    private var task: URLSessionWebSocketTask?
    private let url = URL(string: "ws://127.0.0.1:8765")!
    private(set) var connected = false
    private var closed = false
    var onMessage: (([String: Any]) -> Void)?
    var onConnection: ((Bool) -> Void)?

    func connect() {
        guard !closed else { return }
        let t = URLSession.shared.webSocketTask(with: url)
        task = t
        t.resume()
        listen(t)
    }

    private func listen(_ t: URLSessionWebSocketTask) {
        t.receive { [weak self] result in
            guard let self = self, t === self.task else { return }
            switch result {
            case .success(let msg):
                if !self.connected { self.connected = true; DispatchQueue.main.async { self.onConnection?(true) } }
                if case .string(let s) = msg, let d = s.data(using: .utf8),
                   let obj = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
                    DispatchQueue.main.async { self.onMessage?(obj) }
                }
                self.listen(t)
            case .failure:
                if self.connected { self.connected = false; DispatchQueue.main.async { self.onConnection?(false) } }
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { self.connect() }
            }
        }
    }

    func send(_ cmd: [String: Any]) {
        guard let d = try? JSONSerialization.data(withJSONObject: cmd), let s = String(data: d, encoding: .utf8) else { return }
        task?.send(.string(s)) { _ in }
    }

    func close() { closed = true; task?.cancel(with: .goingAway, reason: nil) }
}
