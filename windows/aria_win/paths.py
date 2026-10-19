"""Dove sta tutto su Windows. L'installer scrive `%APPDATA%\\Aria\\paths.json` (python, software, config); le variabili ARIA_* servono ai test."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

MAX_LOG = 5 * 1024 * 1024                                       # oltre i 5 MB il log vecchio diventa «.1» e se ne inizia uno nuovo


def _dir(env: str, base_env: str, fallback: str) -> Path:
    if os.environ.get(env):
        return Path(os.environ[env])
    base = os.environ.get(base_env)
    return (Path(base) if base else Path.home() / fallback) / "Aria"


def support_dir() -> Path:
    """Configurazione, carattere, memoria: %APPDATA%\\Aria."""
    return _dir("ARIA_SUPPORT", "APPDATA", "AppData/Roaming")


def local_dir() -> Path:
    """Ambiente Python, programma, risorse, log: %LOCALAPPDATA%\\Aria."""
    return _dir("ARIA_LOCAL", "LOCALAPPDATA", "AppData/Local")


def logs_dir() -> Path:
    return local_dir() / "Logs"


def overrides() -> dict:
    try:
        data = json.loads((support_dir() / "paths.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def python_exe(windowless: bool = True) -> str:
    """Il Python dell'ambiente di Aria. `pythonw.exe` (senza finestra, ma senza nemmeno un terminale per scrivere) per l'involucro e per l'avvio automatico;
    `python.exe` per il backend e per i programmi di cui si legge il risultato (partono comunque nascosti, con CREATE_NO_WINDOW)."""
    want = "pythonw.exe" if windowless else "python.exe"
    p = overrides().get("python")
    if p:
        sibling = Path(p).with_name(want)
        return str(sibling) if sibling.exists() else p
    scripts = local_dir() / "venv" / "Scripts"
    exe = scripts / want
    return str(exe if exe.exists() else scripts / "python.exe")


def software_dir() -> str:
    return overrides().get("software") or str(local_dir() / "software")


def config_file() -> str:
    return overrides().get("config") or str(support_dir() / "config.yaml")


def persona_file() -> str:
    return str(Path(config_file()).parent / "persona.md")


def resources_dir() -> Path:
    """overlay.html, neural.js e le icone (le stesse dell'app per Mac)."""
    return Path(os.environ.get("ARIA_RESOURCES") or local_dir() / "resources")


def backend_log() -> Path:
    return logs_dir() / "backend.log"


def app_log() -> Path:
    return logs_dir() / "app.log"


def rotate(path: Path, limit: int = MAX_LOG) -> None:
    """Un log che cresce per mesi non serve a nessuno: se e' troppo grande diventa «.1»."""
    try:
        if path.exists() and path.stat().st_size > limit:
            old = path.with_name(path.name + ".1")
            old.unlink(missing_ok=True)
            path.rename(old)
    except OSError:
        pass


def log(msg: str) -> None:
    try:
        logs_dir().mkdir(parents=True, exist_ok=True)
        with open(app_log(), "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}\n")
    except OSError:
        pass
