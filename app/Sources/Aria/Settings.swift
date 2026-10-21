import AppKit
import SwiftUI

// MARK: - dialogo con il programma Python (`python -m aria.models`)

/// Lo stato dei modelli lo conosce Python (cosa c'e' in cache, cosa c'e' in Ollama): l'app lo chiede e mostra.
enum ModelsCLI {
    static func makeProcess(_ args: [String]) -> Process {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: Paths.python)
        p.arguments = ["-m", "aria.models"] + args + ["--config", Paths.configFile]
        p.currentDirectoryURL = URL(fileURLWithPath: Paths.software)
        Paths.bootstrap()
        var env = Paths.pythonEnvironment()
        env["HF_HUB_DISABLE_XET"] = "1"
        p.environment = env
        return p
    }

    /// Esegue e aspetta la fine; restituisce codice di uscita e output.
    static func run(_ args: [String]) async -> (Int32, Data) {
        await withCheckedContinuation { cont in
            DispatchQueue.global().async {
                let p = makeProcess(args)
                let out = Pipe()
                p.standardOutput = out
                p.standardError = FileHandle.nullDevice
                do { try p.run() } catch { cont.resume(returning: (-1, Data())); return }
                let data = out.fileHandleForReading.readDataToEndOfFile()
                p.waitUntilExit()
                cont.resume(returning: (p.terminationStatus, data))
            }
        }
    }

    /// Esegue leggendo l'output riga per riga (ogni riga e' un JSON di avanzamento).
    static func stream(_ args: [String], onEvent: @escaping ([String: Any]) -> Void, onExit: @escaping (Int32) -> Void) -> Process? {
        let p = makeProcess(args)
        let out = Pipe()
        p.standardOutput = out
        p.standardError = FileHandle.nullDevice
        var buffer = Data()
        out.fileHandleForReading.readabilityHandler = { h in
            let d = h.availableData
            if d.isEmpty { return }
            buffer.append(d)
            while let nl = buffer.firstIndex(of: 0x0A) {
                let line = buffer.subdata(in: buffer.startIndex..<nl)
                buffer.removeSubrange(buffer.startIndex...nl)
                if let o = try? JSONSerialization.jsonObject(with: line) as? [String: Any] { onEvent(o) }
            }
        }
        p.terminationHandler = { proc in
            out.fileHandleForReading.readabilityHandler = nil
            onExit(proc.terminationStatus)
        }
        do { try p.run() } catch { return nil }
        return p
    }
}


// MARK: - dati restituiti da Python

struct ModelPart: Codable {
    let name: String
    let label: String
    let mb: Double?
    let installed: Bool
}

struct ProfileInfo: Codable, Identifiable {
    let id: String
    let label: String
    let summary: String
    let ramGb: Double
    let measured: Bool
    let stt: ModelPart
    let llm: ModelPart
    let needMb: Double
}

struct STTModel: Codable, Identifiable {
    let repo: String
    let label: String
    let mb: Double?
    let wer: [Double]?              // errore sulle parole in %: pulito, rumoroso, volume basso (misurato qui)
    let sec: Double?
    let note: String
    let installed: Bool
    let custom: Bool
    let removable: Bool?            // solo per quelli installati
    let block: String?              // perche' non si puo' togliere: "in uso" | "ultimo installato"
    var id: String { repo }
}

/// Un chatbot: "mlx" = dentro Aria (nessun Ollama), "ollama" = un modello di Ollama (se c'e').
struct LLMModel: Codable, Identifiable {
    let ref: String                 // "mlx:org/nome" oppure il nome di Ollama
    let source: String
    let label: String
    let gb: Double?
    let note: String
    let heavy: Bool
    let reasoning: Bool
    let installed: Bool
    let custom: Bool
    let removable: Bool?
    let block: String?
    var id: String { ref }
}

struct LLMInfo: Codable, Identifiable {
    let name: String
    let gb: Double
    let params: String?
    let heavy: Bool
    let reasoning: Bool
    var id: String { name }
}

/// La cartella dove Aria puo' scrivere e leggere file (solo lì dentro).
struct WorkspaceInfo: Codable {
    let path: String?
    let valid: Bool
    let error: String?
    let files: Int
}

/// Un "potere" di Aria sul Mac (promemoria, musica, scorciatoie...) con il suo interruttore.
struct PowerInfo: Codable, Identifiable {
    let id: String
    let label: String
    let hint: String
    let enabled: Bool
}

/// La lingua di Aria: `current` e' quella in uso, `chosen` quella scelta nelle Impostazioni (nil = segue il Mac), `system` quella del Mac.
struct LanguageInfo: Codable {
    let current: String
    let chosen: String?
    let system: String
    let supported: [String]
}

struct SettingsStatus: Codable {
    let profiles: [ProfileInfo]
    let sttModels: [STTModel]
    let llmModels: [LLMModel]
    let installedLlms: [LLMInfo]
    let ollama: Bool
    let ollamaInstalled: Bool
    let activeProfile: String
    let activeStt: String
    let activeLlm: String
    let diskFreeGb: Double
    let ramTotalGb: Double?
    let workspace: WorkspaceInfo?
    let powers: [PowerInfo]?
    let wakePhrase: String?
    let language: LanguageInfo?
}

/// Il separatore dei decimali della lingua in uso: la virgola in italiano, il punto in inglese.
private func dec(_ s: String) -> String { L10n.isEnglish ? s : s.replacingOccurrences(of: ".", with: ",") }

private func sizeText(_ mb: Double) -> String {
    dec(mb >= 1000 ? String(format: "%.1f GB", mb / 1000) : "\(Int(mb.rounded())) MB")
}

private func gbText(_ gb: Double) -> String { dec(String(format: "%.1f", gb)) }

/// Stessa regola di Python (`_llm_known`): "llama3.1" va bene anche se Ollama lo chiama "llama3.1:latest".
private func llmMatches(_ installed: String, _ wanted: String) -> Bool {
    installed == wanted || installed == wanted + ":latest" || (!wanted.contains(":") && installed.hasPrefix(wanted + ":"))
}

/// Cosa mostra una carta della versione.
struct CardData: Identifiable {
    let id: String
    let label: String
    let summary: String
    let stt: String?                // None = ancora da scegliere
    let llm: String?
    let ramGb: Double?
    let ramMeasured: Bool
    let needMb: Double?             // nil = non si sa
    let installed: Bool
}

// MARK: - modello della finestra

@MainActor
final class SettingsModel: ObservableObject {
    static let customID = "personalizzata"
    static let otherTag = "__altro__"

