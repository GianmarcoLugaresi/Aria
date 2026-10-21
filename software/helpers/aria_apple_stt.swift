// Riconoscimento vocale integrato nel Mac (Apple SpeechTranscriber, macOS 26+), come programma di supporto di Aria.
// Uso:  aria-apple-stt [--locale it-IT|en-US|...]      (senza argomento: it-IT)
// Protocollo (una riga per richiesta, su stdin/stdout):   «percorso.wav\n»  ->  «R\t<testo>\n»      (all'avvio scrive «READY\n»)
// Gira tutto sul Mac: il modello della lingua e' di sistema (non pesa sulla RAM di Aria). Compilazione: vedi app/install.sh
import AVFoundation
import Foundation
import Speech

/// La lingua richiesta con `--locale` (di fabbrica italiano).
let wantedLocale: String = {
    let a = CommandLine.arguments
    if let i = a.firstIndex(of: "--locale"), i + 1 < a.count { return a[i + 1] }
    return "it-IT"
}()

func isWanted(_ l: Locale) -> Bool {
    let id = wantedLocale.replacingOccurrences(of: "_", with: "-").lowercased()
    return l.identifier(.bcp47).lowercased() == id || l.identifier.replacingOccurrences(of: "_", with: "-").lowercased() == id
}

func transcribe(_ path: String, locale: Locale) async throws -> String {
    let file = try AVAudioFile(forReading: URL(fileURLWithPath: path))
    let t = SpeechTranscriber(locale: locale, preset: .transcription)
    let analyzer = SpeechAnalyzer(modules: [t])
    let collector = Task { () -> String in
        var s = ""
        for try await r in t.results { s += String(r.text.characters) }
        return s
    }
    if let last = try await analyzer.analyzeSequence(from: file) { try await analyzer.finalizeAndFinish(through: last) } else { await analyzer.cancelAndFinishNow() }
    return try await collector.value
}

func say(_ s: String) { FileHandle.standardOutput.write((s + "\n").data(using: .utf8)!) }

@main struct Main {
    static func main() async {
        let locale = Locale(identifier: wantedLocale)
        do {
            if !(await SpeechTranscriber.installedLocales).contains(where: isWanted) {
                let probe = SpeechTranscriber(locale: locale, preset: .transcription)
                if let req = try await AssetInventory.assetInstallationRequest(supporting: [probe]) { try await req.downloadAndInstall() }
            }
        } catch {
            say("ERR\timpossibile preparare la lingua \(wantedLocale): \(error)")
            return
        }
        say("READY")
        while let line = readLine() {
            let path = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if path.isEmpty { continue }
            do {
                let text = try await transcribe(path, locale: locale).replacingOccurrences(of: "\t", with: " ").replacingOccurrences(of: "\n", with: " ")
                say("R\t" + text.trimmingCharacters(in: .whitespaces))
            } catch {
                say("E\t\(error)")
            }
        }
    }
}
