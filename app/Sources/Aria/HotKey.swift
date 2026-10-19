import Carbon.HIToolbox

/// Scorciatoia globale (non richiede permessi di accessibilita').
final class HotKey {
    private var ref: EventHotKeyRef?
    private static var handlers: [UInt32: () -> Void] = [:]
    private static var installed = false

    init(keyCode: UInt32, modifiers: UInt32, id: UInt32 = 1, handler: @escaping () -> Void) {
        HotKey.handlers[id] = handler
        if !HotKey.installed {
            var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
            InstallEventHandler(GetApplicationEventTarget(), { (_, event, _) -> OSStatus in
                var hk = EventHotKeyID()
                GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                                  nil, MemoryLayout<EventHotKeyID>.size, nil, &hk)
                DispatchQueue.main.async { HotKey.handlers[hk.id]?() }
                return noErr
            }, 1, &spec, nil, nil)
            HotKey.installed = true
        }
        let hkID = EventHotKeyID(signature: OSType(0x41524941), id: id)      // 'ARIA'
        RegisterEventHotKey(keyCode, modifiers, hkID, GetApplicationEventTarget(), 0, &ref)
    }

    deinit { if let r = ref { UnregisterEventHotKey(r) } }
}
