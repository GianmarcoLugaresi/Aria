"""Impara dall'utente SOLO da quello che dice, con regole esplicite (nessun modello): niente fatti inventati.

Riconosce: il nome ("mi chiamo X"), la citta' ("abito a X", "sono di X"), le correzioni ("non mi chiamo X"),
e fatti in prima persona (famiglia, animali, lavoro, studio, salute, gusti, eta', impegni con data).
Quando Aria ha appena fatto una domanda ("come ti chiami?") la risposta puo' essere anche solo "Mario" (expect=True).
Le parole sono quelle dette dall'utente, quindi un errore di dettatura resta un errore di dettatura: per questo Aria ripete sempre quello
che ha capito ("Piacere, Mario!") e basta una correzione ("no, mi chiamo...") per aggiustarlo.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

_W = r"[A-Za-zÀ-ÖØ-öø-ÿ'’]"
_WORD = re.compile(rf"{_W}+")
_NOT_NAMES = {
    "un", "una", "uno", "il", "lo", "la", "i", "gli", "le", "a", "in", "di", "da", "su", "con", "per", "qui", "qua", "ciao", "allora", "beh", "ehm", "mh", "ok",
    "bene", "male", "stanco", "stanca", "felice", "contento", "contenta", "triste", "tranquillo", "tranquilla", "pronto", "pronta", "qui", "casa",
    "io", "tu", "lui", "lei", "che", "come", "cosa", "chi", "dove", "quando", "perché", "perche", "non", "sì", "si", "no", "grazie", "scusa", "aria",
    "mio", "mia", "nome", "piacere", "dunque", "poi", "e", "o", "ma", "se", "sono", "ho", "faccio", "vado", "sto", "arrivo", "ancora", "già", "gia",
    "niente", "nulla", "tutto", "tanto", "molto", "poco", "solo", "anche", "ora", "adesso", "oggi", "domani", "ieri", "stasera", "boh",
    "era", "ero", "hai", "ha", "abbiamo", "stavo", "studiavo", "faccio", "fai", "fa", "vai", "va", "e", "è", "sei", "siamo", "state", "stato", "stata", "fatto", "detto",
}
_NOT_CITIES = _NOT_NAMES | {
    "fretta", "buon", "cattivo", "umore", "turno", "guardia", "nuovo", "nuova", "passaggio", "parola", "corsa", "ritorno", "pessimo", "ottimo",
    "lavoro", "scuola", "ufficio", "camera", "letto", "campo", "strada", "viaggio", "vacanza", "ferie", "riunione", "palestra", "mezzo", "parte",
    "centro", "periferia", "campagna", "montagna", "collina", "paese", "paesino", "appartamento", "affitto", "zona", "provincia", "regione",
    "quartiere", "condominio", "villetta", "mansarda", "albergo", "hotel", "italia", "europa", "via", "piazza", "corso", "viale",      # «abito in centro», «vivo in Italia»: non sono la città per il meteo
}
_GLUE = {"della", "delle", "dello", "degli", "dei", "del", "nel", "nella", "nello", "con", "per", "su", "sul", "sulla", "tra", "fra", "alle", "alla", "allo", "agli", "ai", "dal", "dalla", "dai", "dalle",
         "mi", "ti", "ci", "vi", "lo", "la", "gli", "le", "un", "una", "uno", "che", "non", "cosa", "come", "dove", "quando", "perche", "grazie", "ciao"}
_COMMAND_VERBS = {"metti", "mettimi", "imposta", "crea", "creami", "aggiungi", "segna", "apri", "aprimi", "cerca", "cercami", "alza", "abbassa", "ferma", "riprendi", "suona", "ricordami", "scrivi", "scrivimi",
                  "leggi", "leggimi", "dimmi", "dammi", "fammi", "fai", "prova", "vai", "chiama", "manda", "accendi", "spegni", "togli", "cancella", "elimina", "cambia", "dimentica", "ricorda", "ricordati", "salva",
                  "mostrami", "portami", "avvia", "lancia", "attiva", "disattiva", "silenzia", "muta", "stop", "basta", "zitta", "ripeti", "aspetta", "scusa"}
_PARTICLES = {"di", "del", "della", "dei", "delle", "dello", "in", "sul", "sulla", "sull", "la", "le", "lo", "d", "al", "alla", "all", "e"}
_DECLINE = re.compile(r"\b(non (?:mi va|importa|voglio|ti (?:dico|voglio dire)|è importante)|preferisco (?:di )?non|no grazie|un['’]?altra volta|dopo|lascia perdere|non adesso)\b", re.I)


def _title(tokens: list[str], city: bool = False) -> str:
    out = []
    for i, t in enumerate(tokens):
        low = t.lower()
        out.append(low if (city and i > 0 and low in _PARTICLES) else (low[:1].upper() + low[1:]))
    return " ".join(out)


_BREAK = {"e", "ma", "però", "pero", "quindi", "perché", "perche", "ho", "sono", "abito", "vivo", "lavoro", "studio", "da", "che", "poi", "mi", "ti", "ora", "adesso"}


def _take(rest: str, stop: set[str], limit: int, city: bool = False) -> str | None:
    """Prende fino a `limit` parole dall'inizio di `rest`, fermandosi alla prima congiunzione/verbo/punteggiatura o parola da scartare."""
    rest = re.split(r"[,.;:!?]", rest, maxsplit=1)[0]
    toks: list[str] = []
    for w in _WORD.findall(rest):
        w = w.strip("'’")
        lw = w.lower()
        if not lw:
            continue
        if toks and lw in _BREAK:
            break
        particle = city and bool(toks) and lw in _PARTICLES            # "San Giovanni in Persiceto"
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


