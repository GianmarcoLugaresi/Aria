"""Il «ritmo» della conversazione: per ogni frase dell'utente, che tipo di mossa fa una persona vera e quanto dura.

Un modello piccolo, lasciato a se' stesso, risponde a tutto allo stesso modo: neutro ("dipende"), lungo, con la domanda in fondo.
Qui si riconosce il tipo di turno e si danno al chatbot UNA mossa precisa, una lunghezza e una regola sulle domande,
poi un filtro deterministico (Governor) fa rispettare i limiti anche se il modello se ne dimentica.

    parere     «secondo te meglio X o Y?»          schierarsi (70/30) con UN argomento, niente «dipende»; alla frase dopo (posizione) tiene il punto
    spiega     «come funziona…», «che vuol dire…»  prima l'immagine concreta, poi il meccanismo; si ferma al primo livello (la cipolla)
    risonanza  racconto/sfogo lungo                 una reazione vera e UNA domanda su un dettaglio concreto
    traino     «boh, niente di che», serata vuota   niente domande: e' lei a portare un pensiero, una scena in cui ci si riconosce
    attrito    «faccio schifo», «andra' male»       smontare il film mentale con ironia affettuosa, senza dargli ragione per servilismo

Le emozioni forti (triste, malato, ansioso…) restano a style.py: li' non si scherza e non si fa il traino.
Idea di partenza: un «motore di conversazione» con una mossa per tipo di turno, un budget di parole e una regola sulle domande, adattato ad Aria (nome, voce, italiano parlato, regole gia' presenti).
"""
from __future__ import annotations

import random
import re
import sys
from dataclasses import dataclass

from . import i18n, rhythm_en
from .textutil import normalize

# ---------------------------------------------------------------- riconoscere il tipo di turno (sul testo normalizzato: minuscolo, senza accenti)
_OPINION = re.compile(r"\b(?:secondo te|che ne pensi|cosa ne pensi|tu cosa ne pensi|tu che faresti|tu cosa faresti|cosa sceglieresti|che scegli|tu che scegli|"
                      r"meglio\s+\w[\w ]{0,40}\s+o\s+\w+|preferisci\s+\w+|ti conviene|mi conviene|ha senso che io|e una buona idea|e una cattiva idea|che opinione hai|il tuo parere|un parere)\b")
_LEAD = r"(?:(?:ok|e|ma|allora|quindi|senti|dai|aspetta|scusa|no|si|ah|oh|eh|boh|bene|va bene)\s+)*"
_EXPLAIN = re.compile(r"\b(?:che cos e|cos e|cosa e|cosa sarebbe|a cosa serve|come funziona|come funzionano|che vuol dire|che significa|cosa significa|cosa vuol dire|che differenza c e|qual e la differenza|differenza tra)\b")
_WHY = re.compile(rf"^{_LEAD}(?:perche|come mai)\b")                       # «perché le foglie sono verdi?» (ma non «perché ti sei bloccata?»: li' si parla di lei)
_ABOUT_HER = re.compile(r"\b(?:ti|tu|te|hai|sei|mi hai|ti sei|aria)\b")
_DEEP = re.compile(r"\b(?:in dettaglio|nel dettaglio|passo passo|per esteso|a lungo|tutto quanto|dimmi tutto|dimmi di piu|approfondisci|approfondiamo|raccontami|parlami)\b")
_SELF_DOWN = re.compile(r"\b(?:faccio schifo|faccio pena|sono un (?:fallito|incapace|idiota|disastro|fallimento|inutile|peso)|sono (?:un )?(?:incapace|inutile|stupid[oa]|scars[oa])|non combino (?:niente|mai niente)|"
                        r"non sono capace|non valgo niente|tutti (?:sono )?(?:migliori|piu bravi) di me|non ce la faro mai|non ce la faccio mai|sono sempre indietro|sono indietro su tutto|sono sempre io quell[oa] che)\b")
