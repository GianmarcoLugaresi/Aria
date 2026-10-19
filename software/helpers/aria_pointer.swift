// Indica qualcosa sullo schermo: un riquadro luminoso che pulsa intorno a una zona, per qualche secondo, senza rubare il focus ne' i clic.
// Uso:  aria-pointer [--seconds 6] [--snapshot out.png] x,y,w,h [x,y,w,h ...]
//   x,y = centro, w,h = dimensioni, tutto da 0 a 1 con l'origine in alto a sinistra dello schermo PRINCIPALE (come li da aria-apple-ocr).
//   Il primo riquadro e' quello principale (luminoso), gli altri piu' tenui. --snapshot disegna in un PNG invece che sullo schermo (per provare l'aspetto).
// Compilazione: vedi app/install.sh
import AppKit
import QuartzCore

var seconds = 6.0
var snapshot: String?
var boxes: [CGRect] = []
var it = CommandLine.arguments.dropFirst().makeIterator()
while let a = it.next() {
    switch a {
    case "--seconds": seconds = Double(it.next() ?? "") ?? 6.0
    case "--snapshot": snapshot = it.next()
    default:
        let p = a.split(separator: ",").compactMap { Double($0) }
        if p.count == 4 { boxes.append(CGRect(x: p[0] - p[2] / 2, y: p[1] - p[3] / 2, width: p[2], height: p[3])) }      // x,y sono il CENTRO: il rettangolo parte da meta' meno
    }
}
guard !boxes.isEmpty, let screen = NSScreen.screens.first else { exit(1) }

let size = screen.frame.size
let cyan = NSColor(red: 0.41, green: 0.88, blue: 1.0, alpha: 1.0).cgColor
let pink = NSColor(red: 1.0, green: 0.66, blue: 0.82, alpha: 1.0).cgColor

/// L'albero dei livelli con i riquadri (coordinate in punti, origine in basso a sinistra come CoreAnimation).
func makeRoot(size: CGSize, boxes: [CGRect]) -> CALayer {
    let root = CALayer()
    root.frame = CGRect(origin: .zero, size: size)
    for (i, b) in boxes.enumerated() {
        let primary = i == 0
        let w = max(b.width * size.width + 28, 64), h = max(b.height * size.height + 20, 44)
        let rect = CGRect(x: b.midX * size.width - w / 2, y: (1 - b.midY) * size.height - h / 2, width: w, height: h)
        let path = CGPath(roundedRect: rect, cornerWidth: min(14, h / 2), cornerHeight: min(14, h / 2), transform: nil)
        let alpha: Float = primary ? 1.0 : 0.55
        // il riquadro fisso, con un alone
        let box = CAShapeLayer()
        box.path = path; box.fillColor = NSColor(red: 0.41, green: 0.88, blue: 1.0, alpha: primary ? 0.12 : 0.06).cgColor
        box.strokeColor = cyan; box.lineWidth = primary ? 3.5 : 2.5; box.opacity = alpha
        box.shadowColor = pink; box.shadowRadius = 14; box.shadowOpacity = 0.9; box.shadowOffset = .zero
        root.addSublayer(box)
        // l'anello che si allarga e svanisce, di continuo (stesso percorso, scalato intorno al centro del riquadro)
        let ring = CAShapeLayer()
        ring.path = CGPath(roundedRect: CGRect(x: -w / 2, y: -h / 2, width: w, height: h), cornerWidth: min(14, h / 2), cornerHeight: min(14, h / 2), transform: nil)
        ring.fillColor = nil; ring.strokeColor = pink; ring.lineWidth = 3
        ring.position = CGPoint(x: rect.midX, y: rect.midY)
        ring.opacity = 0
        let grow = CABasicAnimation(keyPath: "transform.scale")
        grow.fromValue = 1.0; grow.toValue = 1.0 + 90 / max(min(w, h), 1)
        let fade = CABasicAnimation(keyPath: "opacity"); fade.fromValue = Float(0.9) * alpha; fade.toValue = 0.0
        let g = CAAnimationGroup(); g.animations = [grow, fade]; g.duration = 1.2; g.repeatCount = .infinity
        g.timingFunction = CAMediaTimingFunction(name: .easeOut)
        ring.add(g, forKey: "pulse")
        root.addSublayer(ring)
    }
    return root
}

let root = makeRoot(size: size, boxes: boxes)

if let out = snapshot {                                   // solo per provare l'aspetto: disegna in un PNG trasparente
    let scale: CGFloat = 1
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size.width * scale), pixelsHigh: Int(size.height * scale), bitsPerSample: 8, samplesPerPixel: 4,
                               hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    if let ctx = NSGraphicsContext(bitmapImageRep: rep)?.cgContext {
        root.render(in: ctx)
    }
    try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: out))
    exit(0)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)                       // niente icona nel Dock, niente menu
let win = NSWindow(contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false)
win.isOpaque = false
win.backgroundColor = .clear
win.hasShadow = false
win.level = .screenSaver
win.ignoresMouseEvents = true                             // i clic passano attraverso: si puo' continuare a lavorare
win.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
let view = NSView(frame: NSRect(origin: .zero, size: size))
view.layer = root                                         // la vista ospita i livelli cosi' come sono (prima il livello, poi wantsLayer)
view.wantsLayer = true
win.contentView = view
win.orderFrontRegardless()
DispatchQueue.main.asyncAfter(deadline: .now() + max(1.0, seconds - 0.5)) {
    NSAnimationContext.runAnimationGroup({ $0.duration = 0.5; win.animator().alphaValue = 0 }, completionHandler: { exit(0) })
}
app.run()
