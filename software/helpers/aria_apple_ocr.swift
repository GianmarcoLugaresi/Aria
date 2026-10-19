// Lettura del testo sullo schermo con il riconoscimento integrato nel Mac (Vision), come programma di supporto di Aria.
// Nessun modello da scaricare e nessuna RAM in piu' per Aria: il modello e' di macOS.
// Protocollo (una riga per richiesta, su stdin/stdout; all'avvio scrive «READY»):
//   «OCR\t<percorso immagine>»  ->  una riga JSON  {"w":2000,"h":1022,"lines":[{"t":"Prova","x":0.84,"y":0.63,"w":0.03,"h":0.012,"words":[{"t":"Prova","x":..,"y":..,"w":..,"h":..}]}, ...]}
//                                   (x,y = centro della riga, w,h = dimensioni, tutto da 0 a 1 con l'origine in alto a sinistra)
//   «PERM»                      ->  {"screen":true|false}      (Aria ha il permesso «Registrazione schermo»?)
//   «ASK»                       ->  {"screen":true|false}      (lo chiede: macOS mostra la finestra del permesso)
// Compilazione: vedi app/install.sh
import AppKit
import CoreGraphics
import Foundation
import Vision

func say(_ s: String) { FileHandle.standardOutput.write((s + "\n").data(using: .utf8)!) }

func jsonLine(_ obj: Any) -> String {
    guard let d = try? JSONSerialization.data(withJSONObject: obj, options: []), let s = String(data: d, encoding: .utf8) else { return "{\"error\":\"json\"}" }
    return s
}

func ocr(_ path: String) -> String {
    guard let img = NSImage(contentsOfFile: path), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return jsonLine(["error": "immagine non leggibile"])
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["it-IT", "en-US"]
    req.usesLanguageCorrection = true
    do { try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req]) } catch { return jsonLine(["error": "\(error)"]) }
    var lines: [[String: Any]] = []
    for o in (req.results ?? []) {
        guard let c = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        // anche ogni parola con il suo riquadro: serve a indicare la parola giusta dentro una riga lunga (non l'intera riga)
        var words: [[String: Any]] = []
        let str = c.string
        str.enumerateSubstrings(in: str.startIndex..<str.endIndex, options: .byWords) { sub, range, _, _ in
            guard let sub = sub, let r = try? c.boundingBox(for: range) else { return }
            let wb = r.boundingBox
            words.append(["t": sub, "x": (wb.midX * 1000).rounded() / 1000, "y": ((1 - wb.midY) * 1000).rounded() / 1000,
                          "w": (wb.width * 1000).rounded() / 1000, "h": (wb.height * 1000).rounded() / 1000])
        }
        lines.append(["t": c.string, "x": (b.midX * 1000).rounded() / 1000, "y": ((1 - b.midY) * 1000).rounded() / 1000,
                      "w": (b.width * 1000).rounded() / 1000, "h": (b.height * 1000).rounded() / 1000, "words": words])
    }
    return jsonLine(["w": cg.width, "h": cg.height, "lines": lines])
}

say("READY")
while let line = readLine() {
    let parts = line.split(separator: "\t", maxSplits: 1, omittingEmptySubsequences: false).map(String.init)
    switch parts[0] {
    case "OCR": say(parts.count > 1 ? ocr(parts[1]) : jsonLine(["error": "manca il percorso"]))
    case "PERM": say(jsonLine(["screen": CGPreflightScreenCaptureAccess()]))
    case "ASK": say(jsonLine(["screen": CGRequestScreenCaptureAccess()]))
    default: say(jsonLine(["error": "comando sconosciuto"]))
    }
}