# ------------------------------------------------------------------------------------ genere (da come parla di se')
_GEND_STEMS = ("stanc", "content", "sicur", "nervos", "preoccupat", "agitat", "stuf", "arrabbiat", "emozionat", "pront", "sol", "liber", "brav", "tranquill", "innamorat",
               "occupat", "stressat", "annoiat", "andat", "stat", "uscit", "tornat", "arrivat", "rimast", "nat", "cresciut", "sposat", "convint", "dispiaciut", "affamat",
               "pigr", "curios", "orgogliós", "soddisfatt", "sfinit", "distrutt", "esaust", "malat", "guarit", "fortunat", "contrari", "sveglio", "sveglia", "demoralizzat", "gasat",
               "teso", "tesa", "abituat", "capit", "riuscit", "partit", "caduto", "cadut", "svegliat", "salvat", "perso", "persa", "lasciat", "ferit", "invecchiat")
_GEND_SELF = re.compile(r"\b(?:non\s+)?(?:sono|mi sento|ero|sarei|sarò|mi sono sentit[oa]|sono stat[oa])\s+(?:(?:molto|tanto|proprio|davvero|un po['’]?|troppo|abbastanza|piuttosto|così|cosi|sempre|ancora|già|gia)\s+)?([a-zà-ù]+)\b", re.I)
_GEND_NOUN = re.compile(r"\bsono\s+(?:un|uno)\s+(?:ragazzo|uomo|maschio|padre|papà|figlio|studente|marito|fidanzato|nonno|fratello|signore)\b|\bsono\s+(?:una)\s+(?:ragazza|donna|femmina|madre|mamma|figlia|studentessa|moglie|fidanzata|nonna|sorella|signora)\b", re.I)


def parse_gender(text: str) -> str | None:
    """'m' o 'f' se l'utente lo lascia capire parlando di se' («sono stanca», «sono un ragazzo»); altrimenti None. Mai indovinato dal nome."""
    t = (text or "").lower()
    m = _GEND_NOUN.search(t)
    if m and not re.search(r"\bnon\s+sono", m.group(0)):
        return "f" if re.search(r"\b(?:una)\b", m.group(0)) else "m"
    for m in _GEND_SELF.finditer(t):
        if m.group(0).lstrip().startswith("non"):
            continue
        w = re.sub(r"issim([oa])$", r"\1", m.group(1))                             # stanchissima -> stanca
        if w.endswith(("o", "a")) and any(w.startswith(st) and len(w) <= len(st) + 3 for st in _GEND_STEMS) and w not in {"sola", "solo"} | set():
            return "m" if w.endswith("o") else "f"
        if w in ("sola", "solo"):
            return "m" if w.endswith("o") else "f"
    return None