    @Published var status: SettingsStatus?
    @Published var selected = "media"
    @Published var sttRepo = ""                        // riconoscimento vocale scelto (repo Hugging Face)
    @Published var sttIsOther = false                  // "Altro modello…": si scrive il nome a mano
    @Published var otherSTT = ""
    @Published var llmName = ""                        // chatbot scelto (nome Ollama)
    @Published var llmIsOther = false
    @Published var otherLLM = ""
    @Published var voice = ""                          // voce di Aria (nome Pocket TTS); la cambia anche il menu
    @Published var wakeText = ""                       // la frase per chiamarla («Hey Aria»), come la scrive l'utente
    @Published var lang = L10n.code                    // la lingua in uso: cambia e la finestra si ridisegna
    private var changingLanguage = false               // un cambio di lingua alla volta (un doppio clic riavvierebbe il cervello due volte)
    var voiceGroups: [(title: String, names: [String])] = []
    var onVoice: ((String) -> Void)?                   // manda il cambio al backend: che dice subito una frase di prova
    @Published var loading = true
    @Published var busy = false                        // download o applicazione in corso
    @Published var downloading = false
    @Published var fraction: Double?
    @Published var progressText = ""
    @Published var error: String?
    @Published var notice: String?
    var onApplied: (() -> Void)?
    var onLanguage: (() -> Void)?                      // la lingua e' cambiata: l'app aggiorna menu e schermatina e riavvia il cervello
    private var process: Process?
    private var cancelled = false
    private var item = ""

    // ---- scelte e stato
    var effectiveSTT: String { (sttIsOther ? otherSTT : sttRepo).trimmingCharacters(in: .whitespaces) }
    var effectiveLLM: String { llmIsOther ? Self.llmRef(otherLLM) : llmName }
    /// Come scrive Python (`profiles.llm_ref_from_text`): con i due punti = Ollama (llama3.1:8b), con una barra = un repo MLX (org/nome).
    static func llmRef(_ text: String) -> String {
        let t = text.trimmingCharacters(in: .whitespaces)
        return (t.hasPrefix("mlx:") || t.contains(":") || !t.contains("/")) ? t : "mlx:" + t
    }
    func llmInfo(_ ref: String) -> LLMModel? {
        status?.llmModels.first { $0.ref == ref || (!ref.hasPrefix("mlx:") && $0.source == "ollama" && llmMatches($0.ref, ref)) }
    }
    func preset(_ id: String) -> ProfileInfo? { status?.profiles.first { $0.id == id } }
    func sttInfo(_ repo: String) -> STTModel? { status?.sttModels.first { $0.repo == repo } }
    var isCustom: Bool { selected == Self.customID }

    var sttInstalled: Bool {
        let r = effectiveSTT
        if let i = sttInfo(r) { return i.installed }
        return status?.profiles.first { $0.stt.name == r }?.stt.installed ?? false        // es. il riconoscimento di config.yaml, non in elenco
    }
    var llmInstalled: Bool { llmInfo(effectiveLLM)?.installed ?? false }
    var sttMB: Double? { sttInfo(effectiveSTT)?.mb ?? status?.profiles.first { $0.stt.name == effectiveSTT }?.stt.mb }
    var llmMB: Double? {
        let n = effectiveLLM
        if let g = llmInfo(n)?.gb { return g * 1000 }
        return status?.profiles.first { $0.llm.name == n }?.llm.mb
    }
    /// MB ancora da scaricare; nil se c'e' un pezzo da scaricare di cui non si conosce il peso.
    var missingMB: Double? {
        var total = 0.0
        if !sttInstalled { guard let m = sttMB else { return nil }; total += m }
        if !llmInstalled { guard let m = llmMB else { return nil }; total += m }
        return total
    }
    var nothingMissing: Bool { sttInstalled && llmInstalled }
    var namesOK: Bool { !effectiveSTT.isEmpty && !effectiveLLM.isEmpty }
    var isChanged: Bool {
        guard let st = status else { return false }
        return selected != st.activeProfile || effectiveSTT != st.activeStt || effectiveLLM != st.activeLlm
    }
    var canApply: Bool { !busy && namesOK && nothingMissing && isChanged }          // un chatbot di Ollama risulta "installato" solo se Ollama e' acceso

    /// Memoria in uso, stimata: la Media e' misurata; le altre combinazioni usano la stessa formula di Python (profiles.estimate_ram_gb).
    var ramEstimate: (gb: Double, measured: Bool)? {
        if let p = preset(selected), p.measured, effectiveSTT == p.stt.name, effectiveLLM == p.llm.name { return (p.ramGb, true) }
        guard let l = llmMB else { return nil }
        return (((1.65 + (sttMB ?? 500) / 1000 + l / 1000 + 0.3) * 10).rounded() / 10, false)
    }

    var cards: [CardData] {
        guard let st = status else { return [] }
        var out: [CardData] = st.profiles.map {
            CardData(id: $0.id, label: $0.label, summary: $0.summary, stt: $0.stt.label + ($0.stt.mb.map { " · " + sizeText($0) } ?? ""),
                     llm: $0.llm.label + " · " + sizeText($0.llm.mb ?? 0), ramGb: $0.ramGb, ramMeasured: $0.measured, needMb: $0.needMb, installed: $0.needMb <= 0)
        }
        let live = isCustom
        let sttLabel = sttInfo(effectiveSTT)?.label ?? effectiveSTT
        out.append(CardData(
            id: Self.customID, label: tr("Personalizzata", "Custom"),
            summary: tr("Scegli tu il modello di riconoscimento vocale e il chatbot, tra quelli che vuoi.", "You pick the speech recognition model and the chatbot, among the ones you like."),
            stt: live && !effectiveSTT.isEmpty ? sttLabel + (sttMB.map { " · " + sizeText($0) } ?? "") : nil,
            llm: live && !effectiveLLM.isEmpty ? (llmInfo(effectiveLLM)?.label ?? effectiveLLM) + (llmMB.map { " · " + sizeText($0) } ?? "") : nil,
            ramGb: live ? ramEstimate?.gb : nil, ramMeasured: false,
            needMb: live ? missingMB : nil, installed: live && nothingMissing))
        return out
    }

    // ---- azioni dell'utente
    func selectCard(_ id: String) {
        guard !busy else { return }
        selected = id
        if let p = preset(id) {                       // una versione imposta i suoi modelli; "Personalizzata" tiene quelli attuali
            sttRepo = p.stt.name; sttIsOther = false
            llmName = p.llm.name; llmIsOther = false
        }
    }
    func pickSTT(_ tag: String) {
        if tag == Self.otherTag { sttIsOther = true } else { sttIsOther = false; sttRepo = tag }
        flipToCustomIfNeeded()
    }
    func pickLLM(_ tag: String) {
        if tag == Self.otherTag { llmIsOther = true } else { llmIsOther = false; llmName = tag }
        flipToCustomIfNeeded()
    }
    /// Se i modelli non sono piu' quelli della versione scelta, la scelta diventa "Personalizzata".
    func flipToCustomIfNeeded() {
        if let p = preset(selected), effectiveSTT != p.stt.name || effectiveLLM != p.llm.name { selected = Self.customID }
    }
    var sttPickerValue: String { sttIsOther ? Self.otherTag : sttRepo }
    var llmPickerValue: String { llmIsOther ? Self.otherTag : llmName }

