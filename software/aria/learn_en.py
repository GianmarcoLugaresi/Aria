"""Impara dall'utente SOLO da quello che dice, con regole esplicite, in inglese. Gemello inglese di learn.py (stesse funzioni, stessi nomi).

Riconosce: il nome («my name is X», «call me X»), la citta' («I live in X», «I'm from X»), le correzioni («my name isn't X»), e fatti in prima persona
(famiglia, animali, lavoro, studio, salute, gusti, eta', impegni con data). Quando Aria ha appena chiesto «what's your name?» la risposta puo' essere anche solo «Mark» (expect=True).
"""
from __future__ import annotations

import datetime as dt
import re

from .learn import Fact, _title

_W = r"[A-Za-zÀ-ÖØ-öø-ÿ'’\-]"
_WORD = re.compile(rf"{_W}+")
_NOT_NAMES = {
    "a", "an", "the", "in", "on", "at", "of", "to", "from", "for", "with", "by", "here", "there", "hi", "hello", "hey", "well", "um", "uh", "ok", "okay", "yes", "no", "yeah", "nope",
    "fine", "good", "great", "bad", "tired", "happy", "sad", "ready", "back", "home", "bored", "busy", "hungry", "cold", "hot", "sick", "sorry", "thanks", "thank", "please", "aria",
    "just", "very", "so", "really", "not", "what", "who", "how", "where", "when", "why", "can", "could", "would", "should", "will", "going", "doing", "looking", "trying", "feeling",
    "still", "also", "already", "now", "today", "tomorrow", "tonight", "yesterday", "my", "me", "myself", "name", "is", "am", "are", "it", "its", "this", "that", "and", "or", "but",
    "i", "you", "he", "she", "we", "they", "something", "nothing", "everything", "anything", "someone", "nobody", "right", "wrong", "sure", "maybe", "perhaps", "stressed", "worried",
    "excited", "nervous", "angry", "alone", "late", "early", "done", "finished", "leaving", "coming", "working", "studying", "eating", "sleeping", "waiting", "calling", "talking", "asking",
}
_NOT_CITIES = _NOT_NAMES | {
    "work", "school", "university", "college", "office", "bed", "bedroom", "kitchen", "town", "city", "country", "countryside", "mountains", "suburbs", "downtown", "center", "centre",
    "apartment", "flat", "house", "dorm", "street", "road", "avenue", "neighborhood", "neighbourhood", "area", "region", "province", "state", "nowhere", "hurry", "trouble", "love",
    "charge", "control", "pain", "debt", "touch", "shape", "danger", "peace", "doubt", "mood", "front", "line", "place", "space", "order", "time", "person", "public", "private",
}
_GLUE = {"the", "a", "an", "of", "with", "for", "on", "in", "at", "to", "from", "by", "this", "that", "what", "how", "where", "when", "why", "thanks", "thank", "hi", "hello", "please", "my", "your"}
_COMMAND_VERBS = {"set", "put", "play", "open", "call", "text", "send", "turn", "tell", "give", "show", "find", "search", "look", "check", "remind", "write", "read", "stop", "start", "pause",
                  "go", "make", "create", "add", "remove", "delete", "cancel", "increase", "lower", "raise", "mute", "unmute", "repeat", "wait", "sorry", "help"}
_PARTICLES = {"of", "the", "de", "la", "le", "del", "di", "da", "van", "von", "upon", "on", "in", "sur", "under", "over"}
_DECLINE = re.compile(r"\b(?:i(?:'d| would) rather not|rather not|no thanks|no thank you|not now|maybe later|another time|some other time|i don(?:'t| t) (?:want to|wanna) (?:say|tell)|i prefer not to|never mind|forget it|skip it|let(?:'s| us) skip)\b", re.I)
_BREAK = {"and", "but", "so", "because", "since", "though", "although", "i", "i'm", "i've", "my", "we", "he", "she", "they", "then", "now", "right", "currently", "these", "days", "lately"}


def _take(rest: str, stop: set[str], limit: int, city: bool = False) -> str | None:
    """Prende fino a `limit` parole dall'inizio di `rest`, fermandosi alla prima congiunzione/pronome/punteggiatura o parola da scartare."""
    rest = re.split(r"[,.;:!?]", rest, maxsplit=1)[0]
    toks: list[str] = []
    for w in _WORD.findall(rest):
        w = w.strip("'’-")
        lw = w.lower()
        if not lw:
            continue
        if toks and lw in _BREAK:
            break
        particle = city and bool(toks) and lw in _PARTICLES
        if lw in stop and not particle:
            if toks:
                break
            return None
        toks.append(w)
        if len(toks) >= limit:
            break
    while toks and city and toks[-1].lower() in _PARTICLES:
        toks.pop()
    if not toks or len(toks[0]) < 2 or sum(len(t) for t in toks) > 40:
        return None
    return _title(toks, city)