# ------------------------------------------------------------------------------------ nome
_NAME_PATTERNS = [
    re.compile(r"\bmi chiamo\s+(.+)", re.I),
    re.compile(r"\bil mio nome (?:è|e)\s+(.+)", re.I),
    re.compile(r"\b(?:chiamami|puoi chiamarmi|mi puoi chiamare|mi chiamano|chiamatemi)\s+(.+)", re.I),
]
_NAME_FILLERS = re.compile(r"^(?:ciao|allora|beh|ehm|mh|dunque|piacere|io|sono|mi chiamo|il mio nome è|il mio nome e|mi puoi chiamare|puoi chiamarmi|chiamami|aria|grazie|ah)[\s,!.]+", re.I)


def parse_name(text: str, expect: bool = False) -> str | None:
    """Il nome che l'utente dice di avere. expect=True: Aria ha appena chiesto 'come ti chiami?': anche un 'Mario' secco vale."""
    t = (text or "").strip()
    for pat in _NAME_PATTERNS:
        m = pat.search(t)
        if m:
            return _take(m.group(1), _NOT_NAMES, 2)
    if not expect or "?" in t or len(t.split()) > 7:
        return None
    for _ in range(4):                                       # toglie i riempitivi iniziali ("allora, io sono ...")
        n = _NAME_FILLERS.sub("", t, count=1)
        if n == t:
            break
        t = n
    if len(t.split()) > 3 or re.search(r"[,;:]", t.strip(" .!")):          # un nome detto cosi' e' una o due parole: «Era analisi due, studiavo da un mese» no
        return None
    words = [w.lower() for w in _WORD.findall(t)]
    if words and (words[0] in _COMMAND_VERBS or any(w in _GLUE for w in words)):    # «metti della musica» non e' un nome
        return None
    return _take(t, _NOT_NAMES, 2)


def parse_name_denial(text: str) -> str | None:
    m = re.search(r"\bnon mi chiamo\s+(.+)", text or "", re.I)
    return _take(m.group(1), _NOT_NAMES, 2) if m else None


# ------------------------------------------------------------------------------------ citta'
_CITY_PATTERNS = [
    re.compile(r"\b(?:abito|vivo|risiedo|sto a vivere)\s+(?:a|ad|in|vicino a|nei pressi di|nella zona di|a poca distanza da)\s+(.+)", re.I),
    re.compile(r"\bsono di\s+(.+)", re.I),
    re.compile(r"\bmi sono trasferit[oa]\s+(?:a|ad|in)\s+(.+)", re.I),
]
_CITY_FILLERS = re.compile(r"^(?:ciao|allora|beh|ehm|mh|dunque|io|abito|vivo|sono|di|a|ad|in|da|vicino|nei pressi di|vicino a|sto|a vivere|dalle parti di|dalle parti|della zona di|zona|città|citta|la città di|la citta di|provincia di)[\s,!.]+", re.I)


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
    m = re.search(r"\bnon (?:abito|vivo|sono)\s+(?:a|ad|in|di)\s+(.+)", text or "", re.I)
    return _take(m.group(1), _NOT_CITIES, 4, city=True) if m else None


def is_decline(text: str) -> bool:
    return bool(_DECLINE.search(text or ""))


# ------------------------------------------------------------------------------------ fatti
@dataclass
class Fact:
    text: str
    importance: int = 3
    kind: str = "fatto"
    due: float | None = None


_REL = r"(?:cane|gatto|gatta|cagnolino|figli[oa]|figli|fratell[oi]|sorell[ae]|ragazz[oa]|fidanzat[oa]|moglie|marito|compagn[oa]|nipot[ei]|pappagallo|coniglio|criceto|cavallo)"
_DAYS = {"lunedì": 0, "lunedi": 0, "martedì": 1, "martedi": 1, "mercoledì": 2, "mercoledi": 2, "giovedì": 3, "giovedi": 3, "venerdì": 4, "venerdi": 4, "sabato": 5, "domenica": 6}
_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
_WHEN = r"(oggi|stasera|stanotte|domani|dopodomani|lunedì|lunedi|martedì|martedi|mercoledì|mercoledi|giovedì|giovedi|venerdì|venerdi|sabato|domenica)"
_VERBS = {"ho": "ha", "devo": "deve", "vado": "va", "parto": "parte", "esco": "esce", "faccio": "fa", "comincio": "comincia", "inizio": "inizia",
          "torno": "torna", "incontro": "incontra", "ho l'": "ha l'"}