    // ---- stato dal programma Python
    func refresh(keepSelection: Bool = false) async {
        loading = true
        var args = ["status"]
        if !otherSTT.trimmingCharacters(in: .whitespaces).isEmpty { args += ["--extra-stt", otherSTT.trimmingCharacters(in: .whitespaces)] }
        if llmIsOther, !otherLLM.trimmingCharacters(in: .whitespaces).isEmpty { args += ["--extra-llm", effectiveLLM] }
        let (code, data) = await ModelsCLI.run(args)
        loading = false
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let decoded = code == 0 ? Result { try dec.decode(SettingsStatus.self, from: data) } : nil
        guard let st = try? decoded?.get() else {
            var why = tr("uscita \(code)", "exit \(code)")
            if case .failure(let e)? = decoded { why = tr("risposta non valida: \(e)", "invalid answer: \(e)") }
            Paths.log(tr("impostazioni: stato non leggibile (\(why)) \(String(decoding: data.prefix(200), as: UTF8.self))", "settings: status unreadable (\(why)) \(String(decoding: data.prefix(200), as: UTF8.self))"))
            error = tr("Non riesco a leggere lo stato dei modelli (controlla i log di Aria).", "I can't read the state of the models (check Aria's logs).")
            return
        }
        status = st
        if !keepSelection {
            selected = st.activeProfile
            sttRepo = st.activeStt; sttIsOther = false
            llmName = st.activeLlm; llmIsOther = false
        } else {                                       // un modello scritto a mano che adesso c'e': diventa una scelta normale dell'elenco
            if sttIsOther, st.sttModels.contains(where: { $0.repo == effectiveSTT && $0.installed }) { sttRepo = effectiveSTT; sttIsOther = false }
            if llmIsOther, let l = st.llmModels.first(where: { $0.installed && ($0.ref == effectiveLLM || ($0.source == "ollama" && llmMatches($0.ref, effectiveLLM))) }) { llmName = l.ref; llmIsOther = false }
        }
    }

    private func choiceArgs() -> [String] { [selected, "--stt", effectiveSTT, "--llm", effectiveLLM] }

    func download() {
        guard status != nil, !busy, namesOK else { return }
        busy = true; downloading = true; cancelled = false
        error = nil; notice = nil; fraction = nil; progressText = tr("Preparo il download…", "Preparing the download…")
        process = ModelsCLI.stream(["download"] + choiceArgs(),
            onEvent: { [weak self] ev in Task { @MainActor in self?.handle(ev) } },
            onExit: { [weak self] code in Task { @MainActor in await self?.downloadEnded(code) } })
        if process == nil {
            busy = false; downloading = false
            error = tr("Non riesco ad avviare il download (Python non trovato: rilancia l'installer).", "I can't start the download (Python not found: run the installer again).")
        }
    }

    private func handle(_ ev: [String: Any]) {
        switch ev["event"] as? String {
        case "start":
            item = ev["item"] as? String ?? ""
            let label = ev["label"] as? String ?? ""
            progressText = item == "stt" ? tr("Scarico il riconoscimento vocale (\(label))…", "Downloading speech recognition (\(label))…")
                                         : tr("Scarico il chatbot (\(label))…", "Downloading the chatbot (\(label))…")
        case "progress":
            let done = (ev["done"] as? NSNumber)?.doubleValue ?? 0
            let total = (ev["total"] as? NSNumber)?.doubleValue ?? 0
            let what = (ev["item"] as? String ?? item) == "stt" ? tr("Riconoscimento vocale", "Speech recognition") : "Chatbot"
            fraction = total > 0 ? min(1, done / total) : nil
            progressText = "\(what): " + tr("\(sizeText(done / 1e6)) di \(sizeText(total / 1e6))", "\(sizeText(done / 1e6)) of \(sizeText(total / 1e6))")
        case "error":
            error = ev["message"] as? String
        default: break
        }
    }

    private func downloadEnded(_ code: Int32) async {
        busy = false; downloading = false; process = nil
        if cancelled { notice = tr("Download interrotto: se lo riavvii riparte da dove era arrivato.", "Download stopped: if you restart it, it resumes where it left off.") }
        else if code == 0 { fraction = 1; notice = tr("Scaricato.", "Downloaded.") }
        else if error == nil { error = tr("Il download si è fermato (codice \(code)). Riprova: riparte da dove era arrivato.", "The download stopped (code \(code)). Try again: it resumes where it left off.") }
        await refresh(keepSelection: true)
    }

    func cancel() { cancelled = true; process?.terminate() }

    // ---- i poteri di Aria
    func setPower(_ id: String, _ on: Bool) async {
        error = nil
        let (code, data) = await ModelsCLI.run(["power", id, on ? "on" : "off"])
        if code != 0 {
            let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            error = obj?["error"] as? String ?? tr("Non sono riuscito a cambiare questa impostazione.", "I couldn't change this setting.")
        }
        await refresh(keepSelection: true)
    }

    // ---- la frase per chiamarla
    func saveWake() async {
        error = nil; notice = nil
        let (_, data) = await ModelsCLI.run(["wake", "set", wakeText])
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        if obj?["ok"] as? Bool == true {
            let phrase = wakeText.trimmingCharacters(in: .whitespaces)
            notice = tr("Fatto: da ora si chiama dicendo «\(phrase)». Riavvio il cervello di Aria (qualche secondo).", "Done: from now on you call her by saying “\(phrase)”. Restarting Aria's brain (a few seconds).")
            onApplied?()
        } else { error = obj?["error"] as? String ?? tr("Non sono riuscito a cambiare la frase.", "I couldn't change the phrase.") }
        await refresh(keepSelection: true)
    }

    // ---- la cartella di Aria
    func chooseWorkspace() async {
        let panel = NSOpenPanel()
        panel.title = tr("Cartella di Aria", "Aria's folder")
        panel.message = tr("Scegli la cartella dove Aria può scrivere e leggere i suoi file. Meglio una cartella nuova, ad esempio «Aria».", "Choose the folder where Aria can write and read its files. A new folder is best, for example “Aria”.")
        panel.prompt = tr("Scegli", "Choose")
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        await setWorkspace(url.path)
    }

