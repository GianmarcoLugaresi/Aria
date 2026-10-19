import Foundation

/// Dove sta tutto. Due modi di essere installata:
///  - app scaricata dalle Release: dentro `Aria.app/Contents/Resources/backend` ci sono Python, le librerie e il programma, e in `.../bin` i programmi di supporto;
///  - installata dai sorgenti con `./app/install.sh`: tutto in `~/Library/Application Support/Aria` (o dove dice `paths.json`).
/// In tutti e due i casi configurazione e carattere stanno in `~/Library/Application Support/Aria`.
enum Paths {
    /// La cartella personale. `ARIA_HOME` (solo per le prove) la sposta altrove: l'app e il suo Python non toccano la vera.
    static let home: URL = {
        if let h = ProcessInfo.processInfo.environment["ARIA_HOME"], !h.isEmpty { return URL(fileURLWithPath: h) }
        return FileManager.default.homeDirectoryForCurrentUser
    }()
    static let support = home.appendingPathComponent("Library/Application Support/Aria")
    static let logs = home.appendingPathComponent("Library/Logs/Aria")

    private static let overrides: [String: String] = {
        let url = support.appendingPathComponent("paths.json")
        guard let data = try? Data(contentsOf: url),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: String] else { return [:] }
        return obj
    }()

    /// La cartella `backend` dentro l'app, se c'e' (app scaricata). Nei build locali dell'installer non c'e'.
    static let bundledBackend: URL? = {
        guard let res = Bundle.main.resourceURL else { return nil }
        let b = res.appendingPathComponent("backend")
        return FileManager.default.isExecutableFile(atPath: b.appendingPathComponent("bin/python3.12").path) ? b : nil
    }()
    static var isBundled: Bool { bundledBackend != nil }
    static var bundledBin: String? {
        guard let res = Bundle.main.resourceURL else { return nil }
        let b = res.appendingPathComponent("bin")
        return FileManager.default.fileExists(atPath: b.path) ? b.path : nil
    }

    static var python: String {
        if let b = bundledBackend { return b.appendingPathComponent("bin/python3.12").path }
        return overrides["python"] ?? support.appendingPathComponent("venv/bin/python").path
    }
    static var software: String {
        if let b = bundledBackend { return b.appendingPathComponent("software").path }
        return overrides["software"] ?? support.appendingPathComponent("software").path
    }
    static var configFile: String { overrides["config"] ?? support.appendingPathComponent("config.yaml").path }
    static var backendLog: URL { logs.appendingPathComponent("backend.log") }
    static var appLog: URL { logs.appendingPathComponent("app.log") }

    /// Ambiente comune a tutti i programmi Python che l'app lancia (il cervello e le Impostazioni).
    static func pythonEnvironment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = software
        env["PYTHONUNBUFFERED"] = "1"
        if let bin = bundledBin { env["ARIA_BIN"] = bin }
        if ProcessInfo.processInfo.environment["ARIA_HOME"] != nil { env["HOME"] = home.path }
        if isBundled {
            env["PYTHONDONTWRITEBYTECODE"] = "1"                                  // l'app e' firmata: niente file nuovi dentro il pacchetto
            env.removeValue(forKey: "PYTHONHOME")
            env.removeValue(forKey: "VIRTUAL_ENV")
        }
        return env
    }

    /// App scaricata, primo avvio: crea la cartella di Aria con configurazione e carattere di partenza (non tocca mai quelli che ci sono gia').
    static func bootstrap() {
        guard isBundled, let res = Bundle.main.resourceURL else { return }
        let fm = FileManager.default
        try? fm.createDirectory(at: support, withIntermediateDirectories: true)
        for (name, dest) in [("config.yaml", URL(fileURLWithPath: configFile)), ("persona.md", support.appendingPathComponent("persona.md"))] {
            let src = res.appendingPathComponent("defaults/" + name)
            if !fm.fileExists(atPath: dest.path), fm.fileExists(atPath: src.path) {
                try? fm.copyItem(at: src, to: dest)
                log("creato \(dest.path)")
            }
        }
    }

    /// Segno che i modelli sono stati scaricati almeno una volta (app scaricata).
    static var modelsMarker: URL { support.appendingPathComponent(".modelli-scaricati") }

    static func log(_ msg: String) {
        try? FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
        let line = "\(ISO8601DateFormatter().string(from: Date())) \(msg)\n"
        if let h = try? FileHandle(forWritingTo: appLog) {
            h.seekToEndOfFile(); h.write(line.data(using: .utf8)!); try? h.close()
        } else {
            try? line.write(to: appLog, atomically: true, encoding: .utf8)
        }
    }
}