# ------------------------------------------------------------------------------------ genere (solo se lo dice: «I'm a guy», «I'm a mom»)
_MALE = r"(?:man|guy|boy|male|father|dad|daddy|son|husband|boyfriend|student boy|grandfather|grandpa|brother|gentleman|dude|bloke)"
_FEMALE = r"(?:woman|girl|female|mother|mom|mum|mommy|mummy|daughter|wife|girlfriend|grandmother|grandma|sister|lady|gal)"
_GEND_NOUN = re.compile(rf"\bi(?:'m| am| m)\s+(?:a|an|the)\s+(?:\w+\s+)?({_MALE}|{_FEMALE})\b", re.I)


def parse_gender(text: str) -> str | None:
    t = (text or "").lower()
    m = _GEND_NOUN.search(t)
    if not m or re.search(r"\bnot\s+(?:a|an)\b", t[:m.start() + 12]):
        return None
    return "m" if re.fullmatch(_MALE, m.group(1)) else "f"


# ------------------------------------------------------------------------------------ nome
_NAME_PATTERNS = [
    re.compile(r"\bmy name(?:'s| is| s)\s+(.+)", re.I),
    re.compile(r"\b(?:call me|you can call me|you may call me|people call me|everyone calls me|friends call me|they call me)\s+(.+)", re.I),
    re.compile(r"\bi(?:'m| am) called\s+(.+)", re.I),
    re.compile(r"\bthe name(?:'s| is)\s+(.+)", re.I),
]
_NAME_FILLERS = re.compile(r"^(?:hi|hello|hey|well|um|uh|so|okay|ok|nice to meet you|pleasure|i(?:'m| am)|it(?:'s| is)|this is|my name is|call me|you can call me|name(?:'s| is)|aria|thanks|thank you|ah|oh)[\s,!.]+", re.I)


def parse_name(text: str, expect: bool = False) -> str | None:
    """Il nome che l'utente dice di avere. expect=True: Aria ha appena chiesto «what's your name?»: anche un «Mark» secco vale."""
    t = (text or "").strip()
    for pat in _NAME_PATTERNS:
        m = pat.search(t)
        if m:
            return _take(m.group(1), _NOT_NAMES, 2)
    if not expect or "?" in t or len(t.split()) > 7:
        return None
    for _ in range(4):
        n = _NAME_FILLERS.sub("", t, count=1)
        if n == t:
            break
        t = n
    if len(t.split()) > 3 or re.search(r"[,;:]", t.strip(" .!")):
        return None
    words = [w.lower() for w in _WORD.findall(t)]
    if words and (words[0] in _COMMAND_VERBS or any(w in _GLUE for w in words)):
        return None
    return _take(t, _NOT_NAMES, 2)


def parse_name_denial(text: str) -> str | None:
    m = re.search(r"\bmy name(?: is not|'s not| isn(?:'t| t)| is n't)\s+(.+)", text or "", re.I) or re.search(r"\bi(?:'m| am) not called\s+(.+)", text or "", re.I)
    return _take(m.group(1), _NOT_NAMES, 2) if m else None


# ------------------------------------------------------------------------------------ citta'
_CITY_PATTERNS = [
    re.compile(r"\bi (?:live|reside|stay|am living|(?:'m| m) living)\s+(?:in|at|near|around|outside of|just outside|close to)\s+(.+)", re.I),
    re.compile(r"\bi(?:'m| am| m) (?:from|based in|located in|living in)\s+(.+)", re.I),
    re.compile(r"\bi (?:moved|relocated)\s+(?:to)\s+(.+)", re.I),
    re.compile(r"\bi(?:'m| am| m) in\s+(?=[A-Z])(.+)"),
]
_CITY_FILLERS = re.compile(r"^(?:hi|hello|hey|well|um|uh|so|okay|ok|i(?:'m| am)|i live|i(?:'m| am) from|it(?:'s| is)|in|near|around|from|the city of|city of|the town of|town of|province of|area|aria|thanks)[\s,!.]+", re.I)


def parse_city(text: str, expect: bool = False) -> str | None:
    t = (text or "").strip()
    for pat in _CITY_PATTERNS:
        m = pat.search(t)
        if m:
            return _take(m.group(1), _NOT_CITIES, 4, city=True)
    if not expect or "?" in t or len(t.split()) > 8:
        return None
    for _ in range(5):
        n = _CITY_FILLERS.sub("", t, count=1)
        if n == t:
            break
        t = n
    return _take(t, _NOT_CITIES, 4, city=True)


