import AppKit

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)      // niente icona nel Dock: vive nella barra dei menu
app.run()
