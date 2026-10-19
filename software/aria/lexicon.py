"""Il «vocabolario di Aria»: le parole che ha motivo di conoscere (il tuo nome, la tua citta', i nomi dei file nella sua cartella, le cose che le hai insegnato).
Il riconoscimento vocale, che non le conosce, le scrive «a orecchio» («Maria» per «Mario», «Sonnium» per «Somnium», «Pocket Titti» per «Pocket TTS»):
qui, se una parola scritta come NOME PROPRIO somiglia nel suono a una del vocabolario, torna quella giusta. Prudente: solo parole con la maiuscola in mezzo alla frase
(o davanti a una virgola), solo se il suono e' (quasi) lo stesso, mai parole che sono gia' nel vocabolario."""
from __future__ import annotations

import re
import unicodedata

_PAIRS = str.maketrans({"b": "p", "d": "t", "g": "k", "v": "f", "m": "n", "c": "k", "q": "k", "z": "s", "x": "k", "y": "i", "j": "i", "w": "u"})


def _fold(w: str) -> str:
    w = unicodedata.normalize("NFKD", w.lower())
    return "".join(c for c in w if c.isalnum() and not unicodedata.combining(c))


def sound_key(word: str) -> str:
    """Una «impronta del suono» all'italiana: consonanti sorde/sonore e m/n si equivalgono (gli errori tipici del riconoscimento), le doppie diventano una, la h sparisce."""
    w = _fold(word)
    for a, b in (("gli", "li"), ("gn", "n"), ("sci", "si"), ("sce", "se"), ("ch", "k"), ("gh", "k"), ("ph", "f"), ("ci", "ki"), ("ce", "ke"), ("gi", "ki"), ("ge", "ke")):
        w = w.replace(a, b)
    w = w.replace("h", "").translate(_PAIRS)
    return re.sub(r"(.)\1+", r"\1", w)


def _dist1(a: str, b: str) -> bool:
    """Distanza di edit <= 1 (inserzione, cancellazione o sostituzione)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    s, l = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(s) and s[i] == l[i]:
        i += 1
    return s[i:] == l[i + 1:]


_TOKEN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’]*")


class Lexicon:
    def __init__(self):
        self.terms: dict[str, str] = {}                 # impronta -> parola giusta
        self.loose: set[str] = set()                    # impronte per cui basta un suono «quasi» uguale (nome e citta' dell'utente); le altre vogliono lo stesso suono

    def add(self, term: str, loose: bool = False) -> None:
        for w in _TOKEN.findall(term or ""):
            if len(_fold(w)) >= 4 and w[0].isupper():
                k = sound_key(w)
                self.terms.setdefault(k, w)
                if loose:
                    self.loose.add(k)

    def add_all(self, terms, loose: bool = False) -> None:
        for t in terms:
            self.add(t, loose)

    def correct(self, text: str) -> str:
        if not self.terms or not text:
            return text
        out, last = [], 0
        for m in _TOKEN.finditer(text):
            w = m.group(0)
            before = text[:m.start()].rstrip()
            starts_sentence = not before or before[-1] in ".!?"
            after = text[m.end():m.end() + 1]
            if not w[0].isupper() or (starts_sentence and after not in (",", ";", ":")):
                continue                                # solo i nomi propri (maiuscola in mezzo alla frase, o «Mario, …» in apertura)
            f = _fold(w)
            if len(f) < 4 or sound_key(w) in self.terms and self.terms[sound_key(w)] == w:
                continue
            key = sound_key(w)
            hit = self.terms.get(key)
            if hit is None and len(key) >= 5:
                for k, v in self.terms.items():
                    if k in self.loose and len(k) >= 5 and _dist1(key, k) and k[0] == key[0]:
                        hit = v
                        break
            if hit and hit != w and _fold(hit) != f:
                out.append((m.start(), m.end(), hit))
        for a, b, rep in reversed(out):
            text = text[:a] + rep + text[b:]
        return text