    func setWorkspace(_ path: String) async {
        error = nil; notice = nil
        let (_, data) = await ModelsCLI.run(["workspace", "set", path])
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        if obj?["ok"] as? Bool == true { notice = tr("Cartella impostata: da ora Aria può salvare lì i suoi file.", "Folder set: from now on Aria can save its files there.") }
        else { error = obj?["error"] as? String ?? tr("Non sono riuscito a impostare la cartella.", "I couldn't set the folder.") }
        await refresh(keepSelection: true)
    }

    func clearWorkspace() async {
        error = nil
        _ = await ModelsCLI.run(["workspace", "clear"])
        notice = tr("Aria non ha più accesso a nessuna cartella (i file che c'erano restano dove sono).", "Aria no longer has access to any folder (the files that were there stay where they are).")
        await refresh(keepSelection: true)
    }

    func openWorkspace() {
        if let p = status?.workspace?.path { NSWorkspace.shared.open(URL(fileURLWithPath: p)) }
    }

    func pickVoice(_ v: String) { voice = v; onVoice?(v) }
    func replayVoice() { if !voice.isEmpty { onVoice?(voice) } }

    /// Toglie un modello dal Mac (il cestino). Python rifiuta quello in uso e l'ultimo installato.
    func remove(kind: String, id: String, label: String) async {
        guard !busy else { return }
        busy = true; error = nil; notice = nil; fraction = nil; progressText = tr("Rimuovo \(label)…", "Removing \(label)…")
        let (code, data) = await ModelsCLI.run(["remove", kind, id])
        busy = false
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        if code == 0, obj?["ok"] as? Bool == true {
            let mb = (obj?["freed_mb"] as? NSNumber)?.doubleValue ?? 0
            notice = tr("Rimosso «\(label)»", "Removed “\(label)”") + (mb > 0 ? tr(": liberati \(sizeText(mb)).", ": freed \(sizeText(mb)).") : ".")
        } else {
            error = obj?["error"] as? String ?? tr("Non sono riuscito a rimuoverlo.", "I couldn't remove it.")
        }
        await refresh(keepSelection: true)
    }

    func apply() async {
        busy = true; error = nil; notice = nil; fraction = nil; progressText = tr("Applico la scelta…", "Applying the choice…")
        let (code, data) = await ModelsCLI.run(["apply"] + choiceArgs())
        busy = false
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        if code == 0, obj?["ok"] as? Bool == true {
            notice = tr("Fatto: Aria si riavvia con la nuova configurazione (ci mette una decina di secondi).", "Done: Aria restarts with the new configuration (it takes about ten seconds).")
            onApplied?()
            await refresh()
        } else {
            error = obj?["error"] as? String ?? tr("Non sono riuscito ad applicare la scelta.", "I couldn't apply the choice.")
        }
    }

    // ---- la lingua
    /// Sceglie la lingua di Aria: «it», «en» oppure «auto» (segue il Mac). Python la salva; l'app ridisegna la finestra e riavvia il cervello (voce, riconoscimento e carattere nella lingua nuova).
    func setLanguage(_ code: String) async {
        guard !busy, !changingLanguage, code != (status?.language?.chosen ?? "auto") else { return }
        changingLanguage = true
        defer { changingLanguage = false }
        error = nil; notice = nil
        let (c, data) = await ModelsCLI.run(["language", "set", code])
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        guard c == 0, obj?["ok"] as? Bool == true else {
            error = obj?["error"] as? String ?? tr("Non sono riuscito a cambiare la lingua.", "I couldn't change the language.")
            return
        }
        L10n.reload()
        lang = L10n.code
        onLanguage?()
        await refresh(keepSelection: true)
        notice = tr("Fatto: Aria ora parla italiano. Il cervello si riavvia (qualche secondo; se la voce italiana non c'è ancora, la scarica la prima volta).",
                    "Done: Aria now speaks English. Her brain is restarting (a few seconds; the first time it also downloads the English voice, about 0.2 GB).")
    }

    /// Collaudo da riga di comando (ARIA_SETTINGS_SELFTEST="apply|versione[|riconoscimento|chatbot]" oppure "download|versione[|riconoscimento|chatbot]"):
    /// fa le stesse azioni dei pulsanti e scrive l'esito in app.log.
    func selfTest(_ spec: String) async {
        let parts = spec.split(separator: "|", omittingEmptySubsequences: false).map(String.init)
        guard parts.count >= 2 else { return }
        await refresh()
        if parts[0] == "remove" {
            await remove(kind: parts[1], id: parts.count > 2 ? parts[2] : "", label: parts.count > 2 ? parts[2] : "")
            Paths.log("selftest[\(spec)]: errore=\(error ?? "-") avviso=\(notice ?? "-")")
            return
        }
        if parts[0] == "workspace" {                                 // "workspace|set|/percorso" oppure "workspace|clear"
            if parts[1] == "set", parts.count > 2 { await setWorkspace(parts[2]) } else { await clearWorkspace() }
            Paths.log("selftest[\(spec)]: errore=\(error ?? "-") avviso=\(notice ?? "-") cartella=\(status?.workspace?.path ?? "-") valida=\(status?.workspace?.valid ?? false)")
            return
        }
        selectCard(parts[1])
        if parts.count > 2, !parts[2].isEmpty { pickSTT(sttInfo(parts[2]) != nil ? parts[2] : Self.otherTag); if sttIsOther { otherSTT = parts[2] } }
        if parts.count > 3, !parts[3].isEmpty { pickLLM(status?.llmModels.contains(where: { $0.ref == parts[3] }) == true ? parts[3] : Self.otherTag); if llmIsOther { otherLLM = parts[3] } }
        Paths.log("selftest[\(spec)]: carta=\(selected) attiva=\(status?.activeProfile ?? "?") stt=\(effectiveSTT) llm=\(effectiveLLM) canApply=\(canApply) mancano=\(missingMB.map { String(Int($0)) } ?? "?") MB")
        if parts[0] == "apply" {
            await apply()
            Paths.log("selftest: errore=\(error ?? "-") avviso=\(notice ?? "-") attiva=\(status?.activeProfile ?? "?") stt=\(status?.activeStt ?? "?") chatbot=\(status?.activeLlm ?? "?")")
        } else if parts[0] == "download" {
            download()
            try? await Task.sleep(nanoseconds: 9_000_000_000)
            Paths.log("selftest: durante il download busy=\(busy) frazione=\(fraction.map { String(format: "%.3f", $0) } ?? "-") testo=\(progressText) errore=\(error ?? "-")")
            cancel()
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            Paths.log("selftest: dopo l'annullamento busy=\(busy) avviso=\(notice ?? "-") errore=\(error ?? "-")")
        }
    }
}