def parse_city_denial(text: str) -> str | None:
    m = re.search(r"\bi(?:'m| am| m)? ?(?:do not|don(?:'t| t)|not)\s+(?:live in|from|in)\s+(.+)", text or "", re.I)
    return _take(m.group(1), _NOT_CITIES, 4, city=True) if m else None


def is_decline(text: str) -> bool:
    return bool(_DECLINE.search(text or ""))


# ------------------------------------------------------------------------------------ fatti
_REL = r"(?:dog|cat|puppy|kitten|son|daughter|kids?|children|brother|sister|boyfriend|girlfriend|wife|husband|partner|nephew|niece|parrot|rabbit|hamster|horse|fish|turtle|bird)"
_DAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_WHEN = r"(today|tonight|tomorrow|the day after tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_VERBS = {"i have": "Has", "i've got": "Has", "i need to": "Needs to", "i have to": "Has to", "i'm going to": "Is going to", "i am going to": "Is going to", "i'm leaving for": "Is leaving for",
          "i'm meeting": "Is meeting", "i am meeting": "Is meeting", "i start": "Starts", "i'm starting": "Is starting", "i'm flying": "Is flying", "i'm seeing": "Is seeing", "i am seeing": "Is seeing",
          "i'm visiting": "Is visiting", "i'm having": "Is having", "i'm taking": "Is taking"}
_VERB_RX = "|".join(sorted((re.escape(k) for k in _VERBS), key=len, reverse=True))
_EV1 = re.compile(rf"\b{_WHEN}(?:\s+(?:morning|afternoon|evening|night))?[\s,]+({_VERB_RX})\s+(.{{3,80}})", re.I)
_EV2 = re.compile(rf"\b({_VERB_RX})\s+(.{{3,70}}?)\s+{_WHEN}\b", re.I)


def _day_of(word: str, now: dt.datetime) -> dt.date:
    w = word.lower()
    if w in ("today", "tonight"):
        return now.date()
    if w == "tomorrow":
        return now.date() + dt.timedelta(days=1)
    if w == "the day after tomorrow":
        return now.date() + dt.timedelta(days=2)
    delta = (_DAYS[w] - now.weekday()) % 7
    return now.date() + dt.timedelta(days=delta or 7)


def _clean(s: str, n: int = 80) -> str:
    return re.split(r"[.;!?,]|\s+(?:and|but)\s+(?:i|my|we)\b", s, maxsplit=1, flags=re.I)[0].strip(" '’")[:n].strip()


