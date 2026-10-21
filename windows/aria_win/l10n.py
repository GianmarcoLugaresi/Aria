"""La lingua dell'involucro Windows (menu, messaggi, schermata): «it» o «en». Una sola per tutto, e la stessa scelta del cervello Python e dell'app per Mac (L10n.swift).

Ordine di scelta: variabile ARIA_LANG (solo per le prove) > scelta fatta dal menu (`settings.json` accanto a config.yaml, chiave `language`) > `language:` di config.yaml >
lingua di Windows (italiano solo se Windows e' in italiano, altrimenti inglese).
L'involucro non importa il pacchetto `aria` (non e' nel suo PYTHONPATH): per questo la stessa logica sta qui, in piccolo.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import paths

LANG_ITALIAN = 0x10                                              # identificatore primario della lingua italiana in Windows (LANGID & 0x3FF)

_code: str | None = None


def clean(raw) -> str | None:
    """«en», «EN», «en-US», «English» -> «en»; «it», «italiano» -> «it»; «auto» o altro -> None."""
    c = str(raw or "").strip().lower().replace("_", "-")
    if c.startswith("it"):
        return "it"
    if c.startswith("en"):
        return "en"
    return None


def system_language() -> str:
    """La lingua di visualizzazione di Windows: «it» se e' l'italiano, altrimenti «en»."""
    try:
        if sys.platform == "win32":
            import ctypes
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()           # type: ignore[attr-defined]
            return "it" if (langid & 0x3FF) == LANG_ITALIAN else "en"
        import locale
        loc = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
        if loc:
            return "it" if loc.startswith("it") else "en"
    except Exception:                                                              # noqa: BLE001
        pass
    return "en"


def _settings_file() -> Path:
    return Path(paths.config_file()).parent / "settings.json"


def settings_choice() -> str | None:
    """La lingua scelta dal menu (None = automatica)."""
    try:
        data = json.loads(_settings_file().read_text(encoding="utf-8"))
        return clean(data.get("language")) if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def config_choice() -> str | None:
    """`language: en` in config.yaml (una riga semplice: niente YAML completo)."""
    try:
        for line in Path(paths.config_file()).read_text(encoding="utf-8").splitlines():
            if line.startswith("language:"):
                return clean(line.split(":", 1)[1].split("#", 1)[0].strip(" \"'"))
    except OSError:
        pass
    return None


def chosen() -> str:
    """Quello che e' scelto nel menu: «it», «en» oppure «auto»."""
    return settings_choice() or "auto"


def detect() -> str:
    return clean(os.environ.get("ARIA_LANG")) or settings_choice() or config_choice() or system_language()


def code() -> str:
    global _code
    if _code is None:
        _code = detect()
    return _code


def reload() -> str:
    global _code
    _code = None
    return code()


def is_english() -> bool:
    return code() == "en"


def tr(it: str, en: str) -> str:
    """La scritta nella lingua in uso: `tr("Esci da Aria", "Quit Aria")`."""
    return en if code() == "en" else it
