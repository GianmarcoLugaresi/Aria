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

from . import i18n
from . import profiles as P
from .docs import relevant_passages
from .filetools import first_sentences
from .macos import Mac, MacError, search_url, site_url
from .textutil import pick
from .speech_en import DAYS as DAYS_EN
from .timeparse import GIORNI, parse_when, say_when
from .workspace import plain_for_speech

log = logging.getLogger("aria.powers")

POWER_TOOLS = {"PROMEMORIA", "PROMEMORIA_LISTA", "EVENTO", "AGENDA", "MUSICA", "VOLUME", "APRI_APP", "WEB", "MAPPA", "SCORCIATOIA", "SCORCIATOIA_OK",
               "SCORCIATOIE", "DOCUMENTO", "BRIEFING", "NON_SO", "SISTEMA"}
CONFIRM = "@CONFERMA"                                   # un risultato "@CONFERMA|TOOL|arg|domanda" = serve il si' dell'utente prima di eseguire
ASK = "@CHIEDI"                                         # "@CHIEDI|TOOL|parte_gia_detta|domanda": manca un pezzo; la risposta a voce lo completa
PASS = "@PASSA"                                         # "non era un comando": la frase va al chiacchierone (chatbot) come qualsiasi altra
POWER_OFF = "Questa funzione è spenta: puoi riaccenderla dalle Impostazioni, in «Cosa può fare Aria»."
POWER_OFF_EN = "That feature is switched off: you can turn it back on in Settings, under \"What Aria can do\"."

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
NEWS_FEED_EN = "https://feeds.bbci.co.uk/news/rss.xml"
QA_SYSTEM_EN = ("Answer the question in English using ONLY the text of the document you are given. If the answer is not in the text, just say that the document doesn't say. "
                "Answer with one sentence, or two if really needed: give the information asked for and nothing more, without repeating it and without commenting on the document. "
                "Speak naturally, in a way that suits being said out loud, with no lists.")


def _clean_title(text: str, limit: int = 120) -> str:
    t = re.sub(r"[\x00-\x1f]+", " ", text or "")
    if i18n.is_en():
        t = re.sub(r"^(?:called|named|titled|saying|that says|reading)\s+", "", t.strip(" ,.;:!?-"), flags=re.I)
        t = re.sub(r"^(?:to|that|about|for|of|on|:|,|-)\s+", "", t.strip(" ,.;:!?-"), flags=re.I)
        t = re.sub(r"^(?:to|that)\s+", "", t.strip(" ,.;:!?-"), flags=re.I)
        t = re.sub(r"\s+", " ", t).strip(" ,.;:!?-")
        return (t[:1].upper() + t[1:])[:limit] if t else ""
    t = re.sub(r"^(?:con scritto|con scritta|con titolo|intitolat[oa]|dal titolo|che si chiama|che dice|dal nome|chiamat[oa]|con nome|scritto|scritta)\s+", "", t.strip(" ,.;:!?-"), flags=re.I)
    t = re.sub(r"^(?:di|che|per|a|:|,|-)\s+", "", t.strip(" ,.;:!?-"), flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" ,.;:!?-")
    return (t[:1].upper() + t[1:])[:limit] if t else ""


def _num(n: int) -> str:
    from .tools import words_it
    return words_it(n) if n < 60 else str(n)


def _at(h: int, m: int) -> str:
    from .tools import words_it
    if i18n.is_en():
        from .speech_en import clock_at
        return clock_at(h, m)
    base = "all'una" if h == 1 else f"alle {words_it(h)}"
    return base + ("" if m == 0 else " e mezza" if m == 30 else " e un quarto" if m == 15 else f" e {words_it(m)}")


_MUSIC_ACK_IT = {"play": ["Ecco la musica.", "Parte la musica.", "Eccola."], "pause": ["Messa in pausa.", "Fatto, silenzio.", "Ok, pausa."],
                 "next": ["Passo alla prossima.", "Ecco la prossima.", "Cambio canzone."], "previous": ["Torno alla precedente.", "Ecco la precedente.", "Torno indietro."]}
_MUSIC_ACK_EN = {"play": ["Here's the music.", "Music coming up.", "Here it comes."], "pause": ["Paused.", "Done, silence.", "Okay, pausing."],
                 "next": ["Skipping to the next one.", "Here's the next one.", "Changing the song."], "previous": ["Going back to the last one.", "Here's the previous one.", "Going back."]}