def extract(text: str, now: dt.datetime | None = None) -> list[Fact]:
    """Fatti che l'utente ha detto di se' (in terza persona e senza indovinare il genere: «Has a dog», «Likes coffee»)."""
    now = now or dt.datetime.now()
    t = (text or "").strip()
    if not t or "?" in t or len(t) > 300:
        return []
    out: list[Fact] = []

    def add(txt: str, imp: int = 3, kind: str = "fatto", due: float | None = None) -> None:
        txt = re.sub(r"\s+", " ", txt).strip()
        if 6 <= len(txt) <= 140 and txt not in [f.text for f in out]:
            out.append(Fact(txt[0].upper() + txt[1:], imp, kind, due))

    for m in re.finditer(r"\bi (?:don't|do not|never) drink(?: any)?\s+(alcohol|wine|beer|coffee|soda|milk)\b", t, re.I):
        add(f"Doesn't drink {m.group(1).lower()}", 4)
    for m in re.finditer(r"\bi(?:'m| am) allergic to\s+([^.,;!?]+)", t, re.I):
        add(f"Allergic to {_clean(m.group(1), 50)}", 5)
    for m in re.finditer(r"\bi have\s+(?:the\s+)?(diabetes|asthma|celiac disease|epilepsy|high blood pressure|migraines?|hypertension)\b", t, re.I):
        add(f"Has {m.group(1).lower()}", 5)
    for m in re.finditer(rf"\bi have\s+(a|an|one|two|three|four)\s+({_REL})(?:\s+(?:named|called)\s+({_W}+))?", t, re.I):
        n = m.group(1).lower()
        add(f"Has {n} {m.group(2).lower()}" + (f" named {m.group(3).capitalize()}" if m.group(3) else ""), 4)
    for m in re.finditer(rf"\bmy\s+({_REL}|mother|mom|mum|father|dad|grandma|grandpa|grandmother|grandfather|aunt|uncle|cousin)\s+(?:is|'s)\s+(?:named|called)\s+({_W}+)", t, re.I):
        if m.group(2).lower() not in _NOT_NAMES:
            add(f"Their {m.group(1).lower()} is called {m.group(2).capitalize()}", 4)
    for m in re.finditer(r"\bi(?:'m| am)\s+(\d{1,3})(?:\s+years? old)?\b(?!\s*(?:percent|%|miles|minutes|km))", t, re.I):
        if 3 <= int(m.group(1)) <= 110 and re.search(r"years? old", t, re.I):
            add(f"Is {m.group(1)} years old (said on {_MONTHS[now.month - 1]} {now.day}, {now.year})", 3)
    for m in re.finditer(r"\bmy birthday(?:'s| is)\s+(?:on\s+)?([^.,;!?]{3,25})", t, re.I):
        add(f"Their birthday is {_clean(m.group(1), 25)}", 4)
    for m in re.finditer(r"\bi work\s+(as|at|for|in|with)\s+([^.,;!?]{3,60})", t, re.I):
        add(f"Works {m.group(1).lower()} {_clean(m.group(2), 60)}", 4)
    for m in re.finditer(r"\bi(?:'m| am)\s+(?:a|an)\s+(student|teacher|nurse|doctor|engineer|developer|designer|lawyer|writer|artist|musician|chef|accountant|electrician|plumber|driver|manager|consultant|researcher|freelancer)\b", t, re.I):
        add(f"Is a {m.group(1).lower()}", 4)
    for m in re.finditer(r"\bi (?:study|am studying|'m studying)\s+([^.,;!?]{3,50})", t, re.I):
        add(f"Studies {_clean(m.group(1), 50)}", 4)
    for m in re.finditer(r"\bi(?:'m| am)\s+(studying|preparing for|working on|building|writing|looking for|learning|organizing|planning)\s+([^.,;!?]{3,60})", t, re.I):
        verb = m.group(1).lower()
        add(f"Is {verb} {_clean(m.group(2), 60)}", 3)
    _diet = {"vegetarian": "Is vegetarian", "vegan": "Is vegan", "celiac": "Is celiac", "diabetic": "Is diabetic", "lactose intolerant": "Is lactose intolerant", "gluten free": "Eats gluten free"}
    for m in re.finditer(r"\bi(?:'m| am)\s+(vegetarian|vegan|celiac|diabetic|lactose intolerant|gluten[- ]free)\b", t, re.I):
        add(_diet[m.group(1).lower().replace("-", " ")], 4)
    for m in re.finditer(r"\bi(?:'m| am)\s+(?:afraid|scared|terrified)\s+of\s+([^.,;!?]{3,40})", t, re.I):
        add(f"Is afraid of {_clean(m.group(1), 40)}", 3)
    for m in re.finditer(r"\b(i had a fight with|i argued with|i broke up with|i lost)\s+([^.,;!?]{3,50})", t, re.I):
        what = {"i had a fight with": "Had a fight with", "i argued with": "Argued with", "i broke up with": "Broke up with", "i lost": "Lost"}[m.group(1).lower()]
        rest = re.sub(r"\bmy\b", "their", _clean(m.group(2), 50), flags=re.I)
        add(f"{what} {rest} (said on {_MONTHS[now.month - 1]} {now.day})", 4)
    for m in re.finditer(r"\bi (love|adore|really like|like|hate|can't stand|can not stand|dislike)\s+([^.,;!?]{3,50})", t, re.I):
        verb = {"love": "Loves", "adore": "Adores", "really like": "Likes", "like": "Likes", "hate": "Hates", "can't stand": "Can't stand", "can not stand": "Can't stand", "dislike": "Dislikes"}[m.group(1).lower()]
        add(f"{verb} {_clean(m.group(2), 50)}", 2 if verb in ("Likes", "Dislikes") else 3)
    for m in list(_EV1.finditer(t)) + [x for x in _EV2.finditer(t)]:
        if m.re is _EV1:
            when, verb, rest = m.group(1), m.group(2), m.group(3)
        else:
            verb, rest, when = m.group(1), m.group(2), m.group(3)
        rest = re.sub(r"\s+(?:on|at|in|for|by|the|a|an|this|next|of|to)$", "", _clean(rest, 70), flags=re.I)         # «a dentist appointment on» (il giorno e' stato tolto): niente preposizione in coda
        if len(rest) < 3 or rest.lower().split()[0] in {"hungry", "tired", "sleepy", "cold", "hot", "fear", "time", "to", "no", "nothing"}:
            continue
        day = _day_of(when, now)
        due = dt.datetime.combine(day, dt.time(23, 59, 59)).timestamp()
        label = f"{_WEEK[day.weekday()]}, {_MONTHS[day.month - 1]} {day.day}"
        add(f"{label}: {_VERBS[verb.lower()]} {rest}", 3, "evento", due)
    return out
