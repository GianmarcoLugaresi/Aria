"""Le piccole cose di ogni giorno, in inglese: conversioni di unita', conti con le date, dado e moneta, cosa sa fare, il «quando» del meteo, le traduzioni.
Gemello inglese di everyday.py (stesse funzioni, stessi nomi: i18n.py sceglie la lingua). Tutto locale e deterministico: un chatbot piccolo, su queste domande, risponde a caso."""
from __future__ import annotations

import datetime as dt
import random
import re
import sys
from typing import Callable

from .speech_en import DAYS, MONTHS, num_words, ordinal, year_words
from .textutil import normalize

# ------------------------------------------------------------------------------- numeri
_ONES = {"zero": 0, "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
         "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def decimals_to_words(text: str) -> str:
    """«2.5» e «two point five» diventano un'unica parola «2punto5» (normalize toglie la punteggiatura e il punto sparirebbe: 2.5 diventerebbe 25)."""
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", text)                                # 1,000 = mille (migliaia all'inglese)
    s = re.sub(r"(\d)\.(\d)", r"\1punto\2", s)
    return re.sub(r"\b([A-Za-z0-9]+)\s+point\s+([A-Za-z0-9]+)\b", r"\1punto\2", s, flags=re.I)


def number_en(text: str) -> int | None:
    """«seven» -> 7, «twenty one» -> 21, «one hundred and five» -> 105, «a thousand» -> 1000, «3» -> 3. None se non e' un numero."""
    t = normalize(text).replace(" and ", " ").strip()
    if not t:
        return None
    if t.isdigit():
        return int(t)
    total, cur, seen = 0, 0, False
    for w in t.split():
        if w in _ONES:
            cur += _ONES[w]; seen = True
        elif w in _TENS:
            cur += _TENS[w]; seen = True
        elif w == "hundred":
            cur = max(cur, 1) * 100; seen = True
        elif w == "thousand":
            total += max(cur, 1) * 1000; cur = 0; seen = True
        elif w == "million":
            total += max(cur, 1) * 1_000_000; cur = 0; seen = True
        else:
            return None
    return total + cur if seen else None


def num(text: str) -> float | None:
    w = normalize(decimals_to_words(text)).strip()
    if w in ("half", "a half", "one half"):
        return 0.5
    if w in ("a quarter", "one quarter", "quarter"):
        return 0.25
    if "punto" in w.replace(" ", ""):
        a, _, b = w.replace(" ", "").partition("punto")
        ai = number_en(a) if a else 0
        digits = b if b.isdigit() else None
        if ai is None or digits is None:
            return None
        return float(f"{ai}.{digits}")
    v = number_en(w)
    return None if v is None else float(v)


def fmt(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.2f}".rstrip("0").rstrip(".")                                    # «16.09»: ci pensa speechify a dirlo («sixteen point zero nine»)


# ------------------------------------------------------------------------------- conversioni
# nome canonico -> (grandezza, fattore verso l'unita' base, singolare, plurale, [altri modi di dirlo])
_U: list[tuple[str, str, float, str, str, list[str]]] = [
    ("mm", "length", 0.001, "millimeter", "millimeters", ["millimeter", "millimeters", "millimetre", "millimetres", "mm"]),
    ("cm", "length", 0.01, "centimeter", "centimeters", ["centimeter", "centimeters", "centimetre", "centimetres", "cm"]),
    ("m", "length", 1.0, "meter", "meters", ["meter", "meters", "metre", "metres", "m"]),
    ("km", "length", 1000.0, "kilometer", "kilometers", ["kilometer", "kilometers", "kilometre", "kilometres", "km", "kms"]),
    ("in", "length", 0.0254, "inch", "inches", ["inch", "inches"]),
    ("ft", "length", 0.3048, "foot", "feet", ["foot", "feet", "ft"]),
    ("yd", "length", 0.9144, "yard", "yards", ["yard", "yards", "yd"]),
    ("mi", "length", 1609.344, "mile", "miles", ["mile", "miles"]),
    ("mg", "mass", 0.000001, "milligram", "milligrams", ["milligram", "milligrams", "mg"]),
    ("g", "mass", 0.001, "gram", "grams", ["gram", "grams", "gramme", "grammes"]),
    ("kg", "mass", 1.0, "kilogram", "kilograms", ["kilogram", "kilograms", "kilo", "kilos", "kg", "kgs"]),
    ("t", "mass", 1000.0, "metric ton", "metric tons", ["metric ton", "metric tons", "tonne", "tonnes"]),
    ("lb", "mass", 0.45359237, "pound", "pounds", ["pound", "pounds", "lb", "lbs"]),
    ("oz", "mass", 0.028349523, "ounce", "ounces", ["ounce", "ounces", "oz"]),
    ("st", "mass", 6.35029318, "stone", "stone", ["stone", "stones"]),
    ("ml", "volume", 0.001, "milliliter", "milliliters", ["milliliter", "milliliters", "millilitre", "millilitres", "ml"]),
    ("cl", "volume", 0.01, "centiliter", "centiliters", ["centiliter", "centiliters", "centilitre", "centilitres", "cl"]),
    ("l", "volume", 1.0, "liter", "liters", ["liter", "liters", "litre", "litres"]),
    ("gal", "volume", 3.785411784, "gallon", "gallons", ["gallon", "gallons", "gal"]),
    ("qt", "volume", 0.946352946, "quart", "quarts", ["quart", "quarts"]),
    ("pt", "volume", 0.473176473, "pint", "pints", ["pint", "pints"]),
    ("cup", "volume", 0.2365882365, "cup", "cups", ["cup", "cups"]),
    ("floz", "volume", 0.0295735296, "fluid ounce", "fluid ounces", ["fluid ounce", "fluid ounces", "fl oz"]),
    ("tbsp", "volume", 0.0147867648, "tablespoon", "tablespoons", ["tablespoon", "tablespoons", "tbsp"]),
    ("tsp", "volume", 0.00492892159, "teaspoon", "teaspoons", ["teaspoon", "teaspoons", "tsp"]),
    ("kmh", "speed", 1 / 3.6, "kilometer per hour", "kilometers per hour", ["kilometer per hour", "kilometers per hour", "kilometre per hour", "kilometres per hour", "km h", "kmh", "kph", "km per hour"]),
    ("ms", "speed", 1.0, "meter per second", "meters per second", ["meter per second", "meters per second", "metres per second", "m s", "mps"]),
    ("mph", "speed", 0.44704, "mile per hour", "miles per hour", ["mile per hour", "miles per hour", "mph", "mi h"]),
    ("knot", "speed", 0.514444, "knot", "knots", ["knot", "knots"]),
    ("sqm", "area", 1.0, "square meter", "square meters", ["square meter", "square meters", "square metre", "square metres", "sqm", "m2"]),
    ("sqft", "area", 0.09290304, "square foot", "square feet", ["square foot", "square feet", "sq ft", "sqft"]),
    ("ha", "area", 10000.0, "hectare", "hectares", ["hectare", "hectares"]),
    ("acre", "area", 4046.8564224, "acre", "acres", ["acre", "acres"]),
    ("sqkm", "area", 1e6, "square kilometer", "square kilometers", ["square kilometer", "square kilometers", "square kilometre", "square kilometres", "sq km"]),
    ("s", "time", 1.0, "second", "seconds", ["second", "seconds", "sec", "secs"]),
    ("min", "time", 60.0, "minute", "minutes", ["minute", "minutes", "min", "mins"]),
    ("h", "time", 3600.0, "hour", "hours", ["hour", "hours", "hr", "hrs"]),
    ("d", "time", 86400.0, "day", "days", ["day", "days"]),
    ("wk", "time", 604800.0, "week", "weeks", ["week", "weeks"]),
    ("kb", "data", 1e3, "kilobyte", "kilobytes", ["kilobyte", "kilobytes", "kb"]),
    ("mb", "data", 1e6, "megabyte", "megabytes", ["megabyte", "megabytes", "mb", "megs"]),
    ("gb", "data", 1e9, "gigabyte", "gigabytes", ["gigabyte", "gigabytes", "gb", "gigs"]),
    ("tb", "data", 1e12, "terabyte", "terabytes", ["terabyte", "terabytes", "tb"]),
    ("c", "temperature", 1.0, "degree Celsius", "degrees Celsius", ["degrees celsius", "degree celsius", "celsius", "centigrade", "degrees centigrade", "degrees c", "c"]),
    ("f", "temperature", 1.0, "degree Fahrenheit", "degrees Fahrenheit", ["degrees fahrenheit", "degree fahrenheit", "fahrenheit", "degrees f", "f"]),
    ("k", "temperature", 1.0, "kelvin", "kelvin", ["kelvin", "kelvins"]),
]
_ALIAS: dict[str, tuple] = {}
for _u in _U:
    for _a in _u[5]:
        _ALIAS.setdefault(_a, _u)
_UNIT_RX = "|".join(sorted((re.escape(a) for a in _ALIAS if a not in ("c", "f", "m", "l", "g", "t", "k", "h", "d", "s")), key=len, reverse=True))
_UNIT_RX_SHORT = "|".join(sorted((re.escape(a) for a in _ALIAS if a in ("c", "f")), key=len, reverse=True))
_CURRENCY = r"(?:euros?|dollars?|pounds? sterling|pounds?|yen|francs?|rubles?|roubles?|yuan|rupees?|crowns?|bitcoins?|us dollars?|canadian dollars?|australian dollars?|cents?)"
_NUM = r"(?:[0-9]+(?:punto[0-9]+)?|[a-z]+(?:[ -][a-z]+)?(?:punto[a-z0-9]+)?)"
_HALF = r"(?:\s+and\s+(?P<half>a\s+half|half))?"
_CONV_PATTERNS = [
    re.compile(rf"\b(?:convert|change|turn|translate)\s+(?P<n>{_NUM})\s+(?P<from>{_UNIT_RX})\s+(?:in|into|to)\s+(?P<to>{_UNIT_RX})\b"),
    re.compile(rf"\bhow\s+(?:many|much)\s+(?P<to>{_UNIT_RX})\s+(?:are|is|in|do|does|would|will)\s+(?:there\s+(?:are\s+)?in\s+|in\s+|it\s+take\s+)?(?:a\s+|an\s+|one\s+)?(?P<n>{_NUM})?\s*(?P<from>{_UNIT_RX}){_HALF}\b"),
    re.compile(rf"\bhow\s+(?:many|much)\s+(?P<to>{_UNIT_RX})\s+(?:in|is|are)\s+(?:a|an|one)\s+(?P<from>{_UNIT_RX})\b"),
    re.compile(rf"\bhow\s+(?:many|much)\s+is\s+(?P<n>{_NUM})\s+(?P<from>{_UNIT_RX}){_HALF}\s+in\s+(?P<to>{_UNIT_RX})\b"),
    re.compile(rf"\b(?:what\s+is|what\s+s|whats)\s+(?P<n>{_NUM})\s+(?P<from>{_UNIT_RX}){_HALF}\s+in\s+(?P<to>{_UNIT_RX})\b"),
    re.compile(rf"\b(?P<n>{_NUM})\s+(?P<from>{_UNIT_RX}){_HALF}\s+(?:in|to|into|equals?|is)\s+(?:how many\s+)?(?P<to>{_UNIT_RX})\b"),
    re.compile(rf"\b(?P<n>{_NUM})\s+(?:degrees\s+)?(?P<from>{_UNIT_RX_SHORT}|celsius|fahrenheit)\s+(?:in|to|into)\s+(?P<to>{_UNIT_RX_SHORT}|celsius|fahrenheit|kelvin)\b"),
]
_CURR_RX = re.compile(rf"\bhow\s+(?:many|much)\s+(?:is\s+)?{_CURRENCY}\s+(?:is|are|in)\b|\b(?:convert|change)\s+\S+\s+{_CURRENCY}\s+(?:in|into|to)\s+{_CURRENCY}\b|\b\S+\s+{_CURRENCY}\s+(?:in|into|to)\s+{_CURRENCY}\b|\bexchange rate\b")


def symbols_to_words(text: str) -> str:
    """«$50», «50€»: Apple scrive il simbolo della valuta, non la parola."""
    t = re.sub(r"\$\s*(\d[\d.,]*)", r"\1 dollars", text)
    t = re.sub(r"€\s*(\d[\d.,]*)", r"\1 euros", t)
    t = re.sub(r"£\s*(\d[\d.,]*)", r"\1 pounds", t)
    return re.sub(r"\s*\$\s*", " dollars ", re.sub(r"\s*€\s*", " euros ", re.sub(r"\s*£\s*", " pounds ", t)))


def conversion_kind(text: str) -> str | None:
    """'unita' se e' una conversione che si fa in locale, 'valuta' se servono i cambi di oggi, altrimenti None."""
    t = normalize(decimals_to_words(symbols_to_words(text)))
    if _CURR_RX.search(t) and not (re.search(r"\bpounds?\b", t) and re.search(r"\b(?:kilograms?|kilos?|kg|grams?|ounces?|oz|stones?|tons?|tonnes?)\b", t)):      # «how many pounds is 5 kilograms»: sono libbre, non sterline
        return "valuta"
    for rx in _CONV_PATTERNS:
        m = rx.search(t)
        if m and _ALIAS[m.group("from")][1] == _ALIAS[m.group("to")][1]:
            n = m.groupdict().get("n")
            if n is None or num(n) is not None:
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
        gd = m.groupdict()
        n = num(gd["n"]) if gd.get("n") else 1.0
        if n is None:
            continue
        if gd.get("half"):
            n += 0.5
        if uf[1] == "temperature":
            c = n if uf[0] == "c" else (n - 32) * 5 / 9 if uf[0] == "f" else n - 273.15
            out = c if ut[0] == "c" else c * 9 / 5 + 32 if ut[0] == "f" else c + 273.15
        else:
            out = n * uf[2] / ut[2]
        out = round(out, 1) if abs(out) >= 100 else round(out, 2) if abs(out) >= 1 else round(out, 4)
        return f"{fmt(n)} {_label(uf, n)} is {fmt(out)} {_label(ut, out)}."
    return "I couldn't work out which conversion you want: tell me, for example, \"how many kilometers is ten miles\"."


# ------------------------------------------------------------------------------- date
_MONTH_NUM = {normalize(m): i + 1 for i, m in enumerate(MONTHS)}
_MONTH_NUM.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12})
_MONTH_RX = "|".join(sorted(_MONTH_NUM, key=len, reverse=True))


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


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    d = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


