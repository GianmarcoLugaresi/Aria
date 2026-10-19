"""Il programma: mette insieme backend, WebSocket, icona, scorciatoia e schermata. `python -m aria_win` (o `pythonw -m aria_win`, senza finestra nera)."""
from __future__ import annotations

import os
import subprocess
import sys
import threading

from . import autostart, hotkey as hotkey_mod, paths, win32
from .backend import BackendManager
from .client import BackendClient
from .model import AppModel
from .overlay import OverlayController, WebviewDriver
from .tray import Tray

DEFAULT_HOTKEY = "Ctrl+Alt+Space"


class AriaApp:
    def __init__(self):
        self.model = AppModel()
        self.backend = BackendManager()
        self.client = BackendClient(on_message=self._on_message, on_connection=self._on_connection)
        self.driver = WebviewDriver()
        self.overlay = OverlayController(self.driver)
        self.tray = Tray(self.model, self._actions())
        self.hotkey = None
        self._quit = threading.Event()

    # ---------------------------------------------------------------- eventi dal backend
    def _on_message(self, m: dict) -> None:
        changed = self.model.handle(m)
        if "state" in changed:
            if self.model.state == "idle":
                self.overlay.hide()
            else:
                self.overlay.show()
        if changed:
            self.tray.refresh()

    def _on_connection(self, ok: bool) -> None:
        self.model.set_connected(ok)
        if not ok:
            self.overlay.hide(0.0)
        self.tray.refresh()

    def _on_problem(self, msg) -> None:
        self.model.problem = msg
        self.tray.refresh()

    # ---------------------------------------------------------------- azioni del menu e della scorciatoia
    def _actions(self) -> dict:
        return {"wake": self.wake, "stop": self.stop, "set_voice": self.set_voice, "toggle_mute": self.toggle_mute, "toggle_autostart": self.toggle_autostart,
                "pick_folder": self.pick_folder, "open_config": lambda: self._open(paths.config_file()), "open_persona": lambda: self._open(paths.persona_file()),
                "open_logs": lambda: self._open(str(paths.logs_dir())), "quit": self.quit}

    def wake(self) -> None:
        if self.model.state == "idle":
            self.overlay.show()                                          # reazione immediata, prima ancora che risponda il backend
            self.client.send({"cmd": "wake"})
        else:
            self.client.send({"cmd": "stop"})

    def stop(self) -> None:
        self.client.send({"cmd": "stop"})

    def set_voice(self, name: str) -> None:
        self.model.voice = name
        self.client.send({"cmd": "voice", "name": name})
        self.tray.refresh()

    def toggle_mute(self) -> None:
        self.model.muted = not self.model.muted
        self.client.send({"cmd": "mute" if self.model.muted else "unmute"})
        self.tray.refresh()

    def toggle_autostart(self) -> None:
        want = not self.model.autostart
        if autostart.set_enabled(want):
            self.model.autostart = want
        self.tray.refresh()

    def pick_folder(self) -> None:
        threading.Thread(target=self._pick_folder, daemon=True).start()

    def _pick_folder(self) -> None:
        r = subprocess.run([sys.executable.replace("pythonw.exe", "python.exe"), "-m", "aria_win.pick_folder"], capture_output=True, text=True, creationflags=0x08000000 if win32.is_windows() else 0)
        folder = r.stdout.strip()
        if not folder:
            return
        env = dict(os.environ, PYTHONPATH=paths.software_dir())
        res = subprocess.run([paths.python_exe(windowless=False), "-m", "aria.models", "workspace", "set", folder, "--config", paths.config_file()], capture_output=True, text=True, env=env,
                             creationflags=0x08000000 if win32.is_windows() else 0)
        paths.log(f"cartella di Aria: {res.stdout.strip()[:200]}")
        self.backend.restart()                                           # la cartella si rilegge all'avvio

    @staticmethod
    def _open(target: str) -> None:
        try:
            os.startfile(target)                                         # type: ignore[attr-defined]
        except (OSError, AttributeError) as e:
            paths.log(f"non riesco ad aprire {target}: {e}")

    # ---------------------------------------------------------------- avvio e chiusura
    def quit(self) -> None:
        if self._quit.is_set():
            return
        self._quit.set()
        self.hotkey and self.hotkey.stop()
        self.client.close()
        self.tray.stop()
        self.backend.stop()
        self.driver.destroy()
        if not self.driver.available:
            os._exit(0)                                                  # (senza ciclo grafico non c'e' niente che ritorni da solo)

    def run(self) -> int:
        if not win32.single_instance():
            paths.log("Aria e' gia' aperta: esco")
            return 0
        paths.log("Aria avviata")
        self.model.autostart = autostart.is_enabled()
        self.backend.on_problem = self._on_problem
        self.backend.start()
        self.client.start()
        spec = os.environ.get("ARIA_HOTKEY", DEFAULT_HOTKEY)
        try:
            self.hotkey = hotkey_mod.HotKey(spec, self.wake)
            if not self.hotkey.start():
                paths.log(f"scorciatoia {spec} non disponibile (la usa un altro programma): resta il menu")
        except ValueError as e:
            paths.log(str(e))
        self.tray.start()
        if self.driver.create():
            try:
                self.driver.run()                                        # bloccante: finisce quando si esce
            except Exception as e:                                       # noqa: BLE001  (di solito: manca il componente WebView2 di Microsoft)
                paths.log(f"schermata non disponibile ({e}): resta l'icona nella barra")
                self.driver.available = False
                self._quit.wait()
        else:
            self._quit.wait()
        return 0


def main() -> int:
    return AriaApp().run()
