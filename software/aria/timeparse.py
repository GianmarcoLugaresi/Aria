"""Date e orari detti a voce in italiano: «domani alle nove e mezza», «lunedì alle 15», «il 15 ottobre», «alle cinque del pomeriggio», «tra due giorni».

`parse_when(testo, adesso)` restituisce quando, se e' stata detta anche l'ora, e il testo rimasto senza le parole di data/ora
(«ricordami domani alle 9 di chiamare Marco» -> quando = domani 9:00, resto = «ricordami di chiamare Marco»).
Autonomo (nessuna dipendenza dal resto di Aria). Regole sulle ore senza «di mattina/sera»: 1-6 = pomeriggio ("alle 5" = 17:00), 7-11 = mattina.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

_ACCENTS = str.maketrans("àáâäèéêëìíîïòóôöùúûüñç’'", "aaaaeeeeiiiioooouuuunc  ")
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
_DAYS = {"lunedi": 0, "martedi": 1, "mercoledi": 2, "giovedi": 3, "venerdi": 4, "sabato": 5, "domenica": 6}
_MONTHS = {m: i + 1 for i, m in enumerate(["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"])}

_UNITS = {"zero": 0, "un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10,
          "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14, "quindici": 15, "sedici": 16, "diciassette": 17, "diciotto": 18, "diciannove": 19}
_TENS = {"venti": 20, "vent": 20, "trenta": 30, "trent": 30, "quaranta": 40, "quarant": 40, "cinquanta": 50, "cinquant": 50}
NUM = r"(?:\d{1,2}|zero|un|uno|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici|tredici|quattordici|quindici|sedici|diciassette|diciotto|diciannove|(?:venti|trenta|quaranta|cinquanta|vent|trent|quarant|cinquant)(?:uno|due|tre|quattro|cinque|sei|sette|otto|nove)?|(?:venti|trenta)(?=\b))"


def fold(raw: str) -> str:
    """Minuscolo e senza accenti, ma della STESSA lunghezza dell'originale (si ritaglia dal testo vero)."""
    return raw.lower().translate(_ACCENTS)


def to_int(word: str) -> int | None:
    w = word.strip().lower()
    if w.isdigit():
        return int(w)
    if w in _UNITS:
        return _UNITS[w]
    for stem, val in _TENS.items():
        if w.startswith(stem):
            rem = w[len(stem):]
            if rem == "":
                return val
            u = _UNITS.get(rem)
            if u is not None and 1 <= u <= 9:
                return val + u
    return None


@dataclass
class When:
    dt: dt.datetime
    has_time: bool            # l'utente ha detto un'ora (altrimenti e' un'ora predefinita)
    has_date: bool            # ha detto un giorno
    rest: str                 # il testo senza le parole di data/ora


def _cut(raw: str, spans: list[tuple[int, int]]) -> str:
    out, last = [], 0
    for a, b in sorted(spans):
        if a < last:
            continue
        out.append(raw[last:a])
        last = b
    out.append(raw[last:])
    return re.sub(r"\s+", " ", "".join(out)).strip(" ,.;:!?-")


_DAYPART = re.compile(r"\b(?:di|del|della|nel|nella|la|in|al)?\s*(mattina|mattino|pomeriggio|sera|notte)\b")
_TIME = re.compile(rf"\b(?:alle ore|alle|all|ore|verso le|per le)\s+({NUM})(?:\s*[:.]\s*(\d{{2}}))?(?:\s+e\s+(mezza|mezzo|un quarto|{NUM}))?(?:\s+meno\s+(un quarto|{NUM}))?\b")


def _hour_with_daypart(h: int, part: str | None) -> int:
    if part in ("pomeriggio", "sera"):
        return h + 12 if h < 12 else h
    if part == "notte":
        return h + 12 if 6 <= h < 12 else (0 if h == 12 else h)
    if part in ("mattina", "mattino"):
        return h
    return h + 12 if 1 <= h <= 6 else h                   # senza indicazioni: "alle 5" e' il pomeriggio


