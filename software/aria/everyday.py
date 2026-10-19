"""Le piccole cose di ogni giorno che Aria deve saper fare SENZA inventare: conversioni di unita', conti con le date, dado e moneta, e dire cosa sa fare.
Tutto locale e deterministico: un chatbot piccolo, su queste domande, risponde a caso (e sbaglia anche i conti)."""
from __future__ import annotations

import datetime as dt
import random
import re
from typing import Callable

from .textutil import normalize

# ------------------------------------------------------------------------------- numeri (anche con la virgola)


def decimals_to_words(text: str) -> str:
    """«2,5» e «due virgola cinque» diventano un'unica parola «2punto5» (normalize toglie la punteggiatura e la virgola sparirebbe: 2,5 diventerebbe 25)."""
    s = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", text)                              # 1.000 = mille (migliaia all'italiana)
    s = re.sub(r"(\d)[,.](\d)", r"\1punto\2", s)
    return re.sub(r"\b([A-Za-zÀ-ÿ0-9]+)\s+virgola\s+([A-Za-zÀ-ÿ0-9]+)\b", r"\1punto\2", s, flags=re.I)


def num(text: str) -> float | None:
    from .intent import number_it
    w = normalize(decimals_to_words(text)).replace(" ", "")
    if w in ("mezzo", "mezza", "unmezzo"):
        return 0.5
    if w in ("unquarto", "unquartodi"):
        return 0.25
    if "punto" in w:
        a, _, b = w.partition("punto")
        ai = number_it(a) if a else 0
        bi = number_it(b)
        if ai is None or bi is None:
            return None
        return float(f"{ai}.{bi}")
    v = number_it(w)
    return None if v is None else float(v)


