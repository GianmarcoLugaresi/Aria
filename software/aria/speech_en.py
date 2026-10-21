"""L'inglese parlato: numeri, orari, date e simboli a parole, per il sintetizzatore. Gemello inglese delle funzioni di speech.py e tools.py (vedi la lingua in i18n.py).

`speechify()` prepara una frase per la voce: «18°C» -> «eighteen degrees Celsius», «40%» -> «forty percent», «6:30 pm» -> «six thirty p m», niente asterischi/emoji/parentesi,
una virgola dopo gli intercalari («Well sure» -> «Well, sure») cosi' la voce fa la pausa che farebbe una persona.
"""
from __future__ import annotations

import datetime as dt
import re

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}


def _below_100(n: int) -> str:
    if n < 20:
        return _ONES[n]
    t, u = divmod(n, 10)
    return _TENS[t] + (f"-{_ONES[u]}" if u else "")


def _below_1000(n: int) -> str:
    h, r = divmod(n, 100)
    if not h:
        return _below_100(r)
    return f"{_ONES[h]} hundred" + (f" {_below_100(r)}" if r else "")


def num_words(n: int) -> str:
    """Un intero in parole inglesi: 1985 -> «one thousand nine hundred eighty-five»; 1250000 -> «one million two hundred fifty thousand»."""
    if n < 0:
        return "minus " + num_words(-n)
    if n < 1000:
        return _below_1000(n)
    out = []
    for size, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (10 ** 3, "thousand")):
        k, n = divmod(n, size)
        if k:
            out.append(f"{_below_1000(k) if k < 1000 else num_words(k)} {name}")
    if n:
        out.append(_below_1000(n))
    return " ".join(out)


