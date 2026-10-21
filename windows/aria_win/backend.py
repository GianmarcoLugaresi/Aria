"""Avvia il «cervello» Python come processo figlio, lo riavvia se cade (con attese sempre piu' lunghe) e scrive il suo log. Come BackendManager di Backend.swift."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from . import paths
from .l10n import tr

CREATE_NO_WINDOW = 0x08000000


class BackendManager:
    def __init__(self, popen=subprocess.Popen, clock=time.monotonic, sleep=time.sleep):
        self._popen, self._clock, self._sleep = popen, clock, sleep
        self.proc: subprocess.Popen | None = None
        self.stopping = False
        self.failures = 0
        self.problem: str | None = None
        self.on_problem = None                                           # callable(str | None)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def command(self) -> list[str]:
        return [paths.python_exe(windowless=False), "-m", "aria.main", "--config", paths.config_file()]          # python.exe (non pythonw: vuole stdout e stderr veri per il log) senza finestra

    @staticmethod
    def gpu_library_dirs() -> list[str]:
        """Le cartelle con le DLL di CUDA che arrivano dai pacchetti pip `nvidia-*` (servono a Whisper su scheda NVIDIA): vanno nel PATH del backend, altrimenti CTranslate2 non le trova."""
        py = paths.python_exe(windowless=False)
        site = os.path.join(os.path.dirname(os.path.dirname(py)), "Lib", "site-packages", "nvidia")
        if not os.path.isdir(site):
            return []
        return [os.path.join(site, d, "bin") for d in sorted(os.listdir(site)) if os.path.isdir(os.path.join(site, d, "bin"))]

    def environment(self) -> dict:
        env = dict(os.environ)
        env.update({"PYTHONPATH": paths.software_dir(), "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1", "TOKENIZERS_PARALLELISM": "false", "ARIA_PARENT_WATCH": "1"})
        gpu = self.gpu_library_dirs()
        if gpu:
            env["PATH"] = os.pathsep.join(gpu + [env.get("PATH", "")])
        return env

    def _report(self, msg: str | None) -> None:
        self.problem = msg
        if msg:
            paths.log(msg)
        if self.on_problem:
            self.on_problem(msg)

    def start(self) -> None:
        """Avvia il backend (se non c'e' gia') e una sentinella che lo riavvia se cade."""
        with self._lock:
            if self.proc is not None and self.proc.poll() is None:
                return
            self.stopping = False
            py = self.command()[0]
            if not os.path.exists(py):
                self._report(tr(f"Python non trovato ({py}). Esegui l'installer.", f"Python not found ({py}). Run the installer."))
                return
            if not os.path.exists(paths.config_file()):
                self._report(tr(f"Configurazione mancante: {paths.config_file()}", f"Configuration missing: {paths.config_file()}"))
                return
            paths.logs_dir().mkdir(parents=True, exist_ok=True)
            paths.rotate(paths.backend_log())
            paths.rotate(paths.app_log())
            log = open(paths.backend_log(), "ab")
            kw: dict = {"cwd": paths.software_dir(), "env": self.environment(), "stdout": log, "stderr": subprocess.STDOUT}
            if sys.platform == "win32":
                kw["creationflags"] = CREATE_NO_WINDOW                   # niente finestra nera
            try:
                self.proc = self._popen(self.command(), **kw)
            except OSError as e:
                self._report(tr(f"Impossibile avviare il backend: {e}", f"I can't start the backend: {e}"))
                return
            self._report(None)
            paths.log(tr(f"backend avviato (pid {self.proc.pid})", f"backend started (pid {self.proc.pid})"))
            started = self._clock()
            self._thread = threading.Thread(target=self._watch, args=(self.proc, started), daemon=True)
            self._thread.start()

    def _watch(self, proc, started: float) -> None:
        code = proc.wait()
        if self.stopping:
            return
        if self._clock() - started > 60:
            self.failures = 0                                           # ha lavorato un minuto: il guasto di prima e' dimenticato
        self.failures += 1
        wait = min(30.0, 3.0 * self.failures)                           # se continua a cadere, aspetta sempre di piu'
        paths.log(tr(f"backend terminato (codice {code}): riavvio tra {int(wait)} s", f"backend stopped (code {code}): restarting in {int(wait)} s"))
        self._sleep(wait)
        if not self.stopping:
            self.start()

    def stop(self) -> None:
        self.stopping = True
        p = self.proc
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=6)
            except Exception:                                           # noqa: BLE001
                p.kill()

    def restart(self) -> None:
        self.stop()
        self.failures = 0
        self.proc = None
        self.start()
