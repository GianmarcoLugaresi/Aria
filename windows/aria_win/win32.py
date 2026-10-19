"""Le poche chiamate a Windows che servono alla schermata (finestra che lascia passare i clic, vetro sfocato, posizione) e al resto dell'involucro.
Tutto e' dietro `sys.platform == "win32"` e dentro try/except: se una chiamata non funziona, la schermata resta semplicemente un po' meno bella."""
from __future__ import annotations

import sys

GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x00080000, 0x00000020, 0x00000080, 0x08000000
LWA_ALPHA = 0x2
SPI_GETWORKAREA = 0x0030
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
ERROR_ALREADY_EXISTS = 183
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
WCA_ACCENT_POLICY = 19
DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2


def is_windows() -> bool:
    return sys.platform == "win32"


def _dll(name: str):
    import ctypes
    return ctypes.WinDLL(name, use_last_error=True)


def find_window(title: str) -> int:
    """L'handle (HWND) della finestra con quel titolo, 0 se non c'e'."""
    if not is_windows():
        return 0
    import ctypes
    from ctypes import wintypes
    u = _dll("user32")
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.FindWindowW.restype = wintypes.HWND
    return int(u.FindWindowW(None, title) or 0)


def _ex_style_all(hwnd: int, add: int) -> None:
    import ctypes
    from ctypes import wintypes
    u = _dll("user32")
    u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    u.GetWindowLongW.restype = ctypes.c_long
    u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    u.SetWindowLongW.restype = ctypes.c_long
    targets = [hwnd]
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(lambda h, _l: (targets.append(h) or True))
    u.EnumChildWindows.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.LPARAM]
    u.EnumChildWindows(hwnd, proc, 0)                                          # (WebView2 mette il suo contenuto in finestre figlie: anche loro devono lasciar passare i clic)
    for h in targets:
        cur = u.GetWindowLongW(h, GWL_EXSTYLE)
        u.SetWindowLongW(h, GWL_EXSTYLE, cur | add)


def make_overlay_style(hwnd: int) -> bool:
    """Finestra che non ruba il focus, non compare in Alt+Tab ne' nella barra delle applicazioni e lascia passare i clic (come NSPanel con ignoresMouseEvents)."""
    if not is_windows() or not hwnd:
        return False
    try:
        _ex_style_all(hwnd, WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        return True
    except Exception:                                                          # noqa: BLE001
        return False


def set_alpha(hwnd: int, alpha: int) -> bool:
    """Trasparenza di tutta la finestra, 0..255 (serve per la dissolvenza)."""
    if not is_windows() or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        u = _dll("user32")
        u.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte, wintypes.DWORD]
        return bool(u.SetLayeredWindowAttributes(hwnd, 0, max(0, min(255, int(alpha))), LWA_ALPHA))
    except Exception:                                                          # noqa: BLE001
        return False


def work_area() -> tuple[int, int, int, int]:
    """(sinistra, alto, destra, basso) dell'area utile dello schermo principale (senza barra delle applicazioni)."""
    if is_windows():
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            if _dll("user32").SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
                return r.left, r.top, r.right, r.bottom
        except Exception:                                                      # noqa: BLE001
            pass
    return 0, 0, 1920, 1040


def enable_acrylic(hwnd: int, tint_abgr: int = 0x70120E0A) -> bool:
    """Vetro sfocato dietro la finestra (acrilico di Windows 10/11). Chiamata non documentata ma usata da molte app; se non funziona la schermata usa il fondo scuro."""
    if not is_windows() or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class AccentPolicy(ctypes.Structure):
            _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int), ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]

        class WinCompAttrData(ctypes.Structure):
            _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]
        acc = AccentPolicy(ACCENT_ENABLE_ACRYLICBLURBEHIND, 2, tint_abgr, 0)
        data = WinCompAttrData(WCA_ACCENT_POLICY, ctypes.cast(ctypes.pointer(acc), ctypes.c_void_p), ctypes.sizeof(acc))
        f = _dll("user32").SetWindowCompositionAttribute
        f.argtypes = [wintypes.HWND, ctypes.POINTER(WinCompAttrData)]
        return bool(f(hwnd, ctypes.byref(data)))
    except Exception:                                                          # noqa: BLE001
        return False


def round_corners(hwnd: int) -> bool:
    """Angoli arrotondati (Windows 11)."""
    if not is_windows() or not hwnd:
        return False
    try:
        import ctypes
        pref = ctypes.c_int(DWMWCP_ROUND)
        return ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(pref), ctypes.sizeof(pref)) == 0   # type: ignore[attr-defined]
    except Exception:                                                          # noqa: BLE001
        return False


def keep_on_top(hwnd: int) -> None:
    if not is_windows() or not hwnd:
        return
    try:
        from ctypes import wintypes
        u = _dll("user32")
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.INT, wintypes.INT, wintypes.INT, wintypes.INT, wintypes.UINT]
        u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    except Exception:                                                          # noqa: BLE001
        pass


def system_uses_light_theme() -> bool:
    """Il tema della barra delle applicazioni e' chiaro? (per scegliere l'icona nera o bianca)."""
    if not is_windows():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "SystemUsesLightTheme")[0])
    except OSError:
        return False


def single_instance(name: str = "Local\\AriaAssistente") -> bool:
    """True se questa e' l'unica copia di Aria aperta (un «mutex» col nome dell'app)."""
    if not is_windows():
        return True
    import ctypes
    from ctypes import wintypes
    k = _dll("kernel32")
    k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateMutexW.restype = wintypes.HANDLE
    handle = k.CreateMutexW(None, False, name)
    single_instance._handle = handle                                           # type: ignore[attr-defined]  (resta aperto finche' vive il programma)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
