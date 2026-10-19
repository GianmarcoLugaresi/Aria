"""I "poteri" di Aria sul Mac: Promemoria, Calendario, Musica e volume, App e siti, Scorciatoie, Documenti, Briefing.

Sono "mixin" di `Tools`. Regole che valgono per tutti:
  - parte SOLO da una richiesta dell'utente riconosciuta a monte (intent.py); il chatbot non puo' lanciarli da solo (vedi MODEL_TOOLS in tools.py);
  - ognuno si accende/spegne dalle Impostazioni (profiles.POWERS); spento = non fa niente e lo dice;
  - i dati dell'utente vanno agli script come argomenti, mai dentro il testo dello script (macos.py);
  - cio' che ha effetti fuori dal Mac o imprevedibili (le Scorciatoie) chiede conferma a voce prima di partire.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
import re
import sys
import xml.etree.ElementTree as ET

from . import profiles as P
from .docs import relevant_passages
from .filetools import first_sentences
from .macos import Mac, MacError, search_url, site_url
from .textutil import pick
from .timeparse import GIORNI, parse_when, say_when
from .workspace import plain_for_speech

log = logging.getLogger("aria.powers")

POWER_TOOLS = {"PROMEMORIA", "PROMEMORIA_LISTA", "EVENTO", "AGENDA", "MUSICA", "VOLUME", "APRI_APP", "WEB", "MAPPA", "SCORCIATOIA", "SCORCIATOIA_OK",
               "SCORCIATOIE", "DOCUMENTO", "BRIEFING", "NON_SO", "SISTEMA"}
CONFIRM = "@CONFERMA"                                   # un risultato "@CONFERMA|TOOL|arg|domanda" = serve il si' dell'utente prima di eseguire
ASK = "@CHIEDI"                                         # "@CHIEDI|TOOL|parte_gia_detta|domanda": manca un pezzo; la risposta a voce lo completa
PASS = "@PASSA"                                         # "non era un comando": la frase va al chiacchierone (chatbot) come qualsiasi altra
POWER_OFF = "Questa funzione è spenta: puoi riaccenderla dalle Impostazioni, in «Cosa può fare Aria»."

REMINDER_SCRIPT = """
on run argv
set theName to item 1 of argv
if (count of argv) > 1 then
set d to current date
set day of d to 1
set year of d to (item 2 of argv as integer)
set month of d to (item 3 of argv as integer)
set day of d to (item 4 of argv as integer)
set hours of d to (item 5 of argv as integer)
set minutes of d to (item 6 of argv as integer)
set seconds of d to 0
tell application "Reminders" to make new reminder with properties {name:theName, remind me date:d}
else
tell application "Reminders" to make new reminder with properties {name:theName}
end if
return "ok"
end run
"""
REMINDERS_LIST_SCRIPT = """
tell application "Reminders"
set out to ""
set n to 0
repeat with r in (reminders whose completed is false)
set out to out & (name of r) & linefeed
set n to n + 1
if n >= 10 then exit repeat
end repeat
return out
end tell
"""
CAL_CREATE_SCRIPT = """
on run argv
set theTitle to item 1 of argv
set isAllDay to ((item 2 of argv) is "1")
set d1 to current date
set day of d1 to 1
set year of d1 to (item 3 of argv as integer)
set month of d1 to (item 4 of argv as integer)
set day of d1 to (item 5 of argv as integer)
set hours of d1 to (item 6 of argv as integer)
set minutes of d1 to (item 7 of argv as integer)
set seconds of d1 to 0
set d2 to d1 + ((item 8 of argv as integer) * minutes)
set wanted to item 9 of argv
tell application "Calendar"
set targetCal to missing value
if wanted is not "" then
repeat with c in calendars
if (name of c) is wanted and writable of c then
set targetCal to c
exit repeat
end if
end repeat
end if
if targetCal is missing value then
repeat with c in calendars
if writable of c then
set targetCal to c
exit repeat
end if
end repeat
end if
if targetCal is missing value then return "NOCAL"
tell targetCal to make new event with properties {summary:theTitle, start date:d1, end date:d2, allday event:isAllDay}
return name of targetCal
end tell
end run
"""
AGENDA_SCRIPT = """
on run argv
set d1 to current date
set day of d1 to 1
set year of d1 to (item 1 of argv as integer)
set month of d1 to (item 2 of argv as integer)
set day of d1 to (item 3 of argv as integer)
set hours of d1 to 0
set minutes of d1 to 0
set seconds of d1 to 0
set d2 to d1 + (1 * days)
set out to ""
tell application "Calendar"
repeat with c in calendars
set evs to (every event of c whose start date is greater than or equal to d1 and start date is less than d2)
repeat with e in evs
set s to start date of e
set out to out & (summary of e) & "|" & (allday event of e) & "|" & (hours of s) & "|" & (minutes of s) & linefeed
end repeat
end repeat
end tell
return out
end run
"""
MUSIC_SCRIPT = """
on run argv
set act to item 1 of argv
tell application "Music"
if act is "play" then
play
return "ok"
else if act is "pause" then
pause
return "ok"
else if act is "next" then
next track
return "ok"
else if act is "previous" then
previous track
return "ok"
else if act is "now" then
if player state is stopped then return "STOP"
return (name of current track) & "|" & (artist of current track)
else if act is "track" then
set q to item 2 of argv
set found to (every track of library playlist 1 whose name contains q)
if (count of found) is 0 then set found to (every track of library playlist 1 whose artist contains q)
if (count of found) is 0 then set found to (every track of library playlist 1 whose album contains q)
if (count of found) is 0 then return "NONE"
play (item 1 of found)
return (name of (item 1 of found)) & "|" & (artist of (item 1 of found))
else if act is "playlist" then
set q to item 2 of argv
set found to (every user playlist whose name contains q)
if (count of found) is 0 then return "NONE"
play (item 1 of found)
return name of (item 1 of found)
end if
end tell
return "ok"
end run
"""
SPOTIFY_SCRIPT = """
on run argv
set act to item 1 of argv
tell application "Spotify"
if act is "play" then
play
else if act is "pause" then
pause
else if act is "next" then
next track
else if act is "previous" then
previous track
else if act is "now" then
if player state is stopped then return "STOP"
return (name of current track) & "|" & (artist of current track)
end if
end tell
return "ok"
end run
"""
QA_SYSTEM = ("Rispondi in italiano alla domanda usando SOLO il testo del documento che ti viene dato. Se la risposta non c'è nel testo, dì soltanto che "
             "nel documento non c'è scritto. Rispondi con una frase, o due se servono davvero: dai l'informazione chiesta e basta, senza ripeterla e senza "
             "commenti sul documento. Parla in modo naturale, adatto a essere detto a voce, senza elenchi.")
NEWS_FEED = "https://www.ansa.it/sito/ansait_rss.xml"


def _clean_title(text: str, limit: int = 120) -> str:
    t = re.sub(r"[\x00-\x1f]+", " ", text or "")
    t = re.sub(r"^(?:con scritto|con scritta|con titolo|intitolat[oa]|dal titolo|che si chiama|che dice|dal nome|chiamat[oa]|con nome|scritto|scritta)\s+", "", t.strip(" ,.;:!?-"), flags=re.I)
    t = re.sub(r"^(?:di|che|per|a|:|,|-)\s+", "", t.strip(" ,.;:!?-"), flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" ,.;:!?-")
    return (t[:1].upper() + t[1:])[:limit] if t else ""


def _num(n: int) -> str:
    from .tools import words_it
    return words_it(n) if n < 60 else str(n)


def _at(h: int, m: int) -> str:
    from .tools import words_it
    base = "all'una" if h == 1 else f"alle {words_it(h)}"
    return base + ("" if m == 0 else " e mezza" if m == 30 else " e un quarto" if m == 15 else f" e {words_it(m)}")


class PowerTools:
    mac: Mac | None = None
    now_fn = staticmethod(dt.datetime.now)             # iniettabile: i test fissano l'ora

    # ---------------------------------------------------------------- comuni
    def _on(self, name: str) -> bool:
        override = (self.cfg.get("powers") or {}).get(name)
        if override is not None:
            return bool(override)
        return P.get_powers(self.cfg.get("_config_path")).get(name, True)

    def _mac(self) -> Mac:
        if self.mac is None:
            if sys.platform == "win32":
                from .winos import WinOS                                      # su Windows: stessi poteri che hanno un senso (app, siti, volume, musica con i tasti multimediali)
                self.mac = WinOS()
            else:
                self.mac = Mac()
        return self.mac

    async def _osa(self, script: str, *args, app: str = "", timeout: float = 20.0) -> str:
        mac = self._mac()
        return await asyncio.get_running_loop().run_in_executor(None, lambda: mac.osa(script, *[str(a) for a in args], app=app, timeout=timeout))

    async def _blocking(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(None, fn, *args)

    # ---------------------------------------------------------------- promemoria
    async def _promemoria(self, arg: str) -> str:
        if not self._on("reminders"):
            return POWER_OFF
        now = self.now_fn()
        no_ask = arg.startswith("!")                                                  # «senza orario»: crea il promemoria senza chiedere altro
        arg = arg.lstrip("!").strip()
        w = parse_when(arg, now)
        title = _clean_title(w.rest if w else arg)
        if not title:
            return f"{ASK}|PROMEMORIA|{arg}|Cosa devo ricordarti?"
        if w is None and not no_ask:
            return f"{ASK}|PROMEMORIA|{arg}|Per quando te lo ricordo?"
        if w and w.dt <= now and w.dt.date() == now.date():
            w.dt += dt.timedelta(days=1)                                              # «ricordami oggi alle 9» detto alle 15: un promemoria nel passato non suonerebbe mai (e si dice «domani alle nove»)
        if w:
            await self._osa(REMINDER_SCRIPT, title, w.dt.year, w.dt.month, w.dt.day, w.dt.hour, w.dt.minute, app="Promemoria")
            when = say_when(w.dt, w.has_time, now)
            return pick([f"Fatto: ti ricorderò «{title}» {when}.", f"Va bene, {when} ti ricordo: {title}.", f"Ok, segnato: {title}, {when}."])
        await self._osa(REMINDER_SCRIPT, title, app="Promemoria")
        return pick([f"Fatto: ho aggiunto «{title}» ai tuoi promemoria.", f"Ok, «{title}» è nei tuoi promemoria.", f"Va bene, l'ho segnato: {title}."])

    async def _promemoria_lista(self, _arg: str) -> str:
        if not self._on("reminders"):
            return POWER_OFF
        items = [ln.strip() for ln in (await self._osa(REMINDERS_LIST_SCRIPT, app="Promemoria")).splitlines() if ln.strip()]
        if not items:
            return "Non hai promemoria da fare."
        n = len(items)
        head = "Hai un promemoria" if n == 1 else f"Hai {_num(n)} promemoria"
        return head + ": " + ", ".join(items[:6]) + (" e altri." if n > 6 else ".")

    # ---------------------------------------------------------------- calendario
    async def _evento(self, arg: str) -> str:
        if not self._on("calendar"):
            return POWER_OFF
        now = self.now_fn()
        w = parse_when(arg, now)
        if not w or not w.has_date:
            return f"{ASK}|EVENTO|{arg}|Per quando lo metto in calendario? Dimmi il giorno e, se vuoi, l'ora."
        title = _clean_title(re.sub(r"^(?:ho|abbiamo|devo|dobbiamo|c e|ci sono|vado|andiamo|ho da)\s+(?:(?:il|lo|la|l|un|una|dei|degli|le|i|gli)\s+)?", "", w.rest.strip(), flags=re.I))
        if not title:
            return f"{ASK}|EVENTO|{arg}|Come lo chiamo, questo evento?"
        wanted = ((self.cfg.get("tools") or {}).get("calendar") or {}).get("name", "") or ""
        out = await self._osa(CAL_CREATE_SCRIPT, title, "0" if w.has_time else "1", w.dt.year, w.dt.month, w.dt.day, w.dt.hour, w.dt.minute, 60, wanted, app="Calendario")
        if out == "NOCAL":
            return "Non trovo un calendario in cui posso scrivere."
        when = say_when(w.dt, w.has_time, now)
        return pick([f"Fatto: «{title}» è in calendario {when}", f"Va bene, ho messo «{title}» in calendario {when}", f"Ok, {when} in calendario: {title}"]) + (f", nel calendario {out}." if out else ".")

    async def _agenda(self, arg: str) -> str:
        if not self._on("calendar"):
            return POWER_OFF
        now = self.now_fn()
        if arg.strip().lower() in ("settimana", "prossimi giorni", "weekend", "fine settimana"):
            return await self._agenda_week(now, weekend=arg.strip().lower() in ("weekend", "fine settimana"))
        w = parse_when(arg or "oggi", now)
        day = w.dt.date() if w else now.date()
        events = await self._events_of(day)
        label = {0: "Oggi", 1: "Domani", 2: "Dopodomani"}.get((day - now.date()).days, GIORNI[day.weekday()][0].upper() + GIORNI[day.weekday()][1:])
        if not events:
            return f"{label} non hai impegni in calendario."
        n = len(events)
        parts = []
        for title, allday, h, m in events[:6]:
            parts.append(f"tutto il giorno «{title}»" if allday else f"{_at(h, m)} «{title}»")
        head = f"{label} hai un impegno" if n == 1 else f"{label} hai {_num(n)} impegni"
        return head + ": " + ", ".join(parts) + (f" e altri {_num(n - 6)}." if n > 6 else ".")

    async def _agenda_week(self, now: dt.datetime, weekend: bool = False) -> str:
        """I prossimi 7 giorni (o il weekend) in poche parole: per ogni giorno con impegni, quanti sono e il primo."""
        days = [now.date() + dt.timedelta(days=i) for i in range(7)]
        if weekend:
            days = [d for d in days if d.weekday() >= 5] or days[:2]
        out, total = [], 0
        for d in days:
            events = await self._events_of(d)
            if not events:
                continue
            total += len(events)
            label = {0: "oggi", 1: "domani"}.get((d - now.date()).days, GIORNI[d.weekday()])
            title, allday, h, m = events[0]
            first = f"«{title}»" + ("" if allday else f" {_at(h, m)}")
            out.append(f"{label} " + (f"un impegno, {first}" if len(events) == 1 else f"{_num(len(events))} impegni, il primo {first}"))
        span = "nel weekend" if weekend else "nei prossimi giorni"
        if not out:
            return f"{span.capitalize()} non hai impegni in calendario."
        return f"{span.capitalize()} hai {_num(total)} impegn{'o' if total == 1 else 'i'}: " + "; ".join(out[:5]) + "."

    async def _events_of(self, day: dt.date) -> list[tuple[str, bool, int, int]]:
        out = await self._osa(AGENDA_SCRIPT, day.year, day.month, day.day, app="Calendario", timeout=30.0)
        events = []
        for ln in out.splitlines():
            parts = ln.split("|")
            if len(parts) >= 4:
                try:
                    events.append((parts[0].strip(), parts[1].strip().lower() == "true", int(parts[2]), int(parts[3])))
                except ValueError:
                    continue
        return sorted(events, key=lambda e: (not e[1], e[2], e[3]))

    # ---------------------------------------------------------------- musica e volume
    async def _music_app(self) -> str:
        pref = ((self.cfg.get("tools") or {}).get("music") or {}).get("app", "auto")
        if pref in ("Music", "Spotify"):
            return pref
        async def running(app: str) -> bool:
            try:
                return (await self._osa(f'return application "{app}" is running', timeout=6.0)).lower() == "true"
            except MacError:
                return False
        if not await running("Music") and await running("Spotify"):
            return "Spotify"
        return "Music"

    async def _musica(self, arg: str) -> str:
        """arg = «azione[:cosa][|app]»: play, pause, next, previous, now, track:Vasco Rossi, playlist:Relax; «|Spotify» / «|Music» se l'app e' stata scelta a voce."""
        if not self._on("music"):
            return POWER_OFF
        arg, _, forced = arg.partition("|")
        act, _, what = arg.partition(":")
        act, what = act.strip(), re.sub(r"^(?:i|il|lo|la|le|gli|l|un|una|dei|degli|delle|di|del|dell)\s+", "", what.strip(), flags=re.I)   # "suona i Queen" -> "Queen"
        mac = self._mac()
        if getattr(mac, "is_windows", False):
            return await self._musica_win(mac, act, what)
        app = forced if forced in ("Music", "Spotify") else await self._music_app()
        if app == "Spotify":
            if act in ("track", "playlist"):                                  # Spotify non si puo' comandare per titolo: si apre la ricerca
                await self._blocking(mac.open_music_search, "Spotify", what)
                return pick([f"Ho aperto la ricerca di «{what}» su Spotify: scegli tu il brano.", f"Ecco «{what}» su Spotify: tocca a te premere play."])
            out = await self._osa(SPOTIFY_SCRIPT, act, app="Spotify")
        else:
            out = await self._osa(MUSIC_SCRIPT, act, what, app="Musica") if what else await self._osa(MUSIC_SCRIPT, act, app="Musica")
        if act == "now":
            if out in ("STOP", ""):
                return "Adesso non sta suonando niente."
            title, _, artist = out.partition("|")
            return f"Sta suonando «{title}»" + (f" di {artist}." if artist else ".")
        if act in ("track", "playlist"):
            title, _, artist = out.partition("|")
            if out == "NONE" or not title:                                       # non e' nella libreria: si apre la ricerca nel catalogo di Apple Music
                try:
                    await self._blocking(mac.open_music_search, "Music", what)
                    return pick([f"«{what}» non è nella tua libreria: ti ho aperto la ricerca su Apple Music.", f"Nella tua libreria non c'è «{what}»: ecco la ricerca su Apple Music."])
                except MacError:
                    return f"Non trovo «{what}» nella tua libreria di Musica."
            return pick([f"Metto «{title}»", f"Ecco «{title}»", f"Parte «{title}»"]) + (f" di {artist}." if artist else ".")
        return pick({"play": ["Ecco la musica.", "Parte la musica.", "Eccola."], "pause": ["Messa in pausa.", "Fatto, silenzio.", "Ok, pausa."],
                     "next": ["Passo alla prossima.", "Ecco la prossima.", "Cambio canzone."], "previous": ["Torno alla precedente.", "Ecco la precedente.", "Torno indietro."]}.get(act, ["Fatto."]))

    async def _musica_win(self, mac, act: str, what: str) -> str:
        """Su Windows non si parla con un'app musicale in particolare: si premono i tasti multimediali (vanno a Spotify, al browser, a qualunque lettore acceso)."""
        if act in ("play", "pause", "next", "previous"):
            await self._blocking(mac.media, act)
            return pick({"play": ["Ecco la musica.", "Parte la musica.", "Eccola."], "pause": ["Messa in pausa.", "Fatto, silenzio.", "Ok, pausa."],
                         "next": ["Passo alla prossima.", "Ecco la prossima.", "Cambio canzone."], "previous": ["Torno alla precedente.", "Ecco la precedente.", "Torno indietro."]}[act])
        if act in ("track", "playlist") and what:
            await self._blocking(mac.open_music_search, "Spotify", what)
            return pick([f"Ho aperto la ricerca di «{what}» su Spotify: scegli tu il brano.", f"Ecco «{what}» su Spotify: tocca a te premere play."])
        return "Su Windows non so dire cosa sta suonando."

    async def _volume(self, arg: str) -> str:
        if not self._on("music"):
            return POWER_OFF
        mac = self._mac()
        act, _, val = arg.partition(":")
        if act == "mute":
            await self._blocking(mac.muted, True)
            return pick(["Ho tolto l'audio.", "Fatto, silenzio.", "Audio spento."])
        if act == "unmute":
            await self._blocking(mac.muted, False)
            return pick(["Audio riacceso.", "Ecco, l'audio è tornato.", "Rimesso."])
        if act == "get":
            return f"Il volume è al {_num(await self._blocking(mac.volume_get))} per cento."
        cur = await self._blocking(mac.volume_get)
        new = {"up": cur + 12, "down": cur - 12}.get(act)
        if act == "set":
            try:
                new = int(val)
            except ValueError:
                return "A che volume lo metto?"
        if new is None:
            return "Non ho capito cosa fare con il volume."
        n = await self._blocking(mac.volume_set, new)
        return pick([f"Volume al {_num(n)} per cento.", f"Ecco, {_num(n)} per cento.", f"Fatto: {_num(n)} per cento."]) if n else "Volume a zero."

    # ---------------------------------------------------------------- app e siti
    async def _apri_app(self, arg: str) -> str:
        """arg: «Safari», oppure «~Safari» se la frase era solo «vai su…» (allora agisce solo se trova davvero quell'app o quel sito).
        Se non trova niente e non sembra proprio il nome di un'app («apri il tuo cuore»), restituisce PASS: ne parla il chatbot, non si inventa un'app."""
        if not self._on("apps"):
            return POWER_OFF
        weak = arg.startswith("~")
        site_only = arg.startswith("sito:")                                           # «apri il sito di Ryanair»: un sito, non un'app
        arg = arg.removeprefix("sito:").lstrip("~").strip()
        mac = self._mac()
        if site_only:
            url = site_url(arg)
            if url:
                await self._blocking(mac.open_url, url)
                return f"Ho aperto il sito {arg}."
            gurl = search_url("google", f"{arg} sito ufficiale")
            await self._blocking(mac.open_url, gurl)
            return f"Non conosco l'indirizzo esatto, quindi ho cercato «{arg}» su Google."
        app = await self._blocking(mac.resolve_app, arg)
        if app:
            await self._blocking(mac.open_app, app)
            return pick([f"Ho aperto {app}.", f"Ecco {app}.", f"Apro {app}."])
        url = site_url(arg)
        if url:
            await self._blocking(mac.open_url, url)
            return f"Ho aperto il sito {arg}."
        looks_like_name = len(arg.split()) <= 3 and arg[:1].isupper() and not re.search(r"\b(?:tuo|tua|miei|mie|bene|cuore|occhi|orecchie|mente|porta|finestra)\b", arg.lower())
        if weak or not looks_like_name:
            return PASS
        return f"Non trovo un'app o un sito che si chiami «{arg}»."

    async def _web(self, arg: str) -> str:
        """arg = 'motore|testo' (es. 'youtube|gatti che suonano')."""
        if not self._on("apps"):
            return POWER_OFF
        engine, _, text = arg.partition("|")
        url = search_url(engine, text)
        if not url:
            return "Non so cercare lì."
        await self._blocking(self._mac().open_url, url)
        return pick([f"Ecco la ricerca su {engine.strip()}: «{text.strip()}».", f"Cerco «{text.strip()}» su {engine.strip()}.", f"Ecco «{text.strip()}» su {engine.strip()}."])

    async def _mappa(self, arg: str) -> str:
        if not self._on("apps"):
            return POWER_OFF
        url = search_url("maps", arg)
        if not url:
            return "Cosa cerco sulla mappa?"
        await self._blocking(self._mac().open_url, url)
        return pick([f"Ecco «{arg.strip()}» sulla mappa.", f"Ti mostro «{arg.strip()}» sulla mappa.", f"Apro la mappa su «{arg.strip()}»."])

    # ---------------------------------------------------------------- cose che non so fare
    async def _sistema(self, arg: str) -> str:
        """Batteria, spazio, versione di macOS, da quanto e' acceso, wifi, IP, memoria: solo letture."""
        from . import sysinfo
        return await sysinfo.answer(arg)

    async def _non_so(self, arg: str) -> str:
        pool = {"call": ["Telefonare non so farlo, mi dispiace. Posso però metterti un promemoria per chiamare qualcuno: dimmi quando.", "Le telefonate non sono il mio mestiere, purtroppo. Se vuoi ti ricordo io di chiamare."],
                "message": ["Mandare messaggi non so farlo. Se ti serve, ti scrivo io il testo e lo incolli tu.", "Non so mandare messaggi, mi dispiace. Posso scriverti il testo, però."],
                "home": ["Luci e casa smart per ora non li controllo, mi dispiace.", "Non sono collegata alla casa: per le luci devi pensarci tu, per ora."],
                "buy": ["Ordinare o prenotare non so farlo. Posso cercarti qualcosa sul web o aprirti il sito, se vuoi.", "Acquisti e prenotazioni per ora non li gestisco. Ti apro il sito, se ti va."],
                "inbox": ["Le mail e i messaggi per ora non li leggo: non ho accesso alla tua posta. Posso aprirti l'app, se vuoi."],
                "print": ["Stampare non so farlo. Posso leggerti il testo o prepararti un documento, e stampi tu."],
                "download": ["Scaricare e installare programmi non so farlo, per ora. Posso aprirti il sito dove si scarica, se vuoi."],
                "system": ["Le impostazioni del Mac, come wifi, bluetooth, luminosità o riavvio, per ora non le controllo. Posso solo alzare e abbassare il volume."],
                "media": ["Foto, video e registrazioni non so farli, per ora."],
                "share": ["Condividere o pubblicare non so farlo, mi dispiace. Se vuoi ti preparo io il testo."],
                "files": ["Spostare, copiare o cancellare file non so farlo: posso solo scrivere nuovi file nella cartella di Aria, e non tocco mai quelli che ci sono."],
                "app": ["Chiudere le app non so farlo, per ora. Posso aprirle, però."],
                "money": ["Pagamenti e bonifici non li faccio: preferisco che ci pensi tu."],
                "stopwatch": ["Il cronometro che conta in avanti non ce l'ho. Posso metterti un timer che ti avvisa dopo un po': dimmi quanto."],
                "bookmark": ["I preferiti del browser non li gestisco. Posso però aprirti il sito o segnarti l'indirizzo in una nota."],
                "speed": ["La velocità con cui parlo per ora non la so cambiare. Se vuoi, posso dirti le cose in modo più breve, oppure ripeterle."],
                "listremove": ["Dalle liste non riesco a togliere le voci: so solo aggiungerne in fondo, per non rovinarti i file. Le togli tu aprendo la cartella, se vuoi."]}.get(arg)
        return random.choice(pool) if pool else "Questa cosa non so farla."

    # ---------------------------------------------------------------- scorciatoie
    async def _scorciatoie(self, _arg: str) -> str:
        if not self._on("shortcuts"):
            return POWER_OFF
        names = await self._blocking(self._mac().shortcuts_list)
        if not names:
            return "Non hai ancora nessuna scorciatoia: creale con l'app Scorciatoie."
        n = len(names)
        return (f"Hai {_num(n)} scorciatoie: " if n > 1 else "Hai una scorciatoia: ") + ", ".join(names[:10]) + (" e altre." if n > 10 else ".")

    async def _scorciatoia(self, arg: str) -> str:
        """Trova la scorciatoia (per nome, anche approssimato) e chiede conferma: parte solo dopo il sì dell'utente."""
        if not self._on("shortcuts"):
            return POWER_OFF
        from .textutil import normalize
        names = await self._blocking(self._mac().shortcuts_list)
        q = normalize(arg)
        match = next((n for n in names if normalize(n) == q), None) or next((n for n in names if q and (q in normalize(n) or normalize(n) in q)), None)
        if match is None:
            return f"Non trovo nessuna scorciatoia che si chiami «{arg.strip()}»."
        allow = ((self.cfg.get("tools") or {}).get("shortcuts") or {}).get("allow") or []
        if allow and match not in allow:
            return f"La scorciatoia «{match}» non è nell'elenco di quelle che posso eseguire."
        if ((self.cfg.get("tools") or {}).get("confirm_shortcuts", True)):
            return f"{CONFIRM}|SCORCIATOIA_OK|{match}|Vuoi che esegua la scorciatoia «{match}»?"
        return await self._scorciatoia_ok(match)

    async def _scorciatoia_ok(self, name: str) -> str:
        if not self._on("shortcuts"):
            return POWER_OFF
        out = await self._blocking(self._mac().shortcuts_run, name)
        extra = first_sentences(plain_for_speech(out, 300), 200) if out else ""
        return f"Fatto: ho eseguito «{name}»." + (f" {extra}" if extra else "")

    # ---------------------------------------------------------------- documenti
    async def _documento(self, arg: str) -> str:
        """arg = 'nome del file|domanda': risponde SOLO con quello che c'e' scritto nel documento (PDF, Word, testo) della cartella di Aria."""
        if not self._on("documents"):
            return POWER_OFF
        ws = self._ws()
        from .filetools import NO_WORKSPACE
        if ws is None:
            return NO_WORKSPACE
        which, _, question = arg.partition("|")
        name = ws.find(which)
        if name is None:
            return f"Non trovo nessun file che somigli a «{which.strip()}» nella tua cartella."
        if self.generate is None:
            return "Per ora non riesco a rispondere sui documenti."
        text = await self._blocking(ws.read, name, 400_000)
        if not text.strip():
            return f"«{ws.display(name)}» è vuoto."
        passages = relevant_passages(text, question)
        answer = (await self.generate(QA_SYSTEM, f"Documento «{ws.display(name)}»:\n{passages}\n\nDomanda: {question.strip()}", 320)).strip()
        return f"«{ws.display(name)}»: {first_sentences(plain_for_speech(answer, 800), 560)}"

    # ---------------------------------------------------------------- briefing
    async def _briefing(self, _arg: str) -> str:
        if not self._on("briefing"):
            return POWER_OFF
        from .tools import NEED_CITY, speak_date
        now = self.now_fn()
        name = self.memory.get_profile("name") if self.memory else None
        hello = "Buongiorno" if now.hour < 12 else "Buon pomeriggio" if now.hour < 18 else "Buonasera"
        parts = [f"{hello}{', ' + name if name else ''}! {speak_date(now)}"]
        try:
            w = await self._weather("oggi")
            if w and w != NEED_CITY:
                parts.append(w)
        except Exception as e:                                           # noqa: BLE001
            log.info("briefing: meteo non disponibile (%s)", e)
        if self._on("calendar"):
            try:
                events = await self._events_of(now.date())
                if events:
                    parts.append("In agenda: " + ", ".join(("tutto il giorno " if a else f"{_at(h, m)} ") + f"«{t}»" for t, a, h, m in events[:4]) + ".")
                else:
                    parts.append("Non hai impegni in calendario.")
            except MacError as e:
                log.info("briefing: calendario non disponibile (%s)", e)
        if self._on("reminders"):
            try:
                items = [ln.strip() for ln in (await self._osa(REMINDERS_LIST_SCRIPT, app="Promemoria")).splitlines() if ln.strip()]
                if items:
                    parts.append("Tra i promemoria: " + ", ".join(items[:3]) + ".")
            except MacError as e:
                log.info("briefing: promemoria non disponibili (%s)", e)
        try:
            heads = await self._headlines(3)
            if heads:
                parts.append("Dalle notizie: " + "; ".join(heads) + ".")
        except Exception as e:                                           # noqa: BLE001
            log.info("briefing: notizie non disponibili (%s)", e)
        return " ".join(parts)

    async def _headlines(self, n: int) -> list[str]:
        feed = ((self.cfg.get("tools") or {}).get("news_feed", NEWS_FEED))
        if not feed:
            return []
        r = await self.http.get(feed, timeout=6.0)
        if len(r.content) > 600_000:
            return []
        root = ET.fromstring(r.content)                                  # ElementTree non risolve entita' esterne: niente XXE
        titles = [re.sub(r"\s+", " ", (it.findtext("title") or "")).strip() for it in root.iter("item")]
        return [t[:110].rstrip(" ,;:") for t in titles if t][:n]
