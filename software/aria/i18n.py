"""La lingua di Aria: «it» (italiano) o «en» (inglese). Una sola per tutto il programma: la scelta e' nelle Impostazioni (settings.json, chiave `language`)
e cambia le scritte dell'app, il riconoscimento vocale, la voce, il carattere, le regole che capiscono le richieste e le frasi che Aria dice.

Ordine di scelta: Impostazioni > `language` di config.yaml > lingua del sistema (italiano solo se il sistema e' in italiano, altrimenti inglese).
Il cambio vale al riavvio del «cervello» (l'app lo fa da sola quando scegli la lingua).
"""
from __future__ import annotations

import locale
import os
import re
import subprocess
import sys

SUPPORTED = ("it", "en")
DEFAULT = "it"
_current = DEFAULT

_ALIASES = {"it": "it", "ita": "it", "italiano": "it", "italian": "it", "en": "en", "eng": "en", "english": "en", "inglese": "en"}


def clean(code, default: str | None = None) -> str | None:
    """«en», «EN», «en-US», «English», «inglese» -> «en»; qualunque altra cosa -> `default`."""
    c = str(code or "").strip().lower().replace("_", "-")
    c = c.split("-")[0] if c else ""
    return _ALIASES.get(c, default)


def system_language() -> str:
    """La lingua del sistema: «it» se la prima lingua preferita e' l'italiano, altrimenti «en» (e' la lingua di chi non e' italiano)."""
    return _read_system_language()


def _read_system_language() -> str:
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=3).stdout
            m = re.search(r"\"?([A-Za-z]{2,3})(?:[-_][A-Za-z0-9]+)*\"?\s*[,)]", out)
            if m:
                return "it" if m.group(1).lower() == "it" else "en"
        if sys.platform == "win32":                                    # la lingua di visualizzazione di Windows (locale.getlocale() puo' restare vuoto)
            import ctypes
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
            return "it" if (langid & 0x3FF) == 0x10 else "en"          # 0x10 = lingua italiana
        loc = locale.getlocale()[0] or os.environ.get("LANG", "")
        if loc:
            return "it" if loc.lower().startswith("it") else "en"
    except Exception:                                                  # noqa: BLE001
        pass
    return "en"


def resolve(settings_language=None, config_language=None) -> str:
    """Impostazioni > config.yaml (se non e' «auto») > lingua del sistema."""
    return clean(settings_language) or clean(config_language) or system_language()


def set_language(code) -> str:
    global _current
    _current = clean(code, DEFAULT) or DEFAULT
    return _current


def language() -> str:
    return _current


def is_en() -> bool:
    return _current == "en"


def pick(it, en):
    """Il valore per la lingua in uso: `pick("Ciao", "Hello")`."""
    return en if _current == "en" else it


# ----------------------------------------------------------------------- impostazioni collegate alla lingua
# Cosa cambia in config quando la lingua e' l'inglese: riconoscimento vocale, voce, carattere. (L'italiano e' quello di config.yaml cosi' com'e'.)
EN_VOICES = ["alba", "anna", "azelma", "cosette", "eponine", "eve", "fantine", "jane", "mary", "vera",                # le voci di Pocket TTS registrate da persone che parlano inglese
             "charles", "george", "jean", "javert", "marius", "michael", "paul"]                                   # (lola, estelle, giovanni… hanno l'accento spagnolo, francese, italiano: restano, ma non nell'elenco)
EN_DEFAULT_VOICE = "alba"                                               # le 27 voci di Pocket TTS hanno gli stessi nomi in ogni lingua; «lola» e' quella di fabbrica dell'italiano
IT_DEFAULT_VOICE = "lola"
POCKET_LANG = {"it": "italian", "en": "english"}
SAY_VOICE = {"it": "Alice", "en": "Samantha"}                           # voce di sistema del comando `say` (se si sceglie «say» come voce)
APPLE_LOCALE = {"it": "it-IT", "en": "en-US"}
WHISPER_LANG = {"it": "it", "en": "en"}
PERSONA_FILE = {"it": None, "en": "persona.en.md"}                       # None = quello di config.yaml (persona_file)
PACKAGED_PERSONA_EN = os.path.join("data", "persona_en.md")             # dentro il pacchetto (aria/data): la copia di partenza per chi non l'ha ancora


def adapt_config(cfg: dict, lang: str) -> dict:
    """Mette in `cfg` (gia' unito a config.yaml e alle Impostazioni) quello che dipende dalla lingua. Non riscrive mai i file dell'utente."""
    lang = clean(lang, DEFAULT) or DEFAULT
    cfg["language"] = lang
    if lang == "it":
        return cfg
    for b in cfg.get("brains") or []:
        stt = b.get("stt")
        if isinstance(stt, dict):
            stt["language"] = WHISPER_LANG[lang]
        tts = b.get("tts")
        if isinstance(tts, dict) and tts.get("kind") in ("pocket", "natural"):
            tts["language"] = POCKET_LANG[lang]
            if tts.get("voice") in (None, IT_DEFAULT_VOICE):
                tts["voice"] = EN_DEFAULT_VOICE
        elif isinstance(tts, dict) and tts.get("kind") == "say" and tts.get("voice") in (None, SAY_VOICE["it"]):
            tts["voice"] = SAY_VOICE[lang]
    if PERSONA_FILE[lang] and cfg.get("persona_file") in (None, "persona.md", "../anima/persona_compatta.md", "../anima/persona.md"):
        cfg["persona_file"] = PERSONA_FILE[lang]
    wake = cfg.get("wake")
    if isinstance(wake, dict) and isinstance(wake.get("stt"), dict):
        wake["stt"]["language"] = WHISPER_LANG[lang]
    return cfg


def units(cfg: dict | None = None) -> str:
    """«metric» o «imperial» (gradi Fahrenheit, miglia): `units` di config.yaml, altrimenti il Mac (Misure ▸ Pollici) o, in inglese, la regione Stati Uniti. L'italiano e' sempre metrico."""
    u = str((cfg or {}).get("units") or "auto").lower()
    if u in ("metric", "imperial"):
        return u
    if _current != "en":
        return "metric"
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["defaults", "read", "-g", "AppleMeasurementUnits"], capture_output=True, text=True, timeout=3).stdout.strip().lower()
            if out:
                return "imperial" if out.startswith("inch") else "metric"
        if sys.platform == "win32":                                    # la regione di Windows («en-US»): Stati Uniti, Liberia, Myanmar usano le miglia e i gradi Fahrenheit
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):  # type: ignore[attr-defined]
                return "imperial" if buf.value.upper().endswith(("-US", "-LR", "-MM")) else "metric"
        loc = (locale.getlocale()[0] or os.environ.get("LANG", "")).replace("-", "_")
        if loc.upper().endswith(("_US", "_LR", "_MM")):
            return "imperial"
    except Exception:                                                  # noqa: BLE001
        pass
    return "metric"