def fmt(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    whole, _, frac = f"{x:.2f}".rstrip("0").rstrip(".").partition(".")
    if not frac:
        return whole
    zeros = len(frac) - len(frac.lstrip("0"))
    return f"{whole} virgola " + "zero " * zeros + (frac.lstrip("0") or "")


# ------------------------------------------------------------------------------- conversioni
# nome canonico -> (grandezza, fattore verso l'unita' base, singolare, plurale, [altri modi di dirlo, senza accenti])
_U: list[tuple[str, str, float, str, str, list[str]]] = [
    ("mm", "lunghezza", 0.001, "millimetro", "millimetri", ["millimetro", "millimetri", "mm"]),
    ("cm", "lunghezza", 0.01, "centimetro", "centimetri", ["centimetro", "centimetri", "cm"]),
    ("m", "lunghezza", 1.0, "metro", "metri", ["metro", "metri", "m"]),
    ("km", "lunghezza", 1000.0, "chilometro", "chilometri", ["chilometro", "chilometri", "kilometro", "kilometri", "km"]),
    ("in", "lunghezza", 0.0254, "pollice", "pollici", ["pollice", "pollici", "inch"]),
    ("ft", "lunghezza", 0.3048, "piede", "piedi", ["piede", "piedi", "foot", "feet"]),
    ("yd", "lunghezza", 0.9144, "iarda", "iarde", ["iarda", "iarde", "yard"]),
    ("mi", "lunghezza", 1609.344, "miglio", "miglia", ["miglio", "miglia"]),
    ("mg", "massa", 0.000001, "milligrammo", "milligrammi", ["milligrammo", "milligrammi", "mg"]),
    ("g", "massa", 0.001, "grammo", "grammi", ["grammo", "grammi", "gr"]),
    ("hg", "massa", 0.1, "etto", "etti", ["etto", "etti", "ettogrammo", "ettogrammi", "ettogr"]),
    ("kg", "massa", 1.0, "chilo", "chili", ["chilo", "chili", "chilogrammo", "chilogrammi", "kilo", "kili", "kg"]),
    ("t", "massa", 1000.0, "tonnellata", "tonnellate", ["tonnellata", "tonnellate"]),
    ("lb", "massa", 0.45359237, "libbra", "libbre", ["libbra", "libbre", "pound", "pounds", "lb"]),
    ("oz", "massa", 0.028349523, "oncia", "once", ["oncia", "once", "ounce", "ounces", "oz"]),
    ("ml", "volume", 0.001, "millilitro", "millilitri", ["millilitro", "millilitri", "ml"]),
    ("cl", "volume", 0.01, "centilitro", "centilitri", ["centilitro", "centilitri", "cl"]),
    ("dl", "volume", 0.1, "decilitro", "decilitri", ["decilitro", "decilitri", "dl"]),
    ("l", "volume", 1.0, "litro", "litri", ["litro", "litri", "l"]),
    ("gal", "volume", 3.785411784, "gallone", "galloni", ["gallone", "galloni", "gallon"]),
    ("cucchiaio", "volume", 0.015, "cucchiaio", "cucchiai", ["cucchiaio", "cucchiai"]),
    ("cucchiaino", "volume", 0.005, "cucchiaino", "cucchiaini", ["cucchiaino", "cucchiaini"]),
    ("kmh", "velocita", 1 / 3.6, "chilometro orario", "chilometri orari", ["chilometro orario", "chilometri orari", "chilometri all ora", "chilometri l ora", "km h", "kmh", "kilometri orari", "chilometri ora"]),
    ("ms", "velocita", 1.0, "metro al secondo", "metri al secondo", ["metro al secondo", "metri al secondo", "metri secondo", "m s"]),
    ("mph", "velocita", 0.44704, "miglio orario", "miglia orarie", ["miglio orario", "miglia orarie", "miglia all ora", "miglia l ora", "mph"]),
    ("nodo", "velocita", 0.514444, "nodo", "nodi", ["nodo", "nodi"]),
    ("mq", "area", 1.0, "metro quadro", "metri quadri", ["metro quadro", "metri quadri", "metro quadrato", "metri quadrati", "mq", "m2", "m quadri", "m quadrati", "m quadro", "m quadrato"]),
    ("ha", "area", 10000.0, "ettaro", "ettari", ["ettaro", "ettari"]),
    ("kmq", "area", 1e6, "chilometro quadrato", "chilometri quadrati", ["chilometro quadrato", "chilometri quadrati", "chilometro quadro", "chilometri quadri", "kmq"]),
    ("acro", "area", 4046.8564224, "acro", "acri", ["acro", "acri"]),
    ("s", "tempo", 1.0, "secondo", "secondi", ["secondo", "secondi"]),
    ("min", "tempo", 60.0, "minuto", "minuti", ["minuto", "minuti"]),
    ("h", "tempo", 3600.0, "ora", "ore", ["ora", "ore"]),
    ("gg", "tempo", 86400.0, "giorno", "giorni", ["giorno", "giorni"]),
    ("sett", "tempo", 604800.0, "settimana", "settimane", ["settimana", "settimane"]),
    ("kb", "dati", 1e3, "kilobyte", "kilobyte", ["kilobyte", "kb", "chilobyte"]),
    ("mb", "dati", 1e6, "megabyte", "megabyte", ["megabyte", "mb", "mega"]),
    ("gb", "dati", 1e9, "gigabyte", "gigabyte", ["gigabyte", "gb", "giga"]),
    ("tb", "dati", 1e12, "terabyte", "terabyte", ["terabyte", "tb", "tera"]),
    ("c", "temperatura", 1.0, "grado Celsius", "gradi Celsius", ["gradi celsius", "grado celsius", "gradi centigradi", "centigradi", "celsius", "gradi c", "°c"]),
    ("f", "temperatura", 1.0, "grado Fahrenheit", "gradi Fahrenheit", ["gradi fahrenheit", "grado fahrenheit", "fahrenheit", "gradi f", "°f"]),
    ("k", "temperatura", 1.0, "kelvin", "kelvin", ["kelvin", "gradi kelvin"]),
]
_ALIAS: dict[str, tuple] = {}
for _u in _U:
    for _a in _u[5]:
        _ALIAS.setdefault(_a, _u)
_UNIT_RX = "|".join(sorted((re.escape(a) for a in _ALIAS), key=len, reverse=True))
_CURRENCY = r"(?:euro|dollari|dollaro|sterline|sterlina|yen|franchi|franco|rubli|rublo|yuan|rupie|corone|bitcoin|dollari americani|dollari canadesi|dollari australiani)"
_NUM = r"(?:[0-9]+(?:punto[0-9]+)?|[a-z]+(?:punto[a-z0-9]+)?)"
_Q = r"(?:quant[oiae]|quanti)"
_HALF = r"(?:\s+e\s+(?P<half>mezzo|mezza))?"
_CONV_PATTERNS = [
    re.compile(rf"\b(?:converti|convertimi|convertire|trasforma|trasformami|trasformare|riporta|portami)\s+(?:{_NUM}\s+)?(?P<n>{_NUM})\s+(?P<from>{_UNIT_RX})\s+(?:in|a|al|alla)\s+(?P<to>{_UNIT_RX})\b"),
    re.compile(rf"\b{_Q}\s+(?P<to>{_UNIT_RX})(?:\s+di\s+\w+)?\s+(?:sono|fanno|fa|e|ci sono|ci stanno|vengono|viene|corrispondono|equivalgono|sono in|fan)\s+(?:in\s+)?(?P<n>{_NUM})\s+(?P<from>{_UNIT_RX}){_HALF}\b"),
    re.compile(rf"\b{_Q}\s+(?:sono|fanno|fa|e|vengono|viene|corrispondono|equivalgono|fan)\s+(?P<n>{_NUM})\s+(?P<from>{_UNIT_RX}){_HALF}\s+(?:in|a|al|alla|espressi in|espresso in)\s+(?P<to>{_UNIT_RX})\b"),
    re.compile(rf"\b(?P<n>{_NUM})\s+(?P<from>{_UNIT_RX}){_HALF}\s+in\s+(?P<to>{_UNIT_RX})\b"),
    re.compile(rf"\b(?P<n>{_NUM})\s+(?P<from>{_UNIT_RX}){_HALF}\s+{_Q}\s+(?P<to>{_UNIT_RX})\s+(?:sono|fanno|fa|vengono|viene|sarebbero)\b"),
    re.compile(rf"\b{_Q}\s+(?P<to>{_UNIT_RX})\s+(?:ha|hanno|c e|ci sono|contiene|contengono|pesa|pesano)\s+(?:in\s+)?(?:un|uno|una|1)\s+(?P<from>{_UNIT_RX})\b"),
]
_CURR_RX = re.compile(rf"\b{_Q}\s+{_CURRENCY}\s+(?:sono|fanno|fa|e|vengono)\s+\S+\s+{_CURRENCY}\b|\b(?:converti|convertimi)\s+\S+\s+{_CURRENCY}\s+in\s+{_CURRENCY}\b|\b\S+\s+{_CURRENCY}\s+in\s+{_CURRENCY}\b|\bcambio\s+{_CURRENCY}\b")


def symbols_to_words(text: str) -> str:
    """«50 $», «20 €»: Apple scrive il simbolo della valuta, non la parola."""
    return re.sub(r"\s*\$\s*", " dollari ", re.sub(r"\s*€\s*", " euro ", re.sub(r"\s*£\s*", " sterline ", text)))


def conversion_kind(text: str) -> str | None:
    """'unita' se e' una conversione che si fa in locale, 'valuta' se servono i cambi di oggi, altrimenti None."""
    t = normalize(decimals_to_words(symbols_to_words(text)))
    if _CURR_RX.search(t):
        return "valuta"
    for rx in _CONV_PATTERNS:
        m = rx.search(t)
        if m and _ALIAS[m.group("from")][1] == _ALIAS[m.group("to")][1] and num(m.group("n") or "1") is not None:
            return "unita"
        if m and "n" not in m.groupdict() and _ALIAS[m.group("from")][1] == _ALIAS[m.group("to")][1]:
            return "unita"
    return None


def _label(u: tuple, value: float) -> str:
    return u[3] if abs(value - 1.0) < 1e-9 else u[4]


def convert(text: str) -> str:
    t = normalize(decimals_to_words(text))
    for rx in _CONV_PATTERNS:
        m = rx.search(t)
        if not m:
            continue
        uf, ut = _ALIAS[m.group("from")], _ALIAS[m.group("to")]
        if uf[1] != ut[1]:
            continue
        n = num(m.group("n")) if "n" in m.groupdict() and m.group("n") else 1.0
        if n is None:
            continue
        if m.groupdict().get("half"):
            n += 0.5                                                       # «due ore e mezza», «due metri e mezzo»
        if uf[1] == "temperatura":
            c = n if uf[0] == "c" else (n - 32) * 5 / 9 if uf[0] == "f" else n - 273.15
            out = c if ut[0] == "c" else c * 9 / 5 + 32 if ut[0] == "f" else c + 273.15
        else:
            out = n * uf[2] / ut[2]
        if abs(out) >= 100:
            out = round(out, 1)
        elif abs(out) >= 1:
            out = round(out, 2)
        else:
            out = round(out, 4)
        return f"{fmt(n)} {_label(uf, n)} sono {fmt(out)} {_label(ut, out)}."
    return "Non sono riuscita a capire quale conversione vuoi: dimmi, per esempio, «quanti chilometri sono dieci miglia»."


# ------------------------------------------------------------------------------- date
_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_MONTH_NUM = {normalize(m): i + 1 for i, m in enumerate(_MESI)}
_MONTH_RX = "|".join(_MONTH_NUM)


def easter(year: int) -> dt.date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


# festa -> funzione(anno) -> data
_HOLIDAYS: dict[str, Callable[[int], dt.date]] = {
    "natale": lambda y: dt.date(y, 12, 25), "santo stefano": lambda y: dt.date(y, 12, 26), "capodanno": lambda y: dt.date(y, 1, 1), "san silvestro": lambda y: dt.date(y, 12, 31),
    "ultimo dell anno": lambda y: dt.date(y, 12, 31), "epifania": lambda y: dt.date(y, 1, 6), "befana": lambda y: dt.date(y, 1, 6), "san valentino": lambda y: dt.date(y, 2, 14),
    "festa della donna": lambda y: dt.date(y, 3, 8), "festa del papa": lambda y: dt.date(y, 3, 19), "pasqua": easter, "pasquetta": lambda y: easter(y) + dt.timedelta(days=1),
    "liberazione": lambda y: dt.date(y, 4, 25), "primo maggio": lambda y: dt.date(y, 5, 1), "festa del lavoro": lambda y: dt.date(y, 5, 1), "festa della repubblica": lambda y: dt.date(y, 6, 2),
    "ferragosto": lambda y: dt.date(y, 8, 15), "ognissanti": lambda y: dt.date(y, 11, 1), "halloween": lambda y: dt.date(y, 10, 31), "immacolata": lambda y: dt.date(y, 12, 8),
    "vigilia di natale": lambda y: dt.date(y, 12, 24), "carnevale": lambda y: easter(y) - dt.timedelta(days=47), "martedi grasso": lambda y: easter(y) - dt.timedelta(days=47),
    "festa della mamma": lambda y: _nth_weekday(y, 5, 6, 2), "festa del papà": lambda y: dt.date(y, 3, 19),
}
_HOL_RX = "|".join(sorted((re.escape(h) for h in _HOLIDAYS), key=len, reverse=True))


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _say_date(d: dt.date, today: dt.date) -> str:
    from .tools import words_it
    day = "primo" if d.day == 1 else words_it(d.day) if d.day < 60 else str(d.day)
    yr = f" {words_it(d.year)}" if d.year != today.year else ""
    return f"{_GIORNI[d.weekday()]} {day} {_MESI[d.month - 1]}{yr}"


def _days_phrase(n: int) -> str:
    return "oggi" if n == 0 else "domani" if n == 1 else "ieri" if n == -1 else f"tra {n} giorni" if n > 0 else f"{-n} giorni fa"


def _parse_date(t: str, today: dt.date, prefer_future: bool = True) -> dt.date | None:
    """Una data detta a voce: «25 dicembre», «il 3 novembre 2027», «primo gennaio», «25/12/2026», o una festa."""
    t = t.strip()
    m = re.search(rf"\b({_HOL_RX})\b(?:\s+(?:del\s+|dell\s+)?(20\d\d))?", t)
    if m:
        year = int(m.group(2)) if m.group(2) else today.year
        d = _HOLIDAYS[m.group(1)](year)
        if not m.group(2) and prefer_future and d < today:
            d = _HOLIDAYS[m.group(1)](year + 1)
        return d
    m = re.search(rf"\b(?:il\s+)?(primo|1|[0-9]{{1,2}}|[a-z]+)\s+({_MONTH_RX})(?:\s+(?:del\s+|dell\s+)?(20\d\d))?\b", t)
    if m:
        dnum = 1 if m.group(1) == "primo" else (num(m.group(1)) or 0)
        if 1 <= dnum <= 31:
            month = _MONTH_NUM[m.group(2)]
            year = int(m.group(3)) if m.group(3) else today.year
            try:
                d = dt.date(year, month, int(dnum))
            except ValueError:
                return None
            if not m.group(3) and prefer_future and d < today:
                d = d.replace(year=year + 1)
            return d
    m = re.search(r"\b(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{2,4}))?\b", t)
    if m:
        try:
            y = int(m.group(3)) if m.group(3) else today.year
            y = y + 2000 if y < 100 else y
            d = dt.date(y, int(m.group(2)), int(m.group(1)))
            if not m.group(3) and prefer_future and d < today:
                d = d.replace(year=y + 1)
            return d
        except ValueError:
            return None
    return None


_UNITS_T = {"giorno": 1, "giorni": 1, "settimana": 7, "settimane": 7, "mese": 30, "mesi": 30, "anno": 365, "anni": 365}


def date_answer(text: str, now: dt.datetime | None = None) -> str:
    from .tools import words_it
    today = (now or dt.datetime.now()).date()
    raw = text
    t = normalize(decimals_to_words(raw))
    # ---- che giorno sara' tra N giorni/settimane/mesi (o N giorni fa)
    m = re.search(r"\b(?:tra|fra)\s+(?P<n>[a-z0-9]+(?: [a-z]+)?)\s+(?P<u>giorni|giorno|settimane|settimana|mesi|mese|anni|anno)\b", t) or \
        re.search(r"\b(?P<n>[a-z0-9]+(?: [a-z]+)?)\s+(?P<u>giorni|giorno|settimane|settimana|mesi|mese|anni|anno)\s+(?P<ago>fa)\b", t)
    if m and re.search(r"\b(?:che giorno|che data|quando|che giorno sara|che giorno era|data)\b", t):
        n = num(m.group("n"))
        if n is None and m.group("n") in ("un", "una", "uno"):
            n = 1.0
        if n is not None:
            u = m.group("u")
            sign = -1 if m.groupdict().get("ago") else 1
            if u.startswith("mes"):
                mm = today.month - 1 + sign * int(n)
                y, mo = today.year + mm // 12, mm % 12 + 1
                last = (dt.date(y + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(days=1)).day
                d = dt.date(y, mo, min(today.day, last))
            elif u.startswith("ann"):
                d = today.replace(year=today.year + sign * int(n), day=min(today.day, 28 if today.month == 2 else today.day))
            else:
                d = today + dt.timedelta(days=sign * int(n) * _UNITS_T[u])
            return (f"Sarà {_say_date(d, today)}." if sign > 0 else f"Era {_say_date(d, today)}.")
    # ---- settimana dell'anno
    if re.search(r"\bche settimana\b|\bsettimana dell anno\b|\bnumero della settimana\b", t):
        return f"Siamo nella settimana numero {words_it(today.isocalendar()[1])} dell'anno."
    # ---- quanti anni ho / ha
    m = re.search(r"\bnato (?:nel|nel|il)?\s*(?:\d{1,2}\s+(?:%s)\s+)?(?:del\s+)?(19\d\d|20\d\d)\b" % _MONTH_RX, t)
    if m and re.search(r"\bquant\w+ anni\b", t):
        age = today.year - int(m.group(1))
        return f"Hai {words_it(age) if age < 60 else age} anni, oppure {words_it(age - 1) if age - 1 < 60 else age - 1} se il compleanno quest'anno deve ancora arrivare."
    # ---- quanti giorni mancano a ...
    m = _COUNTDOWN.search(t)
    if m:
        what = m.group("what")
        if re.search(r"\bfine\s+(?:dell\s+)?anno\b", what):
            d = dt.date(today.year, 12, 31)
        elif re.search(r"\bfine\s+(?:del\s+)?mese\b", what):
            d = (dt.date(today.year + (today.month == 12), today.month % 12 + 1, 1) - dt.timedelta(days=1))
        elif re.search(r"\bfine\s+(?:della\s+)?settimana\b|\bweekend\b", what):
            d = today + dt.timedelta(days=(4 - today.weekday()) % 7 or 7) if today.weekday() > 4 else today + dt.timedelta(days=4 - today.weekday())
        elif re.search(r"\b(?:estate)\b", what):
            d = dt.date(today.year, 6, 21) if today <= dt.date(today.year, 6, 21) else dt.date(today.year + 1, 6, 21)
        else:
            d = _parse_date(what, today)
        if d is not None:
            n = (d - today).days
            label = what.strip()
            if n == 0:
                return "È oggi!"
            return f"Mancano {words_it(n) if n < 60 else n} giorni: sarà {_say_date(d, today)}." if n > 1 else "Manca un solo giorno: è domani." if n == 1 else f"È passato da {-n} giorni."
    # ---- quanti giorni sono passati dal ... / da quanti giorni
    m = re.search(r"\bquant\w+ (?:giorni|tempo) (?:sono passati|e passato|passano|fa)\s+(?:dal|dall|dalla|da)\s+(?P<what>.+)$", t)
    if m:
        d = _parse_date(m.group("what"), today, prefer_future=False)
        if d is not None:
            n = (today - d).days
            return f"Sono passati {words_it(n) if n < 60 else n} giorni." if n > 0 else "È oggi." if n == 0 else f"Non è ancora successo: mancano {-n} giorni."
    # ---- quanti giorni tra A e B
    m = re.search(r"\b(?:quanti giorni|quanto tempo)\s+(?:ci sono|passano|passa|sono)?\s*tra\s+(?P<a>.+?)\s+e\s+(?P<b>.+)$", t)
    if m:
        a, b = _parse_date(m.group("a"), today, False), _parse_date(m.group("b"), today, False)
        if a and b:
            if b < a and not re.search(r"20\d\d", m.group("b")):
                b = b.replace(year=b.year + 1)
            n = abs((b - a).days)
            return f"Ci sono {words_it(n) if n < 60 else n} giorni."
    # ---- quando e' / che giorno e' (una festa o una data)
    d = _parse_date(t, today, prefer_future=not re.search(r"\bquest anno\b|\bdi quest anno\b", t))
    if d is not None and re.search(r"\b(?:quando|che giorno|che data|in che giorno|cade|giorno della settimana)\b", t):
        when = _say_date(d, today)
        name = _hol_name(t)
        if not name:
            return when[:1].upper() + when[1:] + "."                              # «che giorno della settimana e' il 25 dicembre?» -> «Venerdì venticinque dicembre.»
        return f"{name} {'cade' if d >= today else 'è caduta'} {when}."
    return "Non sono riuscita a fare questo calcolo con le date. Prova, per esempio: «quanti giorni mancano a Natale?»."


def _hol_name(t: str) -> str:
    m = re.search(rf"\b({_HOL_RX})\b", t)
    return m.group(1).capitalize() if m else ""


_COUNTDOWN = re.compile(r"\b(?:(?:quanti giorni|quanto tempo|quante settimane|quanti mesi|quanto)\s+(?:mancano|manca|ci vogliono|restano|rimangono)\s+(?:a|ad|al|alla|allo|all|fino a|fino al|fino alla|per|per il|per la|per l)|(?:tra|fra)\s+(?:quanti giorni|quanto tempo|quante settimane|quanti mesi)\s+(?:e|cade|arriva|sara|ricorre))\s+(?P<what>.+)$")


def date_kind(text: str) -> bool:
    """Una domanda di calcolo con le date (non «che giorno e' oggi?», che e' ORA; non «quanto manca al timer?», che e' del timer)?"""
    t = normalize(decimals_to_words(text))
    mc = _COUNTDOWN.search(t)
    if mc:
        what = mc.group("what")
        return bool(re.search(rf"\b(?:{_HOL_RX}|fine (?:dell )?anno|fine (?:del )?mese|fine (?:della )?settimana|weekend|estate|{_MONTH_RX})\b|\b\d{{1,2}}\s*[/-]\s*\d{{1,2}}\b", what)) and not re.search(r"\b(?:timer|sveglia|arrivare|arrivo|finire|partire|pranzo|cena)\b", what)
    if re.search(r"\b(?:quanti giorni|quanto tempo|quante settimane|quanti mesi)\s+(?:ci sono|passano|sono passati|e passato|fa)\b", t):
        return True
    if re.search(r"\b(?:tra|fra)\s+[a-z0-9]+(?: [a-z]+)?\s+(?:giorni|giorno|settimane|settimana|mesi|mese|anni|anno)\b", t) and re.search(r"\bche (?:giorno|data)\b|\bquando sara\b", t):
        return True
    if re.search(r"\b[a-z0-9]+(?: [a-z]+)?\s+(?:giorni|settimane|mesi|anni)\s+fa\b", t) and re.search(r"\bche (?:giorno|data)\b|\bquando\b", t):
        return True
    if re.search(r"\bche settimana\b|\bsettimana dell anno\b", t):
        return True
    if re.search(r"\bquant\w+ anni\b", t) and re.search(r"\bnato\b", t):
        return True
    if re.search(rf"\b(?:quando (?:e|era|fu|cade|sara|casca)|che giorno (?:e|era|fu|cade|sara|della settimana)|in che giorno cade|che giorno della settimana)\b.*\b(?:{_HOL_RX}|(?:il\s+)?(?:primo|[0-9]{{1,2}})\s+(?:{_MONTH_RX}))", t):
        return True
    if re.search(rf"\b(?:che giorno|che data|quando)\b.*\b(?:{_HOL_RX})\b", t):
        return True
    return False


# ------------------------------------------------------------------------------- dado, moneta, sorteggi
_CARDS_SEED = ["asso", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "fante", "cavallo", "re"]
_SUITS = ["cuori", "quadri", "fiori", "picche"]


def chance_kind(text: str) -> str | None:
    t = normalize(text)
    if re.search(r"\b(?:tira|tirami|lancia|lanciami|butta|buttami|rotola|fai rotolare|gioca|fammi|fai|dammi|facciamo|giochiamo a)\s+(?:un|uno|il|i|due|tre|quattro|\d+)?\s*(?:dado|dadi)\b|\b(?:dado|dadi)\b.*\b(?:tira|lancia)\b|^(?:un\s+)?dado$", t):
        return "dado"
    if re.search(r"\b(?:lancia|lanciami|tira|tirami|butta)\s+(?:una|la)\s+moneta\b|\btesta o croce\b|\bfai testa o croce\b|\bmoneta\b.*\b(?:testa|croce)\b", t):
        return "moneta"
    if re.search(r"\b(?:scegli|sceglimi|dimmi|estrai|estraimi|pensa a|genera|generami|dammi)\s+(?:un\s+)?numero\s+(?:a caso|casuale)?\s*(?:da|tra|fra)?\b", t) and re.search(r"\bnumero\b", t):
        return "numero"
    if re.search(r"\bnumero (?:a caso|casuale)\b", t):
        return "numero"
    if re.search(r"\b(?:pesca|pescami|estrai|estraimi)\s+(?:una|la)\s+carta\b", t):
        return "carta"
    if re.search(r"\b(?:scegli|sceglimi|decidi|decidimi|sorteggia)\b.*\b(?:tra|fra)\b.+\b(?:e|o)\b|\bscegli a caso\b", t):
        return "scelta"
    return None


def chance_answer(text: str, rng: random.Random | None = None) -> str:
    r = rng or random
    t = normalize(decimals_to_words(text))
    kind = chance_kind(text)
    if kind == "dado":
        m = re.search(r"\b(due|tre|quattro|\d+)\s+dadi\b", t)
        n = int(num(m.group(1)) or 1) if m else 1
        n = max(1, min(n, 6))
        mf = re.search(r"\b(?:a|da)\s+(\w+)\s+facce\b", t)
        faces = int(num(mf.group(1)) or 6) if mf else 6
        faces = max(2, min(faces, 1000))
        res = [r.randint(1, faces) for _ in range(n)]
        if n == 1:
            return f"È uscito {res[0]}."
        return "Sono usciti " + ", ".join(str(x) for x in res) + f": in tutto {sum(res)}."
    if kind == "moneta":
        return r.choice(["È uscita testa.", "È uscita croce."])
    if kind == "numero":
        nums = re.findall(r"[0-9]+(?:punto[0-9]+)?|[a-z]+", t.partition("numero")[2])
        vals = [v for v in (num(x) for x in nums) if v is not None]
        lo, hi = (int(vals[0]), int(vals[1])) if len(vals) >= 2 else (1, 10) if not vals else (1, int(vals[0]))
        if lo > hi:
            lo, hi = hi, lo
        return f"Il numero è {r.randint(lo, hi)}."
    if kind == "carta":
        return f"Hai pescato: {r.choice(_CARDS_SEED)} di {r.choice(_SUITS)}."
    if kind == "scelta":
        m = re.search(r"\b(?:tra|fra)\s+(.+)$", text, flags=re.I)
        body = m.group(1) if m else ""
        opts = [o.strip(" .,!?") for o in re.split(r"\s*,\s*|\s+\bo\b\s+|\s+\be\b\s+|\s+oppure\s+", body) if o.strip(" .,!?")]
        if len(opts) >= 2:
            return f"Scelgo {r.choice(opts)}."
    return "Dimmi cosa tiro: per esempio «tira un dado», «testa o croce» o «scegli un numero da uno a dieci»."


# ------------------------------------------------------------------------------- cosa sa fare
def help_kind(text: str) -> bool:
    t = normalize(text)
    return bool(re.search(
        r"^(?:aiuto|aiutami|help)$|^(?:ma\s+|senti\s+|dimmi\s+|allora\s+)?(?:cosa|che cosa|che)\s+(?:sai|puoi|riesci a|riesci|sei in grado di|posso)\s+(?:fare|chiederti|chiedere|dirmi)|\b(?:come funzioni|come ti uso|come si usa|a cosa servi|a che cosa servi|che funzioni hai|che poteri hai|quali poteri hai|"
        r"spiegami come (?:usarti|funzioni|si usa|ti si usa)|come faccio a usarti|elencami (?:le tue funzioni|i tuoi poteri|cosa sai fare)|cosa sai fare|dimmi cosa sai fare|che cosa sai fare|che cose sai fare|quali sono le tue funzioni|quali funzioni hai|che comandi conosci|quali comandi conosci|"
        r"come funziona (?:questa cosa|questo|tutto questo|questa roba|questo coso|il tuo funzionamento)|che cosa posso chiederti|cosa posso chiederti|cosa ti posso chiedere|cosa posso dirti|come ti si usa|come posso usarti|come ti uso|non so come usarti|non so come si usa|non so cosa chiederti|non so cosa puoi fare|non so cosa sai fare)\b", t))


def help_text(powers: dict[str, bool] | None = None) -> str:
    on = powers or {}

    def has(k: str) -> bool:
        return on.get(k, True)
    parts = ["Posso dirti che tempo fa, l'ora e la data, fare calcoli, conversioni e traduzioni, tirare un dado o una moneta, e ricordarti le cose con timer e sveglie"]
    mac = []
    if has("reminders") or has("calendar"):
        mac.append("metterti promemoria ed eventi in calendario e dirti cosa hai in agenda")
    if has("music"):
        mac.append("controllare la musica e il volume")
    if has("apps"):
        mac.append("aprire app, siti e mappe")
    if mac:
        parts.append("Sul Mac so " + ", ".join(mac))
    parts.append("Nella mia cartella scrivo documenti e ricerche, tengo le liste della spesa e le note, e rispondo a domande sui tuoi file")
    if has("screen_mac") or has("screen_model"):
        parts.append("e posso guardare lo schermo per dirti dove sta un pulsante o per leggerti quello che c'è")
    parts.append("Non so telefonare, mandare messaggi, comprare o controllare la casa")
    return ". ".join(p[:1].upper() + p[1:] if i else p for i, p in enumerate(parts)) + ". Se vuoi sapere come si fa una cosa, chiedimelo."


# ------------------------------------------------------------------------------- «quando» del meteo
_WEEKDAYS = {normalize(g): i for i, g in enumerate(_GIORNI)}
_WHEN_RX = re.compile(
    r"\b(?:dopodomani|domani|oggi|stasera|stanotte|stamattina|"
    r"(?:nel|questo|il prossimo|per il)\s+(?:weekend|fine settimana)|weekend|fine settimana|"
    r"(?:tra|fra)\s+(?:un|una|uno|[a-z0-9]+)\s+(?:giorni|giorno|settimane|settimana)|"
    r"(?:nei|nei prossimi|per i prossimi)\s+(?:prossimi\s+)?giorni|"
    r"(?:questa|la|nella|per la|in)\s+(?:prossima\s+)?settimana(?:\s+prossima)?|(?:prossima|settimana)\s+(?:settimana|prossima)|"
    r"luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|sabato|domenica|"
    r"(?:il\s+)?(?:primo|\d{1,2})\s+(?:" + "|".join(_MESI) + r"))\b", re.I)


def when_phrase(text: str) -> str:
    """La parte «quando» di una domanda sul meteo: «sabato», «dopodomani», «tra tre giorni», «nel weekend»… (stringa vuota se non c'e')."""
    m = _WHEN_RX.search(text)
    return m.group(0) if m else ""


def forecast_when(text: str, today: dt.date | None = None) -> tuple[list[int] | None, str, str]:
    """-> (giorni da oggi di cui dare le previsioni, etichetta, testo senza le parole del giorno). Se la data e' oltre il limite delle previsioni: (None, spiegazione, resto)."""
    today = today or dt.date.today()
    rest = _WHEN_RX.sub(" ", text)
    rest = re.sub(r"\s+", " ", rest).strip()
    t = normalize(text)
    if re.search(r"\bdopodomani\b", t):
        return [2], "Dopodomani", rest
    if re.search(r"\bdomani\b", t):
        return [1], "Domani", rest
    if re.search(r"\b(?:weekend|fine settimana)\b", t):
        sat = (5 - today.weekday()) % 7 if today.weekday() != 6 else 0
        if today.weekday() == 5:
            return [0, 1], "Nel weekend", rest
        if today.weekday() == 6:
            return [0], "Oggi", rest
        return [sat, sat + 1], "Nel weekend", rest
    m = re.search(r"\b(?:tra|fra)\s+(un|una|uno|[a-z0-9]+)\s+(giorni|giorno|settimane|settimana)\b", t)
    if m:
        n = 1.0 if m.group(1) in ("un", "una", "uno") else num(m.group(1))
        if n is not None:
            days = int(n) * (7 if m.group(2).startswith("settiman") else 1)
            if days > 15:
                return None, "Le previsioni arrivano al massimo a quindici giorni da oggi.", rest
            return [days], ("Tra un giorno" if days == 1 else f"Tra {days} giorni"), rest
    if re.search(r"\bprossimi giorni\b", t):
        return [1, 2, 3], "Nei prossimi giorni", re.sub(r"\s+", " ", re.sub(r"(?i)\b(?:per\s+|nei\s+)?prossimi giorni\b", " ", rest)).strip()        # (prima restava nel nome della citta')
    if re.search(r"\b(?:questa|la|nella|per la|in)\s+settimana\b|\bsettimana prossima\b|\bprossima settimana\b", t):
        start = 7 - today.weekday() if re.search(r"\bprossima\b", t) else 0          # «che tempo fa questa settimana a Torino?»: prima diventava «oggi» e «settimana» finiva nel nome della citta'
        if start + 6 > 15:
            start = max(0, 15 - 6)
        return list(range(start, start + 7)), ("La prossima settimana" if start else "Questa settimana"), re.sub(r"\s+", " ", re.sub(r"(?i)\b(?:questa|la|nella|per la|in)?\s*(?:settimana prossima|prossima settimana|settimana)\b", " ", rest)).strip()
    for name, wd in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", t):
            off = (wd - today.weekday()) % 7
            return [off], _GIORNI[wd].capitalize(), rest
    m = re.search(rf"\b(?:il\s+)?(primo|\d{{1,2}})\s+({_MONTH_RX})\b", t)
    if m:
        d = _parse_date(m.group(0), today)
        if d is not None:
            off = (d - today).days
            if off > 15:
                return None, "Le previsioni arrivano al massimo a quindici giorni da oggi.", rest
            return [off], _say_date(d, today).capitalize(), rest
    return [0], "Oggi", rest


# ------------------------------------------------------------------------------- traduzioni
_LANGS = {"inglese": "inglese", "francese": "francese", "spagnolo": "spagnolo", "tedesco": "tedesco", "portoghese": "portoghese", "italiano": "italiano", "olandese": "olandese",
          "latino": "latino", "rumeno": "rumeno", "polacco": "polacco", "svedese": "svedese", "catalano": "catalano", "inglese americano": "inglese", "americano": "inglese", "britannico": "inglese"}
_LANG_RX = "|".join(sorted(_LANGS, key=len, reverse=True))
_OTHER_LANGS = r"(?:cinese|giapponese|russo|arabo|coreano|greco|turco|hindi|ebraico|thailandese|vietnamita|ucraino)"
_TR_PATTERNS = [
    re.compile(rf"^(?:traduci|traducimi|tradurre)\s+(?:questa frase |la frase |questo testo |il testo |queste parole |la parola |questa parola )?(?:in|per|nella lingua)\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})\s*[:,\-]\s*(?P<text>.+)$", re.I),
    re.compile(rf"^(?:traduci|traducimi|tradurre|traducilo|traducila|fammi la traduzione)\s+(?:in|per|nella lingua)\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})\s*[:,\-]?\s+(?P<text>.+)$", re.I),
    re.compile(rf"^(?:traduci|traducimi|tradurre)\s+(?:questa frase |la frase |questo testo |il testo |queste parole |la parola |questa parola )?(?P<text>.+?)\s+(?:in|per|nella lingua)\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})$", re.I),
    re.compile(rf"^(?:come|cosa)\s+(?:si dice|dico|dicono|si traduce|vuol dire|significa)\s+(?P<text>.+?)\s+in\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})$", re.I),
    re.compile(rf"^in\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})\s+(?:come si dice|come dico|come si traduce|si dice|dico|come si scrive)\s+(?P<text>.+)$", re.I),
    re.compile(rf"^(?:qual e|dimmi|mi dici|sai)\s+(?:la traduzione|il traducente|come si traduce)\s+(?:di|in)\s+(?P<text>.+?)\s+in\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})$", re.I),
    re.compile(rf"^(?:come|cosa)\s+(?:si dice|dico)\s+in\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})\s+(?P<text>.+)$", re.I),
]


def translation_request(text: str) -> tuple[str, str] | None:
    """(lingua, frase da tradurre) se e' una richiesta di traduzione, altrimenti None. La frase e' presa dal testo originale (maiuscole comprese)."""
    t = re.sub(r"\s+", " ", text.strip(" .!?"))
    t = re.sub(r"^(traduci|traducimi|tradurre)\s*,\s*", r"\1 ", t, flags=re.I)                 # «Traduci, mi chiamo Luca in tedesco»
    f = normalize(t)
    if not f or len(f.split()) > 40:
        return None
    # lavora sul testo originale ma con le stesse parole chiave in minuscolo senza accenti: si confronta f e si ritaglia da t
    for rx in _TR_PATTERNS:
        m = rx.match(_fold_keep(t))
        if m:
            lang = m.group("lang").lower()
            body = t[m.start("text"):m.end("text")].strip(" .,;:!?\"'«»“”")
            if body:
                return lang, body
    return None


def _fold_keep(s: str) -> str:
    """Minuscolo senza accenti ma della stessa lunghezza (le posizioni valgono anche per l'originale)."""
    import unicodedata
    out = []
    for ch in s:
        d = unicodedata.normalize("NFD", ch)
        base = "".join(c for c in d if not unicodedata.combining(c)) or ch
        out.append(base[0].lower() if base else ch)
    return "".join(out)


def translation_ok_lang(lang: str) -> bool:
    return lang in _LANGS or lang in ("francese",)