_HOLIDAYS: dict[str, Callable[[int], dt.date]] = {
    "christmas": lambda y: dt.date(y, 12, 25), "christmas day": lambda y: dt.date(y, 12, 25), "christmas eve": lambda y: dt.date(y, 12, 24), "boxing day": lambda y: dt.date(y, 12, 26),
    "new year": lambda y: dt.date(y, 1, 1), "new years": lambda y: dt.date(y, 1, 1), "new year s day": lambda y: dt.date(y, 1, 1), "new year s": lambda y: dt.date(y, 1, 1),
    "new year s eve": lambda y: dt.date(y, 12, 31), "new years eve": lambda y: dt.date(y, 12, 31), "valentine s day": lambda y: dt.date(y, 2, 14), "valentines day": lambda y: dt.date(y, 2, 14),
    "valentines": lambda y: dt.date(y, 2, 14), "st patrick s day": lambda y: dt.date(y, 3, 17), "easter": easter, "easter sunday": easter, "easter monday": lambda y: easter(y) + dt.timedelta(days=1),
    "good friday": lambda y: easter(y) - dt.timedelta(days=2), "halloween": lambda y: dt.date(y, 10, 31), "independence day": lambda y: dt.date(y, 7, 4), "fourth of july": lambda y: dt.date(y, 7, 4),
    "july fourth": lambda y: dt.date(y, 7, 4), "4th of july": lambda y: dt.date(y, 7, 4), "thanksgiving": lambda y: _nth_weekday(y, 11, 3, 4), "black friday": lambda y: _nth_weekday(y, 11, 3, 4) + dt.timedelta(days=1),
    "mother s day": lambda y: _nth_weekday(y, 5, 6, 2), "mothers day": lambda y: _nth_weekday(y, 5, 6, 2), "father s day": lambda y: _nth_weekday(y, 6, 6, 3), "fathers day": lambda y: _nth_weekday(y, 6, 6, 3),
    "memorial day": lambda y: _last_weekday(y, 5, 0), "labor day": lambda y: _nth_weekday(y, 9, 0, 1), "labour day": lambda y: dt.date(y, 5, 1), "may day": lambda y: dt.date(y, 5, 1),
    "mlk day": lambda y: _nth_weekday(y, 1, 0, 3), "presidents day": lambda y: _nth_weekday(y, 2, 0, 3), "columbus day": lambda y: _nth_weekday(y, 10, 0, 2), "veterans day": lambda y: dt.date(y, 11, 11),
    "bonfire night": lambda y: dt.date(y, 11, 5), "guy fawkes night": lambda y: dt.date(y, 11, 5), "remembrance day": lambda y: dt.date(y, 11, 11),
}
_HOL_RX = "|".join(sorted((re.escape(h).replace(r"\ ", " ") for h in _HOLIDAYS), key=len, reverse=True))