_EV1 = re.compile(rf"\b{_WHEN}(?:\s+(?:mattina|pomeriggio|sera|notte))?[\s,]+(?:io\s+)?(ho|devo|vado|parto|esco|faccio|comincio|inizio|torno|incontro)\s+(.{{3,80}})", re.I)
_EV2 = re.compile(rf"\b(ho|devo|vado|parto|esco|faccio|comincio|inizio|torno|incontro)\s+(.{{3,70}}?)\s+{_WHEN}\b", re.I)


def _day_of(word: str, now: dt.datetime) -> dt.date:
    w = word.lower()
    if w in ("oggi", "stasera", "stanotte"):
        return now.date()
    if w == "domani":
        return now.date() + dt.timedelta(days=1)
    if w == "dopodomani":
        return now.date() + dt.timedelta(days=2)
    delta = (_DAYS[w] - now.weekday()) % 7
    return now.date() + dt.timedelta(days=delta or 7)


def _clean(s: str, n: int = 80) -> str:
    return re.split(r"[.;!?,]", s, maxsplit=1)[0].strip(" '’")[:n].strip()


def extract(text: str, now: dt.datetime | None = None) -> list[Fact]:
    """Fatti che l'utente ha detto di se' (in terza persona e senza indovinare il genere: 'Ha un cane', 'Apprezza il caffè')."""
    now = now or dt.datetime.now()
    t = (text or "").strip()
    if not t or "?" in t or len(t) > 300:
        return []
    out: list[Fact] = []

    def add(txt: str, imp: int = 3, kind: str = "fatto", due: float | None = None) -> None:
        txt = re.sub(r"\s+", " ", txt).strip()
        if 6 <= len(txt) <= 140 and txt not in [f.text for f in out]:
            out.append(Fact(txt[0].upper() + txt[1:], imp, kind, due))

    for m in re.finditer(r"\bsono allergic[oa]\s+(?:a|ai|alle|al|agli|alla|allo)\s+(.+)", t, re.I):
        add(f"Allergia: {_clean(m.group(1), 50)}", 5)
    for m in re.finditer(r"\bho\s+(?:il|la|l['’])\s*(diabete|asma|celiachia|epilessia|ipertensione|emicrania)\b", t, re.I):
        add(f"Ha {m.group(1).lower()}", 5)
    for m in re.finditer(rf"\bho\s+(un|una|due|tre|quattro)\s+({_REL})(?:\s+che si chiama\s+({_W}+))?", t, re.I):
        add(f"Ha {m.group(1).lower()} {m.group(2).lower()}" + (f" che si chiama {m.group(3).capitalize()}" if m.group(3) else ""), 4)
    for m in re.finditer(rf"\b(?:mio|mia)\s+({_REL}|madre|mamma|padre|papà|nonn[oa]|zi[oa]|cugin[oa])\s+si chiama\s+({_W}+)", t, re.I):
        if m.group(2).lower() not in _NOT_NAMES:
            add(f"Suo/sua {m.group(1).lower()} si chiama {m.group(2).capitalize()}", 4)
    for m in re.finditer(r"\bho\s+(\d{1,3})\s+anni\b", t, re.I):
        if 3 <= int(m.group(1)) <= 110:
            add(f"Ha {m.group(1)} anni (detto il {now.day} {_MESI[now.month - 1]} {now.year})", 3)
    for m in re.finditer(r"\bil mio compleanno (?:è|e)\s+(?:il\s+)?(.{3,25})", t, re.I):
        add(f"Il suo compleanno è il {_clean(m.group(1), 25)}", 4)
    for m in re.finditer(r"\blavoro\s+(come|da|in|per|nel|nella|alla|al)\s+(.{3,60})", t, re.I):
        add(f"Lavora {m.group(1).lower()} {_clean(m.group(2), 60)}", 4)
    for m in re.finditer(r"\b(?:studio|frequento)\s+(.{3,50})", t, re.I):
        add(f"Studia {_clean(m.group(1), 50)}", 4)
    for m in re.finditer(r"\bsto\s+(studiando|preparando|lavorando a|lavorando su|costruendo|scrivendo|cercando|imparando|organizzando)\s+(.{3,60})", t, re.I):
        verb = {"studiando": "Sta studiando", "preparando": "Sta preparando", "lavorando a": "Sta lavorando a", "lavorando su": "Sta lavorando su", "costruendo": "Sta costruendo",
                "scrivendo": "Sta scrivendo", "cercando": "Sta cercando", "imparando": "Sta imparando", "organizzando": "Sta organizzando"}[m.group(1).lower()]
        add(f"{verb} {_clean(m.group(2), 60)}", 3)
    _diet = {"vegetarian": "Mangia vegetariano", "vegan": "È vegano", "celiac": "È celiaco", "diabetic": "È diabetico", "astemi": "Non beve alcol"}
    for m in re.finditer(r"\bsono\s+(vegetarian|vegan|celiac|diabetic|astemi)[oa]\b", t, re.I):
        add(_diet[m.group(1).lower()], 4)
    for m in re.finditer(r"\bsono\s+intollerante\s+(?:al|alla|ai|alle)\s+(.{3,30})", t, re.I):
        add(f"È intollerante: {_clean(m.group(1), 30)}", 5)
    for m in re.finditer(r"\bho paura\s+(di|dei|delle|degli|del|della|dello)\s+(.{3,40})", t, re.I):
        add(f"Ha paura {m.group(1).lower()} {_clean(m.group(2), 40)}", 3)
    for m in re.finditer(r"\b(ho litigato con|ho discusso con|mi sono lasciat[oa] con|ho perso)\s+(.{3,50})", t, re.I):
        what = {"ho litigato con": "Ha litigato con", "ho discusso con": "Ha discusso con", "ho perso": "Ha perso"}.get(m.group(1).lower(), "Si è lasciato/a con")
        rest = re.sub(r"\bmiei\b", "suoi", re.sub(r"\bmie\b", "sue", re.sub(r"\bmia\b", "sua", re.sub(r"\bmio\b", "suo", _clean(m.group(2), 50)))))
        add(f"{what} {rest} (detto il {now.day} {_MESI[now.month - 1]})", 4)
    for m in re.finditer(r"\b(adoro|amo|odio|detesto)\s+(.{3,50})", t, re.I):
        verb = {"adoro": "Adora", "amo": "Ama", "odio": "Odia", "detesto": "Detesta"}[m.group(1).lower()]
        add(f"{verb} {_clean(m.group(2), 50)}", 3)
    for m in re.finditer(r"\bnon mi piace(?:no)?\s+(.{3,50})", t, re.I):
        add(f"Non apprezza {_clean(m.group(1), 50)}", 2)
    for m in re.finditer(r"(?<!non )\bmi piace(?:no)?\s+(.{3,50})", t, re.I):
        add(f"Apprezza {_clean(m.group(1), 50)}", 2)

    for m in list(_EV1.finditer(t)) + [x for x in _EV2.finditer(t)]:
        if m.re is _EV1:
            when, verb, rest = m.group(1), m.group(2), m.group(3)
        else:
            verb, rest, when = m.group(1), m.group(2), m.group(3)
        rest = _clean(rest, 70)
        if len(rest) < 3 or rest.lower().split()[0] in {"fame", "sonno", "freddo", "caldo", "paura", "voglia", "bisogno", "fretta"}:
            continue
        day = _day_of(when, now)
        due = dt.datetime.combine(day, dt.time(23, 59, 59)).timestamp()
        label = f"{_GIORNI[day.weekday()]} {day.day} {_MESI[day.month - 1]}"
        add(f"{label[0].upper() + label[1:]}: {_VERBS[verb.lower()]} {rest}", 3, "evento", due)
    return out
