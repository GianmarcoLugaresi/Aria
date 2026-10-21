import AppKit
import AVFoundation
import Carbon.HIToolbox
import ServiceManagement

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private let backend = BackendManager()
    private let client = BackendClient()
    private let overlay = OverlayController()
    private var hotKey: HotKey?

    private var state = "idle"
    private var muted = false
    private var currentVoice = ""
    private var micDenied = false
    private var problem: String?
    private var ready = false
    private var paused = false                                         // a batteria con lo schermo spento il backend smette di ascoltare
    private var wakePhrase = "Hey Aria"                                // la frase di attivazione vera: la dice il backend (config.yaml), qui non e' scritta a mano
    private var signalSources: [DispatchSourceSignal] = []

    private let femaleVoices = ["lola", "vera", "eve", "jane", "mary", "cosette", "anna", "estelle", "fantine"]
    private let maleVoices = ["giovanni", "paul", "george", "michael", "javert"]
    private let naturalOnlyVoices = ["aria", "chiara", "elena", "marco"]     // esistono solo con la «voce naturale» accesa (Impostazioni)
    // In inglese le voci di Pocket TTS hanno gli stessi nomi (parlano inglese); la voce naturale c'e' solo in italiano.
    private let femaleVoicesEn = ["alba", "anna", "azelma", "cosette", "eponine", "eve", "fantine", "jane", "mary", "vera"]       // solo voci registrate da persone che parlano inglese (lola, estelle… hanno l'accento spagnolo, francese…)
    private let maleVoicesEn = ["charles", "george", "jean", "javert", "marius", "michael", "paul"]
    private var voiceGroups: [(title: String, names: [String])] {
        if L10n.isEnglish { return [("Female voices", femaleVoicesEn), ("Male voices", maleVoicesEn)] }
        return [("Voci femminili", femaleVoices), ("Voci maschili", maleVoices), ("Solo con la voce naturale", naturalOnlyVoices)]
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        // una sola copia alla volta
        let me = Bundle.main.bundleIdentifier ?? "it.aria.assistente"
        if NSRunningApplication.runningApplications(withBundleIdentifier: me).count > 1 {
            Paths.log(tr("Aria e' gia' aperta: esco", "Aria is already open: quitting"))
            NSApp.terminate(nil)
            return
        }
        Paths.log(tr("Aria avviata", "Aria started"))
        for sig in [SIGTERM, SIGINT, SIGHUP] {                         // chiusura "gentile" anche da terminale: ferma il backend
            signal(sig, SIG_IGN)
            let src = DispatchSource.makeSignalSource(signal: sig, queue: .main)
            src.setEventHandler { NSApp.terminate(nil) }
            src.resume()
            signalSources.append(src)
        }
        setupStatusItem()
        requestMicrophone()

        // ⌥ + Spazio: se sta lavorando la ferma, altrimenti la sveglia
        hotKey = HotKey(keyCode: UInt32(kVK_Space), modifiers: UInt32(optionKey)) { [weak self] in self?.hotkeyPressed() }

        client.onMessage = { [weak self] in self?.handle($0) }
        client.onConnection = { [weak self] ok in
            self?.refreshMenu()
            if !ok { self?.state = "idle" }
        }
        backend.onProblem = { [weak self] p in self?.problem = p; self?.refreshMenu() }
        backend.start()
        client.connect()
        if ProcessInfo.processInfo.environment["ARIA_OPEN_SETTINGS"] != nil {         // debug: apre subito le Impostazioni
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in self?.openSettings() }
        }
        if let spec = ProcessInfo.processInfo.environment["ARIA_SETTINGS_SELFTEST"] {  // debug: esegue le azioni dei pulsanti (vedi Settings.swift)
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
                self?.openSettings()
                Task { @MainActor in await SettingsWindowController.shared.model.selfTest(spec) }
            }
        }
        if let dir = ProcessInfo.processInfo.environment["ARIA_SNAPSHOT_DIR"] {      // debug: foto periodiche dell'overlay
            var n = 0
            Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self] _ in
                n += 1
                self?.overlay.snapshot(to: "\(dir)/overlay_\(n).png")
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        client.close()
        backend.stop()
    }

    // MARK: - barra dei menu
    private func setupStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        updateIcon()
        statusItem.menu = NSMenu()
        refreshMenu()
    }

    // Il logo di Aria (Resources/MenuIcon*.png, nero con trasparenza, 36 px = 18 pt @2x).
    // A riposo e' un'immagine "template": macOS la colora da solo per barra chiara/scura. Quando lavora prende il colore dello stato (come la schermata).
    private lazy var menuIcon = AppDelegate.loadMenuMask("MenuIcon")
    private lazy var menuIconMuted = AppDelegate.loadMenuMask("MenuIconMuted")
    private static let stateColors: [String: NSColor] = [
        "listening": NSColor(srgbRed: 0.10, green: 0.70, blue: 0.92, alpha: 1),
        "thinking": NSColor(srgbRed: 0.62, green: 0.36, blue: 0.95, alpha: 1),
        "speaking": NSColor(srgbRed: 0.95, green: 0.34, blue: 0.62, alpha: 1),
        "error": NSColor(srgbRed: 1.00, green: 0.40, blue: 0.30, alpha: 1),
    ]

    private static func loadMenuMask(_ name: String) -> NSImage? {
        guard let u = Bundle.main.url(forResource: name, withExtension: "png"), let i = NSImage(contentsOf: u) else { return nil }
        i.size = NSSize(width: 18, height: 18)
        return i
    }

    private func tinted(_ mask: NSImage, _ color: NSColor) -> NSImage {
        let img = NSImage(size: mask.size, flipped: false) { rect in
            mask.draw(in: rect)
            color.set()
            rect.fill(using: .sourceIn)
            return true
        }
        img.isTemplate = false
        return img
    }

    private func updateIcon() {
        guard let b = statusItem.button else { return }
        guard let base = menuIcon, let slashed = menuIconMuted else {          // risorsa mancante: simbolo di sistema
            let sym = NSImage(systemSymbolName: muted ? "mic.slash" : "waveform", accessibilityDescription: "Aria")
            sym?.isTemplate = true
            b.image = sym
            return
        }
        if muted {
            slashed.isTemplate = true
            b.image = slashed
        } else if problem != nil, let c = AppDelegate.stateColors["error"] {
            b.image = tinted(base, c)
        } else if let c = AppDelegate.stateColors[state] {
            b.image = tinted(base, c)
        } else {
            base.isTemplate = true
            b.image = base
        }
        b.image?.accessibilityDescription = "Aria"
    }

    private func refreshMenu() {
        let m = NSMenu()
        let wake = NSMenuItem(title: state == "idle" ? tr("Parla con Aria", "Talk to Aria") : tr("Ferma Aria", "Stop Aria"), action: #selector(hotkeyPressed), keyEquivalent: " ")
        wake.keyEquivalentModifierMask = [.option]
        wake.target = self
        m.addItem(wake)
        m.addItem(.separator())

        for line in wrapMenuText(statusText()) {                          // lo stato puo' essere lungo (es. il download dei modelli): a capo, senza allargare il pannello
            let stateItem = NSMenuItem(title: line, action: nil, keyEquivalent: "")
            stateItem.isEnabled = false
            m.addItem(stateItem)
        }
        if micDenied {
            let fix = NSMenuItem(title: tr("Microfono non autorizzato: apri le impostazioni…", "Microphone not allowed: open settings…"), action: #selector(openMicSettings), keyEquivalent: "")
            fix.target = self
            m.addItem(fix)
        }
        m.addItem(.separator())

        let voiceMenu = NSMenu()
        for (title, list) in voiceGroups {
            let h = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            h.isEnabled = false
            voiceMenu.addItem(h)
            for v in list {
                let it = NSMenuItem(title: v.capitalized, action: #selector(pickVoice(_:)), keyEquivalent: "")
                it.representedObject = v
                it.target = self
                it.state = (v == currentVoice) ? .on : .off
                voiceMenu.addItem(it)
            }
            voiceMenu.addItem(.separator())
        }
        let voiceItem = NSMenuItem(title: tr("Voce", "Voice"), action: nil, keyEquivalent: "")
        voiceItem.submenu = voiceMenu
        m.addItem(voiceItem)

        let mute = NSMenuItem(title: tr("Silenzia il microfono (niente “\(wakePhrase)”)", "Mute the microphone (no “\(wakePhrase)”)"), action: #selector(toggleMute), keyEquivalent: "")
        mute.target = self
        mute.state = muted ? .on : .off
        m.addItem(mute)

        let login = NSMenuItem(title: tr("Apri all'accesso", "Open at login"), action: #selector(toggleLogin), keyEquivalent: "")
        login.target = self
        login.state = (SMAppService.mainApp.status == .enabled) ? .on : .off
        m.addItem(login)
        m.addItem(.separator())

        let settings = NSMenuItem(title: tr("Impostazioni…", "Settings…"), action: #selector(openSettings), keyEquivalent: ",")
        settings.target = self
        m.addItem(settings)
        let logs = NSMenuItem(title: tr("Mostra i log", "Show logs"), action: #selector(openLogs), keyEquivalent: "")
        logs.target = self
        m.addItem(logs)
        let quit = NSMenuItem(title: tr("Esci da Aria", "Quit Aria"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        m.addItem(quit)
        statusItem.menu = m
        updateIcon()
    }

    private func statusText() -> String {
        if let p = problem { return "⚠︎ " + p }
        if !client.connected { return tr("Stato: in avvio…", "Status: starting…") }
        if !ready { return tr("Stato: sto caricando i modelli…", "Status: loading the models…") }
        if muted { return tr("Stato: microfono silenziato", "Status: microphone muted") }
        if paused && state == "idle" { return tr("Stato: in pausa (a batteria, schermo spento)", "Status: paused (on battery, screen off)") }
        switch state {
        case "listening": return tr("Stato: ti ascolta", "Status: listening")
        case "thinking": return tr("Stato: ci pensa", "Status: thinking")
        case "speaking": return tr("Stato: sta parlando", "Status: speaking")
        default: return tr("Stato: pronta, di' «\(wakePhrase)»", "Status: ready, say “\(wakePhrase)”")
        }
    }

    // MARK: - eventi dal backend
    private func handle(_ m: [String: Any]) {
        if let s = m["state"] as? String, s != state {
            state = s
            if s == "idle" { overlay.hide() } else { overlay.show() }
            refreshMenu()
        }
        if let v = m["voice"] as? String, v != currentVoice {
            currentVoice = v
            refreshMenu()
            MainActor.assumeIsolated { SettingsWindowController.shared.model.voice = v }
        }
        if let mu = m["muted"] as? Bool, mu != muted { muted = mu; refreshMenu() }
        if let r = m["ready"] as? Bool, r != ready { ready = r; refreshMenu() }
        if let p = m["paused"] as? Bool, p != paused { paused = p; refreshMenu() }
        if let w = m["wake_phrase"] as? String, !w.isEmpty {
            let pretty = w.split(separator: " ").map { $0.prefix(1).uppercased() + $0.dropFirst() }.joined(separator: " ")
            if pretty != wakePhrase { wakePhrase = pretty; refreshMenu() }
        }
    }

    // MARK: - azioni
    @objc private func hotkeyPressed() {
        if state == "idle" {
            overlay.show()                           // reazione immediata, prima ancora che risponda il backend
            client.send(["cmd": "wake"])
        } else {
            client.send(["cmd": "stop"])
        }
    }

    @objc private func pickVoice(_ sender: NSMenuItem) {
        guard let v = sender.representedObject as? String else { return }
        setVoice(v)
    }

    /// Cambia voce (dal menu o dalle Impostazioni): il backend la salva e dice subito una frase di prova.
    private func setVoice(_ v: String) {
        currentVoice = v
        client.send(["cmd": "voice", "name": v])
        refreshMenu()
        MainActor.assumeIsolated { SettingsWindowController.shared.model.voice = v }
    }

    @objc private func toggleMute() {
        muted.toggle()
        client.send(["cmd": muted ? "mute" : "unmute"])
        refreshMenu()
    }

    @objc private func toggleLogin() {
        do {
            if SMAppService.mainApp.status == .enabled { try SMAppService.mainApp.unregister() }
            else { try SMAppService.mainApp.register() }
        } catch { Paths.log("login item: \(error.localizedDescription)") }
        refreshMenu()
    }

    @objc private func openSettings() {
        MainActor.assumeIsolated {                                // arriva dal menu: e' gia' il thread principale
            SettingsWindowController.shared.show(
                voices: voiceGroups, currentVoice: currentVoice,
                onVoice: { [weak self] v in self?.setVoice(v) },
                onApplied: { [weak self] in
                    guard let self = self else { return }
                    self.ready = false                                // il menu torna a dire "sto caricando i modelli…"
                    self.refreshMenu()
                    self.backend.restart()
                },
                onLanguage: { [weak self] in self?.languageChanged() })
        }
    }

    /// La lingua e' cambiata nelle Impostazioni: scritte nuove (menu, schermatina) e il cervello riparte nella lingua nuova (voce, riconoscimento, carattere).
    private func languageChanged() {
        L10n.reload()
        overlay.setLanguage(L10n.code)
        ready = false
        currentVoice = ""                                             // le voci della lingua nuova hanno altri nomi: il cervello dira' quella in uso
        MainActor.assumeIsolated { SettingsWindowController.shared.model.voiceGroups = voiceGroups; SettingsWindowController.shared.model.voice = "" }
        refreshMenu()
        backend.restart()
    }

    @objc private func openLogs() { NSWorkspace.shared.open(Paths.logs) }

    @objc private func openMicSettings() {
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")!)
    }

    private func requestMicrophone() {
        let env = ProcessInfo.processInfo.environment
        if env["ARIA_NO_BACKEND"] != nil || env["ARIA_FAKE_AUDIO"] != nil { return }     // prove senza backend o con audio finto: niente richiesta microfono
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: break
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { ok in
                DispatchQueue.main.async { self.micDenied = !ok; self.refreshMenu() }
            }
        default:
            micDenied = true
        }
    }
}
