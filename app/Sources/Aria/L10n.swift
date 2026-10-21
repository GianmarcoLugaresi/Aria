import Foundation

/// La lingua dell'app: «it» (italiano) o «en» (inglese). Una sola per tutto: scritte dei menu e delle Impostazioni, schermatina, messaggi;
/// il "cervello" Python (voce, riconoscimento, carattere, frasi) legge la stessa scelta da `settings.json` (chiave `language`).
///
/// Ordine di scelta: variabile `ARIA_LANG` (solo per le prove) > scelta nelle Impostazioni (`settings.json`) > `language:` di config.yaml > lingua del Mac
/// (italiano solo se il Mac e' in italiano, altrimenti inglese).
enum L10n {
    private(set) static var code: String = detect()
    static var isEnglish: Bool { code == "en" }

    static func reload() { code = detect() }
    static func set(_ c: String) { code = clean(c) ?? code }

    static func clean(_ raw: String?) -> String? {
        let c = (raw ?? "").lowercased().trimmingCharacters(in: .whitespaces)
        if c.hasPrefix("it") { return "it" }
        if c.hasPrefix("en") { return "en" }
        return nil
    }

    static func detect() -> String {
        if let forced = clean(ProcessInfo.processInfo.environment["ARIA_LANG"]) { return forced }
        let dir = URL(fileURLWithPath: Paths.configFile).deletingLastPathComponent()
        if let data = try? Data(contentsOf: dir.appendingPathComponent("settings.json")),
           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let chosen = clean(obj["language"] as? String) { return chosen }
        if let text = try? String(contentsOfFile: Paths.configFile, encoding: .utf8) {          // `language: en` in config.yaml (riga semplice: niente YAML completo)
            for line in text.split(separator: "\n") where line.hasPrefix("language:") {
                let v = line.dropFirst("language:".count).split(separator: "#").first.map { String($0) }
                if let c = clean(v?.trimmingCharacters(in: CharacterSet(charactersIn: " \"'"))) { return c }
            }
        }
        return clean(Locale.preferredLanguages.first) == "it" ? "it" : "en"
    }
}

/// La scritta nella lingua in uso: `tr("Esci da Aria", "Quit Aria")`.
func tr(_ it: String, _ en: String) -> String { L10n.isEnglish ? en : it }
