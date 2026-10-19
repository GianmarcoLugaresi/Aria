// Gli elementi dell'interfaccia dell'app in primo piano (pulsanti, menu, campi, icone con descrizione) con la loro POSIZIONE ESATTA, letti con l'API Accessibilita' di macOS.
// Serve a Aria per indicare anche le icone senza scritta e le voci di menu. Tutto locale, solo quando glielo chiedi.
// Protocollo (una riga per richiesta, su stdin/stdout; all'avvio scrive «READY»):
//   «PERM»  -> {"ax":true|false}            (Aria ha il permesso «Accessibilita»?)
//   «ASK»   -> {"ax":true|false}            (lo chiede: macOS mostra la finestra / apre il pannello)
//   «DUMP»  -> {"ax":true,"app":"Finder","win":"build","n":N,"elements":[{"r":"AXButton","t":["Condividi"],"x":0.86,"y":0.06,"w":0.02,"h":0.03,"m":"File"}, ...]}
//             x,y = centro, w,h = dimensioni, da 0 a 1 sullo schermo PRINCIPALE (origine in alto a sinistra); "m" = il menu in alto a cui appartiene (se e' una voce di menu)
// Compilazione: vedi app/install.sh
import AppKit
import ApplicationServices
import Foundation

func say(_ s: String) { FileHandle.standardOutput.write((s + "\n").data(using: .utf8)!) }
func jsonLine(_ obj: Any) -> String {
    guard let d = try? JSONSerialization.data(withJSONObject: obj, options: []), let s = String(data: d, encoding: .utf8) else { return "{\"error\":\"json\"}" }
    return s
}

func attr(_ el: AXUIElement, _ name: String) -> AnyObject? {
    var v: CFTypeRef?
    return AXUIElementCopyAttributeValue(el, name as CFString, &v) == .success ? (v as AnyObject?) : nil
}

func frameOf(_ el: AXUIElement) -> CGRect? {
    guard let pv = attr(el, kAXPositionAttribute), let sv = attr(el, kAXSizeAttribute) else { return nil }
    var p = CGPoint.zero, s = CGSize.zero
    guard AXValueGetValue(pv as! AXValue, .cgPoint, &p), AXValueGetValue(sv as! AXValue, .cgSize, &s) else { return nil }
    return CGRect(origin: p, size: s)
}

func labels(_ el: AXUIElement) -> [String] {
    var out: [String] = []
    for name in [kAXTitleAttribute, kAXDescriptionAttribute, kAXHelpAttribute, "AXPlaceholderValue", kAXValueAttribute, "AXLabel"] {
        if let s = attr(el, name) as? String {
            let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
            if !t.isEmpty && t.count <= 90 && !out.contains(t) { out.append(t) }
        }
    }
    return out
}

func isTrusted(prompt: Bool) -> Bool {
    let opts = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: prompt] as CFDictionary
    return AXIsProcessTrustedWithOptions(opts)
}

func dump() -> String {
    guard isTrusted(prompt: false) else { return jsonLine(["ax": false]) }
    guard let app = NSWorkspace.shared.frontmostApplication else { return jsonLine(["ax": true, "n": 0, "elements": []]) }
    let axApp = AXUIElementCreateApplication(app.processIdentifier)
    AXUIElementSetMessagingTimeout(axApp, 0.4)
    _ = AXUIElementSetAttributeValue(axApp, "AXManualAccessibility" as CFString, kCFBooleanTrue)         // le app Chromium/Electron espongono cosi' anche il contenuto delle pagine
    let screen = NSScreen.screens.first?.frame.size ?? CGSize(width: 1, height: 1)
    let deadline = Date().addingTimeInterval(2.0)
    var elements: [[String: Any]] = []
    var winTitle = ""
    let interesting: Set<String> = ["AXButton", "AXMenuItem", "AXMenuBarItem", "AXMenuButton", "AXPopUpButton", "AXCheckBox", "AXRadioButton", "AXTextField", "AXTextArea", "AXLink", "AXTab",
                                    "AXTabGroup", "AXComboBox", "AXSlider", "AXSearchField", "AXImage", "AXStaticText", "AXCell", "AXRow", "AXDisclosureTriangle", "AXToolbar", "AXSegmentedControl", "AXGroup", "AXHeading"]

    func walk(_ el: AXUIElement, depth: Int, menu: String?) {
        if depth > 16 || elements.count >= 3500 || Date() > deadline { return }
        let role = (attr(el, kAXRoleAttribute) as? String) ?? ""
        var currentMenu = menu
        if depth == 1 && role == "AXMenuBarItem" { currentMenu = (attr(el, kAXTitleAttribute) as? String) ?? menu }
        if interesting.contains(role), let f = frameOf(el), f.width > 2, f.height > 2 {
            var t = labels(el)
            if role == "AXStaticText" || role == "AXGroup" || role == "AXCell" || role == "AXRow" { t = t.filter { $0.count <= 60 } }
            if !t.isEmpty {
                var d: [String: Any] = ["r": role, "t": t, "x": ((f.midX / screen.width) * 1000).rounded() / 1000, "y": ((f.midY / screen.height) * 1000).rounded() / 1000,
                                        "w": ((f.width / screen.width) * 1000).rounded() / 1000, "h": ((f.height / screen.height) * 1000).rounded() / 1000]
                if let m = currentMenu, role == "AXMenuItem" || role == "AXMenuBarItem" { d["m"] = m }
                if let en = attr(el, kAXEnabledAttribute) as? Bool, !en { d["off"] = true }
                elements.append(d)
            }
        }
        if let kids = attr(el, kAXChildrenAttribute) as? [AXUIElement] {
            for k in kids { walk(k, depth: depth + 1, menu: currentMenu) }
        }
    }
    if let wins = attr(axApp, kAXWindowsAttribute) as? [AXUIElement] {
        for (i, w) in wins.enumerated() where i < 4 {
            if i == 0 { winTitle = (attr(w, kAXTitleAttribute) as? String) ?? "" }
            walk(w, depth: 0, menu: nil)
        }
    }
    if let bar = attr(axApp, kAXMenuBarAttribute) {
        walk(bar as! AXUIElement, depth: 0, menu: nil)
    }
    return jsonLine(["ax": true, "app": app.localizedName ?? "", "win": winTitle, "n": elements.count, "elements": elements])
}

say("READY")
while let line = readLine() {
    switch line.split(separator: "\t").first.map(String.init) ?? "" {
    case "PERM": say(jsonLine(["ax": isTrusted(prompt: false)]))
    case "ASK": say(jsonLine(["ax": isTrusted(prompt: true)]))
    case "DUMP": say(dump())
    default: say(jsonLine(["error": "comando sconosciuto"]))
    }
}
