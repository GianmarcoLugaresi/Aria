"""Tiene Ollama acceso: se non risponde lo apre da solo (app per Mac, altrimenti `ollama serve`) e aspetta che sia pronto."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time

import httpx

log = logging.getLogger("aria.ollama")
HOST = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
_CLI_PATHS = ("/opt/homebrew/bin/ollama", "/usr/local/bin/ollama", "/Applications/Ollama.app/Contents/Resources/ollama",
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"))          # (l'ultimo: Windows)


def is_local(base_url: str | None) -> bool:
    """True se l'indirizzo del chatbot e' un Ollama su questo computer (porta 11434)."""
    b = (base_url or "").lower()
    return "11434" in b and ("127.0.0.1" in b or "localhost" in b or "[::1]" in b)


def is_up(timeout: float = 1.5) -> bool:
    try:
        return httpx.get(HOST + "/api/tags", timeout=timeout).status_code < 500
    except Exception:                                            # noqa: BLE001
        return False


def _cli() -> str | None:
    return shutil.which("ollama") or next((p for p in _CLI_PATHS if os.path.exists(p)), None)


def installed() -> bool:
    """C'e' Ollama su questo Mac (app o comando)? Serve solo a decidere se mostrarlo nelle Impostazioni: Aria funziona anche senza."""
    return (sys.platform == "darwin" and os.path.exists("/Applications/Ollama.app")) or _cli() is not None


def start() -> bool:
    """Lancia Ollama senza aspettare. False se non c'e' proprio (ne' app ne' comando)."""
    if sys.platform == "darwin":
        r = subprocess.run(["open", "-g", "-j", "-a", "Ollama"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            return True                                          # l'app (icona nella barra dei menu) lancia il server da sola
    cli = _cli()
    if not cli:
        return False
    if sys.platform == "win32":
        flags = 0x00000008 | 0x00000200 | 0x08000000                       # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW: sopravvive ad Aria e non apre una finestra nera
        subprocess.Popen([cli, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    else:
        subprocess.Popen([cli, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)   # sopravvive ad Aria
    return True


def ensure_running(wait_s: float = 30.0) -> bool:
    """True se alla fine Ollama risponde. Bloccante: da chiamare in un thread."""
    if is_up():
        return True
    log.info("Ollama non risponde: lo avvio")
    if not start():
        log.warning("Ollama non e' installato (ne' app ne' comando 'ollama')")
        return False
    end = time.monotonic() + wait_s
    while time.monotonic() < end:
        time.sleep(0.8)
        if is_up():
            log.info("Ollama e' pronto")
            return True
    log.warning("Ollama non e' diventato pronto entro %d s", int(wait_s))
    return False