// MARK: - vista

private struct ProfileCard: View {
    let c: CardData
    let selected: Bool
    let active: Bool

    private func row(_ icon: String, _ title: String, _ value: String?) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: icon).frame(width: 14).foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 0) {
                Text(title).font(.caption2).foregroundStyle(.secondary)
                Text(value ?? tr("scelto da te, qui sotto", "chosen by you, below")).font(.caption).foregroundStyle(value == nil ? .secondary : .primary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(c.label).font(.headline)
                Spacer()
                if active {
                    Text(tr("In uso", "In use")).font(.caption2.weight(.semibold)).padding(.horizontal, 7).padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.2), in: Capsule())
                }
            }
            Text(c.summary).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Divider()
            row("waveform", tr("Ti ascolta con", "Listens with"), c.stt)
            row("sparkles", tr("Risponde con", "Answers with"), c.llm)
            row("memorychip", tr("Memoria in uso", "Memory in use"), c.ramGb.map { "≈ \(gbText($0)) GB" + (c.ramMeasured ? "" : tr(" (stima)", " (estimate)")) })
            Spacer(minLength: 0)
            if c.installed {
                Label(tr("Pronta", "Ready"), systemImage: "checkmark.circle.fill").font(.caption).foregroundStyle(.green)
            } else if let need = c.needMb, c.stt != nil || c.id != SettingsModel.customID {
                Label(need > 0 ? tr("Da scaricare · \(sizeText(need))", "To download · \(sizeText(need))") : tr("Da completare", "To complete"), systemImage: "arrow.down.circle").font(.caption).foregroundStyle(.orange)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 215, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 14).fill(selected ? Color.accentColor.opacity(0.10) : Color.primary.opacity(0.04)))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(selected ? Color.accentColor : Color.primary.opacity(0.12), lineWidth: selected ? 2 : 1))
        .contentShape(RoundedRectangle(cornerRadius: 14))
    }
}

/// Un modello che l'utente sta per togliere (serve la conferma).
struct PendingRemoval: Identifiable {
    let kind: String            // "stt" | "llm"
    let id: String
    let label: String
    let mb: Double?
}

