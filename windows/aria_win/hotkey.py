"""Scorciatoia globale con RegisterHotKey (non servono permessi). Alt+Spazio su Windows apre il menu della finestra, quindi di fabbrica e' Ctrl+Alt+Spazio."""
from __future__ import annotations

import sys
import threading

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
_MODS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "shift": MOD_SHIFT, "win": MOD_WIN, "super": MOD_WIN}
_KEYS = {"spazio": 0x20, "space": 0x20, "invio": 0x0D, "enter": 0x0D, "tab": 0x09, "esc": 0x1B}


def parse(spec: str) -> tuple[int, int]:
    """«Ctrl+Alt+Spazio» -> (modificatori, codice tasto virtuale). Solleva ValueError se non si capisce."""
    parts = [p.strip().lower() for p in spec.replace(" ", "").split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError(f"Scorciatoia non valida: {spec!r} (serve almeno un modificatore e un tasto)")
    mods, key = 0, parts[-1]
    for p in parts[:-1]:
        if p not in _MODS:
            raise ValueError(f"Modificatore sconosciuto: {p!r}")
        mods |= _MODS[p]
    if key in _KEYS:
        vk = _KEYS[key]
    elif len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])
    else:
        raise ValueError(f"Tasto sconosciuto: {key!r}")
    return mods, vk


class HotKey:
    def __init__(self, spec: str, callback, ident: int = 1):
        self.spec, self.callback, self.ident = spec, callback, ident
        self.mods, self.vk = parse(spec)
        self.ok = False
        self._tid = 0
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    def start(self) -> bool:
        """True se Windows ha accettato la scorciatoia (False se un altro programma l'ha gia' presa)."""
        if sys.platform != "win32":
            return False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._ready.wait(3)
        return self.ok

    def _loop(self) -> None:
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32           # type: ignore[attr-defined]
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self._tid = kernel32.GetCurrentThreadId()
        self.ok = bool(user32.RegisterHotKey(None, self.ident, self.mods | MOD_NOREPEAT, self.vk))
        self._ready.set()
        if not self.ok:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam == self.ident:
                try:
                    self.callback()
                except Exception:                                                  # noqa: BLE001
                    pass
        user32.UnregisterHotKey(None, self.ident)

    def stop(self) -> None:
        if sys.platform == "win32" and self._tid:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)       # type: ignore[attr-defined]
