"""Gli "atti" della conversazione che una persona gestisce senza pensarci: saluti, grazie, «ok», «come?», risate.

Rispondere a «grazie» con un giro di chatbot («Di nulla! Se hai altre domande...») suona finto: qui le risposte sono corte, variate e immediate
(senza chiedere niente al modello, quindi anche senza attesa). Tutto cio' che non e' un atto di questo tipo prosegue normalmente.
"""
from __future__ import annotations

import datetime as dt
import random
import re

from .textutil import normalize

_NAME = r"(?:\s+aria)?"
_FAREWELL = re.compile(
    r"^(?:(?:ok|va bene|bene|allora|beh|senti|dai)\s+)*(?:ciao(?: ciao)?|a dopo|a presto|a domani|a stasera|ci sentiamo|ci vediamo|buonanotte|buona notte|buona serata|"
    r"buona giornata|buon pomeriggio|buon proseguimento|arrivederci|addio|a piu tardi|vado a dormire|vado via|devo andare|devo scappare|scappo|ti saluto|ti lascio|"
    r"me ne vado|ho finito|e tutto|e tutto per ora|per ora basta|non mi serve altro|niente altro|e tutto grazie)"
    r"(?:\s+(?:aria|grazie|a tutti|e grazie|ancora|di nuovo|per ora|per oggi|e buonanotte|buona serata|buona notte|buonanotte|a dopo|a domani|a presto|ciao))*$")
_THANKS = re.compile(r"^(?:(?:ok|va bene|bene|perfetto|ottimo|grandioso|fantastico|bravissima|brava)\s+)*(?:grazie(?: mille| tante| davvero| di cuore)?|ti ringrazio|gentilissima|sei gentile|"
                     r"sei un angelo|sei stata gentile|molto gentile|sei fantastica|sei grande|sei bravissima)(?:\s+(?:mille|tante|aria|davvero|molto|ancora|di tutto|per tutto|dell aiuto))*$")
_ACK = re.compile(r"^(?:ah\s+)?(?:ok|okay|va bene|vabbe|capito|ho capito|chiaro|perfetto|ottimo|bene|benissimo|mh|mhm|mmh|uhm|aha|ah ok|ah va bene|ah capito|ah chiaro|certo|esatto|giusto|"
                  r"d accordo|molto bene|a posto|splendido)(?:\s+(?:grazie|perfetto|capito|va bene|ok|chiaro|aria))*$")
_LAUGH = re.compile(r"^(?:ah\s*){2,}h*$|^(?:ha\s*){2,}$|^(?:he\s*){2,}$|^ahah\w*$|^hahah\w*$|^ahahah\w*$|^(?:ah\s+){2,}ah$|^(?:eh\s*){2,}$|^ridicola$|^che ridere$|^mi hai fatto ridere$|^ahah che ridere$")
_REPEAT = re.compile(r"^(?:come|cosa|prego|scusa|scusami|eh|puoi ripetere|puoi ripeterlo|ripeti|ripetilo|ripeti pure|ripeti per favore|non ho capito|non ho sentito|cos hai detto|che hai detto|"
                     r"che cosa hai detto|come hai detto|me lo ripeti|ancora una volta|un altra volta|di nuovo|puoi dirlo di nuovo|non ho sentito bene)\??$")


def _t(text: str) -> str:
    return normalize(text).strip()


_GREET = re.compile(r"^(?:ciao|salve|buongiorno|buonasera|buon pomeriggio|ehi|ehila|hey|ei|pronto|ciao ciao)(?:\s+(?:aria|a te|a tutti))?$")