_CATASTROPHE = re.compile(r"\b(?:sicuramente|di sicuro|di certo)\b.{0,40}\b(?:andra male|va male|mi dicono di no|mi bocciano|mi licenziano|non rispondono|non risponde|e finita)\b|"
                          r"\b(?:andra (?:sicuramente |di sicuro )?male|andra tutto male|finira male|e tutto inutile|e andata, e finita|ormai e tutto perso|non cambiera mai niente)\b|"
                          r"\b(?:e se poi|ma se poi)\b.{0,50}\b(?:dicono di no|va male|mi lasciano|mi bocciano|sbaglio|non mi vogliono)\b")
_BIG_DECISION = re.compile(r"\b(?:lavoro|licenzi\w*|lasci\w*|trasferi\w*|sposar\w*|divorzi\w*|figli\w*|fidanzat\w*|compagn[ao]|universita|laurea|mutuo|investi\w*|medico|cura|terapia|farmaci\w*)\b")
_LOW_ENERGY = re.compile(r"\b(?:niente di che|niente di speciale|solita (?:roba|giornata|storia|serata)|come al solito|non (?:ho|c ho) (?:voglia|nessuna voglia)(?: di (?:fare )?niente)?|giornata piatta|giornata vuota|serata vuota|"
                         r"che noia|lasciamo perdere|lascia stare|non so che fare|non c e (?:nessuno|niente)|non succede niente|il solito|tiro avanti)\b|^(?:boh|mah|mh+|mmh+|bho|eh)\b")


@dataclass(frozen=True)
class Turn:
    mode: str                    # parere | spiega | risonanza | traino | attrito
    min_words: int
    max_words: int
    max_sentences: int
    max_tokens: int              # tetto della generazione (circa due token a parola, piu' un po' di margine)
    temp_delta: float            # rispetto alla temperatura di base del chatbot (le risposte "di fatti" piu' ferme, quelle "di carattere" piu' libere)
    allow_question: bool
    move: str                    # la mossa, in una frase
    shots: str                   # categoria degli esempi in examples.BANK

    @property
    def budget(self) -> str:
        if i18n.is_en():
            return rhythm_en.TEXT["budget"].format(lo=self.min_words, hi=self.max_words, sent=self.max_sentences)
        return f"tra {self.min_words} e {self.max_words} parole, al massimo {self.max_sentences} frasi"

    @property
    def question_rule(self) -> str:
        if i18n.is_en():
            return rhythm_en.TEXT["ask" if self.allow_question else "noask"]
        if self.allow_question:
            return "Puoi chiudere con UNA sola domanda breve su un dettaglio concreto, non su come si sente."
        return "NIENTE domande in questa risposta: nessun punto interrogativo. Chiudi con un'affermazione o un pensiero tuo."


MOVES = {
    "parere": "Prendi subito posizione: dì chiaro cosa sceglieresti tu e porta UN solo motivo concreto, non una lista. Mai «dipende» né «ci sono pro e contro»; al massimo concedi una mezza frase all'altra parte.",
    "spiega": "Comincia con un paragone concreto o un'immagine di tutti i giorni («fai conto che…», «immagina…»), poi dì cosa succede con verbi semplici. Ti fermi al primo livello: i dettagli solo se li chiede.",
    "risonanza": "Prima una reazione tua, spontanea e brevissima a quello che ha raccontato (a parole tue, mai «mi dispiace che tu»), poi UNA domanda su un dettaglio concreto del fatto, come la farebbe un'amica curiosa.",
    "traino": "Non fargli domande e non dargli consigli: porta tu la conversazione. Dì un pensiero tuo sulla situazione, un'osservazione curiosa o una scena quotidiana in cui ci si riconosce. Parla in generale, senza raccontare cose che ti sono successe.",
    "attrito": "Non dargli ragione per gentilezza e non dire «capisco». Smonta con ironia affettuosa il film che si sta facendo, riportandolo coi piedi per terra con un fatto concreto. Niente consigli e niente «prova a…»: ruvida ma dalla sua parte.",
    "posizione": "Ha obiettato o chiesto altro sul tuo parere: tieni la tua posizione. Se l'obiezione è buona concedi una mezza frase, poi di' perché per te vale ancora la tua scelta. Non cambiare idea al primo ostacolo e non dire «dipende».",
}