def ordinal(n: int) -> str:
    """1 -> first, 2 -> second, 21 -> twenty-first, 100 -> one hundredth."""
    w = num_words(n)
    cut = max(w.rfind(" "), w.rfind("-")) + 1
    head, last = w[:cut], w[cut:]
    if last in _ORD:
        last = _ORD[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last = last + "th"
    return head + last


def year_words(y: int) -> str:
    """Un anno come lo si dice: 2026 -> «twenty twenty-six», 2005 -> «two thousand five», 1999 -> «nineteen ninety-nine», 1905 -> «nineteen oh five»."""
    if 2000 <= y < 2010:
        return "two thousand" + (f" {_ONES[y - 2000]}" if y > 2000 else "")
    if y < 1000 or y >= 10000:
        return num_words(y)
    hi, lo = divmod(y, 100)
    if lo == 0:
        return f"{_below_100(hi)} hundred"
    return f"{_below_100(hi)} " + (f"oh {_ONES[lo]}" if lo < 10 else _below_100(lo))


def _digits(s: str) -> str:
    return " ".join(_ONES[int(c)] for c in s)


def _decimal(whole: str, frac: str) -> str:
    return f"{num_words(int(whole))} point {_digits(frac)}"


def speak_number(x: float) -> str:
    """Un numero come risposta a voce: 3 -> «three», 3.5 -> «three point five»."""
    if float(x).is_integer():
        return num_words(int(x))
    txt = f"{x:.4f}".rstrip("0").rstrip(".")
    whole, _, frac = txt.partition(".")
    return (("minus " if x < 0 else "") + _decimal(whole.lstrip("-"), frac)) if frac else num_words(int(x))


# ------------------------------------------------------------------------------- orari e date
def _h12(h: int) -> int:
    return h % 12 or 12


def day_part(now: dt.datetime | None = None) -> str:
    h = (now or dt.datetime.now()).hour
    return "morning" if 5 <= h < 12 else "afternoon" if 12 <= h < 18 else "evening" if 18 <= h < 23 else "night"


def speak_time(now: dt.datetime | None = None) -> str:
    """«It's ten forty-nine.», «It's a quarter past ten.», «It's noon.»"""
    n = now or dt.datetime.now()
    h, m = n.hour, n.minute
    if h == 0 and m == 0:
        return "It's midnight."
    if h == 12 and m == 0:
        return "It's noon."
    if m == 0:
        return f"It's {num_words(_h12(h))} o'clock."
    if m == 15:
        return f"It's a quarter past {num_words(_h12(h))}."
    if m == 30:
        return f"It's half past {num_words(_h12(h))}."
    if m == 45:
        return f"It's a quarter to {num_words(_h12(h + 1))}."
    return f"It's {num_words(_h12(h))} {'oh ' + _ONES[m] if m < 10 else _below_100(m)}."


def speak_clock(t: dt.datetime) -> str:
    """7:05 -> «seven oh five», 18:42 -> «six forty-two»: per i dati di alba e tramonto."""
    h, m = _h12(t.hour), t.minute
    return num_words(h) + ("" if m == 0 else f" oh {_ONES[m]}" if m < 10 else f" {_below_100(m)}")


def speak_date(now: dt.datetime | None = None) -> str:
    n = now or dt.datetime.now()
    return f"Today is {DAYS[n.weekday()]}, {MONTHS[n.month - 1]} {ordinal(n.day)}, {year_words(n.year)}."


def now_en(now: dt.datetime | None = None) -> str:
    n = now or dt.datetime.now()
    return f"{DAYS[n.weekday()]}, {MONTHS[n.month - 1]} {n.day}, {n.year}, at {n.hour}:{n.minute:02d}"


def words(n: int) -> str:
    """Numeri piccoli e anni per i messaggi («two timers», «twenty twenty-six»)."""
    return year_words(n) if 1100 <= n <= 2099 else num_words(n)


def fmt_duration(sec: int) -> str:
    h, rest = divmod(int(sec), 3600)
    m, s = divmod(rest, 60)
    parts = []
    if h:
        parts.append(f"{h} {'hour' if h == 1 else 'hours'}")
    if m:
        parts.append(f"{m} {'minute' if m == 1 else 'minutes'}")
    if s and not h:
        parts.append(f"{s} {'second' if s == 1 else 'seconds'}")
    return " and ".join(parts) or "0 seconds"


def clock_at(h: int, m: int) -> str:
    """«at nine thirty a m», «at three p m», «at noon», «at midnight»: un orario a voce, con a m / p m perche' a voce 9 e 21 non si distinguono."""
    if h == 0 and m == 0:
        return "at midnight"
    if h == 12 and m == 0:
        return "at noon"
    suffix = " a m" if h < 12 else " p m"
    at = num_words(_h12(h)) + ("" if m == 0 else f" oh {_ONES[m]}" if m < 10 else f" {_below_100(m)}")
    return f"at {at}{suffix}"


def say_when(when: dt.datetime, has_time: bool, now: dt.datetime) -> str:
    """«tomorrow at nine thirty», «Monday at three p m», «today»: come si dice a voce."""
    delta = (when.date() - now.date()).days
    if delta == 0:
        day = "today"
    elif delta == 1:
        day = "tomorrow"
    elif 0 < delta < 7:
        day = DAYS[when.weekday()]
    else:
        day = f"{DAYS[when.weekday()]}, {MONTHS[when.month - 1]} {ordinal(when.day)}"
    if not has_time:
        return day
    return f"{day} {clock_at(when.hour, when.minute)}"


# ------------------------------------------------------------------------------- il testo del chatbot, pronto per la voce
_UNITS = [(r"km\s*/\s*h", "kilometers per hour"), (r"mph", "miles per hour"), (r"ghz", "gigahertz"), (r"mhz", "megahertz"), (r"khz", "kilohertz"), (r"hz", "hertz"), (r"tb", "terabytes"), (r"km", "kilometers"), (r"kg", "kilograms"), (r"cm", "centimeters"), (r"mm", "millimeters"),
          (r"ml", "milliliters"), (r"gb", "gigabytes"), (r"mb", "megabytes"), (r"kb", "kilobytes"), (r"mins?", "minutes"), (r"secs?", "seconds"), (r"hrs?", "hours"),
          (r"lbs?", "pounds"), (r"oz", "ounces"), (r"ft", "feet"), (r"h", "hours"), (r"m", "meters"), (r"g", "grams"), (r"l", "liters")]
_ABBR = [(r"\betc\.", "et cetera"), (r"\be\.g\.", "for example"), (r"\bi\.e\.", "that is"), (r"\bDr\.", "Doctor"), (r"\bMr\.", "Mister"), (r"\bMrs\.", "Missus"), (r"\bMs\.", "Miss"),
         (r"\bProf\.", "Professor"), (r"\bvs\.?", "versus"), (r"\bapprox\.", "approximately"), (r"\bno\.\s*(?=\d)", "number "), (r"\bp\.m\.?", "p m"), (r"\ba\.m\.?", "a m")]
_MARKER_RE = re.compile(r"(^|[.!?…]\s+)((?:well|hmm+|um+|uh+|oh|ah|so yeah|anyway|okay then|alright then))\s+(?=[a-zA-Z])", re.I)


def speechify(text: str) -> str:
    t = text or ""
    t = re.sub(r"(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+(?:com|org|net|io|it|co\.uk|edu|gov|app|dev|ai|eu))\b(?:/\S*)?", lambda m: m.group(1).replace(".", " dot "), t, flags=re.I)         # example.com/page -> «example dot com»
    t = re.sub(r"\((\d{3})\)\s*(?=\d{3}[-. ]\d{4})", r"\1 ", t)                         # il prefisso (555) di un telefono non e' una nota tra parentesi
    t = re.sub(r"\*[^*\n]{1,60}\*", " ", t)                                          # *smiles*: azioni tra asterischi, non si dicono
    t = re.sub(r"\([^)\n]{0,120}\)", " ", t)                                         # (note tra parentesi)
    t = re.sub(r"\[[^\]\n]{0,80}\]", " ", t)
    t = re.sub(r"#\s?(\d+)", r"number \1", t)                                         # «#1» = «number 1»
    t = re.sub(r"[_*#~`<>|\[\]{}]+", " ", t)
    t = re.sub(r"[«»\"“”]", "", t)
    t = re.sub(r"\s*[—–]\s*", ", ", t)
    t = re.sub(r"\s*&\s*", " and ", t)
    t = re.sub(r"\.{3,}", "…", t)
    t = re.sub(r"([!?]){2,}", r"\1", t)
    t = re.sub(r"([,;:])\1+", r"\1", t)

    def part(h: int) -> str:
        return "in the morning" if 5 <= h < 12 else "in the afternoon" if 12 <= h < 17 else "in the evening" if 17 <= h < 21 else "at night"

    def clock(m):                                                                      # 18:30 -> «six thirty in the evening»; 9:05 am -> «nine oh five a m»
        h, mi, suf = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower().replace(".", "")
        if h == 0 and mi == 0 and not suf:
            return "midnight"
        if h == 12 and mi == 0 and not suf:
            return "noon"
        words_ = num_words(_h12(h)) + ("" if mi == 0 else f" oh {_ONES[mi]}" if mi < 10 else f" {_below_100(mi)}")
        if suf in ("am", "pm"):
            return words_ + (" o'clock" if mi == 0 else "") + f" {suf[0]} m"
        return words_ + (" o'clock" if mi == 0 else "") + " " + part(h)
    def end_dot(m) -> str:                                                           # «5 p.m.» a fine frase: il punto dell'abbreviazione e' anche il punto della frase
        return "." if m.group(0).endswith(".") and re.match(r"\s*$|\s+[A-Z\"“]", m.string[m.end():]) else ""
    t = re.sub(r"\b([01]?\d|2[0-3]):([0-5]\d)(?:\s*([ap]\.m\.|[ap]m))?(?![\d:])", lambda m: clock(m) + (end_dot(m) if m.group(3) else ""), t, flags=re.I)
    t = re.sub(r"\b(\d{1,2})\s*([ap])(?:\.m\.|m)(?![A-Za-z])", lambda m: f"{num_words(int(m.group(1)))} {m.group(2).lower()} m" + end_dot(m), t, flags=re.I)

    t = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", lambda m: " dot ".join(num_words(int(x)) for x in m.group(0).split(".")), t)       # 192.168.1.1 (prima delle versioni)
    t = re.sub(r"(?<![\d.])(?:(1)[-. ])?(\d{3})[-. ](\d{3})[-. ](\d{4})(?!\d)(?!\.\d)", lambda m: ", ".join(_digits(g) for g in m.groups() if g), t)           # 555-123-4567 a cifre
    t = re.sub(r"(?<![\d.-])(\d{3})-(\d{4})(?!\d)(?!\.\d)(?!-)", lambda m: f"{_digits(m.group(1))}, {_digits(m.group(2))}", t)                       # 555-0134

    def numdate(m) -> str:
        from . import i18n
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y if y >= 100 else (1900 + y if y >= 70 else 2000 + y)
        first_is_month = a <= 12 and (b > 12 or i18n.units() == "imperial")               # 04/07/1990: negli Stati Uniti e' il 7 aprile, altrove il 4 luglio
        month, day = (a, b) if first_is_month else (b, a)
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return m.group(0)
        return f"{MONTHS[month - 1]} {ordinal(day)}, {year_words(y)}"
    t = re.sub(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?![\d/])", numdate, t)
    t = re.sub(r"\b(\d+)\s+(1/2|1/3|2/3|1/4|3/4)\b", lambda m: f"{m.group(1)} and {m.group(2)}", t)                                               # 2 1/4 -> «2 and 1/4»
    t = re.sub(r"\b(\d{1,2}):(\d)(?![\d:])", r"\1 to \2", t)                                  # 3:1 = «three to one» (i minuti hanno due cifre)
    t = re.sub(r"(?<![\w'])'(\d{2})\b", r"\1", t)                                              # '95

    def saint_or_street(m) -> str:                                                    # «St. John» = Saint; «Main St. near the park» = Street; nel dubbio si lascia com'e'
        prev, rest = m.group(1), m.string[m.end():]
        dot = m.group(0).endswith(".")
        if prev and not re.match(r"\s+[A-Z]", rest):
            return f"{prev} Street" + ("." if dot and not rest.strip() else "")
        if not prev and re.match(r"\s+[A-Z]", rest):
            return "Saint"
        return m.group(0)
    t = re.sub(r"(?:\b([A-Z][a-z]+)\s+)?\bSt\b\.?", saint_or_street, t)

    def version(m):
        return " point ".join(num_words(int(x)) for x in m.group(0).split("."))
    t = re.sub(r"\b\d+(?:\.\d+){2,}\b", version, t)                                  # versioni: «macOS 27.0.1»
    t = re.sub(r"\b(\d{1,3})((?:,\d{3})+)\b", lambda m: (m.group(1) + m.group(2)).replace(",", ""), t)             # 1,250,000
    t = re.sub(r"(?<![\w)])[-−](?=\d)", "minus ", t)                                   # «-5°C» -> «minus 5°C» (non «10-20» né «3-2»)
    t = re.sub(r"\b(\d+)'(\d{1,2})\b", lambda m: f"{m.group(1)} foot {m.group(2)}", t)           # 5'11" -> «5 foot 11»
    t = re.sub(r"(\d+(?:\.\d+)?)\s*%", lambda m: m.group(1) + " percent", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*°\s*C\b", lambda m: m.group(1) + " degrees Celsius", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*°\s*F\b", lambda m: m.group(1) + " degrees Fahrenheit", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*°", lambda m: m.group(1) + " degrees", t)
    def money(whole: str, cents: str | None, one: str, many: str, cent: str) -> str:
        w = int(whole.replace(",", ""))
        c = int(cents) if cents else 0
        out = f"{num_words(w)} {one if w == 1 else many}"
        return out + (f" and {num_words(c)} {cent if c == 1 else cent + 's'}" if c else "")
    t = re.sub(r"\$\s*(\d[\d,]*)(?:\.(\d{2}))?\b", lambda m: money(m.group(1), m.group(2), "dollar", "dollars", "cent"), t)
    t = re.sub(r"€\s*(\d[\d,]*)(?:\.(\d{2}))?\b", lambda m: money(m.group(1), m.group(2), "euro", "euros", "cent"), t)
    t = re.sub(r"(\d[\d,]*)(?:\.(\d{2}))?\s*€", lambda m: money(m.group(1), m.group(2), "euro", "euros", "cent"), t)
    t = re.sub(r"£\s*(\d[\d,]*)(?:\.(\d{2}))?\b", lambda m: money(m.group(1), m.group(2), "pound", "pounds", "pence").replace("pences", "pence"), t)
    for rx, rep in _ABBR:
        t = re.sub(rx, rep, t)
    for rx, rep in _UNITS:                                                           # solo se attaccate o dopo un numero: «5 km», «20kg»
        t = re.sub(rf"(?<=\d)\s*{rx}\b", " " + rep, t, flags=re.I)
    def slash(m) -> str:
        a, b = int(m.group(1)), int(m.group(2))
        frac = {(1, 2): "one half", (1, 3): "one third", (2, 3): "two thirds", (1, 4): "one quarter", (3, 4): "three quarters"}
        if (a, b) in frac:
            return frac[(a, b)]
        if 1 <= a <= 12 and 13 <= b <= 31:
            return f"{MONTHS[a - 1]} {ordinal(b)}"                                     # 10/22 = October twenty-second
        if b in (5, 10, 20, 100):
            return f"{num_words(a)} out of {num_words(b)}"                             # 9/10 = nine out of ten
        return f"{num_words(a)} slash {num_words(b)}"
    t = re.sub(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", slash, t)
    t = re.sub(r"\b(20\d\d|19\d\d)-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])\b", lambda m: f"{MONTHS[int(m.group(2)) - 1]} {ordinal(int(m.group(3)))}, {year_words(int(m.group(1)))}", t)      # 2026-10-21
    t = re.sub(r"(?<![\w.])(\d+)\s*-\s*(\d+)(?![\w.])", lambda m: f"{m.group(1)} to {m.group(2)}" if int(m.group(1)) < int(m.group(2)) else m.group(0), t)      # 25-30 -> «25 to 30»; il punteggio 3-2 resta
    t = re.sub(r"(?<=\d)\s*\+\s*(?=\d)", " plus ", t)
    t = re.sub(r"(?<=\d)\s*=\s*(?=\d)", " equals ", t)
    t = re.sub(r"\b(\d+)(st|nd|rd|th)\b", lambda m: ordinal(int(m.group(1))), t, flags=re.I)
    t = re.sub(r"\b(\d+)\.(\d+)\b", lambda m: _decimal(m.group(1), m.group(2)), t)

    def integer(m):
        s = m.group(0)
        if len(s) > 9:
            return _digits(s)
        n = int(s)
        if len(s) == 4 and 1100 <= n <= 2099 and re.search(r"(?:\b(?:in|since|from|until|till|by|of|year|during|before|after|circa|than|and|to|through|between|early|late|mid)|\b(?:" + "|".join(MONTHS) + r"))\s+(?:\w+,?\s+)?$", m.string[:m.start()], re.I):
            return year_words(n)
        return num_words(n)
    t = re.sub(r"\b\d+\b", integer, t)
    t = _MARKER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}, ", t.strip())            # «Well sure» -> «Well, sure»
    t = re.sub(r"\s+([,.;:!?…])", r"\1", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()