struct SettingsView: View {
    @ObservedObject var m: SettingsModel
    @State private var pending: PendingRemoval?

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(tr("Impostazioni di Aria", "Aria Settings")).font(.title2.weight(.semibold))
                        Text(tr("Tutto resta sul tuo Mac: niente abbonamenti, niente cloud.", "Everything stays on your Mac: no subscriptions, no cloud.")).font(.callout).foregroundStyle(.secondary)
                    }
                    if let st = m.status {
                        languageSection(st)
                        versions(st)
                        recognition(st)
                        chatbots(st)
                        voiceSection()
                        wakeSection(st)
                        workspaceSection(st)
                        powersSection(st)
                        summary(st)
                        installedModels(st)
                    } else if m.loading {
                        ProgressView(tr("Leggo cosa è installato…", "Reading what is installed…"))
                    }
                }
                .padding(24)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider()
            VStack(alignment: .leading, spacing: 8) {                   // barra fissa: i pulsanti si vedono sempre
                if let e = m.error { Label(e, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true) }
                if let n = m.notice { Label(n, systemImage: "checkmark.circle.fill").foregroundStyle(.green).fixedSize(horizontal: false, vertical: true) }
                if let st = m.status { actions(st) }
            }
            .padding(.horizontal, 24).padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.bar)
        }
        .frame(minWidth: 700, minHeight: 640)
        .id(m.lang)                                                       // cambia la lingua: tutta la finestra si ridisegna con le scritte nuove
        .confirmationDialog(tr("Rimuovere «\(pending?.label ?? "")»?", "Remove “\(pending?.label ?? "")”?"), isPresented: Binding(get: { pending != nil }, set: { if !$0 { pending = nil } }), presenting: pending) { p in
            Button(tr("Rimuovi", "Remove"), role: .destructive) { Task { await m.remove(kind: p.kind, id: p.id, label: p.label) } }
            Button(tr("Annulla", "Cancel"), role: .cancel) {}
        } message: { p in
            Text(tr("Libera" + (p.mb.map { " circa \(sizeText($0))" } ?? " spazio") + " sul Mac. Potrai riscaricarlo quando vuoi.",
                    "Frees" + (p.mb.map { " about \(sizeText($0))" } ?? " space") + " on your Mac. You can download it again whenever you like."))
        }
    }

    /// La lingua di Aria: scritte dell'app, voce, riconoscimento vocale e carattere. «Automatica» segue la lingua del Mac.
    private func languageSection(_ st: SettingsStatus) -> some View {
        let chosen = st.language?.chosen ?? "auto"
        return VStack(alignment: .leading, spacing: 8) {
            Text(tr("Lingua", "Language")).font(.headline)
            Picker("", selection: Binding(get: { chosen }, set: { v in Task { await m.setLanguage(v) } })) {
                Text(tr("Automatica (come il Mac)", "Automatic (like the Mac)")).tag("auto")
                Text("Italiano").tag("it")
                Text("English").tag("en")
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(maxWidth: 420)
            .disabled(m.busy)
            Text(tr("Cambia le scritte dell'app, la lingua che Aria capisce e parla (riconoscimento vocale e voce) e il suo carattere. Cambiando lingua Aria si riavvia; la prima volta che passi all'inglese scarica la voce inglese (circa 0,2 GB). Alcune funzioni sono solo in italiano per ora: la voce naturale (Qwen3-TTS).",
                    "Changes the app's text, the language Aria understands and speaks (speech recognition and voice) and her personality. Aria restarts when you change language; the first time you switch to English it downloads the English voice (about 0.2 GB). Some features are Italian-only for now: the natural voice (Qwen3-TTS)."))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func versions(_ st: SettingsStatus) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(tr("Versione", "Version")).font(.headline)
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 12, alignment: .top), GridItem(.flexible(), spacing: 12, alignment: .top)], spacing: 12) {
                ForEach(m.cards) { c in
                    ProfileCard(c: c, selected: c.id == m.selected, active: c.id == st.activeProfile)
                        .onTapGesture { m.selectCard(c.id) }
                }
            }
            Text(tr("Scegliendo una versione, riconoscimento vocale e chatbot si impostano da soli; se poi cambi uno dei due qui sotto, la scelta diventa «Personalizzata». «Media» è la configurazione di sempre. Le memorie di Leggera, Pesante e Personalizzata sono stime.",
                    "When you pick a version, speech recognition and chatbot are set automatically; if you then change one of the two below, the choice becomes “Custom”. “Medium” is the usual setup. The memory figures for Light, Heavy and Custom are estimates."))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func sttLabel(_ s: STTModel) -> String {
        s.label + (s.mb.map { " · " + sizeText($0) } ?? "") + (s.installed ? "" : tr(" · da scaricare", " · to download"))
    }

    private func recognition(_ st: SettingsStatus) -> some View {
        var options = st.sttModels
        if !m.sttIsOther, !m.sttRepo.isEmpty, !options.contains(where: { $0.repo == m.sttRepo }),
           let p = st.profiles.first(where: { $0.stt.name == m.sttRepo }) {      // es. il riconoscimento di config.yaml, che non e' in elenco
            options.append(STTModel(repo: p.stt.name, label: p.stt.label, mb: p.stt.mb, wer: nil, sec: nil, note: tr("Quello di config.yaml.", "The one from config.yaml."), installed: p.stt.installed, custom: true, removable: nil, block: nil))
        }
        let info = m.sttIsOther ? nil : options.first { $0.repo == m.sttRepo }
        return VStack(alignment: .leading, spacing: 8) {
            Text(tr("Riconoscimento vocale (cosa capisce di quello che dici)", "Speech recognition (what it understands of what you say)")).font(.headline)
            Picker("", selection: Binding(get: { m.sttPickerValue }, set: { m.pickSTT($0) })) {
                ForEach(options) { s in Text(sttLabel(s)).tag(s.repo) }
                Text(tr("Altro modello…", "Other model…")).tag(SettingsModel.otherTag)
            }
            .labelsHidden()
            .disabled(m.busy)
            if m.sttIsOther {
                TextField(tr("organizzazione/nome, ad esempio mlx-community/whisper-small-mlx", "organisation/name, for example mlx-community/whisper-small-mlx"), text: $m.otherSTT)
                    .textFieldStyle(.roundedBorder)
                    .disabled(m.busy)
                Text(tr("Serve un modello nel formato MLX Whisper su Hugging Face (di solito «mlx-community/whisper-…»). Premi «Scarica» per controllarlo e scaricarlo.",
                        "It needs a model in the MLX Whisper format on Hugging Face (usually “mlx-community/whisper-…”). Press “Download” to check it and download it."))
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            } else if let i = info {
                VStack(alignment: .leading, spacing: 2) {
                    if let w = i.wer {
                        Text(tr("Errori sulle parole (misurati qui su 54 frasi): \(Int(w[0]))% con audio pulito · \(Int(w[1]))% con rumore · \(Int(w[2]))% con volume basso" + (i.sec.map { " · circa \(dec(String(format: "%.2f", $0))) s a frase" } ?? ""),
                                "Word errors (measured here on 54 Italian sentences): \(Int(w[0]))% with clean audio · \(Int(w[1]))% with noise · \(Int(w[2]))% with low volume" + (i.sec.map { " · about \(dec(String(format: "%.2f", $0))) s per sentence" } ?? "")))
                            .font(.caption)
                    } else {
                        Text(tr("Non ancora misurato su questo Mac.", "Not measured on this Mac yet.")).font(.caption)
                    }
                    Text(i.note).font(.caption).foregroundStyle(.secondary)
                }
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func voiceSection() -> some View {
        var groups = m.voiceGroups
        if !m.voice.isEmpty, !groups.contains(where: { $0.names.contains(m.voice) }) { groups.append((title: tr("Altre", "Other"), names: [m.voice])) }
        return VStack(alignment: .leading, spacing: 8) {
            Text(tr("Voce (come ti parla Aria)", "Voice (how Aria talks to you)")).font(.headline)
            HStack(spacing: 10) {
                Picker("", selection: Binding(get: { m.voice }, set: { m.pickVoice($0) })) {
                    ForEach(groups, id: \.title) { g in
                        Section(g.title) { ForEach(g.names, id: \.self) { Text($0.capitalized).tag($0) } }
                    }
                }
                .labelsHidden()
                Button { m.replayVoice() } label: { Label(tr("Riascolta", "Play again"), systemImage: "speaker.wave.2.fill") }
                    .disabled(m.voice.isEmpty)
            }
            Text(tr("Appena scegli una voce Aria dice una frase di prova, così senti subito se ti piace. La prova non parte se stai parlando con lei o se sta ancora caricando i modelli.",
                    "As soon as you pick a voice Aria says a test sentence, so you can hear at once whether you like it. The test doesn't play if you are talking to her or she is still loading the models."))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func wakeSection(_ st: SettingsStatus) -> some View {
        let current = (st.wakePhrase ?? "hey aria").split(separator: " ").map { $0.prefix(1).uppercased() + $0.dropFirst() }.joined(separator: " ")
        return VStack(alignment: .leading, spacing: 8) {
            Text(tr("Come la chiami", "What you call her")).font(.headline)
            HStack(spacing: 10) {
                TextField(current, text: $m.wakeText)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 260)
                    .onSubmit { Task { await m.saveWake() } }
                Button { Task { await m.saveWake() } } label: { Label(tr("Usa questa", "Use this"), systemImage: "checkmark.circle") }
                    .disabled(m.busy || m.wakeText.trimmingCharacters(in: .whitespaces).isEmpty
                              || m.wakeText.trimmingCharacters(in: .whitespaces).lowercased() == current.lowercased())
            }
            Text(tr("Adesso: «\(current)». Due o tre parole (con una sola si sveglierebbe ogni volta che la senti in una frase). Il riconoscimento accetta anche come la scrive di solito: per «Hey Aria» vanno bene «Ehi Aria», «Ei Aria»…",
                    "Right now: “\(current)”. Two or three words (with a single one she would wake up every time she hears it in a sentence). Recognition also accepts the usual spellings: for “Hey Aria”, “Hey Area” or “Hay Aria” work too."))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func workspaceSection(_ st: SettingsStatus) -> some View {
        let w = st.workspace
        return VStack(alignment: .leading, spacing: 8) {
            Text(tr("Cartella di Aria (dove può scrivere e leggere)", "Aria's folder (where she can write and read)")).font(.headline)
            if let path = w?.path {
                HStack(spacing: 8) {
                    Image(systemName: w?.valid == true ? "folder.fill" : "exclamationmark.triangle.fill").foregroundStyle(w?.valid == true ? Color.accentColor : .orange)
                    VStack(alignment: .leading, spacing: 1) {
                        Text((path as NSString).lastPathComponent).font(.callout)
                        Text(path + (w?.valid == true ? " · \(w?.files ?? 0) " + (w?.files == 1 ? tr("file", "file") : tr("file", "files")) : "")).font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                    }
                }
                if let e = w?.error { Text(e).font(.caption).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true) }
            } else {
                Text(tr("Nessuna cartella: Aria non salva né legge file.", "No folder: Aria neither saves nor reads files.")).font(.callout).foregroundStyle(.secondary)
            }
            HStack(spacing: 10) {
                Button { Task { await m.chooseWorkspace() } } label: { Label(w?.path == nil ? tr("Scegli una cartella…", "Choose a folder…") : tr("Cambia cartella…", "Change folder…"), systemImage: "folder.badge.plus") }
                if w?.path != nil {
                    Button { m.openWorkspace() } label: { Label(tr("Apri", "Open"), systemImage: "arrow.up.forward.app") }.disabled(w?.valid != true)
                    Button(role: .destructive) { Task { await m.clearWorkspace() } } label: { Label(tr("Togli accesso", "Remove access"), systemImage: "xmark.circle") }
                }
            }
            .disabled(m.busy)
            Text(tr("Con una cartella impostata puoi dire: «scrivimi un testo sulla fotosintesi», «fai una ricerca veloce sui polpi» (la salva con le fonti), «aggiungi latte alla lista della spesa», «segna una nota…», «leggimi il file…», «riassumi il documento…», «apri la cartella». Aria lavora SOLO lì dentro: solo file di testo, non cancella niente, non sovrascrive (se il nome esiste ne crea uno nuovo) e non esce dalla cartella. macOS può chiederti di consentire l'accesso a Documenti o Scrivania la prima volta.",
                    "With a folder set you can say: “write me a text about photosynthesis”, “do some quick research on octopuses” (she saves it with the sources), “add milk to the shopping list”, “make a note…”, “read me the file…”, “summarise the document…”, “open the folder”. Aria works ONLY in there: text files only, she deletes nothing, overwrites nothing (if the name exists she creates a new one) and never leaves the folder. macOS may ask you to allow access to Documents or Desktop the first time."))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func powersSection(_ st: SettingsStatus) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(tr("Cosa può fare Aria sul tuo Mac", "What Aria can do on your Mac")).font(.headline)
            ForEach(st.powers ?? []) { p in
                Toggle(isOn: Binding(get: { p.enabled }, set: { v in Task { await m.setPower(p.id, v) } })) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(p.label).font(.callout)
                        Text(p.hint).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .disabled(m.busy)
            }
            Text(tr("Aria li usa solo quando glielo chiedi a voce, mai da sola e mai su ordine di un testo trovato sul web. Le Scorciatoie chiedono sempre «sì» prima di partire. La prima volta macOS chiede il permesso di far controllare ad Aria Calendario, Promemoria, Musica…: consentilo (puoi toglierlo in Impostazioni di Sistema → Privacy e sicurezza → Automazione).",
                    "Aria uses them only when you ask out loud, never on her own and never on the orders of a text found on the web. Shortcuts always ask for a “yes” before running. The first time, macOS asks for permission to let Aria control Calendar, Reminders, Music…: allow it (you can take it away in System Settings → Privacy & Security → Automation)."))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func llmLabel(_ l: LLMModel) -> String {
        l.label + (l.gb.map { " · \(gbText($0)) GB" } ?? "") + (l.heavy ? tr(" · molto pesante", " · very heavy") : "") + (l.installed ? "" : tr(" · da scaricare", " · to download"))
    }

    private func chatbots(_ st: SettingsStatus) -> some View {
        var models = st.llmModels
        if !m.llmIsOther, !m.llmName.isEmpty, !models.contains(where: { $0.ref == m.llmName }) {          // es. il chatbot di config.yaml, che non e' in elenco
            models.append(LLMModel(ref: m.llmName, source: m.llmName.hasPrefix("mlx:") ? "mlx" : "ollama", label: m.llmName, gb: nil, note: "",
                                   heavy: false, reasoning: false, installed: false, custom: true, removable: nil, block: nil))
        }
        let inside = models.filter { $0.source == "mlx" }
        let ollama = models.filter { $0.source == "ollama" }
        let current = models.first { $0.ref == m.llmName }
        return VStack(alignment: .leading, spacing: 8) {
            Text(tr("Chatbot (cosa ti risponde)", "Chatbot (what answers you)")).font(.headline)
            Picker("", selection: Binding(get: { m.llmPickerValue }, set: { m.pickLLM($0) })) {
                Section(tr("Dentro Aria · non serve Ollama", "Inside Aria · no Ollama needed")) { ForEach(inside) { Text(llmLabel($0)).tag($0.ref) } }
                if !ollama.isEmpty { Section(tr("Ollama · installati su questo Mac", "Ollama · installed on this Mac")) { ForEach(ollama) { Text(llmLabel($0)).tag($0.ref) } } }
                Text(tr("Altro chatbot…", "Other chatbot…")).tag(SettingsModel.otherTag)
            }
            .labelsHidden()
            .disabled(m.busy)
            if m.llmIsOther {
                TextField(tr("mlx-community/… (dentro Aria) oppure llama3.1:8b (Ollama)", "mlx-community/… (inside Aria) or llama3.1:8b (Ollama)"), text: $m.otherLLM)
                    .textFieldStyle(.roundedBorder)
                    .disabled(m.busy)
                Text(tr("Un nome con i due punti (llama3.1:8b) è un modello di Ollama; un nome con la barra (organizzazione/nome) è un modello MLX di Hugging Face, che gira dentro Aria. Premi «Scarica» per controllarlo e prenderlo.",
                        "A name with a colon (llama3.1:8b) is an Ollama model; a name with a slash (organisation/name) is an MLX model from Hugging Face, which runs inside Aria. Press “Download” to check it and fetch it."))
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            } else if let c = current, !c.note.isEmpty {
                Text(c.note).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Text(tr("I chatbot «dentro Aria» girano nell'app stessa: non serve installare altro. I modelli oltre gli 8 GB rispondono più lentamente e, con 16 GB di RAM, possono rallentare tutto il Mac.",
                    "The chatbots “inside Aria” run in the app itself: nothing else to install. Models over 8 GB answer more slowly and, with 16 GB of RAM, can slow down the whole Mac."))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            if st.ollamaInstalled && !st.ollama {
                Text(tr("Ollama è installato ma spento: aprilo solo se vuoi usare anche i suoi modelli (Aria funziona senza).", "Ollama is installed but not running: open it only if you also want to use its models (Aria works without it).")).font(.caption).foregroundStyle(.secondary)
            }
            if current?.reasoning == true {
                Text(tr("Questo chatbot «ragiona» prima di rispondere: Aria glielo disattiva per non farti aspettare.", "This chatbot “reasons” before answering: Aria switches that off so you don't have to wait.")).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func modelRow(kind: String, id: String, label: String, detail: String, mb: Double?, block: String?) -> some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 1) {
                Text(label).font(.callout)
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if block == "in uso" {
                Text(tr("In uso", "In use")).font(.caption2.weight(.semibold)).padding(.horizontal, 7).padding(.vertical, 2)
                    .background(Color.accentColor.opacity(0.2), in: Capsule())
            }
            Button {
                pending = PendingRemoval(kind: kind, id: id, label: label, mb: mb)
            } label: {
                Image(systemName: "trash")
            }
            .buttonStyle(.borderless)
            .disabled(block != nil || m.busy)
            .help(block == "in uso" ? tr("È quello che Aria sta usando: scegline un altro prima di toglierlo.", "It is the one Aria is using: pick another before removing it.")
                  : block != nil ? tr("È l'unico installato: Aria ha bisogno di almeno uno.", "It is the only one installed: Aria needs at least one.") : tr("Rimuovi dal Mac", "Remove from this Mac"))
        }
        .padding(.vertical, 6).padding(.horizontal, 10)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.04)))
    }

    private func installedModels(_ st: SettingsStatus) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(tr("Modelli installati", "Installed models")).font(.headline)
            Text(tr("Toglili per liberare spazio. Aria ha bisogno di almeno un modello di riconoscimento vocale e uno di chatbot, e non si può togliere quello in uso. Puoi riscaricarli quando vuoi.",
                    "Remove them to free up space. Aria needs at least one speech recognition model and one chatbot, and the one in use can't be removed. You can download them again whenever you like."))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Text(tr("Riconoscimento vocale", "Speech recognition")).font(.subheadline.weight(.medium)).padding(.top, 4)
            ForEach(st.sttModels.filter { $0.installed }) { s in
                modelRow(kind: "stt", id: s.repo, label: s.label, detail: s.mb.map { sizeText($0) } ?? "—", mb: s.mb, block: s.block)
            }
            Text("Chatbot").font(.subheadline.weight(.medium)).padding(.top, 4)
            ForEach(st.llmModels.filter { $0.installed }) { l in
                modelRow(kind: "llm", id: l.ref, label: l.label,
                         detail: (l.gb.map { gbText($0) + " GB · " } ?? "") + (l.source == "ollama" ? "Ollama" : tr("dentro Aria", "inside Aria")), mb: l.gb.map { $0 * 1000 }, block: l.block)
            }
        }
    }

    private func summary(_ st: SettingsStatus) -> some View {
        Group {
            if let r = m.ramEstimate {
                let tight = (st.ramTotalGb ?? 16) * 0.7 < r.gb
                Label(tr("Memoria stimata con questa scelta: ≈ \(gbText(r.gb)) GB su \(gbText(st.ramTotalGb ?? 16)) GB" + (r.measured ? " (misurata)" : "") +
                         (tight ? ". È tanta: chiudi le altre app, o il Mac rallenta." : "."),
                         "Estimated memory with this choice: ≈ \(gbText(r.gb)) GB out of \(gbText(st.ramTotalGb ?? 16)) GB" + (r.measured ? " (measured)" : "") +
                         (tight ? ". That's a lot: close your other apps, or the Mac slows down." : ".")),
                      systemImage: tight ? "exclamationmark.triangle.fill" : "memorychip")
                    .font(.callout).foregroundStyle(tight ? .orange : .secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func actions(_ st: SettingsStatus) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if m.busy {
                if let f = m.fraction { ProgressView(value: f) } else { ProgressView().controlSize(.small) }
                Text(m.progressText).font(.callout).monospacedDigit()
                if m.downloading { Button(tr("Annulla il download", "Cancel the download")) { m.cancel() } }
            } else {
                HStack(spacing: 12) {
                    if !m.nothingMissing && m.namesOK {
                        let known = m.missingMB
                        Button { m.download() } label: {
                            Label(tr("Scarica ciò che manca", "Download what's missing") + (known.map { " (\(sizeText($0)))" } ?? tr(" (peso da verificare)", " (size to be checked)")), systemImage: "arrow.down.circle.fill")
                        }
                        .controlSize(.large)
                    }
                    Button { Task { await m.apply() } } label: {
                        Label(tr("Applica e riavvia Aria", "Apply and restart Aria"), systemImage: "arrow.triangle.2.circlepath")
                    }
                    .controlSize(.large)
                    .keyboardShortcut(.defaultAction)
                    .disabled(!m.canApply)
                }
                if !m.nothingMissing && m.namesOK {
                    let tooBig = m.missingMB.map { (st.diskFreeGb * 1000) < $0 + 1500 } ?? false
                    Text(tr("Spazio libero sul Mac: \(String(format: "%.0f", st.diskFreeGb)) GB." + (tooBig ? " Non basta: libera spazio prima di scaricare." : " Con la tua rete il download può richiedere molto tempo; se lo interrompi riparte da dove era arrivato."),
                            "Free space on the Mac: \(String(format: "%.0f", st.diskFreeGb)) GB." + (tooBig ? " That's not enough: free up space before downloading." : " On your network the download can take a long time; if you stop it, it resumes where it left off.")))
                        .font(.caption).foregroundStyle(tooBig ? .orange : .secondary).fixedSize(horizontal: false, vertical: true)
                } else if !m.canApply && m.nothingMissing && !m.isChanged {
                    Text(tr("Stai già usando questa configurazione.", "You are already using this configuration.")).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
    }
}

// MARK: - finestra

@MainActor
final class SettingsWindowController: NSObject, NSWindowDelegate {
    static let shared = SettingsWindowController()
    let model = SettingsModel()
    private var window: NSWindow?

    func show(voices: [(title: String, names: [String])], currentVoice: String, onVoice: @escaping (String) -> Void, onApplied: @escaping () -> Void, onLanguage: @escaping () -> Void = {}) {
        model.onApplied = onApplied
        model.onLanguage = { [weak self] in
            onLanguage()
            self?.window?.title = tr("Impostazioni di Aria", "Aria Settings")
        }
        model.voiceGroups = voices
        model.voice = currentVoice
        model.onVoice = onVoice
        if window == nil {
            let w = NSWindow(contentViewController: NSHostingController(rootView: SettingsView(m: model)))
            w.title = tr("Impostazioni di Aria", "Aria Settings")
            w.styleMask = [.titled, .closable, .miniaturizable, .resizable]
            w.setContentSize(NSSize(width: 760, height: 860))
            w.isReleasedWhenClosed = false
            w.delegate = self
            w.center()
            window = w
        }
        model.error = nil; model.notice = nil
        Task { await model.refresh() }
        NSApp.setActivationPolicy(.regular)                // finche' e' aperta: finestra normale, con icona nel Dock
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)              // di nuovo solo barra dei menu
    }
}
