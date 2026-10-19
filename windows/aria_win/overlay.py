"""La schermata di Aria (nome, onda di sfere e sottotitoli): una finestra senza bordi, sempre in primo piano, che non ruba il focus e lascia passare i clic.

Dentro c'e' la stessa pagina dell'app per Mac (overlay.html + neural.js) che si collega da sola al backend; qui si occupano solo di mostrarla e nasconderla.
Sul Mac la finestra e' il «Liquid Glass» di macOS 26: su Windows l'equivalente piu' vicino e' l'acrilico (vetro sfocato), se Windows lo concede."""
from __future__ import annotations

import threading
import time

from . import paths, win32

SIZE = (520, 330)
TITLE = "Aria · schermata"
RISE = 26                                                       # quanto sale (pixel) mentre compare
BOTTOM_MARGIN = 64


def page_url() -> str:
    return (paths.resources_dir() / "overlay.html").as_uri()


def target_origin(area: tuple[int, int, int, int], size: tuple[int, int] = SIZE) -> tuple[int, int]:
    """In basso al centro dell'area utile, un po' sopra la barra delle applicazioni."""
    left, top, right, bottom = area
    return left + (right - left - size[0]) // 2, bottom - size[1] - BOTTOM_MARGIN


class OverlayController:
    """La logica di comparsa e sparizione (la stessa di Overlay.swift); `driver` e' chi sa davvero muovere la finestra."""

    def __init__(self, driver, hide_delay: float = 2.6, timer=threading.Timer, pool=None):
        from concurrent.futures import ThreadPoolExecutor
        self.driver, self.hide_delay, self._timer_cls = driver, hide_delay, timer
        self.visible = False
        self._hide_timer = None
        self._lock = threading.Lock()
        self._pool = pool or ThreadPoolExecutor(max_workers=1, thread_name_prefix="overlay")           # un solo lavoratore: le animazioni (0,3 s) non fermano chi ascolta il backend e restano in ordine

    def show(self) -> None:
        with self._lock:
            if self._hide_timer:
                self._hide_timer.cancel()
                self._hide_timer = None
            if not self.visible:
                self.visible = True
                self._pool.submit(self.driver.appear)

    def hide(self, after: float | None = None) -> None:
        """Nasconde dopo `after` secondi, a meno che nel frattempo non arrivi un nuovo show()."""
        with self._lock:
            if self._hide_timer:
                self._hide_timer.cancel()
            t = self._timer_cls(self.hide_delay if after is None else after, self._do_hide)
            t.daemon = True
            self._hide_timer = t
            t.start()

    def _do_hide(self) -> None:
        with self._lock:
            if not self.visible:
                return
            self.visible = False
            self._hide_timer = None
        self._pool.submit(self.driver.disappear)


class WebviewDriver:
    """pywebview (WebView2) + le chiamate Win32 di win32.py. Se pywebview o WebView2 mancano, `available` e' False e Aria funziona solo con l'icona nella barra."""

    def __init__(self, fade_ms: int = 280):
        self.window = None
        self.hwnd = 0
        self.fade_ms = fade_ms
        self.styled = False
        self.available = False

    def create(self) -> bool:
        try:
            import webview
        except ImportError:
            paths.log("pywebview non installato: niente schermata, resta l'icona")
            return False
        x, y = target_origin(win32.work_area())
        kw = dict(url=page_url(), width=SIZE[0], height=SIZE[1], x=x, y=y + RISE, frameless=True, on_top=True, transparent=True, resizable=False,
                  easy_drag=False, focus=False, hidden=True, shadow=False)
        while True:                                               # (versioni diverse di pywebview ammettono parametri diversi: si tolgono quelli che non conosce)
            try:
                self.window = webview.create_window(TITLE, **kw)
                break
            except TypeError as e:
                bad = next((k for k in list(kw) if k in str(e)), None)
                if bad is None or bad in ("url", "width", "height"):
                    paths.log(f"schermata non creata: {e}")
                    return False
                kw.pop(bad)
        self.available = True
        return True

    def run(self, on_ready=None) -> None:
        """Avvia il ciclo grafico (bloccante: deve stare nel thread principale). Ritorna quando tutte le finestre sono chiuse."""
        import webview
        webview.start(on_ready, gui="edgechromium") if on_ready else webview.start(gui="edgechromium")

    def _style(self) -> None:
        if self.styled or self.window is None:
            return
        self.hwnd = win32.find_window(TITLE)
        if not self.hwnd:
            return
        win32.make_overlay_style(self.hwnd)
        glass = win32.enable_acrylic(self.hwnd)
        win32.round_corners(self.hwnd)
        if not glass:
            try:
                self.window.evaluate_js("document.body.classList.add('card')")           # senza vetro sfocato: fondo scuro pieno, come nel browser
            except Exception:                                                            # noqa: BLE001
                pass
        self.styled = True

    def _fade(self, start: int, end: int) -> None:
        steps = 8
        for i in range(1, steps + 1):
            win32.set_alpha(self.hwnd, int(start + (end - start) * i / steps))
            time.sleep(self.fade_ms / 1000 / steps)

    def appear(self) -> None:
        if self.window is None:
            return
        try:
            x, y = target_origin(win32.work_area())
            self.window.move(x, y + RISE)
            self.window.show()
            self._style()
            win32.set_alpha(self.hwnd, 0)
            win32.keep_on_top(self.hwnd)
            self.window.move(x, y)
            self._fade(0, 255)
        except Exception as e:                                                           # noqa: BLE001
            paths.log(f"schermata: non riesco a mostrarla ({e})")

    def disappear(self) -> None:
        if self.window is None:
            return
        try:
            self._fade(255, 0)
            self.window.hide()
        except Exception as e:                                                           # noqa: BLE001
            paths.log(f"schermata: non riesco a nasconderla ({e})")

    def destroy(self) -> None:
        try:
            if self.window is not None:
                self.window.destroy()
        except Exception:                                                                # noqa: BLE001
            pass