def is_greeting(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 3 and bool(_GREET.match(t))


def is_farewell(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 6 and bool(_FAREWELL.match(t))


_DISMISS = re.compile(
    r"^(?:(?:ok|ora|adesso|va bene|bene|grazie|allora|dai|aria|per ora|per favore|per piacere|senti|beh)\s+)*(?:(?:puoi|potresti|ti puoi|ti potresti|ti va di|e ora)\s+)?"
    r"(?:spegniti|spegnerti|spegni te stessa|spegni aria|chiuditi|chiuderti|chiudi aria|disattivati|disattivarti|riposati|riposarti|"
    r"(?:mettiti|metterti) in (?:background|disparte|standby|pausa|silenzio)|(?:vai|andare|torna|tornare|ritorna) in (?:background|standby|pausa|riposo|disparte)|"
    r"(?:vai|andare|torna|tornare) a (?:dormire|riposare|riposo|nanna))"
    r"(?:\s+(?:pure|ora|adesso|per ora|per favore|per piacere|grazie|aria|in background|te stessa|da sola|a dormire|ok))*$")
DISMISS_REPLIES = ["Va bene, mi metto in disparte. Chiamami quando ti serve.", "Ok, torno in background. Se ti serve, basta chiamarmi.", "Certo, resto qui in silenzio. Chiamami quando vuoi.",
                   "D'accordo, mi spengo. Per risvegliarmi basta chiamarmi."]


def is_dismissal(text: str) -> bool:
    """«spegniti», «vai in background», «puoi chiuderti»: l'utente vuole che Aria torni in disparte (la conversazione finisce, l'app resta nella barra dei menu)."""
    t = _t(text)
    return bool(t) and len(t.split()) <= 8 and bool(_DISMISS.match(t))


_VOICE_NAMES = {n: n for n in ("aria", "chiara", "elena", "marco", "lola", "vera", "eve", "jane", "mary", "cosette", "anna", "estelle", "fantine", "giovanni", "paul", "george", "michael", "javert")}
_VOICE_ALL = "|".join(_VOICE_NAMES)
_VOICE_NAT_ON = re.compile(r"^(?:(?:puoi |potresti |vorrei che tu |voglio che tu )?(?:attiva|attivami|accendi|metti|usa|usare|mettere|attivare|abilita|prova|provare)\s+(?:la |una |quella |l )?(?:voce\s+(?:piu\s+)?(?:naturale|umana|nuova|migliore|bella)|(?:piu\s+)?(?:naturale|umana)\s+voce)|(?:vorrei|voglio|mi piacerebbe)\s+(?:una\s+)?voce\s+(?:piu\s+)?(?:naturale|umana|migliore)|(?:parla|parlami)\s+(?:con\s+(?:una\s+|la\s+)?voce\s+(?:piu\s+)?(?:naturale|umana)|in modo piu naturale))$")
_VOICE_NAT_OFF = re.compile(r"^(?:(?:puoi |potresti )?(?:torna|tornare|ritorna|ritornare|ripassa)\s+(?:alla|a)\s+(?:voce\s+(?:di prima|normale|standard|vecchia|precedente)|quella\s+di\s+prima)|(?:togli|disattiva|spegni|metti via|elimina)\s+(?:la\s+)?voce\s+(?:naturale|nuova)|(?:rimetti|usa|metti)\s+(?:la\s+)?voce\s+(?:di prima|normale|standard|vecchia|precedente))$")
_VOICE_CYCLE = re.compile(r"^(?:(?:puoi|potresti|vorrei che tu|voglio che tu|riesci a|mi puoi)\s+)?(?:cambia|cambiare|cambiami|cambiarmi|cambi|cambiarti|variami)\s+(?:la\s+)?(?:voce|vocina)$|^(?:usa|metti|mettimi|prova|provane|fammi sentire|fammi provare|passa a)\s+(?:un altra|un altro|altra|altre|un altro tipo di)\s+(?:voce|vocina)$|^(?:un altra|altra|una diversa|diversa|un altra diversa)\s+voce$|^(?:voce|vocina)\s+(?:diversa|nuova|differente)$|^(?:voglio|vorrei|mi piacerebbe)\s+(?:cambiare\s+(?:la\s+)?voce|un altra voce|una voce diversa)$|^(?:non mi piace|odio|non sopporto)\s+(?:questa|la tua)\s+voce$")
_VOICE_SET = re.compile(r"^(?:(?:puoi|potresti|vorrei|voglio|mi piacerebbe|riesci a)\s+)?(?:(?:usa|usare|metti|mettere|mettimi|passa|passare|parla|parlami|cambia|cambiare|prova|provare|fammi sentire|fammi provare)\s+)?(?:(?:con|alla|a|in|la|come)\s+)*(?:la\s+)?voce\s+(?:di|da|come|stile)?\s*(?P<n>" + _VOICE_ALL + r")$|^(?:usa|metti|mettimi|passa a|parla come|parlami come)\s+(?P<n2>aria|chiara|elena|marco)$|^(?:voglio|vorrei|mi piacerebbe)\s+(?:una\s+)?voce\s+(?P<g>maschile|femminile|da uomo|da donna|di uomo|di donna|giovane|matura|calma|vivace)$|^(?:usa|metti|mettimi|passa a|parla con)\s+(?:una\s+|la\s+)?voce\s+(?P<g2>maschile|femminile|da uomo|da donna|di uomo|di donna|giovane|matura|calma|vivace)$")
_VOICE_GENDER = {"maschile": "marco", "da uomo": "marco", "di uomo": "marco", "femminile": "aria", "da donna": "aria", "di donna": "aria", "giovane": "chiara", "vivace": "chiara", "matura": "elena", "calma": "elena"}


def voice_request(text: str):
    """Richieste sulla voce di Aria: ('natural_on', ''), ('natural_off', ''), ('cycle', ''), ('set', 'marco'). None se non lo e'."""
    t = _t(text)
    if not t or len(t.split()) > 10:
        return None
    if _VOICE_NAT_ON.match(t):
        return ("natural_on", "")
    if _VOICE_NAT_OFF.match(t):
        return ("natural_off", "")
    m = _VOICE_SET.match(t)
    if m:
        n = m.group("n") or m.group("n2")
        return ("set", _VOICE_NAMES[n] if n else _VOICE_GENDER.get(m.group("g") or m.group("g2"), "aria"))
    if _VOICE_CYCLE.match(t):
        return ("cycle", "")
    return None


def is_thanks(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 7 and bool(_THANKS.match(t))


def is_ack(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 4 and bool(_ACK.match(t))


def is_laugh(text: str) -> bool:
    t = _t(text)
    return bool(t) and bool(_LAUGH.match(t))


_PRESENCE = re.compile(r"^(?:aria|ci sei|ci sei ancora|sei li|sei qui|mi senti|mi ascolti|mi ricevi|pronto|ehi aria|ehi|ehila)(?:\s+(?:aria|ci sei|mi senti))?$")
_APOLOGY = re.compile(r"^(?:scusa|scusami|scusa aria|perdonami|mi dispiace|ops|oddio scusa|scusa tanto|scusa scusa)$")


def is_presence_check(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 3 and bool(_PRESENCE.match(t))


def is_apology(text: str) -> bool:
    t = _t(text)
    return bool(t) and bool(_APOLOGY.match(t))


PRESENCE_REPLIES = ["Sì, sono qui.", "Eccomi, ti ascolto.", "Ci sono, dimmi pure.", "Sì, sì, ci sono."]
APOLOGY_REPLIES = ["Ma figurati, di niente.", "Non c'è problema.", "Ma di cosa, va tutto bene.", "Figurati, nessun problema."]


def presence_reply(last: str | None = None) -> str:
    return _pick(PRESENCE_REPLIES, last)


def apology_reply(last: str | None = None) -> str:
    return _pick(APOLOGY_REPLIES, last)


def is_repeat_request(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 6 and bool(_REPEAT.match(t))


# ---- le lamentele su Aria stessa («ti mangi le parole», «ti sei bloccata», «non hai capito»): una persona prende atto in una frase, non fa un discorso
_C_VOICE = re.compile(r"\b(?:ti mangi le parole|mangi le parole|inghiotti le parole|non si capisce|non (?:ti )?capisco (?:niente|nulla|bene)|parli (?:troppo )?(?:veloce|in fretta|rapido|di fretta)|"
                      r"parli (?:troppo )?(?:piano|basso|sotto voce)|non ti sento (?:bene|niente|nulla)|ti sento (?:male|poco)|la voce (?:si taglia|salta|e strana)|ti si sente male)\b")
_C_GLITCH = re.compile(r"\b(?:ti (?:buggi|blocchi|sei bloccata|incanti|sei incantata|pianti|inceppi|incarti|impalli)|sei (?:bloccata|impallata|incantata|lenta|lentissima|troppo lenta)|"
                       r"ci metti (?:troppo|tanto)|non funzioni|funzioni male|ogni tanto (?:non rispondi|ti fermi))\b")
_C_WRONG = re.compile(r"\b(?:non hai capito|hai (?:capito male|sbagliato|frainteso)|rispondi a caso|non (?:c entra|ha senso)|non e quello che (?:ho detto|volevo)|sei fuori strada)\b")


def complaint_kind(text: str) -> str | None:
    """«voice» (la voce si mangia le parole), «glitch» (si blocca, e' lenta), «wrong» (ha capito male) oppure None. Solo frasi brevi dette a lei (seconda persona)."""
    t = _t(text)
    if not t or len(t.split()) > 14:
        return None
    for kind, rx in (("voice", _C_VOICE), ("glitch", _C_GLITCH), ("wrong", _C_WRONG)):
        if rx.search(t):
            return kind
    return None


COMPLAINT_REPLIES = {
    "voice": ["Hai ragione, a volte la voce mi si taglia. Se ti sfugge qualcosa dimmi «ripeti» e lo ridico.", "Eh, lo so, ogni tanto mi mangio le parole. Dimmi «ripeti» e lo rifaccio con calma.",
              "Scusa, a volte la voce mi esce male. Se non ti torna, chiedimi di ripetere."],
    "glitch": ["Lo so, ogni tanto mi incarto. Dammi un attimo e riproviamo.", "Hai ragione, a volte mi blocco. Se succede, dimmi «hey Aria» e riparto.", "Eh, ogni tanto mi inceppo, scusa. Ci riprovo."],
    "wrong": ["Scusa, mi sa che mi sono persa. Me lo dici di nuovo con altre parole?", "Hai ragione, non ci sono arrivata. Riprova a dirmelo?", "Ops, ho frainteso. Ripetimelo, per favore?"],
}


# ---- risposte: corte, diverse, mai identiche due volte di fila
THANKS_REPLIES = ["Figurati!", "Di niente!", "Ma figurati, è un piacere.", "Quando vuoi.", "Prego!", "Ci mancherebbe.", "Con piacere!", "Ma di niente."]
LAUGH_REPLIES = ["Eh, ogni tanto mi riesce.", "Mi fa piacere farti ridere.", "Ah, ti è piaciuta.", "Dai, che bello sentirti ridere.", "Lo sapevo che ti avrebbe fatto ridere."]
REPEAT_PREFIX = ["Dicevo: ", "Ti ripeto: ", "Certo. ", "Ho detto: "]
UNCLEAR = ["Scusa, non ho capito bene. Puoi ripetere?", "Mmh, non ti ho sentito bene. Me lo ridici?", "Scusa, mi è sfuggito. Puoi ripetere?",
           "Non ho afferrato, riprova pure.", "Scusami, non ho capito: lo ripeti?"]
UNCLEAR_AGAIN = ["Continuo a non capire, scusa. Prova a dirlo con altre parole?", "Niente, non riesco a sentirti bene. Prova ad avvicinarti al microfono."]


def _pick(pool: list[str], last: str | None) -> str:
    options = [p for p in pool if p != last] or pool
    return random.choice(options)


def thanks_reply(last: str | None = None) -> str:
    return _pick(THANKS_REPLIES, last)


def complaint_reply(kind: str, last: str | None = None) -> str:
    return _pick(COMPLAINT_REPLIES[kind], last)


def laugh_reply(last: str | None = None) -> str:
    return _pick(LAUGH_REPLIES, last)


def repeat_reply(previous: str) -> str:
    return random.choice(REPEAT_PREFIX) + previous


def unclear_reply(times: int = 0, last: str | None = None) -> str:
    return _pick(UNCLEAR_AGAIN if times >= 1 else UNCLEAR, last)


def farewell_reply(now: dt.datetime | None = None, name: str | None = None, text: str = "", last: str | None = None) -> str:
    """Un congedo adatto al momento: «Buonanotte!» di notte, «Buona giornata!» al mattino, e se ha detto che va a dormire/uscire, una risposta su quello."""
    n = now or dt.datetime.now()
    t = _t(text)
    nm = f", {name}" if name else ""
    if re.search(r"\b(?:buonanotte|buona notte|vado a dormire)\b", t) or n.hour >= 23 or n.hour < 5:
        pool = [f"Buonanotte{nm}!", f"Dormi bene{nm}.", f"Buonanotte, a domani!", "Sogni d'oro!"]
    elif re.search(r"\bbuona serata\b", t) or 18 <= n.hour < 23:
        pool = [f"Buona serata{nm}!", f"A dopo{nm}!", "Ciao, a presto!", f"Ci sentiamo{nm}."]
    elif n.hour < 12:
        pool = [f"Buona giornata{nm}!", f"Ciao{nm}, a dopo!", "A presto!", f"Ci sentiamo{nm}."]
    else:
        pool = [f"Buon pomeriggio{nm}!", f"Ciao{nm}, a dopo!", "A presto!", f"Ci sentiamo{nm}."]
    return _pick(pool, last)


def greeting_and_name(now: dt.datetime | None = None) -> str:
    """La prima volta (o finche' non sa come ti chiami): si presenta e lo chiede, come si fa quando si conosce qualcuno."""
    n = now or dt.datetime.now()
    hello = "Buongiorno" if 5 <= n.hour < 12 else "Buonasera" if 18 <= n.hour < 23 else "Ciao"
    return random.choice([f"{hello}! Piacere, sono Aria. Tu come ti chiami?", f"{hello}, io sono Aria. E tu, come ti chiami?", f"Eccomi, sono Aria! Mi dici come ti chiami?"])


def greeting(now: dt.datetime | None = None, name: str | None = None, since_last_s: float | None = None, followup: str | None = None) -> str:
    """Il «ciao» con cui Aria risponde quando la chiami (solo «hey aria», senza una richiesta). Cambia con l'ora, col nome e con quanto e' passato."""
    n = now or dt.datetime.now()
    nm = f" {name}" if name else ""
    if followup:                                                                      # c'e' qualcosa di cui chiedere: lo fa subito, come un'amica
        return random.choice([f"Ehi{nm}! {followup}", f"Ciao{nm}! {followup}", f"Eccoti{nm}. {followup}"])
    if since_last_s is not None and since_last_s < 20 * 60:
        return random.choice(["Rieccomi!", f"Eccomi di nuovo{nm}.", "Dimmi pure.", "Sì, dimmi."])
    if n.hour >= 23 or n.hour < 5:
        return random.choice([f"Ehi{nm}, sei ancora in piedi? Dimmi.", f"Ciao{nm}. A quest'ora? Dimmi pure.", f"Eccomi{nm}, dimmi."])
    if n.hour < 12:
        return random.choice([f"Buongiorno{nm}!", f"Ciao{nm}, buongiorno!", f"Eccomi{nm}, buongiorno.", "Ciao! Dimmi pure."])
    if n.hour < 18:
        return random.choice([f"Ciao{nm}!", f"Eccomi{nm}, dimmi pure.", "Ciao! Dimmi.", f"Ehi{nm}, ciao!"])
    return random.choice([f"Buonasera{nm}!", f"Ciao{nm}, buonasera.", f"Eccomi{nm}, dimmi pure.", "Ciao! Dimmi pure."])


# ---- frasi lasciate a meta': «e poi…», «quindi, ehm,»: aspetta un attimo prima di rispondere
_TRAILING = {"e", "ma", "che", "di", "da", "in", "con", "per", "tra", "fra", "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "del", "dello", "della", "dei", "degli", "delle",
             "nel", "nello", "nella", "nei", "sul", "sullo", "sulla", "al", "allo", "alla", "ai", "alle", "cioe", "tipo", "allora", "quindi", "poi", "oppure", "anche", "mentre",
             "perche", "se", "quando", "come", "ehm", "eh", "mmm", "uhm", "cioè", "o", "ed", "a", "su", "dei", "del", "pero", "ovvero", "siccome", "dunque"}


def looks_unfinished(text: str) -> bool:
    """True se la trascrizione sembra interrotta a meta': finisce con una virgola o «…», oppure senza punto e con una parola che di solito ne introduce un'altra."""
    t = (text or "").strip()
    if not t or len(t.split()) < 2:
        return False
    if t.endswith(("?", "!")):
        return False
    if t.endswith((",", "…", "...", ";", ":", "-")):
        return True
    if t.endswith("."):
        return False
    last = normalize(t).split()[-1] if normalize(t).split() else ""
    return last in _TRAILING
