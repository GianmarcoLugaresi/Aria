"""Strumenti gratuiti, senza chiavi API: ora, meteo (Open-Meteo), Wikipedia, ricerca web, timer, calcolo, memoria.

Il modello li chiama scrivendo una riga [[NOME: argomento]]; qui la eseguiamo e restituiamo UNA stringa breve
che il modello poi trasforma in risposta a voce.
"""
from __future__ import annotations

import ast
import asyncio
import datetime as dt
import json
import logging
import math
import operator
import os
import re
import time
from typing import Awaitable, Callable

import httpx

from .filetools import FILE_TOOLS, FileTools
from .macos import MacError
from .powers import ASK, POWER_TOOLS, PowerTools
from .screen import ScreenTools
from .timeparse import parse_when, say_when
from .workspace import WorkspaceError
from .textutil import ToolCall, normalize, pick

log = logging.getLogger("aria.tools")

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
OFFLINE = "Non riesco a collegarmi a internet in questo momento."

WMO = {0: "sereno", 1: "quasi sereno", 2: "poco nuvoloso", 3: "coperto", 45: "nebbia", 48: "nebbia con brina",
       51: "pioggerella", 53: "pioggerella", 55: "pioggerella intensa", 56: "pioggerella gelata", 57: "pioggerella gelata",
       61: "pioggia debole", 63: "pioggia", 65: "pioggia forte", 66: "pioggia gelata", 67: "pioggia gelata forte",
       71: "neve debole", 73: "neve", 75: "neve forte", 77: "nevischio", 80: "rovesci deboli", 81: "rovesci", 82: "rovesci violenti",
       85: "rovesci di neve", 86: "rovesci di neve forti", 95: "temporale", 96: "temporale con grandine", 99: "temporale con grandine forte"}


# ------------------------------------------------------------------------------- numeri e durate
_UNITS = {"zero": 0, "un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "tré": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
          "otto": 8, "nove": 9, "dieci": 10, "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14, "quindici": 15,
          "sedici": 16, "diciassette": 17, "diciotto": 18, "diciannove": 19, "cento": 100}
_TENS = {"vent": 20, "trent": 30, "quarant": 40, "cinquant": 50, "sessant": 60, "settant": 70, "ottant": 80, "novant": 90}


def it_number(word: str) -> int | None:
    w = word.lower().replace("é", "e").replace("è", "e")
    if w.isdigit():
        return int(w)
    if w in _UNITS:
        return _UNITS[w]
    if w == "tre":
        return 3
    for stem, val in _TENS.items():
        if w.startswith(stem):
            rem = w[len(stem):]
            if rem in ("i", "a"):
                return val
            for cand in (rem, rem[1:]):
                u = _UNITS.get(cand)
                if u is not None and 1 <= u <= 9:
                    return val + u
    return None