def _say_date(d: dt.date, today: dt.date) -> str:
    yr = f", {year_words(d.year)}" if d.year != today.year else ""
    return f"{DAYS[d.weekday()]}, {MONTHS[d.month - 1]} {ordinal(d.day)}{yr}"


def _parse_date(t: str, today: dt.date, prefer_future: bool = True) -> dt.date | None:
    """Una data detta a voce: «December 25th», «the 3rd of November 2027», «12/25/2026», o una festa."""
    t = t.strip()
    m = re.search(rf"\b({_HOL_RX})\b(?:\s+(?:of\s+)?(20\d\d))?", t)
    if m:
        year = int(m.group(2)) if m.group(2) else today.year
        d = _HOLIDAYS[m.group(1)](year)
        if not m.group(2) and prefer_future and d < today:
            d = _HOLIDAYS[m.group(1)](year + 1)
        return d
    ord_rx = r"(?:\d{1,2}(?:st|nd|rd|th)?|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|twentieth|twenty [a-z]+|thirtieth|thirty first)"
    m = re.search(rf"\b(?:the\s+)?(?P<d>{ord_rx})\s+of\s+(?P<mo>{_MONTH_RX})(?:\s+(?P<y>20\d\d))?\b|\b(?P<mo2>{_MONTH_RX})\s+(?:the\s+)?(?P<d2>{ord_rx})(?:\s+(?P<y2>20\d\d))?\b", t)
    if m:
        from .timeparse_en import ordinal_value
        dtxt, mo, ytxt = (m.group("d"), m.group("mo"), m.group("y")) if m.group("d") else (m.group("d2"), m.group("mo2"), m.group("y2"))
        dnum = ordinal_value(dtxt.replace(" ", "-")) or ordinal_value(dtxt) or number_en(dtxt)
        if dnum and 1 <= dnum <= 31:
            year = int(ytxt) if ytxt else today.year
            try:
                d = dt.date(year, _MONTH_NUM[mo], int(dnum))
            except ValueError:
                return None
            if not ytxt and prefer_future and d < today:
                d = d.replace(year=year + 1)
            return d
    m = re.search(r"\b(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{2,4}))?\b", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        mo, dd = (b, a) if a > 12 else (a, b)
        try:
            y = int(m.group(3)) if m.group(3) else today.year
            y = y + 2000 if y < 100 else y
            d = dt.date(y, mo, dd)
            if not m.group(3) and prefer_future and d < today:
                d = d.replace(year=y + 1)
            return d
        except ValueError:
            return None
    return None


_UNITS_T = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30, "year": 365, "years": 365}


