"""Pezzi di testo: spezzare le frasi per il TTS, intercettare i comandi [[STRUMENTO: ...]] e fermare "stop"."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterator

import random as _random

VARIETY = True                                      # i test lo spengono: la prima variante e' sempre quella "storica"


def pick(options: list[str]) -> str:
    """Una frase tra piu' modi di dire la stessa cosa: una persona non conferma sempre allo stesso modo."""
    return _random.choice(options) if VARIETY else options[0]


_ABBR = {"sig", "sigg", "dott", "dr", "prof", "ing", "avv", "sig.ra", "ecc", "es", "cfr", "pag", "tel", "vs", "n"}
_END = ".!?…"


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U0000FE0F\U0000200D\U00002B50\U00002B06\U00002934\U00002935*_#~`]+")


def strip_emoji(text: str) -> str:
    """Via emoji e simboli da markdown: il sintetizzatore non li sa leggere (o li legge male)."""
    return re.sub(r"[ \t]{2,}", " ", _EMOJI.sub("", text)).strip()


def strip_think(text: str) -> str:
    """Toglie i blocchi <think>...</think> (alcuni modelli ragionano ad alta voce)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).replace("<think>", "").replace("</think>", "")


class SentenceChunker:
    """Riceve pezzi di testo in streaming e restituisce frasi pronte per il TTS.

    La prima frase parte presto (appena c'e' una pausa ragionevole) per ridurre l'attesa; le successive
    sono frasi intere. Non spezza su abbreviazioni (dott., sig., ecc.) ne' sui numeri decimali.
    """

    def __init__(self, first_min: int = 18, min_len: int = 30, max_len: int = 220):
        self.buf = ""
        self.first = True
        self.first_min, self.min_len, self.max_len = first_min, min_len, max_len

    def _find_cut(self, s: str) -> int:
        """Indice (esclusivo) dove tagliare, oppure -1."""
        need = self.first_min if self.first else self.min_len
        for i, ch in enumerate(s):
            if ch in _END:
                if ch == "." and i + 1 < len(s) and s[i + 1].isdigit() and i > 0 and s[i - 1].isdigit():
                    continue                                    # 3.14
                if ch == "." and i + 1 >= len(s):
                    return -1                                   # potrebbe continuare ("..." / "dott.")
                j = i
                while j + 1 < len(s) and s[j + 1] in _END + '"»)':
                    j += 1
                if j + 1 >= len(s):
                    return -1 if ch == "." else (j + 1 if j + 1 >= need else -1)
                if s[j + 1] not in " \n":
                    continue
                word = re.findall(r"([A-Za-zÀ-ÿ\.]+)\.?$", s[:i + 1].rstrip("."))
                if ch == "." and word and word[-1].lower().rstrip(".") in _ABBR:
                    continue
                if j + 1 >= need:
                    return j + 1
            elif ch in ",;:" and self.first and i + 1 >= 90 and i + 1 < len(s) and s[i + 1] == " ":
                return i + 1                                    # prima frase molto lunga: puo' partire a una virgola (le piu' corte aspettano la fine: la voce chiude male un pezzo a meta')
        if len(s) >= self.max_len:
            k = s.rfind(" ", 0, self.max_len)
            return k + 1 if k > 40 else self.max_len
        return -1

    def push(self, text: str) -> Iterator[str]:
        self.buf += text
        while True:
            cut = self._find_cut(self.buf)
            if cut < 0:
                break
            sent, self.buf = self.buf[:cut].strip(), self.buf[cut:].lstrip()
            if sent:
                self.first = False
                yield sent

    def flush(self) -> Iterator[str]:
        rest = self.buf.strip()
        self.buf = ""
        if rest:
            self.first = False
            yield rest


# --- comandi strumento -------------------------------------------------------------------
TOOL_RE = re.compile(r"\[\[\s*([A-Za-zÀ-ÿ_]+)\s*:?\s*(.*?)\s*\]\]", re.S)


@dataclass
class ToolCall:
    name: str
    arg: str


class TagFilter:
    """Filtra lo stream: lascia passare il testo normale e blocca/estrae i comandi [[NOME: argomento]].

    push() restituisce (testo_da_dire, [ToolCall...]). Un comando incompleto viene tenuto in buffer.
    """

    def __init__(self):
        self.buf = ""

    def push(self, chunk: str) -> tuple[str, list[ToolCall]]:
        self.buf += chunk
        out, calls = "", []
        while True:
            i = self.buf.find("[[")
            if i < 0:
                # nessun comando: tieni solo un eventuale "[" finale (potrebbe essere l'inizio di "[[")
                keep = 1 if self.buf.endswith("[") else 0
                out += self.buf[: len(self.buf) - keep]
                self.buf = self.buf[len(self.buf) - keep:]
                break
            out += self.buf[:i]
            j = self.buf.find("]]", i)
            if j < 0:
                self.buf = self.buf[i:]                         # comando ancora incompleto
                break
            m = TOOL_RE.fullmatch(self.buf[i:j + 2])
            if m:
                calls.append(ToolCall(m.group(1).upper(), m.group(2).strip()))
            self.buf = self.buf[j + 2:]
        return out, calls

    def flush(self) -> str:
        rest, self.buf = self.buf, ""
        return "" if rest.startswith("[[") else rest


# --- parole di comando / wake word -------------------------------------------------------
def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _ratio(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


# nomi che somigliano ad "aria" ma non sono lei: "ciao Maria" non deve svegliarla
_NOT_ARIA = {"maria", "mario", "marie", "mari", "mara", "maia", "ria", "sara", "clara", "laura", "lara", "ario", "arianna", "ariana", "daria", "aurelia", "dario", "ilaria", "valeria", "zaira"}


# «hey» detto da un italiano il riconoscimento lo scrive in vari modi: «hey», «ehi», «ei», «hei»…
_HEY = ("hey", "ehi", "ei", "hei", "ey", "ehy", "hay")


def matches_phrase(text: str, phrase: str, threshold: float = 0.72) -> bool:
    """True se `text` contiene (quasi) `phrase`, parola per parola: tollera trascrizioni imprecise
    ("ciao arya", "ciao area", "ehi aria" per "hey aria") ma non nomi simili ("ciao Maria")."""
    pw = normalize(phrase).split()
    if len(pw) >= 2 and pw[0] in _HEY:
        return _matches_hey(normalize(text).split(), pw[1:])
    return _matches(text, phrase, threshold)


def _matches_hey(words: list[str], rest: list[str]) -> bool:
    """«hey aria» (e le sue grafie: «ehi aria», «ei aria»…): la prima parola deve essere proprio una di quelle (una corta e storpiabile come «hey» farebbe passare «che aria fredda»),
    il nome deve combaciare bene e non essere un nome simile («hey Maria»)."""
    n = len(rest)
    for i, w in enumerate(words):
        if w in _HEY and words[i + 1:i + 1 + n] and len(words[i + 1:i + 1 + n]) == n:
            cand = words[i + 1:i + 1 + n]
            if not any(c in _NOT_ARIA for c in cand) and all(_ratio(c, q) >= 0.74 for c, q in zip(cand, rest)):
                return True
        joined = "".join(rest)
        if w not in _NOT_ARIA and any(_ratio(w, v + joined) >= 0.85 for v in _HEY):       # «heyaria» attaccato
            return True
    return False


def _matches(text: str, phrase: str, threshold: float) -> bool:
    t, p = normalize(text), normalize(phrase)
    if not t or not p:
        return False
    words, pw = t.split(), p.split()
    n = len(pw)
    for i in range(len(words)):
        if n == 1:
            cand = words[i:i + 1]
        else:
            cand = words[i:i + n]
            if len(cand) < n:                                   # "ciaoaria" attaccato
                if len(cand) == 1 and _ratio(cand[0], "".join(pw)) >= max(threshold, 0.85) and cand[0] not in _NOT_ARIA:
                    return True
                continue
        if any(w in _NOT_ARIA for w in cand[1:]):
            continue
        # il primo termine puo' essere un po' storpiato, l'ultimo (il nome) deve combaciare bene
        ok = all(_ratio(w, q) >= (0.78 if k == n - 1 else 0.7) for k, (w, q) in enumerate(zip(cand, pw)))
        if ok:
            return True
        if n >= 2 and len(cand) == n and _ratio(" ".join(cand), p) >= max(threshold, 0.85) and cand[-1] not in _NOT_ARIA:
            return True
    return False


STOP_WORDS = {"stop", "basta", "zitta", "silenzio", "fermati", "taci", "ok basta", "basta cosi"}


def is_stop_command(text: str) -> bool:
    t = normalize(text)
    return t in STOP_WORDS or any(t.startswith(w + " ") and len(t.split()) <= 3 for w in ("stop", "basta", "zitta"))