def parse_duration(text: str) -> int | None:
    """'dieci minuti' -> 600, 'un'ora e mezza' -> 5400, 'mezz'ora' -> 1800, '2 ore e 30 minuti' -> 9000."""
    raw = text.lower().replace("’", "'")
    raw = re.sub(r"(\d+)[,.](\d+)\s*(?:ore|ora|h|hr|hrs)\b", lambda m: f"{round(float(m.group(1) + '.' + m.group(2)) * 60)} minuti", raw)           # «1,5 ore» -> 90 minuti
    raw = re.sub(r"(\d+)\s*(?:h|hr|hrs)\s*(\d+)\b(?!\s*(?:ore|ora|h))", r"\1 ore \2 minuti", raw)                                                   # «1h30»
    raw = re.sub(r"(\d+)\s*(?:h|hr|hrs)\b", r"\1 ore", raw)                                                                                        # «2h»
    raw = re.sub(r"(\d+)\s*(?:mins?|m|')(?![a-z])", r"\1 minuti", raw)                                                                             # «30 min», «30m», «10'»
    raw = re.sub(r"(\d+)\s*(?:secs?|s)\b", r"\1 secondi", raw)                                                                                    # «45 sec»
    t = normalize(raw).replace("mezzora", "mezz ora")
    t = re.sub(r"\b(?:tre|3) quarti d ora\b", "45 minuti", t)
    tokens = t.split()
    total, found = 0, False
    if "quarto d ora" in t:
        total, found = total + 900, True
        tokens = " ".join(tokens).replace("quarto d ora", "").split()
    if "mezz ora" in " ".join(tokens):
        total, found = total + 1800, True
        tokens = " ".join(tokens).replace("mezz ora", "").split()
    mult = {"secondo": 1, "secondi": 1, "minuto": 60, "minuti": 60, "ora": 3600, "ore": 3600}
    last_unit = 0
    i = 0
    while i < len(tokens):
        n = it_number(tokens[i])
        if n is not None and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt in mult:
                total += n * mult[nxt]
                last_unit, found, i = mult[nxt], True, i + 2
                continue
        if (tokens[i] == "e" and i + 1 < len(tokens) and last_unit == 3600 and (i + 2 >= len(tokens) or tokens[i + 2] not in mult and tokens[i + 2] != "quarto")
                and (tokens[i + 1].isdigit() or tokens[i + 1] not in ("un", "uno", "una", "mezza", "mezzo")) and it_number(tokens[i + 1]) is not None):
            total += it_number(tokens[i + 1]) * 60                # «un'ora e 30», «un'ora e venti» = un'ora e trenta / venti minuti
            found, i = True, i + 2
            continue
        if tokens[i] == "e" and i + 1 < len(tokens) and tokens[i + 1] in ("mezza", "mezzo") and last_unit:
            total += last_unit // 2
            found, i = True, i + 2
            continue
        if tokens[i] == "e" and i + 2 < len(tokens) and tokens[i + 1] in ("un", "uno") and tokens[i + 2] == "quarto" and last_unit == 3600:
            total += 900
            found, i = True, i + 3
            continue
        i += 1
    return total if found and total > 0 else None


def fmt_duration(sec: int) -> str:
    h, rest = divmod(int(sec), 3600)
    m, s = divmod(rest, 60)
    parts = []
    if h:
        parts.append(f"{h} {'ora' if h == 1 else 'ore'}")
    if m:
        parts.append(f"{m} {'minuto' if m == 1 else 'minuti'}")
    if s and not h:
        parts.append(f"{s} {'secondo' if s == 1 else 'secondi'}")
    return " e ".join(parts) or "0 secondi"


# ------------------------------------------------------------------------------- calcolo sicuro
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_FUN = {"sqrt": math.sqrt, "abs": abs, "round": round}


def safe_eval(expr: str) -> float:
    expr = expr.lower().replace("x", "*").replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", ".").replace("%", "/100")

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            v = ev(n.operand)
            return v if isinstance(n.op, ast.UAdd) else -v
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise ValueError("esponente troppo grande")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUN and len(n.args) == 1:
            return _FUN[n.func.id](ev(n.args[0]))
        raise ValueError("espressione non valida")

    return ev(ast.parse(expr.strip(), mode="eval").body)


def speak_number(x: float) -> str:
    if float(x).is_integer():
        return str(int(x))
    return f"{x:.4f}".rstrip("0").rstrip(".").replace(".", " virgola ")


# ------------------------------------------------------------------------------- ora
def now_it(now: dt.datetime | None = None) -> str:
    n = now or dt.datetime.now()
    return f"{GIORNI[n.weekday()]} {n.day} {MESI[n.month - 1]} {n.year}, ore {n.hour}:{n.minute:02d}"


_U = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "undici", "dodici", "tredici",
      "quattordici", "quindici", "sedici", "diciassette", "diciotto", "diciannove"]
_T = {2: "venti", 3: "trenta", 4: "quaranta", 5: "cinquanta"}


def words_it(n: int) -> str:
    """0-59 e 2000-2099 in parole ("ventitré", "duemilaventisei"): il TTS legge le cifre in modo imprevedibile."""
    if n >= 2000:
        return "duemila" + (words_it(n - 2000) if n > 2000 else "")
    if n < 20:
        return _U[n]
    t, u = divmod(n, 10)
    base = _T[t]
    if u in (1, 8):
        base = base[:-1]                                     # ventuno, ventotto
    return base + (("tré" if u == 3 else _U[u]) if u else "")


def speak_clock(t: dt.datetime) -> str:
    """18:42 -> «diciotto e quarantadue»"""
    return f"{words_it(t.hour)} e {words_it(t.minute)}" if t.minute else f"{words_it(t.hour)}"