def _turn(mode: str, allow_question: bool) -> Turn:
    spec = {
        "parere": (25, 60, 3, 120, +0.10, "parere"),
        "spiega": (35, 75, 4, 150, -0.10, "cipolla"),
        "risonanza": (8, 28, 2, 64, +0.05, "risonanza"),
        "traino": (25, 50, 3, 110, +0.10, "traino"),
        "attrito": (20, 45, 3, 100, +0.05, "attrito"),
        "posizione": (15, 45, 2, 100, +0.05, "posizione"),
    }[mode]
    lo, hi, sent, tok, dt, shots = spec
    return Turn(mode, lo, hi, sent, tok, dt, allow_question, (rhythm_en.MOVES if i18n.is_en() else MOVES)[mode], shots)


def asked_last(history: list[dict]) -> bool:
    """L'ultima cosa che Aria ha detto era una domanda? (in quel caso questo turno non ne fa: mai due di fila)"""
    last = next((m["content"] for m in reversed(history) if m.get("role") == "assistant" and m.get("content", "").strip()), "")
    return last.rstrip().endswith("?")


def plan(history: list[dict], user_text: str, mood: str | None = None, long: str | None = None, rng: random.Random | None = None, prev: str | None = None) -> Turn | None:
    """Il tipo di turno per questa frase, oppure None (si lascia fare a style.turn_hint: saluti, ok, emozioni forti, spiegazioni lunghe richieste, quiz…).
    `history` e' la conversazione SENZA la frase di adesso; `prev` la mossa del turno prima (un parere si difende anche alla frase dopo)."""
    if long or mood:
        return None                                                         # richieste di discorsi lunghi e momenti delicati hanno le loro regole
    text = (user_text or "").strip()
    if not text:
        return None
    from . import dialog
    if dialog.is_ack(text) or dialog.is_laugh(text):
        return None
    rng = rng or random
    t = normalize(text)
    words = len(text.split())
    can_ask = not asked_last(history)
    R = rhythm_en if i18n.is_en() else sys.modules[__name__]
    _SELF_DOWN, _CATASTROPHE, _OPINION, _DEEP, _BIG_DECISION, _LOW_ENERGY = R.SELF_DOWN, R.CATASTROPHE, R.OPINION, R.DEEP, R.BIG_DECISION, R.LOW_ENERGY
    if _SELF_DOWN.search(t) or _CATASTROPHE.search(t):
        return _turn("attrito", False)
    if _OPINION.search(t) and not _DEEP.search(t) and not _BIG_DECISION.search(t):                  # una scelta di vita non si liquida con un 70/30: ci pensa style (esempi «consiglio»)
        return _turn("parere", can_ask and rng.random() < 0.4)
    if prev in ("parere", "posizione") and words <= 14 and not _DEEP.search(t) and not _BIG_DECISION.search(t) and not is_concept_question(t):
        return _turn("posizione", can_ask and rng.random() < 0.3)                           # obiezione o domanda di seguito: tiene la sua posizione
    if is_concept_question(t) and not _DEEP.search(t):
        return _turn("spiega", can_ask and rng.random() < 0.25)
    if text.endswith("?") and words > 6:
        return None                                                         # una domanda vera e propria che non e' di nessun tipo qui sopra: risposta normale
    if _LOW_ENERGY.search(t) and len(_LOW_ENERGY.sub(" ", t).split()) <= 2:                  # «boh, giornata piatta» si', «boh, adesso ricomincio da capo» no (ha un contenuto)
        return _turn("traino", False)
    if words >= 24 and not text.endswith("?"):
        return _turn("risonanza", can_ask and rng.random() < 0.85)           # un racconto/sfogo: reagisce e (di solito) chiede un dettaglio
    return None


