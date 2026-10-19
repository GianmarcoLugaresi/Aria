"""Aria su Windows: aprire app e siti, volume, tasti multimediali. L'equivalente di macos.py per i poteri che hanno un senso anche li'.

Quello che qui non c'e' (Promemoria, Calendario, Scorciatoie, AppleScript) risponde onestamente «su Windows non c'e'» invece di far finta.
Come nel resto del programma: i dati detti a voce non finiscono mai in una riga di comando (si apre con ShellExecute / webbrowser, mai con `cmd /c`)."""
from __future__ import annotations

import ctypes
import os
import re
import sys
import time
import urllib.parse
from difflib import SequenceMatcher

from .macos import Mac, MacError, _FILLER
from .textutil import normalize

NOT_ON_WINDOWS = "Su Windows questa funzione non c'è ancora."

# tasti virtuali di Windows
VK_VOLUME_MUTE, VK_VOLUME_DOWN, VK_VOLUME_UP = 0xAD, 0xAE, 0xAF
VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_PLAY_PAUSE = 0xB0, 0xB1, 0xB3
KEYEVENTF_KEYUP = 0x0002

# nomi di app che l'utente dice in italiano e che su Windows si chiamano in un altro modo (nome normalizzato -> nome nel menu Start)
WIN_ALIASES = {"browser": "edge", "internet": "edge", "calcolatrice": "calcolatrice", "blocco note": "blocco note", "note": "blocco note", "esplora file": "esplora file",
               "file": "esplora file", "impostazioni": "impostazioni", "terminale": "terminale", "prompt dei comandi": "prompt dei comandi", "musica": "spotify", "posta": "posta"}


def press_key(vk: int, times: int = 1) -> None:
    """Preme un tasto virtuale (volume, multimedia) come farebbe la tastiera. Solo su Windows."""
    if sys.platform != "win32":
        raise MacError(NOT_ON_WINDOWS)
    user32 = ctypes.windll.user32                                                         # type: ignore[attr-defined]
    for _ in range(max(1, times)):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)