def speak_time(now: dt.datetime | None = None) -> str:
    n = now or dt.datetime.now()
    h, m = n.hour, n.minute
    if m == 45:                                             # "l'una meno un quarto"
        h, tail = (h + 1) % 24, " meno un quarto"
    else:
        tail = "" if m == 0 else " e un quarto" if m == 15 else " e mezza" if m == 30 else f" e {words_it(m)}"
    if h == 0:
        return f"È mezzanotte{tail}."
    if h == 12:
        return f"È mezzogiorno{tail}."
    h12 = h % 12 or 12
    return ("È l'una" if h12 == 1 else f"Sono le {words_it(h12)}") + tail + ("." if m else " in punto.")


def speak_date(now: dt.datetime | None = None) -> str:
    n = now or dt.datetime.now()
    day = "primo" if n.day == 1 else words_it(n.day)
    return f"Oggi è {GIORNI[n.weekday()]} {day} {MESI[n.month - 1]} {words_it(n.year)}."


def day_part(now: dt.datetime | None = None) -> str:
    h = (now or dt.datetime.now()).hour
    return "mattina" if 5 <= h < 12 else "pomeriggio" if 12 <= h < 18 else "sera" if 18 <= h < 23 else "notte"


# ------------------------------------------------------------------------------- Tools
# strumenti la cui risposta e' gia' una frase pronta da dire: si legge direttamente, senza passare dal modello
SPEAK_VERBATIM = {"METEO", "TIMER", "TIMER_STATO", "TIMER_ANNULLA", "CALCOLA", "CONVERTI", "DATA", "CASO", "AIUTO", "TRADUCI", "RICORDA", "DIMENTICA", "ORA", "MEMORIA", "SCHERMO"} | FILE_TOOLS | POWER_TOOLS
# Gli UNICI strumenti che il chatbot puo' lanciare da solo con [[NOME: ...]]. Tutto il resto (file, Mac) parte solo da una richiesta dell'utente
# riconosciuta a monte: un testo trovato sul web non puo' far fare niente ad Aria.
MODEL_TOOLS = {"CERCA", "WIKI", "METEO", "TIMER", "CALCOLA", "RICORDA", "ORA", "MEMORIA"}
REFUSED = "Questa cosa la faccio solo quando me la chiedi tu a voce."
NEED_CITY = "@CITTA"                                   # il meteo non sa dove abiti l'utente: chi chiama deve chiederglielo
FAILURES = ("Non ", "Su Wikipedia non", "Nessun ", "Strumento")


