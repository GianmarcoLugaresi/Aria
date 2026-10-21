"""Il programma: mette insieme backend, WebSocket, icona, scorciatoia e schermata. `python -m aria_win` (o `pythonw -m aria_win`, senza finestra nera)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading

from . import autostart, hotkey as hotkey_mod, l10n, paths, win32
from .backend import BackendManager
from .client import BackendClient
from .model import AppModel
from .overlay import OverlayController, WebviewDriver
from .l10n import tr
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
        self._language_lock = threading.Lock()                          # un cambio di lingua alla volta (un doppio clic riavvierebbe il cervello due volte)

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
        return {"wake": self.wake, "stop": self.stop, "set_voice": self.set_voice, "set_language": self.set_language, "toggle_mute": self.toggle_mute, "toggle_autostart": self.toggle_autostart,
                "pick_folder": self.pick_folder, "open_config": lambda: self._open(paths.config_file()), "open_persona": lambda: self._open(self.persona_path()),
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

    # ---------------------------------------------------------------- lingua
    def set_language(self, code: str) -> None:
        threading.Thread(target=self._set_language, args=(code,), daemon=True).start()

    def _models_cli(self, *args: str):
        """`python -m aria.models …` (lo stesso programma che usa l'app per Mac): stampa un JSON {"ok": true/false, "error": …}."""
        env = dict(os.environ, PYTHONPATH=paths.software_dir(), PYTHONUTF8="1")
        res = subprocess.run([paths.python_exe(windowless=False), "-m", "aria.models", *args, "--config", paths.config_file()], capture_output=True, text=True, env=env,
                             creationflags=0x08000000 if win32.is_windows() else 0, cwd=paths.software_dir() if os.path.isdir(paths.software_dir()) else None)
        for line in reversed((res.stdout or "").strip().splitlines()):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    return res.returncode, obj
            except ValueError:
                continue
        return res.returncode, {}

    def _set_language(self, code: str) -> None:
        """Sceglie la lingua (it, en o auto): il programma Python la salva in settings.json, poi si ridisegna tutto e il cervello riparte nella lingua nuova."""
        if not self._language_lock.acquire(blocking=False):
            return
        try:
            if code == self.model.language_choice:
                return
            rc, obj = self._models_cli("language", "set", code)
            if rc != 0 or obj.get("ok") is not True:
                paths.log(tr(f"lingua: non sono riuscita a cambiarla ({obj.get('error') or rc})", f"language: I couldn't change it ({obj.get('error') or rc})"))
                self.model.problem = str(obj.get("error") or tr("Non sono riuscita a cambiare la lingua.", "I couldn't change the language."))
                self.tray.refresh()
                return
            self.model.problem = None
            self.model.language_choice = l10n.chosen()
            l10n.reload()
            self.model.voice = ""                                         # le voci della lingua nuova hanno altri nomi: il cervello dira' quella in uso
            self.model.ready = False                                      # il menu torna a dire «sto caricando i modelli…»
            self.driver.set_language(l10n.code())
            paths.log(tr(f"lingua: ora {l10n.code()}", f"language: now {l10n.code()}"))
            self.tray.refresh()
            self.backend.restart()
        finally:
            self._language_lock.release()

    @staticmethod
    def persona_path() -> str:
        """Il carattere in uso: in inglese persona.en.md, che al primo uso si prepara da quello incluso nel programma (lo fa anche il cervello, ma il menu puo' essere cliccato prima)."""
        if not l10n.is_english():
            return paths.persona_file()
        target = os.path.join(os.path.dirname(paths.config_file()), "persona.en.md")
        if not os.path.exists(target):
            packaged = os.path.join(paths.software_dir(), "aria", "data", "persona_en.md")
            try:
                if os.path.exists(packaged):
                    shutil.copyfile(packaged, target)
            except OSError as e:
                paths.log(tr(f"carattere inglese: non riesco a prepararlo ({e})", f"English personality: I can't prepare it ({e})"))
        return target if os.path.exists(target) else paths.persona_file()

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
        paths.log(tr(f"cartella di Aria: {res.stdout.strip()[:200]}", f"Aria's folder: {res.stdout.strip()[:200]}"))
        self.backend.restart()                                           # la cartella si rilegge all'avvio

    @staticmethod
    def _open(target: str) -> None:
        try:
            os.startfile(target)                                         # type: ignore[attr-defined]
        except (OSError, AttributeError) as e:
            paths.log(tr(f"non riesco ad aprire {target}: {e}", f"I can't open {target}: {e}"))

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
            paths.log(tr("Aria e' gia' aperta: esco", "Aria is already open: quitting"))
            return 0
        paths.log(tr("Aria avviata", "Aria started"))
        self.model.autostart = autostart.is_enabled()
        self.model.language_choice = l10n.chosen()
        self.backend.on_problem = self._on_problem
        self.backend.start()
        self.client.start()
        spec = os.environ.get("ARIA_HOTKEY", DEFAULT_HOTKEY)
        self.model.hotkey = spec                                             # il menu mostra quella vera (prima mostrava sempre la scorciatoia di fabbrica)
        try:
            self.hotkey = hotkey_mod.HotKey(spec, self.wake)
            if not self.hotkey.start():
                paths.log(tr(f"scorciatoia {spec} non disponibile (la usa un altro programma): resta il menu", f"shortcut {spec} not available (another program uses it): the menu remains"))
        except ValueError as e:
            paths.log(str(e))
        self.tray.start()
        if self.driver.create():
            try:
                self.driver.run()                                        # bloccante: finisce quando si esce
            except Exception as e:                                       # noqa: BLE001  (di solito: manca il componente WebView2 di Microsoft)
                paths.log(tr(f"schermata non disponibile ({e}): resta l'icona nella barra", f"overlay not available ({e}): the tray icon remains"))
                self.driver.available = False
                self._quit.wait()
        else:
            self._quit.wait()
        return 0


def main() -> int:
    return AriaApp().run()
