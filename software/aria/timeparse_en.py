"""Date, orari e durate dette a voce in inglese: «tomorrow at nine thirty», «Monday at 3 pm», «on October 15th», «in two days», «half an hour».

Gemello inglese di timeparse.py (e di parse_duration in tools.py). `parse_when(testo, adesso)` restituisce quando, se e' stata detta anche l'ora, e il testo rimasto senza
le parole di data/ora («remind me tomorrow at 9 to call Mark» -> quando = domani 9:00, resto = «remind me to call Mark»).
Regole sulle ore senza «am/pm» ne' «in the morning/evening»: 1-6 = pomeriggio («at 5» = 17:00), 7-11 = mattina.
"""
from __future__ import annotations

import datetime as dt
import re

from .timeparse import When, _cut, fold

_DAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
_MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}
_MON_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
_MONTH_RX = "|".join(list(_MONTHS) + list(_MON_ABBR))

_ONES = {"zero": 0, "oh": 0, "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
        "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20,
        "thirtieth": 30}
_ORD_TENS = {"twenty": 20, "thirty": 30}

_NUM_WORDS = "|".join(sorted(list(_ONES) + [t + r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?" for t in _TENS], key=len, reverse=True))
NUM = rf"(?:\d{{1,2}}|{_NUM_WORDS})"


def to_int(word: str) -> int | None:
    w = word.strip().lower().replace("-", " ")
    if w.isdigit():
        return int(w)
    if w in _ONES:
        return _ONES[w]
    parts = w.split()
    if len(parts) == 2 and parts[0] in _TENS and parts[1] in _ONES and 1 <= _ONES[parts[1]] <= 9:
        return _TENS[parts[0]] + _ONES[parts[1]]
    if len(parts) == 1 and parts[0] in _TENS:
        return _TENS[parts[0]]
    return None


def ordinal_value(word: str) -> int | None:
    w = word.strip().lower().replace("-", " ")
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?", w)
    if m:
        return int(m.group(1))
    if w in _ORD:
        return _ORD[w]
    parts = w.split()
    if len(parts) == 2 and parts[0] in _ORD_TENS and parts[1] in _ORD and _ORD[parts[1]] < 10:
        return _ORD_TENS[parts[0]] + _ORD[parts[1]]
    return None


_ORDINAL_RX = r"(?:\d{1,2}(?:st|nd|rd|th)?|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|twentieth|twenty[- ](?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)|thirtieth|thirty[- ]first)"

_DAYPART = re.compile(r"\b(?:in the|at|this|during the|of the)?\s*(morning|afternoon|evening|night|tonight)\b")
_AMPM = r"(?:\s*(?:a\s?m|p\s?m|a\.m\.|p\.m\.|in the morning|in the afternoon|in the evening|at night))"
_TIME_DIGITS = re.compile(r"\b(?:at|around|by|for|until|till|from)\s+(\d{1,2})(?:\s*[:.]\s*(\d{2}))?(\s*(?:a\s?m|p\s?m|a\.m\.|p\.m\.|o['’ ]?clock))?(?!\d)(?!\s*(?:minutes?|hours?|days?|weeks?))")
_TIME_WORDS = re.compile(rf"\b(?:at|around|by|for|until|till|from)\s+({NUM})(?:\s+(?:o['’ ]?clock))?(?:\s+((?:oh\s+)?{NUM}))?({_AMPM})?\b")
_PAST_TO = re.compile(rf"\b(?:at\s+)?(half|(?:a\s+)?quarter|{NUM}(?:\s+minutes?)?)\s+(past|after|to|before|of)\s+({NUM})\b")


def _add_month(d: dt.date) -> dt.date:
    y, mo = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    for day in (d.day, 28):                                                    # (il 31 in un mese di 30 giorni: si scende)
        for dd in (day, day - 1, day - 2, day - 3):
            try:
                return dt.date(y, mo, dd)
            except ValueError:
                continue
    return dt.date(y, mo, 28)


def _hour_with_daypart(h: int, part: str | None, mer: str | None = None) -> int:
    if mer:
        mer = mer.replace(" ", "").replace(".", "")
        if mer.startswith("p") or "afternoon" in mer or "evening" in mer or "night" in mer:
            return h + 12 if h < 12 else h
        if mer.startswith("a") or "morning" in mer:
            return 0 if h == 12 else h
    if part in ("afternoon", "evening"):
        return h + 12 if h < 12 else h
    if part in ("night", "tonight"):
        return h + 12 if 6 <= h < 12 else (0 if h == 12 else h)
    if part == "morning":
        return 0 if h == 12 else h
    return h + 12 if 1 <= h <= 6 else h                   # senza indicazioni: «at 5» e' il pomeriggio


def _minutes(txt: str) -> int | None:
    t = re.sub(r"\bminutes?\b", "", txt).strip()
    if t in ("half",):
        return 30
    if t in ("quarter", "a quarter"):
        return 15
    t = re.sub(r"^oh\s+", "", t)
    return to_int(t)


def _delta_amount(txt: str) -> float | None:
    t = txt.strip()
    if t in ("a", "an", "one"):
        return 1
    return to_int(t)


def parse_when(raw: str, now: dt.datetime, default_hour: int = 9) -> When | None:
    f = fold(raw)
    spans: list[tuple[int, int]] = []

    # ---- relativo: «in two hours», «in 3 days», «in an hour and a half», «in half an hour», «in a quarter of an hour»
    m = re.search(rf"\bin\s+(half an? hour|a quarter of an hour|three quarters of an hour|({NUM})(?:\s+and\s+a\s+half)?\s+(minutes?|hours?|days?|weeks?))\b", f)
    if m:
        whole = m.group(1)
        if whole.startswith("half"):
            delta = dt.timedelta(minutes=30); unit = "hour"
        elif whole.startswith("a quarter"):
            delta = dt.timedelta(minutes=15); unit = "hour"
        elif whole.startswith("three quarters"):
            delta = dt.timedelta(minutes=45); unit = "hour"
        else:
            n = _delta_amount(m.group(2)) or 0
            unit = m.group(3)
            half = " and a half" in whole
            if unit.startswith("minute"):
                delta = dt.timedelta(minutes=n + (0.5 if half else 0))
            elif unit.startswith("hour"):
                delta = dt.timedelta(minutes=(n + (0.5 if half else 0)) * 60)
            elif unit.startswith("day"):
                delta = dt.timedelta(days=n + (0.5 if half else 0))
            else:
                delta = dt.timedelta(weeks=n)
        end = m.end()
        if unit.startswith("hour") and not whole.startswith(("half", "a quarter", "three")):
            tail = re.match(rf"\s+and\s+(a half|a quarter|three quarters|({NUM})\s+minutes?)\b", f[end:])
            if tail and "and a half" not in whole:                              # «in an hour and a half», «in 2 hours and 20 minutes»
                g = tail.group(1)
                delta += dt.timedelta(minutes=30 if g == "a half" else 15 if g == "a quarter" else 45 if g == "three quarters" else (to_int(tail.group(2)) or 0))
                end += tail.end()
        when = now + delta
        timed = unit.startswith(("minute", "hour"))
        if not timed:
            when = when.replace(hour=default_hour, minute=0, second=0, microsecond=0)
        spans.append((m.start(), end))
        tm = _TIME_DIGITS.search(f)                                              # «in two days at 6 pm»
        if tm and not timed:
            when = when.replace(hour=_hour_with_daypart(int(tm.group(1)), None, tm.group(3)), minute=int(tm.group(2) or 0))
            spans.append((tm.start(), tm.end()))
            timed = True
        return When(when.replace(second=0, microsecond=0), timed, True, _cut(raw, spans))

    # ---- giorno
    day: dt.date | None = None
    part_default: str | None = None
    for pat, fn in (
        (r"\bthe day after tomorrow\b|\bday after tomorrow\b", lambda m: now.date() + dt.timedelta(days=2)),
        (r"\btomorrow\b", lambda m: now.date() + dt.timedelta(days=1)),
        (r"\btonight\b", lambda m: now.date()),
        (r"\btoday\b", lambda m: now.date()),
        (r"\bthis (?:morning|afternoon|evening)\b", lambda m: now.date()),
        (r"\bnext week\b", lambda m: now.date() + dt.timedelta(days=7)),
        (r"\bnext month\b", lambda m: _add_month(now.date())),
        (r"\b(?:this|on the|at the) weekend\b", lambda m: now.date() + dt.timedelta(days=(5 - now.weekday()) % 7 or 7) if now.weekday() < 5 else now.date()),
    ):
        m = re.search(pat, f)
        if m:
            day = fn(m)
            word = m.group(0)
            part_default = "night" if "tonight" in word else word.split()[-1] if word.startswith("this ") else None
            spans.append((m.start(), m.end()))
            break
    if day is None:
        m = re.search(r"\b(?:(?:on|next|this|coming)\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", f)
        if m:
            delta = (_DAYS[m.group(1)] - now.weekday()) % 7 or 7
            day = now.date() + dt.timedelta(days=delta)
            spans.append((m.start(), m.end()))
    if day is None:
        m = re.search(rf"\b(?:on\s+)?(?:the\s+)?({_ORDINAL_RX})\s+of\s+({_MONTH_RX})(?:\s+(\d{{4}}))?\b|\b(?:on\s+)?({_MONTH_RX})\.?\s+(?:the\s+)?({_ORDINAL_RX})(?:,?\s+(\d{{4}}))?\b", f)
        if m:
            if m.group(1):
                d, mo, ystr = ordinal_value(m.group(1)), m.group(2), m.group(3)
            else:
                d, mo, ystr = ordinal_value(m.group(5)), m.group(4), m.group(6)
            mo = _MONTHS.get(mo) or _MON_ABBR.get(mo.rstrip("."))
            y = int(ystr) if ystr else now.year
            if d and mo:
                for _ in range(1 if ystr else 5):                               # (il 29 febbraio senza anno: il prossimo che esiste)
                    try:
                        cand = dt.date(y, mo, d)
                    except ValueError:
                        y += 1
                        continue
                    if not ystr and cand < now.date():
                        y += 1
                        continue
                    day = cand
                    spans.append((m.start(), m.end()))
                    break
    if day is None:
        m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", f)               # numeri: mese/giorno all'americana (se il primo e' oltre 12, e' il giorno)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            mo, d = (b, a) if a > 12 else (a, b)
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
        m = re.search(rf"\bon the ({_ORDINAL_RX})\b(?!\s+of)", f)
        d = ordinal_value(m.group(1)) if m else None
        if m and d and 1 <= d <= 31:
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
    early = _DAYPART.search(f)
    if part is None and early:
        part = early.group(1)                                                  # «tomorrow night at 10», «this evening at 6»: l'ora va letta con la parte della giornata
    amb = False                                                                # ora detta senza «am/pm» e senza parte della giornata: «at 7»
    hour = minute = None
    tm_found = None
    mpt = _PAST_TO.search(f)
    mer_in_time: str | None = None
    if mpt and to_int(mpt.group(3)) is not None and 1 <= (to_int(mpt.group(3)) or 0) <= 12:
        mins = _minutes(mpt.group(1))
        h = to_int(mpt.group(3))
        if mins is not None and 0 < mins < 60:
            tail = re.match(rf"({_AMPM})", f[mpt.end():])
            mer_in_time = tail.group(1) if tail else None
            base = _hour_with_daypart(h % 24, part, mer_in_time)
            if mpt.group(2) in ("past", "after"):
                hour, minute = base, mins
            else:
                hour, minute = (base - 1) % 24, 60 - mins
            spans.append((mpt.start(), mpt.end() + (tail.end() if tail else 0)))
            tm_found = mpt
    if hour is None:
        tm = _TIME_DIGITS.search(f)
        if tm:
            h = int(tm.group(1))
            suf = (tm.group(3) or "").strip()
            if 0 <= h <= 24 and not (h > 12 and suf in ("am", "pm", "a m", "p m", "a.m.", "p.m.")):
                minute = int(tm.group(2)) if tm.group(2) else 0
                mer = suf if suf and "clock" not in suf else None
                if not mer:
                    dpm = re.match(r"\s*(in the (?:morning|afternoon|evening)|at night)", f[tm.end():])
                    if dpm:
                        mer = dpm.group(1)
                        spans.append((tm.end(), tm.end() + dpm.end()))
                hour = _hour_with_daypart(h % 24 if h != 24 else 0, part, mer) if not (h >= 13) else h % 24
                amb = mer is None and part is None and 1 <= h <= 12
                spans.append((tm.start(), tm.end()))
                tm_found = tm
    if hour is None:
        tw = _TIME_WORDS.search(f)
        if tw:
            h = to_int(tw.group(1))
            if h is not None and 1 <= h <= 12:
                minute = 0
                if tw.group(2):
                    mm = _minutes(tw.group(2))
                    if mm is not None and 0 <= mm < 60 and not re.match(r"^(?:a|an)$", tw.group(2).strip()):
                        minute = mm
                    else:
                        tw = None
                if tw:
                    mer = (tw.group(3) or "").strip() or None
                    hour = _hour_with_daypart(h, part, mer)
                    amb = mer is None and part is None
                    spans.append((tw.start(), tw.end()))
                    tm_found = tw
    if hour is None:
        for word, (h, mi) in (("noon", (12, 0)), ("midday", (12, 0)), ("midnight", (0, 0))):
            m = re.search(rf"\b(?:(?:at|around|by)\s+)?{word}\b", f)
            if m:
                hour, minute = h, mi
                spans.append((m.start(), m.end()))
                tm_found = m
                break
    if hour is None:
        for pat, (h, mi) in ((r"\bafter lunch\b", (14, 0)), (r"\bafter dinner\b", (21, 0)), (r"\bbefore lunch\b", (12, 0)), (r"\bbefore dinner\b", (19, 0)),
                             (r"\bat lunch(?:time)?\b", (13, 0)), (r"\bat dinner(?:time)?\b", (20, 0)), (r"\blater (?:this )?afternoon\b", (16, 0)), (r"\blate (?:this )?evening\b", (22, 0))):
            m = re.search(pat, f)
            if m:
                hour, minute = h, mi
                spans.append((m.start(), m.end()))
                tm_found = m
                break
    if hour is None and part is None:
        ml = re.search(r"\blater(?: (?:today|on today|on|this day))?\b", f)                       # «later today»: fra un paio d'ore, a quarti d'ora; troppo tardi = domattina
        if ml and (day is None or day == now.date()):
            soon = now + dt.timedelta(hours=2, minutes=14)
            soon = soon.replace(minute=soon.minute - soon.minute % 15, second=0, microsecond=0)
            if soon.date() > now.date() or soon.hour >= 22:
                day, hour, minute = now.date() + dt.timedelta(days=1), 9, 0
            else:
                hour, minute = soon.hour, soon.minute
            spans.append((ml.start(), ml.end()))
            tm_found = ml
    dm = _DAYPART.search(f)
    if dm and not any(a <= dm.start() < b for a, b in spans):
        part = part or dm.group(1)
        spans.append((dm.start(), dm.end()))
    if day is None and hour is None and part is None:
        return None
    if hour is None:
        hour = {"morning": 9, "afternoon": 15, "evening": 19, "night": 22, "tonight": 22}.get(part or "", default_hour)
        minute = 0
    has_time = tm_found is not None
    target_day = day or now.date()
    when = dt.datetime.combine(target_day, dt.time(hour % 24, minute or 0))
    if day is None and when <= now:                                            # solo l'ora, gia' passata oggi: domani
        if amb and when.hour < 12 and when + dt.timedelta(hours=12) > now:     # «at 7» detto alle 14:30: sono le 19 di oggi, non le 7 di domani
            when += dt.timedelta(hours=12)
        else:
            when += dt.timedelta(days=1)
    elif part_default == "night" and when <= now and when.hour < 12:           # «tonight at 2» detto alle 22: e' la notte che viene
        when += dt.timedelta(days=1)
    return When(when, has_time, day is not None, _cut(raw, spans))


# ------------------------------------------------------------------------------- durate
def parse_duration(text: str) -> int | None:
    """'ten minutes' -> 600, 'an hour and a half' -> 5400, 'half an hour' -> 1800, '2 hours 30 minutes' -> 9000, '1h30' -> 5400, 'a quarter of an hour' -> 900."""
    raw = text.lower().replace("’", "'")
    raw = re.sub(r"(\d+)\.(\d+)\s*(?:hours?|hrs?|h)\b", lambda m: f"{round(float(m.group(1) + '.' + m.group(2)) * 60)} minutes", raw)        # «1.5 hours» -> 90 minutes
    raw = re.sub(r"(\d+)\s*(?:h|hr|hrs)\s*(\d+)\b(?!\s*(?:hours?|h))", r"\1 hours \2 minutes", raw)                                       # «1h30»
    raw = re.sub(r"(\d+)\s*(?:h|hr|hrs)\b", r"\1 hours", raw)
    raw = re.sub(r"(\d+)\s*(?:mins?|m|')(?![a-z])", r"\1 minutes", raw)
    raw = re.sub(r"(\d+)\s*(?:secs?|s)\b", r"\1 seconds", raw)
    t = re.sub(r"[^a-z0-9 ]+", " ", raw.replace("-", " "))
    t = re.sub(r"\s+", " ", t).strip()
    total, found = 0, False
    for rx, secs in ((r"\bthree quarters of an hour\b", 2700), (r"\ba quarter of an hour\b|\bquarter of an hour\b|\ba quarter hour\b", 900), (r"\bhalf an hour\b|\ba half hour\b|\bhalf hour\b", 1800)):
        if re.search(rx, t):
            total, found = total + secs, True
            t = re.sub(rx, " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    mult = {"second": 1, "seconds": 1, "sec": 1, "minute": 60, "minutes": 60, "min": 60, "hour": 3600, "hours": 3600}
    tokens = t.split()
    i, last_unit = 0, 0
    while i < len(tokens):
        # «one and a half hours», «two and a half minutes»
        if i + 4 < len(tokens) + 0 and tokens[i + 1:i + 4] == ["and", "a", "half"] and tokens[i + 4] in mult and to_int(tokens[i]) is not None:
            total += int((to_int(tokens[i]) + 0.5) * mult[tokens[i + 4]])
            last_unit, found, i = mult[tokens[i + 4]], True, i + 5
            continue
        n = None
        used = 1
        if tokens[i] in _TENS and i + 1 < len(tokens) and tokens[i + 1] in _ONES and 1 <= _ONES[tokens[i + 1]] <= 9:
            n, used = _TENS[tokens[i]] + _ONES[tokens[i + 1]], 2
        else:
            n = to_int(tokens[i])
        if n is not None and i + used < len(tokens) and tokens[i + used] in mult:
            total += n * mult[tokens[i + used]]
            last_unit, found, i = mult[tokens[i + used]], True, i + used + 1
            continue
        if tokens[i] == "and" and i + 2 < len(tokens) and tokens[i + 1] == "a" and tokens[i + 2] == "half" and last_unit:      # «an hour and a half»
            total += last_unit // 2
            found, i = True, i + 3
            continue
        if tokens[i] == "and" and i + 3 < len(tokens) + 0 and tokens[i + 1] == "a" and tokens[i + 2] == "quarter" and last_unit == 3600:
            total += 900
            found, i = True, i + 3
            continue
        if tokens[i] == "an" and i + 1 < len(tokens) and tokens[i + 1] in ("hour", "hours"):
            total += 3600
            last_unit, found, i = 3600, True, i + 2
            continue
        if tokens[i] in ("a",) and i + 1 < len(tokens) and tokens[i + 1] in ("minute", "second"):
            total += mult[tokens[i + 1]]
            last_unit, found, i = mult[tokens[i + 1]], True, i + 2
            continue
        i += 1
    return total if found and total > 0 else None