def is_concept_question(t: str) -> bool:
    """Sul testo normalizzato: «come funziona una cache?», «che vuol dire che un file clippa?», «perché le foglie sono verdi?»."""
    R = rhythm_en if i18n.is_en() else sys.modules[__name__]
    return bool(R.EXPLAIN.search(t) or (R.WHY.search(t) and not R.ABOUT_HER.search(t)))


def hint(turn: Turn) -> str:
    """Le tre righe per il prompt: la mossa, la lunghezza, la regola delle domande."""
    return f"{turn.move} {rhythm_en.TEXT['length'] if i18n.is_en() else 'Lunghezza'}: {turn.budget}. {turn.question_rule}"


def temperature(turn: Turn | None, base: float) -> float | None:
    if turn is None:
        return None
    return round(min(1.0, max(0.2, base + turn.temp_delta)), 2)


# ---------------------------------------------------------------- il filtro: fa rispettare i limiti anche se il modello se ne dimentica
_TAG_Q = re.compile(r",?\s*(?:vero|non credi|che dici|ti pare|no|giusto|eh)\s*\?$", re.I)
_END = re.compile(r"[.!?…][\"»)]*$")
_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def _words(s: str) -> int:
    return len(s.split())


def _unquestion(s: str) -> str:
    """«…, vero?» -> «…»: la coda da domanda retorica diventa un'affermazione."""
    out = (rhythm_en.TAG_Q if i18n.is_en() else _TAG_Q).sub(".", s.rstrip())
    return out if out != s.rstrip() else s


class Governor:
    """Passa le frasi della risposta (anche a pezzi, mentre arrivano) e toglie quelle fuori misura: domande dove non sono ammesse, frasi oltre il tetto di frasi o di parole.

        gov = Governor(turn)
        for chunk in chunks:
            text = gov.take(chunk)            # il pezzo da dire (puo' essere vuoto)
            if gov.done: break                # tetto raggiunto: a fine frase ci si ferma
    """

    def __init__(self, turn: Turn | None, slack: float = 1.25):
        self.turn, self.slack = turn, slack
        self.sentences = 0
        self.words = 0
        self.open = False                       # l'ultimo pezzo detto non e' finito a un punto
        self.done = False

    def take(self, chunk: str) -> str:
        t = self.turn
        if t is None or self.done:
            return chunk if t is None else ""
        out: list[str] = []
        parts = [p for p in _SPLIT.split(chunk.strip()) if p]
        for i, part in enumerate(parts):
            fresh = not (i == 0 and self.open)                           # il primo pezzo continua una frase gia' cominciata
            ends = bool(_END.search(part))
            if fresh and ends and part.rstrip().endswith("?") and not t.allow_question:
                if out or self.sentences or i < len(parts) - 1:
                    continue                                            # c'e' altro da dire (o e' stato detto): la domanda salta
                part = _unquestion(part)
            if self.sentences >= t.max_sentences and not self.open:
                self.done = True
                break
            out.append(part)
            self.words += _words(part)
            self.open = not ends
            if ends:
                self.sentences += 1
                if self.sentences >= t.max_sentences or self.words >= t.max_words * self.slack:
                    self.done = True
                    break
        return " ".join(out)


def enforce(text: str, turn: Turn | None) -> str:
    """Lo stesso filtro su una risposta intera (per i test e per la misura): rimette in riga lunghezza e domande."""
    if turn is None:
        return text
    gov = Governor(turn)
    return gov.take(text)


# nomi senza il trattino basso: li usa anche rhythm_en.py, cosi' plan() sceglie le tabelle della lingua in uso con lo stesso codice
OPINION, SELF_DOWN, CATASTROPHE, DEEP, BIG_DECISION, LOW_ENERGY, EXPLAIN, WHY, ABOUT_HER = _OPINION, _SELF_DOWN, _CATASTROPHE, _DEEP, _BIG_DECISION, _LOW_ENERGY, _EXPLAIN, _WHY, _ABOUT_HER