class Tools(FileTools, PowerTools, ScreenTools):
    def __init__(self, cfg: dict, memory=None, on_timer: Callable[[str], Awaitable[None]] | None = None,
                 client: httpx.AsyncClient | None = None):
        self.cfg, self.memory, self.on_timer = cfg, memory, on_timer
        self.http = client or httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "Aria/0.2 (assistente vocale personale; uso locale) python-httpx"})
        self.timers: dict[int, asyncio.Task] = {}
        self.timer_meta: dict[int, tuple[float, str]] = {}      # id -> (quando scatta, etichetta): per «quanto manca?» e «annulla il timer»
        self._tid = 0

    async def run(self, call: ToolCall) -> str:
        fn = {"CERCA": self._search, "WIKI": self._wiki, "METEO": self._weather, "TIMER": self._timer, "TIMER_STATO": self._timer_stato, "TIMER_ANNULLA": self._timer_annulla, "CALCOLA": self._calc,
              "CONVERTI": self._converti, "TRADUCI": self._traduci, "DATA": self._data, "CASO": self._caso, "AIUTO": self._aiuto,
              "RICORDA": self._remember, "DIMENTICA": self._forget, "ORA": self._now, "MEMORIA": self._memoria,
              "SCRIVI": self._scrivi, "SALVA": self._salva, "RICERCA": self._ricerca, "LISTA": self._lista, "NOTA": self._nota, "ELENCO": self._elenco,
              "LEGGI": self._leggi, "RIASSUMI": self._riassumi, "APRI": self._apri,
              "PROMEMORIA": self._promemoria, "PROMEMORIA_LISTA": self._promemoria_lista, "EVENTO": self._evento, "AGENDA": self._agenda,
              "MUSICA": self._musica, "VOLUME": self._volume, "APRI_APP": self._apri_app, "WEB": self._web, "MAPPA": self._mappa,
              "SCORCIATOIA": self._scorciatoia, "SCORCIATOIA_OK": self._scorciatoia_ok, "SCORCIATOIE": self._scorciatoie,
              "DOCUMENTO": self._documento, "BRIEFING": self._briefing, "NON_SO": self._non_so, "SCHERMO": self._schermo, "SISTEMA": self._sistema}.get(call.name)
        if fn is None:
            return f"Strumento '{call.name}' sconosciuto."
        try:
            out = await fn(call.arg)
        except PermissionError:
            log.warning("strumento %s: permesso negato", call.name)
            return "Non ho il permesso di scrivere in quella cartella: controlla i permessi di Aria in Impostazioni di Sistema, sotto Privacy e sicurezza."
        except (WorkspaceError, MacError) as e:                  # problemi spiegabili: il messaggio e' gia' in italiano
            return str(e)
        except (httpx.HTTPError, asyncio.TimeoutError, OSError) as e:
            log.warning("strumento %s: errore di rete %s", call.name, e)
            return OFFLINE
        except Exception as e:                                  # noqa: BLE001
            log.exception("strumento %s fallito", call.name)
            return f"Non ci sono riuscita: {e}"
        return out[:1500 if call.name == "BRIEFING" else 900]

    # --- semplici
    async def _now(self, arg: str) -> str:
        a = arg.strip().lower()
        if a.startswith("citta:"):                                  # «che ora e' a Tokyo?»: l'ora di la', non la nostra
            from . import worldclock
            hit = worldclock.find_zone(a[6:])
            if not hit:
                return "Non so che fuso orario abbia quel posto."
            zone, name = hit
            try:
                when = worldclock.time_in(zone)
            except Exception:                                       # noqa: BLE001  (Windows senza il pacchetto tzdata: i fusi orari non ci sono)
                return "Non ho i dati dei fusi orari su questo computer, quindi non so dirti l'ora di là."
            said = speak_time(when)
            h = when.hour
            if said.startswith(("Sono", "È l'una")) and h not in (0, 12):                 # a 12 ore ci si confonde: si aggiunge «di sera», «di mattina»…
                part = "di notte" if h < 5 else "di mattina" if h < 12 else "del pomeriggio" if h < 18 else "di sera"
                said = said.rstrip(".") + f" {part}."
            said = said[0].lower() + said[1:]                         # «Sono le tre e dieci.» -> «sono le tre e dieci.»
            where = name if name.startswith(("in ", "a ", "nel", "negli", "alle")) else f"a {name}"
            today = dt.date.today()
            extra = " Là è già domani." if when.date() > today else " Là è ancora ieri." if when.date() < today else ""
            return f"{where[0].upper() + where[1:]} {said}{extra}"
        if a.startswith("data") or a.startswith("giorno"):
            return speak_date()
        return speak_time() if a.startswith("ora") else speak_time() + " " + speak_date()

    async def _calc(self, arg: str) -> str:
        try:
            return f"Fa {speak_number(safe_eval(arg))}."
        except Exception:                                       # noqa: BLE001
            return "Non riesco a fare questo calcolo."

    async def _converti(self, arg: str) -> str:
        from . import everyday
        return everyday.convert(arg)

    async def _data(self, arg: str) -> str:
        from . import everyday
        return everyday.date_answer(arg, self.now_fn())

    TRANSLATE_SYSTEM = ("Sei un traduttore. Traduci la frase nella lingua richiesta. Rispondi SOLO con la traduzione, senza spiegazioni, senza virgolette e senza note. "
                        "Se la lingua richiesta e' l'italiano, traduci in italiano.")

    async def _traduci(self, arg: str) -> str:
        """arg = «inglese|buongiorno a tutti». Un prompt a parte, a temperatura zero: il chatbot libero, su questo, scrive «bene morning»."""
        lang, _, body = arg.partition("|")
        lang, body = lang.strip().lower(), body.strip()
        if not body:
            return "Dimmi cosa devo tradurre e in che lingua, per esempio: traduci buongiorno in inglese."
        if lang in ("cinese", "giapponese", "russo", "arabo", "coreano", "greco", "turco", "hindi", "ebraico", "thailandese", "vietnamita", "ucraino"):
            return f"In {lang} non so scrivere né pronunciare bene. Posso tradurre in inglese, francese, spagnolo, tedesco, portoghese e in altre lingue europee."
        if self.generate is None:
            return "Per ora non riesco a tradurre."
        out = (await self.generate(self.TRANSLATE_SYSTEM, f"Lingua: {lang}\nFrase: {body}", 120, 0.0)).strip()
        out = out.splitlines()[0].strip().strip("\"'«»“” ") if out else ""
        if not out:
            return "Non sono riuscita a tradurlo, riprova."
        return f"In {lang}: {out}."

    async def _caso(self, arg: str) -> str:
        from . import everyday
        return everyday.chance_answer(arg)

    async def _aiuto(self, _arg: str) -> str:
        from . import everyday
        from . import profiles as P
        return everyday.help_text(P.get_powers(self.cfg.get("_config_path")))

    async def _remember(self, arg: str) -> str:
        if not self.memory:
            return "Memoria disattivata."
        return "Va bene, me lo ricordo." if self.memory.add_fact(arg) else "Lo sapevo già."

    async def _memoria(self, _arg: str) -> str:
        return self.memory.describe() if self.memory else "Memoria disattivata."

    async def _forget(self, arg: str) -> str:
        if not self.memory:
            return "Memoria disattivata."
        n = self.memory.forget(arg)
        return "Fatto, l'ho dimenticato." if n else "Non ricordavo niente del genere."

    # --- timer
    async def _timer(self, arg: str) -> str:
        """arg = «dieci minuti | pasta» (una durata) oppure «metti una sveglia alle 7:30 | » (un orario). I timer si salvano su disco e si riarmano
        al prossimo avvio: una sveglia del mattino non si perde se Aria viene riaperta."""
        dur_txt, _, label = arg.partition("|")
        label = label.strip()
        now = self.now_fn()
        sec = parse_duration(dur_txt)
        at = None
        if not sec:
            w = parse_when(dur_txt, now) if dur_txt.strip() else None
            if w and w.has_time:
                at = w.dt
                sec = max(1, int((at - now).total_seconds()))
            else:
                return f"{ASK}|TIMER||Per quanto tempo, o a che ora?"
        self._tid += 1
        tid = self._tid
        due = time.time() + sec
        self.timers[tid] = asyncio.create_task(self._fire(tid, sec, label, due))
        self.timer_meta[tid] = (due, label)
        self._save_timers(add=(tid, due, label))
        if at is not None:
            when = say_when(at, True, now)
            if label.startswith("di "):
                return pick([f"Va bene, {when} ti ricordo {label}.", f"Ok, {when} ti dico {label}."])
            return pick([f"Sveglia impostata {when}", f"Va bene, ti sveglio {when}", f"Ok, sveglia {when}"]) + (f", per {label}." if label else ".")
        d = fmt_duration(sec)
        if label.startswith("di "):                                           # «ricordami tra dieci minuti di spegnere il forno»
            return pick([f"Va bene, tra {d} ti ricordo {label}.", f"Ok, tra {d} ti dico {label}."])
        return pick([f"Timer impostato: {d}", f"Ok, {d}", f"Va bene, ti avviso tra {d}"]) + (f", per {label}." if label else ".")

    def _live_timers(self) -> list[tuple[int, float, str]]:
        now = time.time()
        return sorted([(tid, due, label) for tid, (due, label) in self.timer_meta.items() if tid in self.timers and due > now - 1], key=lambda x: x[1])

    def _drop_timer(self, tid: int) -> None:
        """Annulla un timer SUBITO (anche se il suo compito non e' ancora partito) e lo toglie dal disco: altrimenti ripartirebbe alla prossima apertura."""
        task = self.timers.pop(tid, None)
        due, _label = self.timer_meta.pop(tid, (None, ""))
        if task:
            task.cancel()
        if due is not None:
            self._save_timers(remove=due)

    async def _timer_stato(self, arg: str) -> str:
        """«quanto manca al timer?», «che timer ho?»"""
        live = self._live_timers()
        if not live:
            return "Non hai nessun timer attivo."
        now = time.time()
        want = normalize(arg)
        if want:
            hit = [t for t in live if want in normalize(t[2])] or live
            live = hit
        if len(live) == 1:
            _tid, due, label = live[0]
            return f"Mancano {fmt_duration(max(1, int(due - now)))}" + (f" al timer per {label}." if label else " al timer.")
        parts = [f"{fmt_duration(max(1, int(due - now)))}" + (f" per {label}" if label else "") for _t, due, label in live[:4]]
        return f"Hai {words_it(len(live))} timer: " + "; ".join(parts) + "."

    async def _timer_annulla(self, arg: str) -> str:
        """«annulla il timer», «ferma la sveglia della pasta», «cancella tutti i timer»"""
        live = self._live_timers()
        if not live:
            return "Non c'è nessun timer attivo."
        want = normalize(arg)
        if re.search(r"\b(?:tutti|tutte)\b", want):
            for tid, _d, _l in live:
                self._drop_timer(tid)
            return "Fatto, ho annullato tutti i timer." if len(live) > 1 else "Fatto, timer annullato."
        pick_ = [t for t in live if want and (want in normalize(t[2]) or normalize(t[2]) in want and t[2])] if want else []
        if not pick_ and len(live) == 1:
            pick_ = live
        if not pick_:
            names = " e ".join(f"{fmt_duration(max(1, int(d - time.time())))}" + (f" per {l}" if l else "") for _t, d, l in live[:4])
            return f"{ASK}|TIMER_ANNULLA||Hai più di un timer: {names}. Quale annullo?"
        for tid, _d, label in pick_:
            self._drop_timer(tid)
        return "Fatto, ho annullato il timer" + (f" per {pick_[0][2]}." if len(pick_) == 1 and pick_[0][2] else ".")

    async def _fire(self, tid: int, sec: float, label: str, due: float | None = None) -> None:
        try:
            await asyncio.sleep(sec)
            if self.on_timer:
                await self.on_timer(label or "il tempo che avevi chiesto")
        finally:
            self.timers.pop(tid, None)
            self.timer_meta.pop(tid, None)
            self._save_timers(remove=due)

    # ---- timer che sopravvivono al riavvio
    def _timers_path(self) -> str | None:
        d = self.cfg.get("data_dir")
        return os.path.join(d, "timers.json") if d else None

    def _save_timers(self, add: tuple | None = None, remove: float | None = None) -> None:
        path = self._timers_path()
        if not path:
            return
        try:
            items = json.load(open(path)) if os.path.exists(path) else []
        except (OSError, ValueError):
            items = []
        if add:
            items.append({"due": add[1], "label": add[2]})
        if remove is not None:
            items = [i for i in items if abs(i["due"] - remove) > 0.5]
        try:
            tmp = path + ".tmp"
            with open(tmp, "w") as f:                                       # (file nuovo e poi scambio: se Aria si chiude a meta' scrittura le sveglie non si perdono)
                json.dump([i for i in items if i["due"] > time.time() - 600], f)
            os.replace(tmp, path)
        except OSError as e:
            log.debug("timer non salvati: %s", e)

    async def restore_timers(self) -> int:
        """Riarma i timer rimasti (chiamato all'avvio). Uno scaduto da poco viene annunciato subito, uno molto vecchio si butta."""
        path = self._timers_path()
        if not path or not os.path.exists(path):
            return 0
        try:
            items = json.load(open(path))
        except (OSError, ValueError):
            return 0
        n = 0
        for i in items:
            left = i["due"] - time.time()
            if left < -600:
                continue
            self._tid += 1
            self.timers[self._tid] = asyncio.create_task(self._fire(self._tid, max(1.0, left), i.get("label", ""), i["due"]))
            self.timer_meta[self._tid] = (i["due"], i.get("label", ""))
            n += 1
        return n

    # --- meteo (Open-Meteo: gratuito, senza chiave)
    async def _weather(self, arg: str) -> str:
        from . import everyday
        loc = self.cfg.get("location") or {}
        sun = arg.startswith("@sole")                                      # «a che ora tramonta il sole?»: alba e tramonto di Open-Meteo
        arg = arg[len("@sole"):].strip() if sun else arg
        offs, label, rest = everyday.forecast_when(arg, self.now_fn().date())
        if offs is None:
            return label                                                   # oltre i 15 giorni le previsioni non ci sono: lo dice invece di dare quelle di oggi
        city = re.sub(r"\b(a|di|meteo|tempo|previsioni|per|il|la|in)\b", " ", rest, flags=re.I).strip(" ,.")
        city = re.sub(r"\s+", " ", city)
        home = (self.memory.get_profile("city") if self.memory else None) or loc.get("city")      # la citta' detta dall'utente vale piu' di quella in config
        target = city or home
        if not target:
            return NEED_CITY
        if loc.get("city") and loc.get("lat") is not None and normalize(target) == normalize(loc["city"]):
            lat, lon, name = loc["lat"], loc["lon"], loc["city"]
        else:
            g = await self.http.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": target, "count": 1, "language": "it"})
            res = (g.json().get("results") or [])
            if not res:
                return f"Non trovo la città '{target}'."
            lat, lon, name = res[0]["latitude"], res[0]["longitude"], res[0]["name"]
        days = max(offs) + 1
        if sun:
            r = await self.http.get("https://api.open-meteo.com/v1/forecast", params={"latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": days, "daily": "sunrise,sunset"})
            d = r.json()["daily"]
            day = offs[0]
            rise, setting = dt.datetime.fromisoformat(d["sunrise"][day]), dt.datetime.fromisoformat(d["sunset"][day])
            return f"{label} a {name} il sole sorge alle {speak_clock(rise)} e tramonta alle {speak_clock(setting)}."
        r = await self.http.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": days,
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
        d = r.json()
        daily = d["daily"]
        parts = []
        for k, day in enumerate(offs):
            rain = round(daily['precipitation_probability_max'][day] or 0)
            lead = label if len(offs) == 1 else (GIORNI[(self.now_fn().date() + dt.timedelta(days=day)).weekday()].capitalize())
            head = f"{lead} a {name}" if k == 0 or len(offs) == 1 else lead
            parts.append(f"{head}: {WMO.get(daily['weather_code'][day], 'variabile')}, "
                         f"tra {round(daily['temperature_2m_min'][day])} e {round(daily['temperature_2m_max'][day])} gradi, "
                         f"probabilità di pioggia {rain} per cento.")
        txt = " ".join(parts)
        if offs == [0]:
            c = d["current"]
            txt += f" Adesso ci sono {round(c['temperature_2m'])} gradi, {WMO.get(c['weather_code'], 'variabile')}."
        return txt

    # --- Wikipedia
    async def _get_json(self, url: str, params: dict | None = None, tries: int = 2):
        """GET con un secondo tentativo: Wikipedia ogni tanto risponde 429/vuoto se le richieste sono ravvicinate."""
        for k in range(tries):
            r = await self.http.get(url, params=params)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    pass
            await asyncio.sleep(0.6 * (k + 1))
        return None

    async def _wiki(self, arg: str) -> str:
        s = await self._get_json("https://it.wikipedia.org/w/api.php",
                                 {"action": "opensearch", "search": arg, "limit": 1, "format": "json", "namespace": 0})
        if not s or not s[1]:
            return f"Su Wikipedia non trovo niente su '{arg}'."
        d = await self._get_json("https://it.wikipedia.org/api/rest_v1/page/summary/" + s[1][0].replace(" ", "_"))
        ex = ((d or {}).get("extract") or "").strip()
        return (f"{s[1][0]}: " + ex[:520]) if ex else f"Nessun riassunto per '{s[1][0]}'."

    # --- ricerca web gratuita: SearXNG (tuo) oppure DuckDuckGo via libreria ddgs
    async def _web_results(self, arg: str, n: int | None = None) -> list[tuple[str, str, str]]:
        """[(titolo, testo, indirizzo)] dalla ricerca web (SearXNG tuo, oppure DuckDuckGo via ddgs)."""
        cfg = self.cfg["tools"]["web_search"]
        n = n or cfg.get("max_results", 4)
        if cfg.get("searxng_url"):
            r = await self.http.get(cfg["searxng_url"].rstrip("/") + "/search",
                                    params={"q": arg, "format": "json", "language": "it-IT", "safesearch": 1})
            return [(x.get("title", ""), x.get("content", ""), x.get("url", "")) for x in r.json().get("results", [])[:n]]

        def blocking():
            from ddgs import DDGS                          # pip install ddgs
            return [(x.get("title", ""), x.get("body", ""), x.get("href", "")) for x in DDGS().text(arg, region="it-it", max_results=n)]
        return await asyncio.get_running_loop().run_in_executor(None, blocking)

    async def _search(self, arg: str) -> str:
        results = await self._web_results(arg)
        if not results:
            return f"Nessun risultato per '{arg}'."
        return "Risultati: " + " | ".join(f"{t}: {b[:160]}" for t, b, _u in results)