def _n_days(n: int) -> str:
    return num_words(n) if n < 60 else str(n)


def _hol_name(t: str) -> str:
    m = re.search(rf"\b({_HOL_RX})\b", t)
    return m.group(1).replace("s day", "'s day").title().replace("'S", "'s") if m else ""


_COUNTDOWN = re.compile(r"\b(?:(?:how many (?:days|weeks|months)|how long|how much time)\s+(?:is it\s+)?(?:until|till|to|before|left until|left till|remain(?:s|ing)? until|are there (?:until|till|to))|"
                        r"(?:days|time)\s+(?:left\s+)?(?:until|till|to)|countdown to)\s+(?P<what>.+)$")


_WD = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
_REL_DAY = re.compile(rf"\b(?P<w>the day after tomorrow|day after tomorrow|the day before yesterday|day before yesterday|tomorrow|yesterday|(?:next|last|this|coming|on)\s+(?:{_WD}))\b")
_ASK_DAY = re.compile(r"\bwhat(?:\s+s|s| is| was| will)?\s+(?:the\s+)?(?:date|day)\b|\bwhich day\b|\bwhat date\b")


def _relative_day(t: str, today: dt.date) -> tuple[str, dt.date] | None:
    """«what day is tomorrow», «what's the date yesterday», «what day is next Friday» -> (come si dice, data)."""
    m = _REL_DAY.search(t)
    if not m or not _ASK_DAY.search(t):
        return None
    w = m.group("w")
    if w.endswith("after tomorrow"):
        return "The day after tomorrow", today + dt.timedelta(days=2)
    if w.endswith("before yesterday"):
        return "The day before yesterday", today - dt.timedelta(days=2)
    if w == "tomorrow":
        return "Tomorrow", today + dt.timedelta(days=1)
    if w == "yesterday":
        return "Yesterday", today - dt.timedelta(days=1)
    kind, name = w.split()
    wd = [d.lower() for d in DAYS].index(name)
    if kind == "last":
        return f"Last {DAYS[wd]}", today - dt.timedelta(days=(today.weekday() - wd) % 7 or 7)
    return f"{kind.capitalize() if kind != 'on' else 'This'} {DAYS[wd]}".replace("Coming", "This"), today + dt.timedelta(days=(wd - today.weekday()) % 7 or 7)