def parse_when(raw: str, now: dt.datetime, default_hour: int = 9) -> When | None:
    f = fold(raw)
    spans: list[tuple[int, int]] = []

    # ---- relativo: "tra due ore", "tra 3 giorni", "tra un quarto d'ora"
    m = re.search(rf"\b(?:tra|fra)\s+({NUM})\s+(minut[io]|or[ae]|giorn[io]|settiman[ae])\b", f)
    if m:
        n = to_int(m.group(1)) or 0
        unit = m.group(2)
        delta = (dt.timedelta(minutes=n) if unit.startswith("min") else dt.timedelta(hours=n) if unit.startswith("or")
                 else dt.timedelta(days=n) if unit.startswith("giorn") else dt.timedelta(weeks=n))
        end = m.end()
        tail = re.match(rf"\s+e\s+(mezza|mezzo|un quarto|tre quarti|({NUM})\s+minut[io])\b", f[end:]) if unit.startswith("or") else None
        if tail:                                                              # «tra un'ora e mezza», «tra 2 ore e un quarto», «tra un'ora e 20 minuti» (prima contava solo l'ora)
            g = tail.group(1)
            delta += dt.timedelta(minutes=30 if g in ("mezza", "mezzo") else 15 if g == "un quarto" else 45 if g == "tre quarti" else (to_int(tail.group(2)) or 0))
            end += tail.end()
        when = now + delta
        timed = unit.startswith(("min", "or"))
        if not timed:
            when = when.replace(hour=default_hour, minute=0, second=0, microsecond=0)
        spans.append((m.start(), end))
        tm = _TIME.search(f)                                                  # "tra due giorni alle 18"
        if tm and not timed:
            when = when.replace(hour=_hour_with_daypart(to_int(tm.group(1)) or 0, None), minute=int(tm.group(2) or 0))
            spans.append((tm.start(), tm.end()))
            timed = True
        return When(when.replace(second=0, microsecond=0), timed, True, _cut(raw, spans))
    m = re.search(r"\b(?:tra|fra)\s+(?:un\s+|tre\s+)?(quarto d ora|quarti d ora|mezz ora|mezzora|un ora|un or)\b", f)
    if m:
        mins = 45 if ("quarti" in m.group(1)) else 15 if "quarto" in m.group(1) else 30 if "mezz" in m.group(1) else 60
        return When((now + dt.timedelta(minutes=mins)).replace(second=0, microsecond=0), True, True, _cut(raw, [(m.start(), m.end())]))

    # ---- giorno
    day: dt.date | None = None
    part_default: str | None = None
    for pat, fn in (
        (r"\bdopodomani\b", lambda m: now.date() + dt.timedelta(days=2)),
        (r"\bdomani\b", lambda m: now.date() + dt.timedelta(days=1)),
        (r"\boggi\b", lambda m: now.date()),
        (r"\bstasera\b", lambda m: now.date()),
        (r"\bstanotte\b", lambda m: now.date()),
        (r"\bstamattina\b|\bstamani\b", lambda m: now.date()),
    ):
        m = re.search(pat, f)
        if m:
            day = fn(m)
            part_default = {"stasera": "sera", "stanotte": "notte", "stamattina": "mattina", "stamani": "mattina"}.get(m.group(0))
            spans.append((m.start(), m.end()))
            break
    if day is None:
        m = re.search(r"\b(?:il\s+|di\s+|per\s+)?(lunedi|martedi|mercoledi|giovedi|venerdi|sabato|domenica)(?:\s+(?:prossimo|prox))?\b", f)
        if m:
            delta = (_DAYS[m.group(1)] - now.weekday()) % 7 or 7
            day = now.date() + dt.timedelta(days=delta)
            spans.append((m.start(), m.end()))
    if day is None:
        m = re.search(rf"\b(?:il\s+)?(\d{{1,2}}|primo)\s+({'|'.join(_MONTHS)})(?:\s+(\d{{4}}))?\b", f)
        if m:
            d, mo = (1 if m.group(1) == "primo" else int(m.group(1))), _MONTHS[m.group(2)]
            y = int(m.group(3)) if m.group(3) else now.year
            for _ in range(1 if m.group(3) else 5):                       # (il 29 febbraio senza anno: il prossimo che esiste)
                try:
                    cand = dt.date(y, mo, d)
                except ValueError:
                    y += 1
                    continue
                if not m.group(3) and cand < now.date():
                    y += 1
                    continue
                day = cand
                spans.append((m.start(), m.end()))
                break
    if day is None:
        m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", f)
        if m:
            d, mo = int(m.group(1)), int(m.group(2))
            y = int(m.group(3)) + (2000 if m.group(3) and len(m.group(3)) == 2 else 0) if m.group(3) else now.year
            try:
                cand = dt.date(y, mo, d)
                if not m.group(3) and cand < now.date():
                    cand = dt.date(y + 1, mo, d)
                day = cand
                spans.append((m.start(), m.end()))
            except ValueError:
                day = None
    if day is None:
        m = re.search(r"\bil\s+(\d{1,2})\b(?!\s*(?:e\b|[:.]\d))(?!\s+(?:" + "|".join(_MONTHS) + r"))", f)
        if m and 1 <= int(m.group(1)) <= 31:
            d = int(m.group(1))
            y, mo = now.year, now.month
            for _ in range(3):
                try:
                    cand = dt.date(y, mo, d)
                except ValueError:
                    cand = None
                if cand and cand >= now.date():
                    day = cand
                    spans.append((m.start(), m.end()))
                    break
                mo += 1
                if mo > 12:
                    mo, y = 1, y + 1

    # ---- parte della giornata e ora
    part = part_default
    dm = _DAYPART.search(f)
    if dm:
        part = dm.group(1)
        spans.append((dm.start(), dm.end()))
    hour = minute = None
    tm = _TIME.search(f)
    if tm:
        h = to_int(tm.group(1))
        if h is not None and 0 <= h <= 24:
            minute = int(tm.group(2)) if tm.group(2) else 0
            extra = tm.group(3)
            if extra:
                minute = 30 if extra in ("mezza", "mezzo") else 15 if extra == "un quarto" else (to_int(extra) or 0)
            less = tm.group(4)
            hour = _hour_with_daypart(h % 24, part)
            if less:
                hour, minute = (hour - 1) % 24, 60 - (15 if less == "un quarto" else (to_int(less) or 0))
            spans.append((tm.start(), tm.end()))
    else:
        for word, (h, mi) in (("mezzogiorno", (12, 0)), ("mezzanotte", (0, 0))):
            m = re.search(rf"\b(?:a\s+|verso\s+)?{word}\b", f)                                 # («domani a mezzogiorno»: anche la «a» non resta nel testo del promemoria)
            if m:
                hour, minute = h, mi
                spans.append((m.start(), m.end()))
                break

    if hour is None:
        for pat, (h, mi) in ((r"\bdopo pranzo\b", (14, 0)), (r"\bdopo cena\b", (21, 30)), (r"\bprima di pranzo\b", (12, 0)), (r"\bprima di cena\b", (19, 30)),
                             (r"\ba pranzo\b", (13, 0)), (r"\ba cena\b", (20, 0)), (r"\bnel pomeriggio\b", (16, 0)), (r"\bsul tardi\b", (18, 0))):
            m = re.search(pat, f)
            if m:
                hour, minute = h, mi
                spans.append((m.start(), m.end()))
                tm = tm or m                                                       # (vale come orario detto: non chiede l'ora)
                break
    if day is None and hour is None and part is None:
        return None
    if hour is None:
        hour = {"mattina": 9, "mattino": 9, "pomeriggio": 15, "sera": 20, "notte": 23}.get(part or "", default_hour)
        minute = 0
    has_time = tm is not None or (hour is not None and bool(re.search(r"\b(?:mezzogiorno|mezzanotte)\b", f)))
    target_day = day or now.date()
    when = dt.datetime.combine(target_day, dt.time(hour % 24, minute or 0))
    if day is None and when <= now:                                            # solo l'ora, gia' passata oggi: domani
        when += dt.timedelta(days=1)
    elif part_default == "notte" and when <= now and when.hour < 12:          # «stanotte alle 2» detto alle 22: e' la notte che viene, non quella passata
        when += dt.timedelta(days=1)
    return When(when, has_time, day is not None, _cut(raw, spans))


def say_when(when: dt.datetime, has_time: bool, now: dt.datetime) -> str:
    """«domani alle nove e mezza», «lunedì alle quindici», «oggi»: come si dice a voce (numeri in lettere)."""
    from .tools import words_it
    delta = (when.date() - now.date()).days
    if delta == 0:
        day = "oggi"
    elif delta == 1:
        day = "domani"
    elif delta == 2:
        day = "dopodomani"
    elif 0 < delta < 7:
        day = GIORNI[when.weekday()]
    else:
        day = f"{GIORNI[when.weekday()]} {words_it(when.day) if when.day < 60 else when.day} {MESI[when.month - 1]}"
    if not has_time:
        return day
    h, m = when.hour, when.minute
    if h == 0 and m == 0:
        return f"{day} a mezzanotte"
    if h == 12 and m == 0:
        return f"{day} a mezzogiorno"
    at = "all'una" if h == 1 else f"alle {words_it(h)}"
    tail = "" if m == 0 else " e mezza" if m == 30 else " e un quarto" if m == 15 else f" e {words_it(m)}"
    return f"{day} {at}{tail}"
