// Riconoscimento vocale integrato nel Mac (Apple SpeechTranscriber, macOS 26+), come programma di supporto di Aria.
// Protocollo (una riga per richiesta, su stdin/stdout):   «percorso.wav\n»  ->  «R\t<testo>\n»      (all'avvio scrive «READY\n»)
// Gira tutto sul Mac: il modello della lingua e' di sistema (non pesa sulla RAM di Aria). Compilazione: vedi app/install.sh
import AVFoundation
import Foundation
import Speech

func isItalian(_ l: Locale) -> Bool { l.identifier == "it_IT" || l.identifier(.bcp47) == "it-IT" }

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
        let locale = Locale(identifier: "it-IT")
        do {
            if !(await SpeechTranscriber.installedLocales).contains(where: isItalian) {
                let probe = SpeechTranscriber(locale: locale, preset: .transcription)
                if let req = try await AssetInventory.assetInstallationRequest(supporting: [probe]) { try await req.downloadAndInstall() }
            }
        } catch {
            say("ERR\timpossibile preparare la lingua italiana: \(error)")
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
