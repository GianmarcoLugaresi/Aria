"""La voce ha detto davvero tutta la frase? Pocket TTS a volte la taglia (l'ultima parola o le ultime due: «domani alle nove» -> «domani»).
Il riconoscimento integrato nel Mac (0,1 s a frase, nessuna RAM in piu') riascolta quello che e' appena uscito: se manca la fine, la frase si rifa'."""
from __future__ import annotations

import difflib
import re

from . import i18n
from .speech import num_words
from .textutil import normalize

_FILLERS = {"ah", "beh", "eh", "mmh", "mmm", "mm", "oh", "boh", "uhm", "ehm", "ehi", "ahah", "ahaha", "uh", "eeh", "ahh", "ooh", "mah", "uff", "wow",
             "um", "umm", "hmm", "hm", "mhm", "erm", "er", "huh", "aw", "aww"}


def _tokens(text: str, name: str | None = None) -> list[str]:
    t = normalize(text)
    t = re.sub(r"\b(\d{1,6})\b", lambda m: " " + num_words(int(m.group(1))) + " ", t)           # «alle 9» -> «alle nove», come le dice speechify
    toks = [w for w in t.split() if w and w not in _FILLERS]
    if name:
        n = normalize(name)
        toks = [w for w in toks if w != n]
    return toks


def _near(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.78


def _found(w: str, pool: list[str]) -> bool:
    return any(_near(w, h) for h in pool)


def score(expected: str, heard: str, name: str | None = None) -> tuple[bool, float, list[str]]:
    """(tutto ok?, punteggio 0..1, parole che mancano alla fine). Si guarda soprattutto la CODA: e' li' che la voce taglia."""
    exp, got = _tokens(expected, name), _tokens(heard, name)
    content = [w for w in exp if len(w) >= 3]
    if len(content) < 2:
        return True, 1.0, []                                              # troppo corta per giudicare
    recall = sum(1 for w in content if _found(w, got)) / len(content)
    tail = content[-1:]                                                 # solo l'ULTIMA parola: il riconoscimento salta spesso le piccole («tua», «la») a meta' frase
    pool = got[-(len(tail) + 3):]
    missing_tail = [w for w in tail if not _found(w, pool)]
    ok = recall >= 0.8 and not missing_tail
    return ok, round(recall - 0.3 * len(missing_tail), 3), missing_tail


_BREAK_EN = {"and", "that", "but", "because", "so", "then", "with", "for", "if", "when", "while", "where", "how", "also", "or", "without", "until", "which", "who", "to", "of", "in", "on", "at", "as", "since", "though", "although"}
_BREAK = {"e", "che", "ma", "perché", "perche", "quindi", "poi", "così", "cosi", "con", "per", "se", "quando", "mentre", "dove", "come", "finché", "finche", "anche", "oppure", "senza", "fino"}


def split_long(text: str, maxc: int = 52) -> list[str]:
    """Pocket TTS taglia e mangia le parole nelle frasi lunghe (misurato: 11 frasi su 16 da 90-120 caratteri uscivano tagliate; i pezzi sotto i ~55 caratteri no). Si spezza dove si
    respirerebbe: alla virgola, o prima di una congiunzione/preposizione, cercando pezzi di lunghezza simile. I pezzi in mezzo finiscono con la virgola (il tono resta «sospeso»)."""
    words = text.split()
    if len(text) <= maxc * 1.25 or len(words) < 6:                    # poco sopra il limite non si spezza: meglio una frase intera che due pezzi a caso
        return [text]
    best, best_cost, cum = None, 1e9, 0
    for i in range(2, len(words) - 1):
        cum = len(" ".join(words[:i]))
        strong = words[i - 1][-1:] in ",;:.!?…"
        if not strong and words[i].lower().strip(",;:") not in (_BREAK_EN if i18n.is_en() else _BREAK):
            continue
        cost = abs(cum - (len(text) - cum)) + (0 if strong else 14)
        if cost < best_cost:
            best, best_cost = i, cost
    if best is None:
        if len(text) <= maxc * 1.6:
            return [text]
        best = len(words) // 2
    a, b = " ".join(words[:best]), " ".join(words[best:])
    if a[-1:].isalnum() or a[-1:] in "»\"')":
        a += ","
    return split_long(a, maxc) + split_long(b, maxc)


def split_sentence(text: str) -> list[str] | None:
    """Per il rifacimento di una frase uscita tagliata: in due pezzi (None se e' troppo corta)."""
    parts = split_long(text, max(18, len(text) // 2 + 2))
    return parts if len(parts) > 1 else None