def start_menu_dirs() -> tuple[str, ...]:
    return tuple(d for d in (os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
                             os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")) if d and os.path.isdir(d))


class WinOS(Mac):
    """Stessi metodi di `Mac` per i poteri che servono (apps, resolve_app, open_app, open_url, open_music_search, volume_*), fatti con le API di Windows."""

    is_windows = True                                                                     # (powers.py sceglie cosa fare guardando questo, non il sistema su cui gira: cosi' si prova anche con un finto)

    def __init__(self, runner=None, platform: str | None = None, app_dirs: tuple[str, ...] | None = None, opener=None, keys=None):
        super().__init__(runner=runner, platform=platform or "win32", app_dirs=app_dirs if app_dirs is not None else start_menu_dirs())
        self._open = opener or self._shell_open
        self._key = keys or press_key
        self._vol = None

    def _need_mac(self) -> None:                                                          # (qui il «Mac» e' Windows: non c'e' niente da controllare)
        return None

    @staticmethod
    def _shell_open(target: str) -> None:
        if sys.platform != "win32":
            raise MacError(NOT_ON_WINDOWS)
        os.startfile(target)                                                              # type: ignore[attr-defined]

    # ---------------------------------------------------------------- cose del Mac che qui non ci sono
    def osa(self, script: str, *args: str, timeout: float = 20.0, app: str = "") -> str:
        raise MacError(NOT_ON_WINDOWS)

    def shortcuts_list(self) -> list[str]:
        raise MacError(NOT_ON_WINDOWS)

    def shortcuts_run(self, name: str, timeout: float = 120.0) -> str:
        raise MacError(NOT_ON_WINDOWS)

    # ---------------------------------------------------------------- app e siti
    def apps(self) -> dict[str, str]:
        """{nome normalizzato: nome} dei collegamenti del menu Start (cache di un minuto)."""
        now = time.monotonic()
        if self._apps and now - self._apps[0] < 60:
            return self._apps[1]
        found: dict[str, str] = {}
        for base in self.app_dirs:
            for root, _dirs, files in os.walk(base):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        name = f[:-4]
                        if re.search(r"\b(?:uninstall|disinstalla|readme|license|licenza|help|guida|manual)\b", name, re.I):
                            continue
                        found.setdefault(normalize(name), os.path.join(root, f))
        self._apps = (now, found)
        return found

    def resolve_app(self, query: str) -> str | None:
        """Il collegamento del menu Start che corrisponde a quello che l'utente ha detto (percorso del .lnk), oppure None."""
        words = [w for w in normalize(query).split() if w not in _FILLER]
        q = " ".join(words)
        if not q:
            return None
        q = WIN_ALIASES.get(q, q)
        apps = self.apps()
        if q in apps:
            return apps[q]
        starts = [p for k, p in apps.items() if len(q) >= 3 and k.startswith(q)]
        if starts:
            return sorted(starts, key=len)[0]
        contains = [p for k, p in apps.items() if q in k.split() or (len(q) >= 4 and q in k)]
        if contains:
            return sorted(contains, key=len)[0]
        best = max(((SequenceMatcher(None, q, k).ratio(), p) for k, p in apps.items()), default=(0.0, None))
        return best[1] if best[0] >= 0.86 else None

    def open_app(self, name: str) -> None:
        try:
            self._open(name)
        except OSError:
            raise MacError(f"Non sono riuscita ad aprire {os.path.splitext(os.path.basename(name))[0]}.")

    def open_url(self, url: str) -> None:
        if urllib.parse.urlparse(url).scheme not in ("http", "https"):                    # ultima barriera: mai file:// o altri protocolli
            raise MacError("Apro solo indirizzi web.")
        try:
            self._open(url)
        except OSError:
            raise MacError("Non sono riuscita ad aprire il sito.")

    def open_music_search(self, app: str, query: str) -> None:
        q = urllib.parse.quote(query.strip()[:80], safe="")
        try:
            self._open(f"spotify:search:{q}")                                             # (se Spotify non c'e' installato Windows non sa cosa farne: errore chiaro)
        except OSError:
            raise MacError("Non sono riuscita ad aprire la ricerca: serve l'app di Spotify.")

    # ---------------------------------------------------------------- volume
    def _endpoint(self):
        """L'interfaccia del volume di Windows (libreria facoltativa `pycaw`), oppure None."""
        if self._vol is None:
            try:
                from pycaw.pycaw import AudioUtilities                                    # type: ignore
                dev = AudioUtilities.GetSpeakers()
                self._vol = getattr(dev, "EndpointVolume", None) or False
            except Exception:                                                             # noqa: BLE001
                self._vol = False
        return self._vol or None

    def volume_get(self) -> int:
        ep = self._endpoint()
        if ep is None:
            raise MacError("Non riesco a leggere il volume.")
        return int(round(float(ep.GetMasterVolumeLevelScalar()) * 100))

    def volume_set(self, n: int) -> int:
        n = max(0, min(100, int(n)))
        ep = self._endpoint()
        if ep is None:
            raise MacError("Non riesco a cambiare il volume.")
        ep.SetMasterVolumeLevelScalar(n / 100.0, None)
        return n

    def muted(self, on: bool) -> None:
        ep = self._endpoint()
        if ep is not None:
            ep.SetMute(1 if on else 0, None)
            return
        self._key(VK_VOLUME_MUTE)                                                         # senza pycaw: il tasto «muto» (alterna, non e' sicuro come impostare)

    # ---------------------------------------------------------------- tasti multimediali (Spotify, YouTube nel browser, qualunque lettore)
    def media(self, act: str) -> bool:
        """play/pause (stesso tasto), next, previous. True se il tasto e' partito."""
        vk = {"play": VK_MEDIA_PLAY_PAUSE, "pause": VK_MEDIA_PLAY_PAUSE, "next": VK_MEDIA_NEXT, "previous": VK_MEDIA_PREV}.get(act)
        if vk is None:
            return False
        self._key(vk)
        return True