def _music_ack() -> dict:
    return _MUSIC_ACK_EN if i18n.is_en() else _MUSIC_ACK_IT


def _off() -> str:
    return i18n.pick(POWER_OFF, POWER_OFF_EN)


def _day_name(d: dt.date) -> str:
    return DAYS_EN[d.weekday()] if i18n.is_en() else GIORNI[d.weekday()][0].upper() + GIORNI[d.weekday()][1:]


NON_SO_EN = {
    "call": ["I can't make phone calls, I'm sorry. I can set you a reminder to call someone, though: tell me when.", "Phone calls aren't really my thing, sadly. If you like, I'll remind you to call."],
    "message": ["I can't send messages. If you need one, I'll write the text and you paste it in.", "I can't send messages, I'm sorry. I can write you the text, though."],
    "home": ["I don't control lights or smart-home devices for now, I'm sorry.", "I'm not connected to your home: for the lights you'll have to do it yourself, for now."],
    "buy": ["I can't order or book things. I can search the web for you or open the website, if you like.", "I don't handle purchases or bookings for now. I'll open the website, if you want."],
    "inbox": ["I don't read emails or messages for now: I have no access to your mail. I can open the app for you, if you like."],
    "print": ["I can't print. I can read you the text or prepare a document, and you print it."],
    "download": ["I can't download or install programs, for now. I can open the website where you download it, if you like."],
    "system": ["I don't control the Mac's settings, like wifi, bluetooth, brightness or restarting, for now. I can only turn the volume up and down."],
    "media": ["I can't take photos, videos or recordings, for now."],
    "share": ["I can't share or publish things, I'm sorry. If you like, I'll prepare the text for you."],
    "files": ["I can't move, copy or delete files: I can only write new files in the Aria folder, and I never touch the ones already there."],
    "app": ["I can't close apps, for now. I can open them, though."],
    "money": ["I don't do payments or transfers: I'd rather you handled that yourself."],
    "stopwatch": ["I don't have a stopwatch that counts up. I can set you a timer that alerts you after a while: just tell me how long."],
    "bookmark": ["I don't manage browser bookmarks. I can open the site for you or note the address down, though."],
    "speed": ["I can't change how fast I talk for now. If you like, I can say things more briefly, or repeat them."],
    "listremove": ["I can't remove items from lists: I can only add to the end, so I don't mess up your files. You can remove them by opening the folder, if you like."],
}


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
            return _off()
        if sys.platform == "win32":
            return await self._promemoria_windows(arg)
        now = self.now_fn()
        no_ask = arg.startswith("!")                                                  # «senza orario»: crea il promemoria senza chiedere altro
        arg = arg.lstrip("!").strip()
        w = parse_when(arg, now)
        title = _clean_title(w.rest if w else arg)
        if not title:
            return f"{ASK}|PROMEMORIA|{arg}|" + i18n.pick("Cosa devo ricordarti?", "What should I remind you about?")
        if w is None and not no_ask:
            return f"{ASK}|PROMEMORIA|{arg}|" + i18n.pick("Per quando te lo ricordo?", "When should I remind you?")
        if w and w.dt <= now and w.dt.date() == now.date():
            w.dt += dt.timedelta(days=1)                                              # «ricordami oggi alle 9» detto alle 15: un promemoria nel passato non suonerebbe mai (e si dice «domani alle nove»)
        if w:
            await self._osa(REMINDER_SCRIPT, title, w.dt.year, w.dt.month, w.dt.day, w.dt.hour, w.dt.minute, app="Promemoria")
            when = say_when(w.dt, w.has_time, now)
            if i18n.is_en():
                return pick([f"Done: I'll remind you about \"{title}\" {when}.", f"All right, {when} I'll remind you: {title}.", f"Okay, noted: {title}, {when}."])
            return pick([f"Fatto: ti ricorderò «{title}» {when}.", f"Va bene, {when} ti ricordo: {title}.", f"Ok, segnato: {title}, {when}."])
        await self._osa(REMINDER_SCRIPT, title, app="Promemoria")
        if i18n.is_en():
            return pick([f"Done: I added \"{title}\" to your reminders.", f"Okay, \"{title}\" is in your reminders.", f"All right, I've noted it: {title}."])
        return pick([f"Fatto: ho aggiunto «{title}» ai tuoi promemoria.", f"Ok, «{title}» è nei tuoi promemoria.", f"Va bene, l'ho segnato: {title}."])

    async def _promemoria_windows(self, arg: str) -> str:
        """Su Windows non c'e' l'app Promemoria: un promemoria e' un timer a un'ora precisa, che Aria dice a voce quando arriva e che si salva su disco (sopravvive al riavvio).
        Senza un'ora non c'e' niente da armare: la chiede."""
        now = self.now_fn()
        arg = arg.lstrip("!").strip()
        w = parse_when(arg, now)
        title = _clean_title(w.rest if w else arg)
        if not title:
            return f"{ASK}|PROMEMORIA|{arg}|" + i18n.pick("Cosa devo ricordarti?", "What should I remind you about?")
        if w is None or not w.has_time:
            return f"{ASK}|PROMEMORIA|{arg}|" + i18n.pick("Per quando te lo ricordo?", "When should I remind you?")
        at = w.dt
        if at <= now and at.date() == now.date():
            at += dt.timedelta(days=1)                                                # «ricordami oggi alle 9» detto alle 15: un'ora passata non suonerebbe mai
        low = f"{title[:1].lower()}{title[1:]}"
        label = i18n.pick(f"di {low}", f"to {low}")         # «ti ricordo di chiamare Mario» / «I'll remind you to call Mark»: lo dice la conferma e, a ora arrivata, il timer
        return await self._timer(f"| {label}", at=at)

    def _windows_reminders(self) -> list[tuple[float, str]]:
        return [(due, label) for _tid, due, label in self._live_timers() if label.startswith(("to ", "that ", "di "))]

    async def _promemoria_lista(self, _arg: str) -> str:
        if not self._on("reminders"):
            return _off()
        if sys.platform == "win32":
            items = self._windows_reminders()
            if not items:
                return i18n.pick("Non hai promemoria da fare.", "You have no reminders to do.")
            import time as _time
            now = self.now_fn()
            def at(due: float) -> dt.datetime:                                           # (all'minuto piu' vicino: un'ora per cui mancano 40 ms non e' «le otto e cinquantanove»)
                return (now + dt.timedelta(seconds=due - _time.time() + 30)).replace(second=0, microsecond=0)
            said = [f"{label[3:] if label.startswith(('di ', 'to ')) else label} ({say_when(at(due), True, now)})" for due, label in items[:6]]
            n = len(items)
            head = i18n.pick("Hai un promemoria" if n == 1 else f"Hai {_num(n)} promemoria", "You have one reminder" if n == 1 else f"You have {_num(n)} reminders")
            return head + ": " + ", ".join(said) + (i18n.pick(" e altri.", " and more.") if n > 6 else ".")
        items = [ln.strip() for ln in (await self._osa(REMINDERS_LIST_SCRIPT, app="Promemoria")).splitlines() if ln.strip()]
        if not items:
            return i18n.pick("Non hai promemoria da fare.", "You have no reminders to do.")
        n = len(items)
        if i18n.is_en():
            head = "You have one reminder" if n == 1 else f"You have {_num(n)} reminders"
            return head + ": " + ", ".join(items[:6]) + (" and more." if n > 6 else ".")
        head = "Hai un promemoria" if n == 1 else f"Hai {_num(n)} promemoria"
        return head + ": " + ", ".join(items[:6]) + (" e altri." if n > 6 else ".")

    # ---------------------------------------------------------------- calendario
    async def _evento(self, arg: str) -> str:
        if not self._on("calendar"):
            return _off()
        now = self.now_fn()
        w = parse_when(arg, now)
        if not w or not w.has_date:
            return f"{ASK}|EVENTO|{arg}|" + i18n.pick("Per quando lo metto in calendario? Dimmi il giorno e, se vuoi, l'ora.", "When should I put it in the calendar? Tell me the day and, if you like, the time.")
        if i18n.is_en():
            title = _clean_title(re.sub(r"^(?:i have|i've got|i got|we have|i need to|i have to|we need to|i'm going to|i go to|i'm having|we're having|there's|there is)\s+(?:(?:an?|the|my|our)\s+)?", "", w.rest.strip(), flags=re.I))
        else:
            title = _clean_title(re.sub(r"^(?:ho|abbiamo|devo|dobbiamo|c e|ci sono|vado|andiamo|ho da)\s+(?:(?:il|lo|la|l|un|una|dei|degli|le|i|gli)\s+)?", "", w.rest.strip(), flags=re.I))
        if not title:
            return f"{ASK}|EVENTO|{arg}|" + i18n.pick("Come lo chiamo, questo evento?", "What should I call this event?")
        wanted = ((self.cfg.get("tools") or {}).get("calendar") or {}).get("name", "") or ""
        out = await self._osa(CAL_CREATE_SCRIPT, title, "0" if w.has_time else "1", w.dt.year, w.dt.month, w.dt.day, w.dt.hour, w.dt.minute, 60, wanted, app="Calendario")
        if out == "NOCAL":
            return i18n.pick("Non trovo un calendario in cui posso scrivere.", "I can't find a calendar I can write to.")
        when = say_when(w.dt, w.has_time, now)
        if i18n.is_en():
            return pick([f"Done: \"{title}\" is on your calendar {when}", f"All right, I put \"{title}\" on your calendar {when}", f"Okay, {when} on the calendar: {title}"]) + (f", in the {out} calendar." if out else ".")
        return pick([f"Fatto: «{title}» è in calendario {when}", f"Va bene, ho messo «{title}» in calendario {when}", f"Ok, {when} in calendario: {title}"]) + (f", nel calendario {out}." if out else ".")

    async def _agenda(self, arg: str) -> str:
        if not self._on("calendar"):
            return _off()
        now = self.now_fn()
        if arg.strip().lower() in ("settimana", "prossimi giorni", "weekend", "fine settimana", "week", "the week", "next few days"):
            return await self._agenda_week(now, weekend=arg.strip().lower() in ("weekend", "fine settimana"))
        en = i18n.is_en()
        w = parse_when(arg or ("today" if en else "oggi"), now)
        day = w.dt.date() if w else now.date()
        events = await self._events_of(day)
        label = ({0: "Today", 1: "Tomorrow", 2: "The day after tomorrow"} if en else {0: "Oggi", 1: "Domani", 2: "Dopodomani"}).get((day - now.date()).days, _day_name(day))
        if not events:
            return f"{label}, you have nothing on your calendar." if en else f"{label} non hai impegni in calendario."
        n = len(events)
        parts = []
        for title, allday, h, m in events[:6]:
            parts.append((f"all day \"{title}\"" if allday else f"{_at(h, m)} \"{title}\"") if en else (f"tutto il giorno «{title}»" if allday else f"{_at(h, m)} «{title}»"))
        if en:
            head = f"{label}, you have one event" if n == 1 else f"{label}, you have {_num(n)} events"
            return head + ": " + ", ".join(parts) + (f" and {_num(n - 6)} more." if n > 6 else ".")
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
            if i18n.is_en():
                label = {0: "today", 1: "tomorrow"}.get((d - now.date()).days, DAYS_EN[d.weekday()])
                title, allday, h, m = events[0]
                first = f"\"{title}\"" + ("" if allday else f" {_at(h, m)}")
                out.append(f"{label} " + (f"one event, {first}" if len(events) == 1 else f"{_num(len(events))} events, the first being {first}"))
                continue
            label = {0: "oggi", 1: "domani"}.get((d - now.date()).days, GIORNI[d.weekday()])
            title, allday, h, m = events[0]
            first = f"«{title}»" + ("" if allday else f" {_at(h, m)}")
            out.append(f"{label} " + (f"un impegno, {first}" if len(events) == 1 else f"{_num(len(events))} impegni, il primo {first}"))
        if i18n.is_en():
            span = "this weekend" if weekend else "over the next few days"
            if not out:
                return f"{span.capitalize()}, you have nothing on your calendar."
            return f"{span.capitalize()}, you have {_num(total)} event{'' if total == 1 else 's'}: " + "; ".join(out[:5]) + "."
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
            return _off()
        arg, _, forced = arg.partition("|")
        act, _, what = arg.partition(":")
        act, what = act.strip(), what.strip() if i18n.is_en() else re.sub(r"^(?:i|il|lo|la|le|gli|l|un|una|dei|degli|delle|di|del|dell)\s+", "", what.strip(), flags=re.I)   # "suona i Queen" -> "Queen"
        mac = self._mac()
        if getattr(mac, "is_windows", False):
            return await self._musica_win(mac, act, what)
        app = forced if forced in ("Music", "Spotify") else await self._music_app()
        if app == "Spotify":
            if act in ("track", "playlist"):                                  # Spotify non si puo' comandare per titolo: si apre la ricerca
                await self._blocking(mac.open_music_search, "Spotify", what)
                return pick([f"I opened a search for \"{what}\" on Spotify: you pick the track.", f"Here's \"{what}\" on Spotify: it's up to you to press play."]) if i18n.is_en() else pick([f"Ho aperto la ricerca di «{what}» su Spotify: scegli tu il brano.", f"Ecco «{what}» su Spotify: tocca a te premere play."])
            out = await self._osa(SPOTIFY_SCRIPT, act, app="Spotify")
        else:
            out = await self._osa(MUSIC_SCRIPT, act, what, app="Musica") if what else await self._osa(MUSIC_SCRIPT, act, app="Musica")
        if act == "now":
            if out in ("STOP", ""):
                return i18n.pick("Adesso non sta suonando niente.", "Nothing is playing right now.")
            title, _, artist = out.partition("|")
            if i18n.is_en():
                return f"It's \"{title}\"" + (f" by {artist}." if artist else ".")
            return f"Sta suonando «{title}»" + (f" di {artist}." if artist else ".")
        if act in ("track", "playlist"):
            title, _, artist = out.partition("|")
            if out == "NONE" or not title:                                       # non e' nella libreria: si apre la ricerca nel catalogo di Apple Music
                try:
                    await self._blocking(mac.open_music_search, "Music", what)
                    if i18n.is_en():
                        return pick([f"\"{what}\" isn't in your library: I opened a search on Apple Music.", f"There's no \"{what}\" in your library: here's the search on Apple Music."])
                    return pick([f"«{what}» non è nella tua libreria: ti ho aperto la ricerca su Apple Music.", f"Nella tua libreria non c'è «{what}»: ecco la ricerca su Apple Music."])
                except MacError:
                    return i18n.pick(f"Non trovo «{what}» nella tua libreria di Musica.", f"I can't find \"{what}\" in your Music library.")
            if i18n.is_en():
                return pick([f"Playing \"{title}\"", f"Here's \"{title}\"", f"Putting on \"{title}\""]) + (f" by {artist}." if artist else ".")
            return pick([f"Metto «{title}»", f"Ecco «{title}»", f"Parte «{title}»"]) + (f" di {artist}." if artist else ".")
        return pick(_music_ack().get(act, [i18n.pick("Fatto.", "Done.")]))

    async def _musica_win(self, mac, act: str, what: str) -> str:
        """Su Windows non si parla con un'app musicale in particolare: si premono i tasti multimediali (vanno a Spotify, al browser, a qualunque lettore acceso)."""
        if act in ("play", "pause", "next", "previous"):
            await self._blocking(mac.media, act)
            return pick(_music_ack()[act])
        if act in ("track", "playlist") and what:
            await self._blocking(mac.open_music_search, "Spotify", what)
            return pick([f"I opened a search for \"{what}\" on Spotify: you pick the track.", f"Here's \"{what}\" on Spotify: it's up to you to press play."]) if i18n.is_en() else pick([f"Ho aperto la ricerca di «{what}» su Spotify: scegli tu il brano.", f"Ecco «{what}» su Spotify: tocca a te premere play."])
        return i18n.pick("Su Windows non so dire cosa sta suonando.", "On Windows I can't tell what is playing.")

    async def _volume(self, arg: str) -> str:
        if not self._on("music"):
            return _off()
        mac = self._mac()
        act, _, val = arg.partition(":")
        if act == "mute":
            await self._blocking(mac.muted, True)
            return pick(["Sound off.", "Done, silence.", "Muted."]) if i18n.is_en() else pick(["Ho tolto l'audio.", "Fatto, silenzio.", "Audio spento."])
        if act == "unmute":
            await self._blocking(mac.muted, False)
            return pick(["Sound back on.", "There, the sound is back.", "Unmuted."]) if i18n.is_en() else pick(["Audio riacceso.", "Ecco, l'audio è tornato.", "Rimesso."])
        if act == "get":
            v = _num(await self._blocking(mac.volume_get))
            return f"The volume is at {v} percent." if i18n.is_en() else f"Il volume è al {v} per cento."
        cur = await self._blocking(mac.volume_get)
        new = {"up": cur + 12, "down": cur - 12}.get(act)
        if act == "set":
            try:
                new = int(val)
            except ValueError:
                return i18n.pick("A che volume lo metto?", "What volume should I set it to?")
        if new is None:
            return i18n.pick("Non ho capito cosa fare con il volume.", "I didn't understand what to do with the volume.")
        n = await self._blocking(mac.volume_set, new)
        if i18n.is_en():
            return pick([f"Volume at {_num(n)} percent.", f"There, {_num(n)} percent.", f"Done: {_num(n)} percent."]) if n else "Volume at zero."
        return pick([f"Volume al {_num(n)} per cento.", f"Ecco, {_num(n)} per cento.", f"Fatto: {_num(n)} per cento."]) if n else "Volume a zero."

    # ---------------------------------------------------------------- app e siti
    async def _apri_app(self, arg: str) -> str:
        """arg: «Safari», oppure «~Safari» se la frase era solo «vai su…» (allora agisce solo se trova davvero quell'app o quel sito).
        Se non trova niente e non sembra proprio il nome di un'app («apri il tuo cuore»), restituisce PASS: ne parla il chatbot, non si inventa un'app."""
        if not self._on("apps"):
            return _off()
        weak = arg.startswith("~")
        site_only = arg.startswith("sito:")                                           # «apri il sito di Ryanair»: un sito, non un'app
        arg = arg.removeprefix("sito:").lstrip("~").strip()
        mac = self._mac()
        if site_only:
            url = site_url(arg)
            if url:
                await self._blocking(mac.open_url, url)
                return i18n.pick(f"Ho aperto il sito {arg}.", f"I opened the {arg} website.")
            gurl = search_url("google", f"{arg} " + i18n.pick("sito ufficiale", "official website"))
            await self._blocking(mac.open_url, gurl)
            return i18n.pick(f"Non conosco l'indirizzo esatto, quindi ho cercato «{arg}» su Google.", f"I don't know the exact address, so I searched Google for \"{arg}\".")
        app = await self._blocking(mac.resolve_app, arg)
        if app:
            await self._blocking(mac.open_app, app)
            return pick([f"I opened {app}.", f"Here's {app}.", f"Opening {app}."]) if i18n.is_en() else pick([f"Ho aperto {app}.", f"Ecco {app}.", f"Apro {app}."])
        url = site_url(arg)
        if url:
            await self._blocking(mac.open_url, url)
            return i18n.pick(f"Ho aperto il sito {arg}.", f"I opened the {arg} website.")
        looks_like_name = len(arg.split()) <= 3 and arg[:1].isupper() and not re.search(i18n.pick(r"\b(?:tuo|tua|miei|mie|bene|cuore|occhi|orecchie|mente|porta|finestra)\b", r"\b(?:your|my|his|her|heart|eyes|ears|mind|door|window|mouth|best)\b"), arg.lower())
        if weak or not looks_like_name:
            return PASS
        return i18n.pick(f"Non trovo un'app o un sito che si chiami «{arg}».", f"I can't find an app or website called \"{arg}\".")

    async def _web(self, arg: str) -> str:
        """arg = 'motore|testo' (es. 'youtube|gatti che suonano')."""
        if not self._on("apps"):
            return _off()
        engine, _, text = arg.partition("|")
        url = search_url(engine, text)
        if not url:
            return i18n.pick("Non so cercare lì.", "I can't search there.")
        await self._blocking(self._mac().open_url, url)
        if i18n.is_en():
            return pick([f"Here's the {engine.strip()} search: \"{text.strip()}\".", f"Searching {engine.strip()} for \"{text.strip()}\".", f"Here's \"{text.strip()}\" on {engine.strip()}."])
        return pick([f"Ecco la ricerca su {engine.strip()}: «{text.strip()}».", f"Cerco «{text.strip()}» su {engine.strip()}.", f"Ecco «{text.strip()}» su {engine.strip()}."])

    async def _mappa(self, arg: str) -> str:
        if not self._on("apps"):
            return _off()
        url = search_url("maps", arg)
        if not url:
            return i18n.pick("Cosa cerco sulla mappa?", "What should I look for on the map?")
        await self._blocking(self._mac().open_url, url)
        if i18n.is_en():
            return pick([f"Here's \"{arg.strip()}\" on the map.", f"Showing you \"{arg.strip()}\" on the map.", f"Opening the map at \"{arg.strip()}\"."])
        return pick([f"Ecco «{arg.strip()}» sulla mappa.", f"Ti mostro «{arg.strip()}» sulla mappa.", f"Apro la mappa su «{arg.strip()}»."])

    # ---------------------------------------------------------------- cose che non so fare
    async def _sistema(self, arg: str) -> str:
        """Batteria, spazio, versione di macOS, da quanto e' acceso, wifi, IP, memoria: solo letture."""
        from . import sysinfo
        return await sysinfo.answer(arg)

    async def _non_so(self, arg: str) -> str:
        out = self._non_so_text(arg)
        return out.replace("the Mac's", "the PC's").replace("del Mac", "del PC") if sys.platform == "win32" else out

    def _non_so_text(self, arg: str) -> str:
        if i18n.is_en():
            pool = NON_SO_EN.get(arg)
            return random.choice(pool) if pool else "I can't do that one."
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
            return _off()
        names = await self._blocking(self._mac().shortcuts_list)
        if not names:
            return i18n.pick("Non hai ancora nessuna scorciatoia: creale con l'app Scorciatoie.", "You don't have any shortcuts yet: create them with the Shortcuts app.")
        n = len(names)
        if i18n.is_en():
            return (f"You have {_num(n)} shortcuts: " if n > 1 else "You have one shortcut: ") + ", ".join(names[:10]) + (" and more." if n > 10 else ".")
        return (f"Hai {_num(n)} scorciatoie: " if n > 1 else "Hai una scorciatoia: ") + ", ".join(names[:10]) + (" e altre." if n > 10 else ".")

    async def _scorciatoia(self, arg: str) -> str:
        """Trova la scorciatoia (per nome, anche approssimato) e chiede conferma: parte solo dopo il sì dell'utente."""
        if not self._on("shortcuts"):
            return _off()
        from .textutil import normalize
        names = await self._blocking(self._mac().shortcuts_list)
        q = normalize(arg)
        match = next((n for n in names if normalize(n) == q), None) or next((n for n in names if q and (q in normalize(n) or normalize(n) in q)), None)
        if match is None:
            return i18n.pick(f"Non trovo nessuna scorciatoia che si chiami «{arg.strip()}».", f"I can't find a shortcut called \"{arg.strip()}\".")
        allow = ((self.cfg.get("tools") or {}).get("shortcuts") or {}).get("allow") or []
        if allow and match not in allow:
            return i18n.pick(f"La scorciatoia «{match}» non è nell'elenco di quelle che posso eseguire.", f"The shortcut \"{match}\" isn't on the list of ones I can run.")
        if ((self.cfg.get("tools") or {}).get("confirm_shortcuts", True)):
            return f"{CONFIRM}|SCORCIATOIA_OK|{match}|" + i18n.pick(f"Vuoi che esegua la scorciatoia «{match}»?", f"Do you want me to run the shortcut \"{match}\"?")
        return await self._scorciatoia_ok(match)

    async def _scorciatoia_ok(self, name: str) -> str:
        if not self._on("shortcuts"):
            return _off()
        out = await self._blocking(self._mac().shortcuts_run, name)
        extra = first_sentences(plain_for_speech(out, 300), 200) if out else ""
        return i18n.pick(f"Fatto: ho eseguito «{name}».", f"Done: I ran \"{name}\".") + (f" {extra}" if extra else "")

    # ---------------------------------------------------------------- documenti
    async def _documento(self, arg: str) -> str:
        """arg = 'nome del file|domanda': risponde SOLO con quello che c'e' scritto nel documento (PDF, Word, testo) della cartella di Aria."""
        if not self._on("documents"):
            return _off()
        ws = self._ws()
        from .filetools import NO_WORKSPACE
        if ws is None:
            return NO_WORKSPACE
        which, _, question = arg.partition("|")
        name = ws.find(which)
        if name is None:
            return i18n.pick(f"Non trovo nessun file che somigli a «{which.strip()}» nella tua cartella.", f"I can't find any file that looks like \"{which.strip()}\" in your folder.")
        if self.generate is None:
            return i18n.pick("Per ora non riesco a rispondere sui documenti.", "I can't answer questions about documents right now.")
        text = await self._blocking(ws.read, name, 400_000)
        if not text.strip():
            return i18n.pick(f"«{ws.display(name)}» è vuoto.", f"\"{ws.display(name)}\" is empty.")
        passages = relevant_passages(text, question)
        if i18n.is_en():
            answer = (await self.generate(QA_SYSTEM_EN, f"Document \"{ws.display(name)}\":\n{passages}\n\nQuestion: {question.strip()}", 320)).strip()
        else:
            answer = (await self.generate(QA_SYSTEM, f"Documento «{ws.display(name)}»:\n{passages}\n\nDomanda: {question.strip()}", 320)).strip()
        return f"«{ws.display(name)}»: {first_sentences(plain_for_speech(answer, 800), 560)}"

    # ---------------------------------------------------------------- briefing
    async def _briefing(self, _arg: str) -> str:
        if not self._on("briefing"):
            return _off()
        from .tools import NEED_CITY, speak_date
        now = self.now_fn()
        name = self.memory.get_profile("name") if self.memory else None
        if i18n.is_en():
            hello = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 18 else "Good evening"
        else:
            hello = "Buongiorno" if now.hour < 12 else "Buon pomeriggio" if now.hour < 18 else "Buonasera"
        parts = [f"{hello}{', ' + name if name else ''}! {speak_date(now)}"]
        try:
            w = await self._weather(i18n.pick("oggi", "today"))
            if w and w != NEED_CITY:
                parts.append(w)
        except Exception as e:                                           # noqa: BLE001
            log.info("briefing: meteo non disponibile (%s)", e)
        if self._on("calendar"):
            try:
                events = await self._events_of(now.date())
                if events:
                    if i18n.is_en():
                        parts.append("On your calendar: " + ", ".join(("all day " if a else f"{_at(h, m)} ") + f"\"{t}\"" for t, a, h, m in events[:4]) + ".")
                    else:
                        parts.append("In agenda: " + ", ".join(("tutto il giorno " if a else f"{_at(h, m)} ") + f"«{t}»" for t, a, h, m in events[:4]) + ".")
                else:
                    parts.append(i18n.pick("Non hai impegni in calendario.", "You have nothing on your calendar."))
            except MacError as e:
                log.info("briefing: calendario non disponibile (%s)", e)
        if self._on("reminders"):
            try:
                if sys.platform == "win32":
                    items = [label[3:] if label.startswith(("di ", "to ")) else label for _due, label in self._windows_reminders()]
                else:
                    items = [ln.strip() for ln in (await self._osa(REMINDERS_LIST_SCRIPT, app="Promemoria")).splitlines() if ln.strip()]
                if items:
                    parts.append(i18n.pick("Tra i promemoria: ", "Among your reminders: ") + ", ".join(items[:3]) + ".")
            except MacError as e:
                log.info("briefing: promemoria non disponibili (%s)", e)
        try:
            heads = await self._headlines(3)
            if heads:
                parts.append(i18n.pick("Dalle notizie: ", "From the news: ") + "; ".join(heads) + ".")
        except Exception as e:                                           # noqa: BLE001
            log.info("briefing: notizie non disponibili (%s)", e)
        return " ".join(parts)

    async def _headlines(self, n: int) -> list[str]:
        feed = ((self.cfg.get("tools") or {}).get("news_feed", i18n.pick(NEWS_FEED, NEWS_FEED_EN)))
        if not feed:
            return []
        r = await self.http.get(feed, timeout=6.0)
        if len(r.content) > 600_000:
            return []
        root = ET.fromstring(r.content)                                  # ElementTree non risolve entita' esterne: niente XXE
        titles = [re.sub(r"\s+", " ", (it.findtext("title") or "")).strip() for it in root.iter("item")]
        return [t[:110].rstrip(" ,;:") for t in titles if t][:n]