def date_answer(text: str, now: dt.datetime | None = None) -> str:
    today = (now or dt.datetime.now()).date()
    t = normalize(decimals_to_words(text))
    rel = _relative_day(t, today)
    if rel:
        label, d = rel
        day = f"{MONTHS[d.month - 1]} {ordinal(d.day)}" if any(w.capitalize() in label for w in _WD.split("|")) else f"{DAYS[d.weekday()]}, {MONTHS[d.month - 1]} {ordinal(d.day)}"      # «Next Friday is October twenty-third» (senza ripetere Friday)
        return f"{label} {'was' if d < today else 'is'} {day}."
    m = re.search(r"\b(?:in)\s+(?P<n>[a-z0-9]+(?: [a-z]+)?)\s+(?P<u>days|day|weeks|week|months|month|years|year)\b", t) or \
        re.search(r"\b(?P<n>[a-z0-9]+(?: [a-z]+)?)\s+(?P<u>days|day|weeks|week|months|month|years|year)\s+(?P<ago>ago)\b", t)
    if m and re.search(r"\bwhat (?:day|date)\b|\bwhen (?:will|was|is)\b|\bwhat was the date\b", t):
        n = num(m.group("n"))
        if n is not None:
            u = m.group("u")
            sign = -1 if m.groupdict().get("ago") else 1
            if u.startswith("month"):
                mm = today.month - 1 + sign * int(n)
                y, mo = today.year + mm // 12, mm % 12 + 1
                last = (dt.date(y + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(days=1)).day
                d = dt.date(y, mo, min(today.day, last))
            elif u.startswith("year"):
                d = today.replace(year=today.year + sign * int(n), day=min(today.day, 28 if today.month == 2 else today.day))
            else:
                d = today + dt.timedelta(days=sign * int(n) * _UNITS_T[u])
            return f"It will be {_say_date(d, today)}." if sign > 0 else f"It was {_say_date(d, today)}."
    if re.search(r"\bwhat week\b|\bweek number\b|\bweek of the year\b", t):
        return f"We're in week number {num_words(today.isocalendar()[1])} of the year."
    m = re.search(r"\bborn (?:in|on)?\s*(?:\w+\s+\d{1,2}(?:st|nd|rd|th)?\s+)?(19\d\d|20\d\d)\b", t)
    if m and re.search(r"\bhow old\b", t):
        age = today.year - int(m.group(1))
        return f"You're {num_words(age)}, or {num_words(age - 1)} if your birthday hasn't come yet this year."
    m = _COUNTDOWN.search(t)
    if m:
        what = m.group("what")
        if re.search(r"\bend of (?:the )?year\b", what):
            d = dt.date(today.year, 12, 31)
        elif re.search(r"\bend of (?:the )?month\b", what):
            d = dt.date(today.year + (today.month == 12), today.month % 12 + 1, 1) - dt.timedelta(days=1)
        elif re.search(r"\b(?:the )?weekend\b|\bend of (?:the )?week\b", what):
            d = today + dt.timedelta(days=(4 - today.weekday()) % 7 or 7) if today.weekday() > 4 else today + dt.timedelta(days=4 - today.weekday())
        elif re.search(r"\bsummer\b", what):
            d = dt.date(today.year, 6, 21) if today <= dt.date(today.year, 6, 21) else dt.date(today.year + 1, 6, 21)
        else:
            d = _parse_date(what, today)
        if d is not None:
            n = (d - today).days
            if n == 0:
                return "It's today!"
            return f"There are {_n_days(n)} days to go: it will be {_say_date(d, today)}." if n > 1 else "Only one day to go: it's tomorrow." if n == 1 else f"That was {_n_days(-n)} days ago."
    m = re.search(r"\bhow (?:many days|long)\s+(?:has it been|have passed|ago was|has passed|since)\s+(?:since\s+)?(?P<what>.+)$", t)
    if m:
        d = _parse_date(m.group("what"), today, prefer_future=False)
        if d is not None:
            n = (today - d).days
            return f"It has been {_n_days(n)} days." if n > 0 else "That's today." if n == 0 else f"That hasn't happened yet: {_n_days(-n)} days to go."
    m = re.search(r"\bhow many days\s+(?:are there\s+)?between\s+(?P<a>.+?)\s+and\s+(?P<b>.+)$", t)
    if m:
        a, b = _parse_date(m.group("a"), today, False), _parse_date(m.group("b"), today, False)
        if a and b:
            if b < a and not re.search(r"20\d\d", m.group("b")):
                b = b.replace(year=b.year + 1)
            return f"There are {_n_days(abs((b - a).days))} days."
    d = _parse_date(t, today, prefer_future=not re.search(r"\bthis year\b", t))
    if d is not None and re.search(r"\b(?:when is|when was|when s|what day|what date|which day|what day of the week|day of the week|does it fall|falls)\b", t):
        when = _say_date(d, today)
        name = _hol_name(t)
        if not name:
            return when + "."
        return f"{name} {'falls on' if d >= today else 'fell on'} {when}."
    return "I couldn't work that out with dates. Try, for example: \"how many days until Christmas?\"."


def date_kind(text: str) -> bool:
    """Una domanda di calcolo con le date (non «what day is it today?», che e' ORA; non «how long is left on the timer?», che e' del timer)?"""
    t = normalize(decimals_to_words(text))
    if _relative_day(t, dt.date.today()):
        return True
    mc = _COUNTDOWN.search(t)
    if mc:
        what = mc.group("what")
        return bool(re.search(rf"\b(?:{_HOL_RX}|end of (?:the )?year|end of (?:the )?month|end of (?:the )?week|weekend|summer|{_MONTH_RX})\b|\b\d{{1,2}}\s*[/-]\s*\d{{1,2}}\b", what)) and not re.search(r"\b(?:timer|alarm|arrive|arrival|finish|leave|my flight|the meeting|lunch|dinner)\b", t)
    if re.search(r"\bhow many days\s+(?:are there\s+)?between\b|\bhow (?:many days|long)\s+(?:has it been|have passed|has passed)\s+since\b|\bhow many days since\b", t):
        return True
    if re.search(r"\bin\s+[a-z0-9]+(?: [a-z]+)?\s+(?:days|day|weeks|week|months|month|years|year)\b", t) and re.search(r"\bwhat (?:day|date)\b|\bwhen will\b", t):
        return True
    if re.search(r"\b[a-z0-9]+(?: [a-z]+)?\s+(?:days|weeks|months|years)\s+ago\b", t) and re.search(r"\bwhat (?:day|date)\b|\bwhen\b", t):
        return True
    if re.search(r"\bwhat week\b|\bweek of the year\b|\bweek number\b", t):
        return True
    if re.search(r"\bhow old\b", t) and re.search(r"\bborn\b", t):
        return True
    if re.search(rf"\b(?:when is|when s|when was|what day is|what day s|what day was|what date is|which day is|what day of the week is|does)\b.*\b(?:{_HOL_RX}|(?:the\s+)?(?:\d{{1,2}}(?:st|nd|rd|th)?)\s+(?:of\s+)?(?:{_MONTH_RX})|(?:{_MONTH_RX})\s+(?:the\s+)?\d{{1,2}})", t):
        return True
    if re.search(rf"\b(?:what day|what date|when)\b.*\b(?:{_HOL_RX})\b", t) and not re.search(r"\bwhat day is (?:it|today)\b", t):
        return True
    return False


# ------------------------------------------------------------------------------- dado, moneta, sorteggi
_RANKS = ["ace", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "jack", "queen", "king"]
_SUITS = ["hearts", "diamonds", "clubs", "spades"]


def chance_kind(text: str) -> str | None:
    t = normalize(text)
    if re.search(r"\b(?:roll|throw|toss|cast)\s+(?:me\s+)?(?:a|an|one|the|two|three|four|\d+)?\s*(?:\w+\s+)?(?:die|dice)\b|\b(?:die|dice)\b.*\b(?:roll|throw)\b|^(?:a\s+)?(?:die|dice)$|\broll a d\d+\b", t):
        return "dado"
    if re.search(r"\b(?:flip|toss|spin)\s+(?:me\s+)?(?:a|the)\s+coin\b|\bheads or tails\b|\bcoin (?:flip|toss)\b", t):
        return "moneta"
    if re.search(r"\b(?:pick|choose|give me|generate|tell me|think of|draw)\s+(?:me\s+)?(?:a\s+)?(?:random\s+)?number\b", t) or re.search(r"\brandom number\b", t):
        return "numero"
    if re.search(r"\b(?:draw|pick|deal)\s+(?:me\s+)?(?:a\s+)?card\b", t):
        return "carta"
    if re.search(r"\b(?:choose|pick|decide|select)\b.*\bbetween\b.+\b(?:and|or)\b|\bpick one at random\b|\bchoose at random\b", t):
        return "scelta"
    return None


def chance_answer(text: str, rng: random.Random | None = None) -> str:
    r = rng or random
    t = normalize(decimals_to_words(text))
    kind = chance_kind(text)
    if kind == "dado":
        m = re.search(r"\b(two|three|four|five|six|\d+)\s+(?:\w+\s+)?dice\b", t)
        n = int(num(m.group(1)) or 1) if m else 1
        n = max(1, min(n, 6))
        mf = re.search(r"\b(?:d|with\s+|a\s+)(\d+)(?:\s+(?:sided|faces))\b|\bd(\d+)\b", t)
        faces = int(next(g for g in mf.groups() if g)) if mf else 6
        faces = max(2, min(faces, 1000))
        res = [r.randint(1, faces) for _ in range(n)]
        if n == 1:
            return f"It's a {res[0]}."
        return "You rolled " + ", ".join(str(x) for x in res) + f": {sum(res)} in total."
    if kind == "moneta":
        return r.choice(["It's heads.", "It's tails."])
    if kind == "numero":
        nums = re.findall(r"[0-9]+(?:punto[0-9]+)?|[a-z]+", t.partition("number")[2])
        vals = [v for v in (num(x) for x in nums) if v is not None]
        lo, hi = (int(vals[0]), int(vals[1])) if len(vals) >= 2 else (1, 10) if not vals else (1, int(vals[0]))
        if lo > hi:
            lo, hi = hi, lo
        return f"The number is {r.randint(lo, hi)}."
    if kind == "carta":
        return f"You drew the {r.choice(_RANKS)} of {r.choice(_SUITS)}."
    if kind == "scelta":
        m = re.search(r"\bbetween\s+(.+)$", text, flags=re.I)
        body = m.group(1) if m else ""
        opts = [o.strip(" .,!?") for o in re.split(r"\s*,\s*|\s+\bor\b\s+|\s+\band\b\s+", body) if o.strip(" .,!?")]
        if len(opts) >= 2:
            return f"I pick {r.choice(opts)}."
    return "Tell me what to roll: for example \"roll a die\", \"flip a coin\" or \"pick a number from one to ten\"."


# ------------------------------------------------------------------------------- cosa sa fare
def help_kind(text: str) -> bool:
    t = normalize(text)
    return bool(re.search(
        r"^(?:help|help me)$|^(?:so\s+|hey\s+|well\s+|tell me\s+|okay\s+)?what\s+(?:can|could)\s+(?:you|i)\s+(?:do|ask you|ask|say|tell you)|\b(?:how do you work|how do i use you|how to use you|what are you for|what are your (?:features|functions|powers|abilities|skills)|"
        r"what can you help (?:me )?with|what can i ask you|what do you do(?: for me| exactly)?$|what are you able to do|what are you capable of|list your (?:features|functions|abilities)|show me what you can do|tell me what you can do)\b|^how does this work$|^how do i (?:talk|speak) to you$", t))


def help_text(powers: dict[str, bool] | None = None) -> str:
    on = powers or {}

    def has(k: str) -> bool:
        return on.get(k, True)
    parts = ["I can tell you the weather, the time and the date, do calculations, conversions and translations, roll a die or flip a coin, and remind you of things with timers and alarms"]
    win = sys.platform == "win32"                                    # su Windows: promemoria di Aria (non l'app), niente calendario e niente schermo
    mac = []
    if has("reminders") or (has("calendar") and not win):
        mac.append("set reminders and tell you which ones are coming up" if win else "add reminders and calendar events and tell you what's on your agenda")
    if has("music"):
        mac.append("control the music and the volume")
    if has("apps"):
        mac.append("open apps, websites and maps")
    if mac:
        parts.append(("On this PC I can " if win else "On the Mac I can ") + ", ".join(mac))
    parts.append("In my folder I write documents and research, keep shopping lists and notes, and answer questions about your files")
    if (has("screen_mac") or has("screen_model")) and not win:
        parts.append("and I can look at the screen to tell you where a button is or to read out what's there")
    parts.append("I can't make phone calls, send messages, buy things or control your home")
    return ". ".join(p[:1].upper() + p[1:] if i else p for i, p in enumerate(parts)) + ". If you want to know how to do something, just ask me."


# ------------------------------------------------------------------------------- «quando» del meteo
_WEEKDAYS = {normalize(g): i for i, g in enumerate(DAYS)}
_WHEN_RX = re.compile(
    r"\b(?:the day after tomorrow|day after tomorrow|tomorrow|today|tonight|this morning|this afternoon|this evening|"
    r"(?:this|next|on the|over the|for the)\s+weekend|weekend|"
    r"in\s+(?:a|an|one|[a-z0-9]+)\s+(?:days|day|weeks|week)|"
    r"(?:over\s+)?(?:the\s+)?next\s+(?:few\s+)?days|(?:this|next)\s+week|(?:the\s+)?(?:coming|upcoming)\s+week|"
    r"(?:on\s+|this\s+|next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"(?:on\s+)?(?:the\s+)?(?:\d{1,2}(?:st|nd|rd|th)?)\s+of\s+(?:" + "|".join(MONTHS) + r")|(?:on\s+)?(?:" + "|".join(MONTHS) + r")\s+(?:the\s+)?\d{1,2}(?:st|nd|rd|th)?)\b", re.I)


def when_phrase(text: str) -> str:
    """La parte «quando» di una domanda sul meteo: «Saturday», «the day after tomorrow», «in three days», «this weekend»… (stringa vuota se non c'e')."""
    m = _WHEN_RX.search(text)
    return m.group(0) if m else ""


def forecast_when(text: str, today: dt.date | None = None) -> tuple[list[int] | None, str, str]:
    """-> (giorni da oggi di cui dare le previsioni, etichetta, testo senza le parole del giorno). Se la data e' oltre il limite delle previsioni: (None, spiegazione, resto)."""
    today = today or dt.date.today()
    rest = re.sub(r"\s+", " ", _WHEN_RX.sub(" ", text)).strip()
    t = normalize(text)
    if re.search(r"\bday after tomorrow\b", t):
        return [2], "The day after tomorrow", rest
    if re.search(r"\btomorrow\b", t):
        return [1], "Tomorrow", rest
    if re.search(r"\bweekend\b", t):
        sat = (5 - today.weekday()) % 7 if today.weekday() != 6 else 0
        if today.weekday() == 5:
            return [0, 1], "This weekend", rest
        if today.weekday() == 6:
            return [0], "Today", rest
        return [sat, sat + 1], "This weekend", rest
    m = re.search(r"\bin\s+(a|an|one|[a-z0-9]+)\s+(days|day|weeks|week)\b", t)
    if m:
        n = 1.0 if m.group(1) in ("a", "an", "one") else num(m.group(1))
        if n is not None:
            days = int(n) * (7 if m.group(2).startswith("week") else 1)
            if days > 15:
                return None, "The forecast only goes up to fifteen days from today.", rest
            return [days], ("In one day" if days == 1 else f"In {num_words(days)} days"), rest
    if re.search(r"\bnext (?:few )?days\b", t):
        return [1, 2, 3], "Over the next few days", re.sub(r"\s+", " ", re.sub(r"(?i)\b(?:over\s+)?(?:the\s+)?next\s+(?:few\s+)?days\b", " ", rest)).strip()
    if re.search(r"\b(?:this|next|coming|upcoming)\s+week\b", t):
        start = 7 - today.weekday() if re.search(r"\bnext\b", t) else 0
        if start + 6 > 15:
            start = max(0, 15 - 6)
        return list(range(start, start + 7)), ("Next week" if start else "This week"), re.sub(r"\s+", " ", re.sub(r"(?i)\b(?:this|next|the coming|the upcoming|coming|upcoming)\s+week\b", " ", rest)).strip()
    for name, wd in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", t):
            off = (wd - today.weekday()) % 7
            return [off], DAYS[wd], rest
    d = _parse_date(t, today)
    if d is not None and re.search(rf"\b{_MONTH_RX}\b", t):
        off = (d - today).days
        if off > 15:
            return None, "The forecast only goes up to fifteen days from today.", rest
        return [off], _say_date(d, today), rest
    return [0], "Today", rest


# ------------------------------------------------------------------------------- traduzioni
_LANGS = {"english": "English", "french": "French", "spanish": "Spanish", "german": "German", "portuguese": "Portuguese", "italian": "Italian", "dutch": "Dutch", "latin": "Latin",
          "romanian": "Romanian", "polish": "Polish", "swedish": "Swedish", "catalan": "Catalan", "american english": "English", "british english": "English"}
_LANG_RX = "|".join(sorted(_LANGS, key=len, reverse=True))
_OTHER_LANGS = r"(?:chinese|japanese|russian|arabic|korean|greek|turkish|hindi|hebrew|thai|vietnamese|ukrainian)"
_TR_PATTERNS = [
    re.compile(rf"^(?:translate)\s+(?:this sentence |the sentence |this text |the text |these words |the word |this word |the phrase |this phrase )?(?:in|into|to)\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})\s*[:,\-]\s*(?P<text>.+)$", re.I),
    re.compile(rf"^(?:translate|translate me)\s+(?:in|into|to)\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})\s*[:,\-]?\s+(?P<text>.+)$", re.I),
    re.compile(rf"^(?:translate)\s+(?:this sentence |the sentence |this text |the text |these words |the word |this word |the phrase |this phrase )?(?P<text>.+?)\s+(?:in|into|to)\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})$", re.I),
    re.compile(rf"^(?:how|what)\s+(?:do you say|do i say|would you say|can i say|is the word for|s the word for|is the translation of|s the translation of|do you translate)\s+(?P<text>.+?)\s+in\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})$", re.I),
    re.compile(rf"^(?:what\s+is|what\s+s|whats)\s+(?P<text>.+?)\s+in\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})$", re.I),
    re.compile(rf"^in\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})\s+(?:how do you say|how do i say|how to say|you say|say)\s+(?P<text>.+)$", re.I),
    re.compile(rf"^(?:how|what)\s+(?:do you say|do i say|would you say)\s+in\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})\s+(?P<text>.+)$", re.I),
    re.compile(rf"^what\s+(?:does|do)\s+(?P<text>.+?)\s+mean\s+in\s+(?P<lang>{_LANG_RX}|{_OTHER_LANGS})$", re.I),
]


def translation_request(text: str) -> tuple[str, str] | None:
    """(lingua, frase da tradurre) se e' una richiesta di traduzione, altrimenti None. La frase e' presa dal testo originale (maiuscole comprese)."""
    t = re.sub(r"\s+", " ", text.strip(" .!?").replace("’", "'"))
    t = re.sub(r"^(translate)\s*,\s*", r"\1 ", t, flags=re.I)
    t = re.sub(r"\b(what|how|where|who)'s\b", r"\1 is", t, flags=re.I)
    if not normalize(t) or len(normalize(t).split()) > 40:
        return None
    for rx in _TR_PATTERNS:
        m = rx.match(t)
        if m:
            lang = m.group("lang").lower()
            body = m.group("text").strip(" .,;:!?\"'“”")
            if body:
                return lang, body
    return None


def translation_ok_lang(lang: str) -> bool:
    return lang in _LANGS or lang in ("french",)
