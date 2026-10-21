import AppKit
import WebKit

/// La "schermatina": un pannello di vetro che fluttua sopra tutto, senza rubare il focus.
final class OverlayController {
    private let panel: NSPanel
    private let web: WKWebView
    private let size = NSSize(width: 520, height: 330)
    private var hideWork: DispatchWorkItem?
    private(set) var visible = false

    init() {
        panel = NSPanel(contentRect: NSRect(origin: .zero, size: size),
                        styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true
        panel.hidesOnDeactivate = false
        panel.ignoresMouseEvents = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle, .stationary]
        panel.appearance = NSAppearance(named: .darkAqua)         // sempre scuro: punti e testo bianchi si leggono su qualunque sfondo
        panel.alphaValue = 0

        let cfg = WKWebViewConfiguration()
        cfg.userContentController.addUserScript(WKUserScript(source: "window.ARIA_LANG = '\(L10n.code)';", injectionTime: .atDocumentStart, forMainFrameOnly: true))      // la schermatina parte gia' nella lingua giusta
        web = WKWebView(frame: NSRect(origin: .zero, size: size), configuration: cfg)
        web.setValue(false, forKey: "drawsBackground")
        if #available(macOS 12.0, *) { web.underPageBackgroundColor = .clear }
        web.autoresizingMask = [.width, .height]

        if #available(macOS 26.0, *) {
            let glass = NSGlassEffectView(frame: NSRect(origin: .zero, size: size))
            glass.cornerRadius = 32
            glass.tintColor = NSColor(white: 0.04, alpha: 0.42)
            glass.contentView = web
            panel.contentView = glass
        } else {
            let fx = NSVisualEffectView(frame: NSRect(origin: .zero, size: size))
            fx.material = .hudWindow
            fx.blendingMode = .behindWindow
            fx.state = .active
            fx.wantsLayer = true
            fx.layer?.cornerRadius = 32
            fx.layer?.masksToBounds = true
            fx.addSubview(web)
            panel.contentView = fx
        }
        loadPage()
    }

    /// Cambia la lingua delle scritte della schermatina (senza ricaricarla).
    func setLanguage(_ code: String) {
        web.configuration.userContentController.removeAllUserScripts()
        web.configuration.userContentController.addUserScript(WKUserScript(source: "window.ARIA_LANG = '\(code)';", injectionTime: .atDocumentStart, forMainFrameOnly: true))
        web.evaluateJavaScript("window.ariaLang && window.ariaLang('\(code)')", completionHandler: nil)
    }

    /// Solo per i test: salva il contenuto della pagina in un PNG.
    func snapshot(to path: String) {
        web.takeSnapshot(with: nil) { image, _ in
            guard let img = image, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
                  let png = rep.representation(using: .png, properties: [:]) else { return }
            try? png.write(to: URL(fileURLWithPath: path))
        }
    }

    private func loadPage() {
        if let url = Bundle.main.url(forResource: "overlay", withExtension: "html") {
            web.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        } else if let dev = ProcessInfo.processInfo.environment["ARIA_OVERLAY_URL"], let url = URL(string: dev) {
            web.load(URLRequest(url: url))
        } else {
            Paths.log(tr("overlay.html non trovato nel bundle", "overlay.html not found in the bundle"))
        }
    }

    private func targetOrigin() -> NSPoint {
        let mouse = NSEvent.mouseLocation
        let screen = NSScreen.screens.first(where: { NSMouseInRect(mouse, $0.frame, false) }) ?? NSScreen.main ?? NSScreen.screens[0]
        let f = screen.visibleFrame
        return NSPoint(x: f.midX - size.width / 2, y: f.minY + 64)
    }

    func show() {
        hideWork?.cancel()
        let end = targetOrigin()
        if !visible {
            panel.setFrameOrigin(NSPoint(x: end.x, y: end.y - 26))
            panel.alphaValue = 0
            panel.orderFrontRegardless()
            visible = true
        }
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.32
            ctx.timingFunction = CAMediaTimingFunction(controlPoints: 0.2, 0.9, 0.25, 1.0)
            panel.animator().alphaValue = 1
            panel.animator().setFrameOrigin(end)
        }
    }

    /// Nasconde dopo `delay` secondi, a meno che nel frattempo non arrivi un nuovo `show()`.
    func hide(after delay: TimeInterval = 2.6) {
        hideWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self = self else { return }
            NSAnimationContext.runAnimationGroup({ ctx in
                ctx.duration = 0.45
                self.panel.animator().alphaValue = 0
                var o = self.panel.frame.origin; o.y -= 16
                self.panel.animator().setFrameOrigin(o)
            }, completionHandler: {
                if self.panel.alphaValue < 0.05 { self.panel.orderOut(nil); self.visible = false }
            })
        }
        hideWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
    }
}
