"""Il ponte tra Aria e macOS: AppleScript (Promemoria, Calendario, Musica, volume), Scorciatoie, aprire app e siti.

Principi di sicurezza:
  - NESSUN testo detto dall'utente finisce dentro uno script o una riga di comando: gli script sono costanti e i dati vanno come ARGOMENTI separati
    (`on run argv`), quindi non si puo' "iniettare" codice con una frase;
  - si apre un'app solo se e' una di quelle installate (cartelle Applicazioni) e si usa il suo nome vero, mai il testo detto;
  - si aprono solo indirizzi http/https di siti pubblici (mai file://, mai indirizzi IP o localhost);
  - ogni comando ha un tempo massimo: se macOS aspetta una risposta a un permesso, Aria non resta appesa.
`Mac` accetta un "runner" per i test: nessun test tocca davvero il Mac.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import urllib.parse
from difflib import SequenceMatcher

from . import i18n
from .textutil import normalize


_ACCENTS = str.maketrans("àáâäèéêëìíîïòóôöùúûüñç", "aaaaeeeeiiiioooouuuunc")


APP_NAMES_EN = {"Promemoria": "Reminders", "Calendario": "Calendar", "Musica": "Music"}


class MacError(Exception):
    """Un problema spiegabile all'utente, gia' nella sua lingua (italiano o inglese, vedi i18n.py)."""


def _subprocess_run(argv: list[str], timeout: float, stdin: str | None = None) -> tuple[int, str, str]:
    try:
        p = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise MacError(i18n.pick("Ci mette troppo: forse macOS sta aspettando che tu consenta ad Aria di controllare quell'app. Controlla se c'è una richiesta aperta e riprova.",
                                 "It's taking too long: macOS may be waiting for you to allow Aria to control that app. Check whether a permission request is open and try again."))
    except FileNotFoundError as e:
        raise MacError(i18n.pick(f"Non trovo il comando «{os.path.basename(argv[0])}» su questo Mac.", f"I can't find the \"{os.path.basename(argv[0])}\" command on this Mac.")) from e
    return p.returncode, p.stdout, p.stderr


# nomi italiani (o comuni) -> nome vero dell'app in /Applications o /System/Applications
APP_ALIASES = {
    "posta": "Mail", "mail": "Mail", "email": "Mail", "messaggi": "Messages", "calendario": "Calendar", "agenda": "Calendar", "promemoria": "Reminders",
    "note": "Notes", "appunti": "Notes", "mappe": "Maps", "foto": "Photos", "musica": "Music", "orologio": "Clock", "calcolatrice": "Calculator",
    "impostazioni": "System Settings", "impostazioni di sistema": "System Settings", "preferenze di sistema": "System Settings",
    "browser": "Safari", "internet": "Safari", "contatti": "Contacts", "rubrica": "Contacts", "anteprima": "Preview", "libri": "Books",
    "borsa": "Stocks", "meteo": "Weather", "facetime": "FaceTime", "podcast": "Podcasts", "registratore": "Voice Memos", "memo vocali": "Voice Memos",
    "monitor attivita": "Activity Monitor", "terminale": "Terminal", "editor di testo": "TextEdit", "testo": "TextEdit", "scorciatoie": "Shortcuts",
    "app store": "App Store", "tv": "TV", "chiavi": "Passwords", "password": "Passwords",
    # i nomi inglesi (la lingua di Aria si sceglie nelle Impostazioni)
    "calendar": "Calendar", "reminders": "Reminders", "notes": "Notes", "maps": "Maps", "photos": "Photos", "music": "Music", "clock": "Clock", "calculator": "Calculator",
    "settings": "System Settings", "system settings": "System Settings", "system preferences": "System Settings", "preferences": "System Settings", "contacts": "Contacts",
    "address book": "Contacts", "books": "Books", "stocks": "Stocks", "weather": "Weather", "podcasts": "Podcasts", "voice memos": "Voice Memos", "voice recorder": "Voice Memos",
    "activity monitor": "Activity Monitor", "terminal": "Terminal", "text editor": "TextEdit", "textedit": "TextEdit", "shortcuts": "Shortcuts", "passwords": "Passwords",
    "keychain": "Passwords", "imessage": "Messages", "text messages": "Messages", "web browser": "Safari",
}
_APP_DIRS = ("/Applications", "/Applications/Utilities", "/System/Applications", "/System/Applications/Utilities")
_FILLER = {"l", "il", "lo", "la", "app", "applicazione", "programma", "di", "del", "dell", "sul", "mio", "mia", "per", "favore",
           "the", "my", "application", "program", "please", "your"}

SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com", "gmail": "https://mail.google.com", "wikipedia": "https://it.wikipedia.org",
    "netflix": "https://www.netflix.com", "amazon": "https://www.amazon.it", "facebook": "https://www.facebook.com", "instagram": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com", "github": "https://github.com", "spotify": "https://open.spotify.com", "repubblica": "https://www.repubblica.it",
    "corriere": "https://www.corriere.it", "ansa": "https://www.ansa.it", "twitter": "https://x.com", "x": "https://x.com", "chatgpt": "https://chatgpt.com",
    "maps": "https://maps.apple.com", "mappe": "https://maps.apple.com", "drive": "https://drive.google.com", "traduttore": "https://translate.google.com",
    "whatsapp": "https://web.whatsapp.com", "telegram": "https://web.telegram.org", "disney plus": "https://www.disneyplus.com", "prime video": "https://www.primevideo.com",
}
_SEARCH_URLS = {
    "youtube": "https://www.youtube.com/results?search_query={q}", "google": "https://www.google.com/search?q={q}",
    "wikipedia": "https://it.wikipedia.org/w/index.php?search={q}", "amazon": "https://www.amazon.it/s?k={q}", "maps": "https://maps.apple.com/?q={q}",
    "mappe": "https://maps.apple.com/?q={q}", "spotify": "https://open.spotify.com/search/{q}", "github": "https://github.com/search?q={q}",
}
_DOMAIN = re.compile(r"^(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
_IP = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


SITES_EN = {"wikipedia": "https://en.wikipedia.org", "amazon": "https://www.amazon.com", "bbc": "https://www.bbc.com", "cnn": "https://www.cnn.com", "nytimes": "https://www.nytimes.com",
            "the guardian": "https://www.theguardian.com", "guardian": "https://www.theguardian.com", "reddit": "https://www.reddit.com", "ebay": "https://www.ebay.com", "imdb": "https://www.imdb.com",
            "translate": "https://translate.google.com", "google translate": "https://translate.google.com", "google drive": "https://drive.google.com", "google maps": "https://maps.google.com",
            "apple maps": "https://maps.apple.com", "hacker news": "https://news.ycombinator.com", "stack overflow": "https://stackoverflow.com", "twitch": "https://www.twitch.tv"}
SEARCH_URLS_EN = {"wikipedia": "https://en.wikipedia.org/w/index.php?search={q}", "amazon": "https://www.amazon.com/s?k={q}", "reddit": "https://www.reddit.com/search/?q={q}",
                  "imdb": "https://www.imdb.com/find/?q={q}", "ebay": "https://www.ebay.com/sch/i.html?_nkw={q}", "bing": "https://www.bing.com/search?q={q}",
                  "duckduckgo": "https://duckduckgo.com/?q={q}", "google maps": "https://maps.google.com/?q={q}", "apple maps": "https://maps.apple.com/?q={q}",
                  "twitter": "https://x.com/search?q={q}", "netflix": "https://www.netflix.com/search?q={q}"}


def site_url(query: str) -> str | None:
    """«youtube», «repubblica punto it», «example.com» -> un indirizzo https sicuro (mai IP, localhost o altri protocolli)."""
    q = re.sub(r"[^a-z0-9. -]+", " ", query.lower().translate(_ACCENTS))          # si tengono i punti: "example.com" e' un indirizzo
    q = re.sub(r"\b(il|lo|la|sito|pagina|web|di|del|dell|the|website|site|webpage|page|of)\b", " ", q)
    q = re.sub(r"\s+", " ", q).strip(" .")
    if i18n.is_en() and q in SITES_EN:
        return SITES_EN[q]
    if q in SITES:
        return SITES[q]
    d = re.sub(r"\s+(?:punto|dot)\s+", ".", q).replace(" ", "")
    if "." in d and _DOMAIN.match(d) and not _IP.match(d) and d != "localhost":
        return "https://" + d
    return None


def search_url(engine: str, text: str) -> str | None:
    e = normalize(engine)
    tpl = (SEARCH_URLS_EN.get(e) if i18n.is_en() else None) or _SEARCH_URLS.get(e)
    return tpl.format(q=urllib.parse.quote(text.strip(), safe="")) if tpl and text.strip() else None


class Mac:
    def __init__(self, runner=None, platform: str | None = None, app_dirs: tuple[str, ...] | None = None):
        self._run = runner or _subprocess_run
        self.platform = platform or sys.platform
        self.app_dirs = app_dirs if app_dirs is not None else _APP_DIRS + (os.path.expanduser("~/Applications"),)
        self._apps: tuple[float, dict[str, str]] | None = None

    def _need_mac(self) -> None:
        if self.platform != "darwin":
            raise MacError(i18n.pick("Questa funzione c'è solo sul Mac.", "This feature only works on the Mac."))

    # ---------------------------------------------------------------- AppleScript
    def osa(self, script: str, *args: str, timeout: float = 20.0, app: str = "") -> str:
        """Esegue uno script costante; i dati vanno in `args` (item N of argv). Restituisce l'output (o solleva MacError spiegabile)."""
        self._need_mac()
        if i18n.is_en():
            app = APP_NAMES_EN.get(app, app)                         # (gli script parlano con i nomi veri delle app; qui serve solo il nome da dire nei messaggi)
        argv = ["osascript"]
        for line in script.strip("\n").splitlines():
            argv += ["-e", line]
        if args:
            argv += ["--"] + [str(a) for a in args]                   # «--»: un dato che comincia con «-e» (un titolo detto a voce) altrimenti osascript lo leggerebbe come
        code, out, err = self._run(argv, timeout, None)              #  un'altra riga di script da eseguire (provato: senza «--» viene eseguito)
        if code != 0:
            low = (err or "").lower()
            if "-1743" in low or "not authorized" in low or "non autorizzat" in low:
                if i18n.is_en():
                    raise MacError(f"I don't have permission to control {app or 'that app'}: allow it in System Settings, Privacy & Security, Automation, under Aria.")
                what = f" {app}" if app else " quell'app"
                raise MacError(f"Non ho il permesso di controllare{what}: consentilo in Impostazioni di Sistema, Privacy e sicurezza, Automazione, alla voce Aria.")
            if "-600" in low or "isn't running" in low or "non è in esecuzione" in low:
                raise MacError(i18n.pick(f"{app or 'L’app'} non è aperta.", f"{app or 'The app'} isn't open."))
            if "-1728" in low or "can't get" in low:
                raise MacError(i18n.pick("Non ho trovato quello che cercavo.", "I couldn't find what I was looking for."))
            tail = f" ({err.strip().splitlines()[-1][:80]})" if err.strip() else "."
            raise MacError(i18n.pick("macOS non ha eseguito il comando", "macOS didn't run the command") + tail)
        return (out or "").strip()

    # ---------------------------------------------------------------- Scorciatoie
    def shortcuts_list(self) -> list[str]:
        self._need_mac()
        code, out, _err = self._run(["shortcuts", "list"], 15.0, None)
        if code != 0:
            raise MacError(i18n.pick("Non riesco a leggere le tue Scorciatoie.", "I can't read your Shortcuts."))
        return [ln.strip() for ln in out.splitlines() if ln.strip()]

    def shortcuts_run(self, name: str, timeout: float = 120.0) -> str:
        self._need_mac()
        code, out, err = self._run(["shortcuts", "run", name], timeout, None)
        if code != 0:
            raise MacError(i18n.pick(f"La scorciatoia «{name}» non è andata a buon fine.", f"The shortcut \"{name}\" didn't succeed."))
        return (out or "").strip()

    # ---------------------------------------------------------------- app e siti
    def apps(self) -> dict[str, str]:
        """{nome normalizzato: nome dell'app} delle app installate (cache di un minuto)."""
        now = time.monotonic()
        if self._apps and now - self._apps[0] < 60:
            return self._apps[1]
        found: dict[str, str] = {}
        for d in self.app_dirs:
            try:
                for n in os.listdir(d):
                    if n.endswith(".app"):
                        found.setdefault(normalize(n[:-4]), n[:-4])
            except OSError:
                continue
        self._apps = (now, found)
        return found

    def resolve_app(self, query: str) -> str | None:
        """L'app installata che corrisponde a quello che l'utente ha detto (nome vero), oppure None."""
        words = [w for w in normalize(query).split() if w not in _FILLER]
        q = " ".join(words)
        if not q:
            return None
        apps = self.apps()
        alias = APP_ALIASES.get(q)
        if alias and normalize(alias) in apps:
            return apps[normalize(alias)]
        if q in apps:
            return apps[q]
        starts = [n for k, n in apps.items() if len(q) >= 3 and k.startswith(q)]
        if len(starts) >= 1:
            return sorted(starts, key=len)[0]
        contains = [n for k, n in apps.items() if q in k.split() or (len(q) >= 4 and q in k)]
        if contains:
            return sorted(contains, key=len)[0]
        best = max(((SequenceMatcher(None, q, k).ratio(), n) for k, n in apps.items()), default=(0.0, None))
        return best[1] if best[0] >= 0.86 else None

    def open_app(self, name: str) -> None:
        self._need_mac()
        code, _o, _e = self._run(["open", "-a", name], 15.0, None)
        if code != 0:
            raise MacError(i18n.pick(f"Non sono riuscita ad aprire {name}.", f"I couldn't open {name}."))

    def open_url(self, url: str) -> None:
        self._need_mac()
        if urllib.parse.urlparse(url).scheme not in ("http", "https"):          # ultima barriera: mai file:// o altri protocolli
            raise MacError(i18n.pick("Apro solo indirizzi web.", "I only open web addresses."))
        code, _o, _e = self._run(["open", url], 15.0, None)
        if code != 0:
            raise MacError(i18n.pick("Non sono riuscita ad aprire il sito.", "I couldn't open the website."))

    def open_music_search(self, app: str, query: str) -> None:
        """Apre la RICERCA nell'app musicale (Apple Music o Spotify): AppleScript non puo' cercare nel catalogo in streaming, ma la ricerca si apre.
        Solo gli schemi music:// e spotify:, con il testo cercato codificato (mai testo libero nella riga di comando)."""
        self._need_mac()
        q = urllib.parse.quote(query.strip()[:80], safe="")
        url = f"spotify:search:{q}" if app == "Spotify" else f"music://music.apple.com/{i18n.pick('it', 'us')}/search?term={q}"
        code, _o, _e = self._run(["open", url], 15.0, None)
        if code != 0:
            raise MacError(i18n.pick("Non sono riuscita ad aprire la ricerca.", "I couldn't open the search."))

    # ---------------------------------------------------------------- volume
    def volume_get(self) -> int:
        out = self.osa("return output volume of (get volume settings)", timeout=8.0)
        try:
            return int(float(out))
        except ValueError:
            raise MacError(i18n.pick("Non riesco a leggere il volume.", "I can't read the volume."))

    def volume_set(self, n: int) -> int:
        n = max(0, min(100, int(n)))
        self.osa("on run argv\nset volume output volume (item 1 of argv as integer)\nend run", str(n), timeout=8.0)
        return n

    def muted(self, on: bool) -> None:
        self.osa("on run argv\nif (item 1 of argv) is \"1\" then\nset volume with output muted\nelse\nset volume without output muted\nend if\nend run",
                 "1" if on else "0", timeout=8.0)
