"""Interrompere Aria con la voce mentre parla, anche con le casse del Mac (senza cancellazione dell'eco).

Il problema: il microfono sente anche la voce di Aria, quindi un rilevatore di voce scatterebbe sempre. Qui invece, mentre parla, ogni mezzo secondo si fa
riconoscere (riconoscimento integrato del Mac, 0,1 s) l'ultimo secondo e mezzo di microfono e si guardano le PAROLE: l'eco di Aria viene riconosciuta come le
parole che Aria sta dicendo (le conosce: e' il testo della sua risposta) e si ignora; se compaiono parole sue diverse («basta», «aspetta», «stop»…), e' l'utente."""
from __future__ import annotations

from . import i18n
from .textutil import normalize
from .voicecheck import _near

STOP_WORDS = {"basta", "stop", "fermati", "ferma", "fermo", "zitta", "zitto", "silenzio", "aspetta", "aspettami", "aspetti", "pausa", "interrompi", "smettila", "taci", "calma", "attimo", "momento", "aria"}
FILLERS = {"ah", "eh", "ehi", "mh", "mmh", "oh", "boh", "uhm", "ehm", "eeh", "mm"}
STOP_WORDS_EN = {"stop", "wait", "hold", "pause", "enough", "quiet", "silence", "shush", "hush", "moment", "second", "sec", "cancel", "interrupt", "aria", "hang", "easy", "whoa", "sorry", "excuse"}
FILLERS_EN = {"ah", "uh", "um", "umm", "uhm", "hmm", "hm", "mm", "mhm", "erm", "er", "oh", "huh", "eh", "ooh", "aah"}


def _decide(heard: str, expected: str, clean: bool) -> tuple[str | None, list[str], bool]:
    """(tipo, parole nuove, debole). `debole` = decisa con la regola larga del microfono pulito (una parola lunga o due parole qualsiasi): va confermata."""
    exp = [w for w in normalize(expected).split() if w]
    new, echoed = [], []
    en = i18n.is_en()
    fillers, stops = (FILLERS_EN, STOP_WORDS_EN) if en else (FILLERS, STOP_WORDS)
    for w in normalize(heard).split():
        if not w or w in fillers:
            continue
        if any(_near(w, e) for e in exp):
            echoed.append(w)
            continue                                                  # e' una parola che Aria sta dicendo: eco
        new.append(w)
    if any(w in stops for w in new):
        return "stop", new, False
    if len([w for w in new if len(w) >= 3]) >= 3:
        return "talk", new, False
    # Col microfono pulito basta poco... ma se nella finestra ci sono anche parole di Aria, il filtro dell'eco non ha tenuto e quel che resta («possiamo FARLA» per «parlarne»,
    # «CASTO» per «contrasto») e' quasi sempre una sua parola capita male: serve un'evidenza piu' forte (le tre parole di sopra)
    # (le paroline come «la», «che», «dove» ci sono in qualunque frase e non provano niente: prova una parola lunga di Aria, o due medie)
    proof = any(len(w) >= 6 for w in echoed) or len([w for w in echoed if len(w) >= 4]) >= 2
    if clean and not proof and (any(len(w) >= 4 for w in new) or len(new) >= 2):
        return "talk", new, True
    return None, new, False


def interruption(heard: str, expected: str, clean: bool = False) -> str | None:
    """«stop» (l'utente chiede di fermarsi/aspettare), «talk» (sta dicendo altro) oppure None (e' solo l'eco di Aria o rumore).
    `clean` = il microfono ha gia' l'eco tolto dal Mac: quello che si sente e' quasi sempre l'utente, quindi basta una parola vera («Indicami…», «Scusa…») o due parole qualsiasi
    (purche' nella finestra non ci siano anche parole di Aria)."""
    return _decide(heard, expected, clean)[0]


class Interrupter:
    """Decide se interrompere, finestra dopo finestra. Una decisione «debole» (microfono pulito, una sola parola nuova) scatta solo se la STESSA parola torna nella finestra dopo
    (~0,2 s): un residuo di eco capito male cambia ogni volta («farla», «casto», «finale»), la voce dell'utente no."""

    def __init__(self):
        self.prev: list[str] = []

    def reset(self) -> None:
        self.prev = []

    def feed(self, heard: str, expected: str, clean: bool = False) -> str | None:
        kind, new, weak = _decide(heard, expected, clean)
        prev, self.prev = self.prev, [w for w in new if len(w) >= 2]
        if kind == "talk" and weak and not any(_near(w, p) for w in new for p in prev if len(w) >= 3 and len(p) >= 3):
            return None
        return kind


class GapListener:
    """Interruzione a voce senza dover sentire l'utente sopra l'eco di Aria: quando le casse sono ZITTE (una pausa tra due frasi) il microfono sente solo la stanza, quindi
    qualunque voce li' dentro e' dell'utente. Si guarda la sua voce (rilevatore di voce) solo dopo un breve «respiro» da quando le casse hanno smesso (il riverbero della stanza)
    e si scatta quando c'e' abbastanza voce di seguito. Cosi' funziona anche a volume alto e con l'eco forte, dove il riconoscimento delle parole non sente l'utente.
    Misurato su un'eco VERA delle casse del Mac: parole sopra l'eco -> l'utente non si sente quasi mai; nelle pause -> 100 % in ~0,7 s."""

    def __init__(self, vad, guard: int = 4, need: int = 4, ref_thr: float = 0.002, vad_thr: float = 0.6):
        self.vad, self.guard, self.need, self.ref_thr, self.vad_thr = vad, guard, need, ref_thr, vad_thr
        self.quiet = 0
        self.voiced = 0
        self.armed = False                                                 # si arma solo dopo che le casse hanno suonato qualcosa (prima Aria sta ancora pensando: non e' un'interruzione)

    def reset(self) -> None:
        self.quiet = self.voiced = 0
        self.armed = False

    def push(self, mic_frame, ref) -> bool:
        """mic_frame: int16 (un blocco), ref: quello che le casse suonavano in quel blocco (float -1..1), o None se non si sa. True = l'utente sta parlando in una pausa."""
        import numpy as np
        p = self.vad.prob(mic_frame)                                       # sempre: il rilevatore ha una memoria e vuole tutti i blocchi
        if ref is None or float(np.sqrt(np.mean(np.asarray(ref, dtype=np.float32) ** 2))) >= self.ref_thr:
            self.quiet = self.voiced = 0                                    # le casse suonano: qui l'eco copre tutto
            if ref is not None:
                self.armed = True
            return False
        if not self.armed:
            return False
        self.quiet += 1
        if self.quiet <= self.guard:
            return False
        self.voiced = self.voiced + 1 if p >= self.vad_thr else max(0, self.voiced - 1)
        return self.voiced >= self.need
