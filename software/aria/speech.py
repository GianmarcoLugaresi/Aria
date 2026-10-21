"""Dal testo del chatbot alla voce: cio' che si LEGGE non e' cio' che si DICE.

`speechify()` prepara una frase per il sintetizzatore: numeri e simboli a parole («18°C» -> «diciotto gradi», «il 40%» -> «il quaranta per cento»),
niente asterischi/emoji/parentesi, una virgola dopo gli intercalari («Beh dipende» -> «Beh, dipende») cosi' la voce fa la pausa che farebbe una persona.
`shape_pause()` regola il silenzio alla fine di ogni frase in base alla punteggiatura: il ritmo del parlato.
"""
from __future__ import annotations

import re

import numpy as np

from . import i18n

_U = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "undici", "dodici", "tredici", "quattordici", "quindici",
      "sedici", "diciassette", "diciotto", "diciannove"]
_T = ["", "", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta", "ottanta", "novanta"]


def _below_100(n: int) -> str:
    if n < 20:
        return _U[n]
    t, u = divmod(n, 10)
    base = _T[t]
    if u in (1, 8):
        base = base[:-1]                                         # ventuno, ventotto
    return base + ("tré" if u == 3 else _U[u] if u else "")


def _below_1000(n: int) -> str:
    c, r = divmod(n, 100)
    head = "" if c == 0 else "cento" if c == 1 else _U[c] + "cento"
    if r == 0:
        return head
    tail = _below_100(r)
    if head and tail[0] in "o" and r >= 80 and r < 90:           # centottanta, duecentottanta
        head = head[:-1]
    return head + tail


def num_words(n: int) -> str:
    """Un intero in parole italiane: 1985 -> «millenovecentottantacinque», 2026 -> «duemilaventisei», 1250000 -> «un milione duecentocinquantamila» (in inglese: speech_en.num_words)."""
    if i18n.is_en():
        from . import speech_en
        return speech_en.num_words(n)
    if n < 0:
        return "meno " + num_words(-n)
    if n < 100:
        return _below_100(n)
    if n < 1000:
        return _below_1000(n)
    if n < 1_000_000:
        k, r = divmod(n, 1000)
        head = "mille" if k == 1 else _below_1000(k) + "mila"
        return head + (_below_1000(r) if r else "")
    if n < 1_000_000_000:
        m, r = divmod(n, 1_000_000)
        head = "un milione" if m == 1 else _below_1000(m) + " milioni"
        return head + (" " + num_words(r) if r else "")
    b, r = divmod(n, 1_000_000_000)
    head = "un miliardo" if b == 1 else _below_1000(b) + " miliardi"
    return head + (" " + num_words(r) if r else "")


def _digits(s: str) -> str:
    return " ".join(_U[int(c)] for c in s)


def _decimal(whole: str, frac: str) -> str:
    if frac.startswith("0") or len(frac) > 3:
        words = _digits(frac)
    else:
        words = num_words(int(frac))
    return f"{num_words(int(whole))} virgola {words}"


_UNITS = [(r"km\s*/\s*h", "chilometri orari"), (r"km", "chilometri"), (r"kg", "chili"), (r"cm", "centimetri"), (r"mm", "millimetri"), (r"ml", "millilitri"),
          (r"gb", "giga"), (r"mb", "mega"), (r"kb", "kilobyte"), (r"min", "minuti"), (r"sec", "secondi"), (r"h", "ore"), (r"m", "metri"), (r"g", "grammi"), (r"l", "litri")]
_ABBR = [(r"\becc\.", "eccetera"), (r"\bes\.", "per esempio"), (r"\bdott\.", "dottor"), (r"\bsig\.ra\b", "signora"), (r"\bsig\.", "signor"), (r"\bprof\.", "professor"),
         (r"\bvs\.?", "contro"), (r"\bn\.\s*(?=\d)", "numero "), (r"\bca\.", "circa"), (r"\bpag\.", "pagina")]
_ORD = {1: "primo", 2: "secondo", 3: "terzo", 4: "quarto", 5: "quinto", 6: "sesto", 7: "settimo", 8: "ottavo", 9: "nono", 10: "decimo"}
_MARKERS = ("beh", "mah", "boh", "dunque", "insomma", "vabbè", "vabbe", "uhm", "ehm", "eh", "ah", "oh", "bé", "ecco, ", "ok")
_MARKER_RE = re.compile(r"(^|[.!?…]\s+)((?:beh|mah|boh|dunque|insomma|vabbè|vabbe|uhm|ehm|eh|ah|oh|bé))\s+(?=[a-zA-ZÀ-ÿ])", re.I)


def speechify(text: str) -> str:
    if i18n.is_en():
        from . import speech_en
        return speech_en.speechify(text)
    t = text or ""
    t = re.sub(r"\*[^*\n]{1,60}\*", " ", t)                                          # *sorride*: azioni tra asterischi, non si dicono
    t = re.sub(r"\([^)\n]{0,120}\)", " ", t)                                         # (note tra parentesi)
    t = re.sub(r"\[[^\]\n]{0,80}\]", " ", t)
    t = re.sub(r"[_*#~`<>|\[\]{}]+", " ", t)                                        # simboli e parentesi sparse (anche un «]» rimasto dai comandi)
    t = re.sub(r"[«»\"“”]", "", t)
    t = re.sub(r"\s*[—–]\s*", ", ", t)
    t = re.sub(r"\s*&\s*", " e ", t)
    t = re.sub(r"\.{3,}", "…", t)
    t = re.sub(r"([!?]){2,}", r"\1", t)
    t = re.sub(r"([,;:])\1+", r"\1", t)
    # orari: 18:30 -> «le diciotto e trenta»
    def clock(m):
        h, mi = int(m.group(2)), int(m.group(3))
        pre = m.group(1) or ""
        art = "" if pre.strip().lower() in ("alle", "le", "ore", "dalle", "fino alle", "verso le", "intorno alle") else "le "
        h_words = "mezzanotte" if h == 0 and mi == 0 else "mezzogiorno" if h == 12 and mi == 0 else num_words(h)
        tail = "" if mi == 0 else " e " + ("mezza" if mi == 30 else "un quarto" if mi == 15 else num_words(mi))
        return f"{pre}{art}{h_words}{tail}"
    t = re.sub(r"(\b(?:alle|dalle|fino alle|verso le|intorno alle|le|ore)\s+)?\b([01]?\d|2[0-3]):([0-5]\d)\b", clock, t, flags=re.I)
    t = re.sub(r"(\b(?:alle|dalle|fino alle|verso le|intorno alle|ore)\s+)\b([01]?\d|2[0-3])\.([0-5]\d)\b(?!\.\d)", clock, t, flags=re.I)       # «alle 18.30» (si scrive anche col punto) non e' «diciotto virgola trenta»
    def version(m):
        parts = m.group(0).split(".")
        if len(parts[0]) <= 3 and all(len(x) == 3 for x in parts[1:]):
            return m.group(0)                                                     # «1.250.000»: sono migliaia (ci pensa la regola piu' sotto)
        return " punto ".join(num_words(int(x)) for x in parts)
    t = re.sub(r"\b\d+(?:\.\d+){2,}\b", version, t)                                  # versioni: «macOS 27.0.1» -> «ventisette punto zero punto uno»
    t = re.sub(r"\b(\d{1,3})((?:\.\d{3})+),(\d+)\b", lambda m: m.group(1) + m.group(2).replace(".", "") + "," + m.group(3), t)          # «1.250,50» -> «1250,50» (migliaia col punto e decimali con la virgola)
    t = re.sub(r"(\d+(?:[.,]\d+)?)\s*%", lambda m: m.group(1) + " per cento", t)
    t = re.sub(r"\b(\d+)\s*[º°ª]\s*(?=(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre|posto|piano|classificato|anno|capitolo|giorno|turno|secolo)\b)",
               lambda m: _ORD.get(int(m.group(1)), num_words(int(m.group(1))) + " ") + " ", t, flags=re.I)
    t = re.sub(r"(\d+(?:[.,]\d+)?)\s*°(?:[CcFf]\b)?", lambda m: m.group(1) + " gradi", t)
    t = re.sub(r"€\s*(\d+(?:[.,]\d+)?)", lambda m: m.group(1) + " euro", t)
    t = re.sub(r"(\d+(?:[.,]\d+)?)\s*€", lambda m: m.group(1) + " euro", t)
    t = re.sub(r"\$\s*(\d+(?:[.,]\d+)?)", lambda m: m.group(1) + " dollari", t)
    for rx, rep in _ABBR:
        t = re.sub(rx, rep, t, flags=re.I)
    for rx, rep in _UNITS:                                                           # solo se attaccate o dopo un numero: «5 km», «20kg»
        t = re.sub(rf"(?<=\d)\s*{rx}\b", " " + rep, t, flags=re.I)
    t = re.sub(r"(?<=\d)\s*\+\s*(?=\d)", " più ", t)
    t = re.sub(r"(?<=\d)\s*=\s*(?=\d)", " uguale a ", t)
    t = re.sub(r"\b(\d{1,3})((?:\.\d{3})+)\b(?!,)", lambda m: str(int((m.group(1) + m.group(2)).replace(".", ""))), t)   # 1.250.000
    t = re.sub(r"\b(\d+)[,.](\d+)\b", lambda m: _decimal(m.group(1), m.group(2)), t)
    t = re.sub(r"\b(\d+)[º°ª]", lambda m: _ORD.get(int(m.group(1)), num_words(int(m.group(1)))), t)
    def integer(m):
        s = m.group(0)
        return _digits(s) if len(s) > 9 else num_words(int(s))
    t = re.sub(r"\b\d+\b", integer, t)
    t = _MARKER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}, ", t.strip())            # «Beh dipende» -> «Beh, dipende»
    t = re.sub(r"\s+([,.;:!?…])", r"\1", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


# ---- il ritmo: quanto silenzio dopo ogni frase
PAUSE_MS = {".": 300, "?": 340, "!": 260, "…": 460, ",": 140, ":": 200, ";": 200}


def trim_silence(pcm: np.ndarray, sr: int, lead_ms: float = 40.0, tail_ms: float = 100.0, floor_db: float = -35.0) -> np.ndarray:
    """Toglie il silenzio all'inizio (Pocket TTS ne mette 300-600 ms, e il primo campione ha uno scatto che fa sembrare «voce» anche l'attacco) e in coda (~1,3 s: la «coda di sicurezza»
    che evita di tagliare l'ultima parola, ma tra un pezzo e l'altro di una frase diventava una pausa da 2 secondi). Si guarda l'energia a finestre da 10 ms, e «voce» e' almeno 30 ms di fila
    sopra -35 dB dal parlato tipico: gli scatti isolati non contano. Lascia un respiro naturale davanti e dietro."""
    if len(pcm) == 0:
        return pcm
    x = np.asarray(pcm).reshape(-1)
    xf = x.astype(np.float32)
    hop = max(1, int(sr * 0.01))
    n = len(xf) // hop
    if n < 6:
        return x
    rms = np.sqrt(np.mean(xf[:n * hop].reshape(n, hop) ** 2, axis=1))
    ref = float(np.percentile(rms, 98))
    if ref <= 0:
        return x
    on = rms > ref * 10 ** (floor_db / 20)
    on3 = on[:-2] & on[1:-1] & on[2:]
    if not on3.any():
        return x
    first = int(np.argmax(on3))
    last = len(on3) - int(np.argmax(on3[::-1])) + 2
    a = max(0, first * hop - int(lead_ms / 1000 * sr))
    b = min(len(x), last * hop + int(tail_ms / 1000 * sr))
    return x[a:b]


def shape_pause(pcm: np.ndarray, sr: int, text: str, floor_db: float = -40.0, min_gap_ms: int = 0) -> np.ndarray:
    """Toglie il silenzio (casuale: 100-550 ms) che il sintetizzatore lascia in coda e ci mette quello giusto per la punteggiatura."""
    if len(pcm) == 0:
        return pcm
    x = pcm.astype(np.float32)
    peak = float(np.max(np.abs(x))) + 1e-9
    idx = np.where(np.abs(x) > peak * 10 ** (floor_db / 20))[0]
    end = int(idx[-1]) + 1 if len(idx) else len(x)
    end = min(len(x), end + int(0.04 * sr))                                          # un attimo di coda naturale
    body = x[:end].copy()
    fade = min(len(body), int(0.012 * sr))
    if fade:
        body[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    last = (text.rstrip()[-1:] or ".")
    ms = PAUSE_MS.get(last, 260)
    if last in ".?!…":
        ms = max(ms, min_gap_ms)                                                      # (la pausa in cui l'utente puo' interrompere)
    gap = int(ms / 1000 * sr)
    return np.concatenate([body, np.zeros(gap, dtype=np.float32)]).astype(pcm.dtype)
