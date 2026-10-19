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
}

private func sizeText(_ mb: Double) -> String {
    let s = mb >= 1000 ? String(format: "%.1f GB", mb / 1000) : "\(Int(mb.rounded())) MB"
    return s.replacingOccurrences(of: ".", with: ",")
}

private func gbText(_ gb: Double) -> String { String(format: "%.1f", gb).replacingOccurrences(of: ".", with: ",") }

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
            id: Self.customID, label: "Personalizzata",
            summary: "Scegli tu il modello di riconoscimento vocale e il chatbot, tra quelli che vuoi.",
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
            var why = "uscita \(code)"
            if case .failure(let e)? = decoded { why = "risposta non valida: \(e)" }
            Paths.log("impostazioni: stato non leggibile (\(why)) \(String(decoding: data.prefix(200), as: UTF8.self))")
            error = "Non riesco a leggere lo stato dei modelli (controlla i log di Aria)."
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
        error = nil; notice = nil; fraction = nil; progressText = "Preparo il download…"
        process = ModelsCLI.stream(["download"] + choiceArgs(),
            onEvent: { [weak self] ev in Task { @MainActor in self?.handle(ev) } },
            onExit: { [weak self] code in Task { @MainActor in await self?.downloadEnded(code) } })
        if process == nil {
            busy = false; downloading = false
            error = "Non riesco ad avviare il download (Python non trovato: rilancia l'installer)."
        }
    }

    private func handle(_ ev: [String: Any]) {
        switch ev["event"] as? String {
        case "start":
            item = ev["item"] as? String ?? ""
            let what = item == "stt" ? "il riconoscimento vocale" : "il chatbot"
            progressText = "Scarico \(what) (\(ev["label"] as? String ?? ""))…"
        case "progress":
            let done = (ev["done"] as? NSNumber)?.doubleValue ?? 0
            let total = (ev["total"] as? NSNumber)?.doubleValue ?? 0
            let what = (ev["item"] as? String ?? item) == "stt" ? "Riconoscimento vocale" : "Chatbot"
            fraction = total > 0 ? min(1, done / total) : nil
            progressText = "\(what): \(sizeText(done / 1e6)) di \(sizeText(total / 1e6))"
        case "error":
            error = ev["message"] as? String
        default: break
        }
    }

    private func downloadEnded(_ code: Int32) async {
        busy = false; downloading = false; process = nil
        if cancelled { notice = "Download interrotto: se lo riavvii riparte da dove era arrivato." }
        else if code == 0 { fraction = 1; notice = "Scaricato." }
        else if error == nil { error = "Il download si è fermato (codice \(code)). Riprova: riparte da dove era arrivato." }
        await refresh(keepSelection: true)
    }

    func cancel() { cancelled = true; process?.terminate() }

    // ---- i poteri di Aria
    func setPower(_ id: String, _ on: Bool) async {
        error = nil
        let (code, data) = await ModelsCLI.run(["power", id, on ? "on" : "off"])
        if code != 0 {
            let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            error = obj?["error"] as? String ?? "Non sono riuscito a cambiare questa impostazione."
        }
        await refresh(keepSelection: true)
    }

    // ---- la frase per chiamarla
    func saveWake() async {
        error = nil; notice = nil
        let (_, data) = await ModelsCLI.run(["wake", "set", wakeText])
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        if obj?["ok"] as? Bool == true {
            notice = "Fatto: da ora si chiama dicendo «\(wakeText.trimmingCharacters(in: .whitespaces))». Riavvio il cervello di Aria (qualche secondo)."
            onApplied?()
        } else { error = obj?["error"] as? String ?? "Non sono riuscito a cambiare la frase." }
        await refresh(keepSelection: true)
    }

    // ---- la cartella di Aria
    func chooseWorkspace() async {
        let panel = NSOpenPanel()
        panel.title = "Cartella di Aria"
        panel.message = "Scegli la cartella dove Aria può scrivere e leggere i suoi file. Meglio una cartella nuova, ad esempio «Aria»."
        panel.prompt = "Scegli"
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
        if obj?["ok"] as? Bool == true { notice = "Cartella impostata: da ora Aria può salvare lì i suoi file." }
        else { error = obj?["error"] as? String ?? "Non sono riuscito a impostare la cartella." }
        await refresh(keepSelection: true)
    }

    func clearWorkspace() async {
        error = nil
        _ = await ModelsCLI.run(["workspace", "clear"])
        notice = "Aria non ha più accesso a nessuna cartella (i file che c'erano restano dove sono)."
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
        busy = true; error = nil; notice = nil; fraction = nil; progressText = "Rimuovo \(label)…"
        let (code, data) = await ModelsCLI.run(["remove", kind, id])
        busy = false
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        if code == 0, obj?["ok"] as? Bool == true {
            let mb = (obj?["freed_mb"] as? NSNumber)?.doubleValue ?? 0
            notice = "Rimosso «\(label)»" + (mb > 0 ? ": liberati \(sizeText(mb))." : ".")
        } else {
            error = obj?["error"] as? String ?? "Non sono riuscito a rimuoverlo."
        }
        await refresh(keepSelection: true)
    }

    func apply() async {
        busy = true; error = nil; notice = nil; fraction = nil; progressText = "Applico la scelta…"
        let (code, data) = await ModelsCLI.run(["apply"] + choiceArgs())
        busy = false
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        if code == 0, obj?["ok"] as? Bool == true {
            notice = "Fatto: Aria si riavvia con la nuova configurazione (ci mette una decina di secondi)."
            onApplied?()
            await refresh()
        } else {
            error = obj?["error"] as? String ?? "Non sono riuscito ad applicare la scelta."
        }
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
                Text(value ?? "scelto da te, qui sotto").font(.caption).foregroundStyle(value == nil ? .secondary : .primary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(c.label).font(.headline)
                Spacer()
                if active {
                    Text("In uso").font(.caption2.weight(.semibold)).padding(.horizontal, 7).padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.2), in: Capsule())
                }
            }
            Text(c.summary).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Divider()
            row("waveform", "Ti ascolta con", c.stt)
            row("sparkles", "Risponde con", c.llm)
            row("memorychip", "Memoria in uso", c.ramGb.map { "≈ \(gbText($0)) GB" + (c.ramMeasured ? "" : " (stima)") })
            Spacer(minLength: 0)
            if c.installed {
                Label("Pronta", systemImage: "checkmark.circle.fill").font(.caption).foregroundStyle(.green)
            } else if let need = c.needMb, c.stt != nil || c.id != SettingsModel.customID {
                Label(need > 0 ? "Da scaricare · \(sizeText(need))" : "Da completare", systemImage: "arrow.down.circle").font(.caption).foregroundStyle(.orange)
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
                        Text("Impostazioni di Aria").font(.title2.weight(.semibold))
                        Text("Tutto resta sul tuo Mac: niente abbonamenti, niente cloud.").font(.callout).foregroundStyle(.secondary)
                    }
                    if let st = m.status {
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
                        ProgressView("Leggo cosa è installato…")
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
        .confirmationDialog("Rimuovere «\(pending?.label ?? "")»?", isPresented: Binding(get: { pending != nil }, set: { if !$0 { pending = nil } }), presenting: pending) { p in
            Button("Rimuovi", role: .destructive) { Task { await m.remove(kind: p.kind, id: p.id, label: p.label) } }
            Button("Annulla", role: .cancel) {}
        } message: { p in
            Text("Libera" + (p.mb.map { " circa \(sizeText($0))" } ?? " spazio") + " sul Mac. Potrai riscaricarlo quando vuoi.")
        }
    }

    private func versions(_ st: SettingsStatus) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Versione").font(.headline)
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 12, alignment: .top), GridItem(.flexible(), spacing: 12, alignment: .top)], spacing: 12) {
                ForEach(m.cards) { c in
                    ProfileCard(c: c, selected: c.id == m.selected, active: c.id == st.activeProfile)
                        .onTapGesture { m.selectCard(c.id) }
                }
            }
            Text("Scegliendo una versione, riconoscimento vocale e chatbot si impostano da soli; se poi cambi uno dei due qui sotto, la scelta diventa «Personalizzata». «Media» è la configurazione di sempre. Le memorie di Leggera, Pesante e Personalizzata sono stime.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func sttLabel(_ s: STTModel) -> String {
        s.label + (s.mb.map { " · " + sizeText($0) } ?? "") + (s.installed ? "" : " · da scaricare")
    }

    private func recognition(_ st: SettingsStatus) -> some View {
        var options = st.sttModels
        if !m.sttIsOther, !m.sttRepo.isEmpty, !options.contains(where: { $0.repo == m.sttRepo }),
           let p = st.profiles.first(where: { $0.stt.name == m.sttRepo }) {      // es. il riconoscimento di config.yaml, che non e' in elenco
            options.append(STTModel(repo: p.stt.name, label: p.stt.label, mb: p.stt.mb, wer: nil, sec: nil, note: "Quello di config.yaml.", installed: p.stt.installed, custom: true, removable: nil, block: nil))
        }
        let info = m.sttIsOther ? nil : options.first { $0.repo == m.sttRepo }
        return VStack(alignment: .leading, spacing: 8) {
            Text("Riconoscimento vocale (cosa capisce di quello che dici)").font(.headline)
            Picker("", selection: Binding(get: { m.sttPickerValue }, set: { m.pickSTT($0) })) {
                ForEach(options) { s in Text(sttLabel(s)).tag(s.repo) }
                Text("Altro modello…").tag(SettingsModel.otherTag)
            }
            .labelsHidden()
            .disabled(m.busy)
            if m.sttIsOther {
                TextField("organizzazione/nome, ad esempio mlx-community/whisper-small-mlx", text: $m.otherSTT)
                    .textFieldStyle(.roundedBorder)
                    .disabled(m.busy)
                Text("Serve un modello nel formato MLX Whisper su Hugging Face (di solito «mlx-community/whisper-…»). Premi «Scarica» per controllarlo e scaricarlo.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            } else if let i = info {
                VStack(alignment: .leading, spacing: 2) {
                    if let w = i.wer {
                        Text("Errori sulle parole (misurati qui su 54 frasi): \(Int(w[0]))% con audio pulito · \(Int(w[1]))% con rumore · \(Int(w[2]))% con volume basso" + (i.sec.map { " · circa \(String(format: "%.2f", $0).replacingOccurrences(of: ".", with: ",")) s a frase" } ?? ""))
                            .font(.caption)
                    } else {
                        Text("Non ancora misurato su questo Mac.").font(.caption)
                    }
                    Text(i.note).font(.caption).foregroundStyle(.secondary)
                }
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func voiceSection() -> some View {
        var groups = m.voiceGroups
        if !m.voice.isEmpty, !groups.contains(where: { $0.names.contains(m.voice) }) { groups.append((title: "Altre", names: [m.voice])) }
        return VStack(alignment: .leading, spacing: 8) {
            Text("Voce (come ti parla Aria)").font(.headline)
            HStack(spacing: 10) {
                Picker("", selection: Binding(get: { m.voice }, set: { m.pickVoice($0) })) {
                    ForEach(groups, id: \.title) { g in
                        Section(g.title) { ForEach(g.names, id: \.self) { Text($0.capitalized).tag($0) } }
                    }
                }
                .labelsHidden()
                Button { m.replayVoice() } label: { Label("Riascolta", systemImage: "speaker.wave.2.fill") }
                    .disabled(m.voice.isEmpty)
            }
            Text("Appena scegli una voce Aria dice una frase di prova, così senti subito se ti piace. La prova non parte se stai parlando con lei o se sta ancora caricando i modelli.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func wakeSection(_ st: SettingsStatus) -> some View {
        let current = (st.wakePhrase ?? "hey aria").split(separator: " ").map { $0.prefix(1).uppercased() + $0.dropFirst() }.joined(separator: " ")
        return VStack(alignment: .leading, spacing: 8) {
            Text("Come la chiami").font(.headline)
            HStack(spacing: 10) {
                TextField(current, text: $m.wakeText)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 260)
                    .onSubmit { Task { await m.saveWake() } }
                Button { Task { await m.saveWake() } } label: { Label("Usa questa", systemImage: "checkmark.circle") }
                    .disabled(m.busy || m.wakeText.trimmingCharacters(in: .whitespaces).isEmpty
                              || m.wakeText.trimmingCharacters(in: .whitespaces).lowercased() == current.lowercased())
            }
            Text("Adesso: «\(current)». Due o tre parole (con una sola si sveglierebbe ogni volta che la senti in una frase). Il riconoscimento accetta anche come la scrive di solito: per «Hey Aria» vanno bene «Ehi Aria», «Ei Aria»…")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func workspaceSection(_ st: SettingsStatus) -> some View {
        let w = st.workspace
        return VStack(alignment: .leading, spacing: 8) {
            Text("Cartella di Aria (dove può scrivere e leggere)").font(.headline)
            if let path = w?.path {
                HStack(spacing: 8) {
                    Image(systemName: w?.valid == true ? "folder.fill" : "exclamationmark.triangle.fill").foregroundStyle(w?.valid == true ? Color.accentColor : .orange)
                    VStack(alignment: .leading, spacing: 1) {
                        Text((path as NSString).lastPathComponent).font(.callout)
                        Text(path + (w?.valid == true ? " · \(w?.files ?? 0) file" : "")).font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                    }
                }
                if let e = w?.error { Text(e).font(.caption).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true) }
            } else {
                Text("Nessuna cartella: Aria non salva né legge file.").font(.callout).foregroundStyle(.secondary)
            }
            HStack(spacing: 10) {
                Button { Task { await m.chooseWorkspace() } } label: { Label(w?.path == nil ? "Scegli una cartella…" : "Cambia cartella…", systemImage: "folder.badge.plus") }
                if w?.path != nil {
                    Button { m.openWorkspace() } label: { Label("Apri", systemImage: "arrow.up.forward.app") }.disabled(w?.valid != true)
                    Button(role: .destructive) { Task { await m.clearWorkspace() } } label: { Label("Togli accesso", systemImage: "xmark.circle") }
                }
            }
            .disabled(m.busy)
            Text("Con una cartella impostata puoi dire: «scrivimi un testo sulla fotosintesi», «fai una ricerca veloce sui polpi» (la salva con le fonti), «aggiungi latte alla lista della spesa», «segna una nota…», «leggimi il file…», «riassumi il documento…», «apri la cartella». Aria lavora SOLO lì dentro: solo file di testo, non cancella niente, non sovrascrive (se il nome esiste ne crea uno nuovo) e non esce dalla cartella. macOS può chiederti di consentire l'accesso a Documenti o Scrivania la prima volta.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func powersSection(_ st: SettingsStatus) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Cosa può fare Aria sul tuo Mac").font(.headline)
            ForEach(st.powers ?? []) { p in
                Toggle(isOn: Binding(get: { p.enabled }, set: { v in Task { await m.setPower(p.id, v) } })) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(p.label).font(.callout)
                        Text(p.hint).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .disabled(m.busy)
            }
            Text("Aria li usa solo quando glielo chiedi a voce, mai da sola e mai su ordine di un testo trovato sul web. Le Scorciatoie chiedono sempre «sì» prima di partire. La prima volta macOS chiede il permesso di far controllare ad Aria Calendario, Promemoria, Musica…: consentilo (puoi toglierlo in Impostazioni di Sistema → Privacy e sicurezza → Automazione).")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func llmLabel(_ l: LLMModel) -> String {
        l.label + (l.gb.map { " · \(gbText($0)) GB" } ?? "") + (l.heavy ? " · molto pesante" : "") + (l.installed ? "" : " · da scaricare")
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
            Text("Chatbot (cosa ti risponde)").font(.headline)
            Picker("", selection: Binding(get: { m.llmPickerValue }, set: { m.pickLLM($0) })) {
                Section("Dentro Aria · non serve Ollama") { ForEach(inside) { Text(llmLabel($0)).tag($0.ref) } }
                if !ollama.isEmpty { Section("Ollama · installati su questo Mac") { ForEach(ollama) { Text(llmLabel($0)).tag($0.ref) } } }
                Text("Altro chatbot…").tag(SettingsModel.otherTag)
            }
            .labelsHidden()
            .disabled(m.busy)
            if m.llmIsOther {
                TextField("mlx-community/… (dentro Aria) oppure llama3.1:8b (Ollama)", text: $m.otherLLM)
                    .textFieldStyle(.roundedBorder)
                    .disabled(m.busy)
                Text("Un nome con i due punti (llama3.1:8b) è un modello di Ollama; un nome con la barra (organizzazione/nome) è un modello MLX di Hugging Face, che gira dentro Aria. Premi «Scarica» per controllarlo e prenderlo.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            } else if let c = current, !c.note.isEmpty {
                Text(c.note).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Text("I chatbot «dentro Aria» girano nell'app stessa: non serve installare altro. I modelli oltre gli 8 GB rispondono più lentamente e, con 16 GB di RAM, possono rallentare tutto il Mac.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            if st.ollamaInstalled && !st.ollama {
                Text("Ollama è installato ma spento: aprilo solo se vuoi usare anche i suoi modelli (Aria funziona senza).").font(.caption).foregroundStyle(.secondary)
            }
            if current?.reasoning == true {
                Text("Questo chatbot «ragiona» prima di rispondere: Aria glielo disattiva per non farti aspettare.").font(.caption).foregroundStyle(.secondary)
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
                Text("In uso").font(.caption2.weight(.semibold)).padding(.horizontal, 7).padding(.vertical, 2)
                    .background(Color.accentColor.opacity(0.2), in: Capsule())
            }
            Button {
                pending = PendingRemoval(kind: kind, id: id, label: label, mb: mb)
            } label: {
                Image(systemName: "trash")
            }
            .buttonStyle(.borderless)
            .disabled(block != nil || m.busy)
            .help(block == "in uso" ? "È quello che Aria sta usando: scegline un altro prima di toglierlo."
                  : block != nil ? "È l'unico installato: Aria ha bisogno di almeno uno." : "Rimuovi dal Mac")
        }
        .padding(.vertical, 6).padding(.horizontal, 10)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.04)))
    }

    private func installedModels(_ st: SettingsStatus) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Modelli installati").font(.headline)
            Text("Toglili per liberare spazio. Aria ha bisogno di almeno un modello di riconoscimento vocale e uno di chatbot, e non si può togliere quello in uso. Puoi riscaricarli quando vuoi.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Text("Riconoscimento vocale").font(.subheadline.weight(.medium)).padding(.top, 4)
            ForEach(st.sttModels.filter { $0.installed }) { s in
                modelRow(kind: "stt", id: s.repo, label: s.label, detail: s.mb.map { sizeText($0) } ?? "—", mb: s.mb, block: s.block)
            }
            Text("Chatbot").font(.subheadline.weight(.medium)).padding(.top, 4)
            ForEach(st.llmModels.filter { $0.installed }) { l in
                modelRow(kind: "llm", id: l.ref, label: l.label,
                         detail: (l.gb.map { gbText($0) + " GB · " } ?? "") + (l.source == "ollama" ? "Ollama" : "dentro Aria"), mb: l.gb.map { $0 * 1000 }, block: l.block)
            }
        }
    }

    private func summary(_ st: SettingsStatus) -> some View {
        Group {
            if let r = m.ramEstimate {
                let tight = (st.ramTotalGb ?? 16) * 0.7 < r.gb
                Label("Memoria stimata con questa scelta: ≈ \(gbText(r.gb)) GB su \(gbText(st.ramTotalGb ?? 16)) GB" + (r.measured ? " (misurata)" : "") +
                      (tight ? ". È tanta: chiudi le altre app, o il Mac rallenta." : "."),
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
                if m.downloading { Button("Annulla il download") { m.cancel() } }
            } else {
                HStack(spacing: 12) {
                    if !m.nothingMissing && m.namesOK {
                        let known = m.missingMB
                        Button { m.download() } label: {
                            Label("Scarica ciò che manca" + (known.map { " (\(sizeText($0)))" } ?? " (peso da verificare)"), systemImage: "arrow.down.circle.fill")
                        }
                        .controlSize(.large)
                    }
                    Button { Task { await m.apply() } } label: {
                        Label("Applica e riavvia Aria", systemImage: "arrow.triangle.2.circlepath")
                    }
                    .controlSize(.large)
                    .keyboardShortcut(.defaultAction)
                    .disabled(!m.canApply)
                }
                if !m.nothingMissing && m.namesOK {
                    let tooBig = m.missingMB.map { (st.diskFreeGb * 1000) < $0 + 1500 } ?? false
                    Text("Spazio libero sul Mac: \(String(format: "%.0f", st.diskFreeGb)) GB." + (tooBig ? " Non basta: libera spazio prima di scaricare." : " Con la tua rete il download può richiedere molto tempo; se lo interrompi riparte da dove era arrivato."))
                        .font(.caption).foregroundStyle(tooBig ? .orange : .secondary).fixedSize(horizontal: false, vertical: true)
                } else if !m.canApply && m.nothingMissing && !m.isChanged {
                    Text("Stai già usando questa configurazione.").font(.caption).foregroundStyle(.secondary)
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

    func show(voices: [(title: String, names: [String])], currentVoice: String, onVoice: @escaping (String) -> Void, onApplied: @escaping () -> Void) {
        model.onApplied = onApplied
        model.voiceGroups = voices
        model.voice = currentVoice
        model.onVoice = onVoice
        if window == nil {
            let w = NSWindow(contentViewController: NSHostingController(rootView: SettingsView(m: model)))
            w.title = "Impostazioni di Aria"
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
