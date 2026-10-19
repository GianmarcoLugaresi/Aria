"""Le «note di regia» per ogni risposta: come sta l'altro, quanto lungo rispondere, come non ripetersi.

Un modello piccolo, lasciato a se' stesso, comincia sempre allo stesso modo, chiude sempre con una domanda e risponde con la stessa lunghezza a tutto.
Qui si guarda cosa e' appena successo (la sua frase, le ultime risposte di Aria) e si danno al modello poche indicazioni mirate, solo per quel turno.
"""
from __future__ import annotations

import datetime as dt
import random
import re
import zlib

from . import rhythm
from .textutil import normalize

_MOODS: list[tuple[str, re.Pattern, str]] = [
    ("malato", re.compile(r"\b(?:mal di (?:testa|pancia|gola|schiena|denti)|febbre|raffreddor\w+|influenza|ho la tosse|sto male|mi fa male|sono malat\w+|mi sento male|nausea)\b"),
     "Non sta bene fisicamente: sii premurosa e breve, con un pensiero gentile. Niente diagnosi."),
    ("triste", re.compile(r"\b(?:triste|giu di morale|mi sento giu|depress\w+|piango|mi manca\w*|malinconi\w+|ho il magone|sconfort\w+|mi sento (?:solo|sola)|sono (?:solo|sola)|solitudine|mi sento vuot\w+)\b"),
     "Ha il morale a terra: rallenta, ascolta, una frase calda e vera. Non sdrammatizzare e non dare consigli se non li chiede."),
    ("arrabbiato", re.compile(r"\b(?:arrabbiat\w+|incazzat\w+|furios\w+|che rabbia|odio|stuf[oa]|non ne posso piu|seccat\w+|irritat\w+|mi ha fatto arrabbiare|mi sta sul|non sopporto)\b"),
     "Ha rabbia addosso: stai dalla sua parte con calma, in due frasi; dagli ragione dove puoi, niente prediche e niente «però»."),
    ("insonnia", re.compile(r"\b(?:non riesco a (?:dormire|addormentarmi|prendere sonno)|non prendo sonno|sono sveglio|sono sveglia|ho perso il sonno|insonnia|mi giro nel letto)\b"),
     "Non riesce a dormire: voce bassa e calma, poche parole, niente consigli da manuale. Stagli vicino."),
    ("ansioso", re.compile(r"\b(?:ansi[ao]\w*|agitat\w+|preoccupat\w+|ho paura|panico|stressat\w+|sono teso|sono tesa|ho un esame|ho un colloquio|ho il colloquio|ho l esame|domani ho un)\b"),
     "Ha un po' d'ansia addosso: voce calma e rassicurante, concreta; non minimizzare («vedrai che va bene» a vuoto) e non fare l'elenco dei consigli."),
    ("stanco", re.compile(r"\b(?:stanc\w+|esaust\w+|distrutt\w+|a pezzi|sfinit\w+|non ce la faccio|ho sonno|dormito poco|giornata pesante|giornataccia|riunioni tutto il giorno|sono morto|sono morta|non ne ho piu)\b"),
     "Ha poche energie, è una giornata pesante: sii dolce, due frasi calde che riconoscono la fatica con parole tue. Niente consigli a raffica e nessun elenco."),
    ("contento", re.compile(r"\b(?:contento|contenta|felice|bellissim\w+|fantastic\w+|ho vinto|ce l ho fatta|promoss\w+|ho passato|ho preso (?:\w+ )?(?:trenta|ventotto|ventisette|trentuno|30|28)|settimo cielo|che bella notizia|evviva|finalmente|ottima notizia|entusiast\w+|non vedo l ora|emozionat\w+|sono al top|giornata bellissima)\b"),
     "Ha una bella notizia o è su di giri: festeggia con entusiasmo vero, a modo tuo, e se ti viene chiedi un dettaglio."),
    ("annoiato", re.compile(r"\b(?:mi annoio|che noia|non so che fare|non ho niente da fare|sono annoiat\w+)\b"),
     "Si annoia: butta lì una cosa leggera o curiosa da raccontare o da fare insieme."),
]

_QUESTION_WORDS = re.compile(r"^(?:che cos|cos e|cosa e|come funziona|come mai|perche|spiegami|raccontami|dimmi di|parlami di|qual e la differenza|differenza tra|quando e|chi era|chi e stato|cosa significa|cosa vuol dire|a cosa serve)")

# ---- risposte LUNGHE: spiegazioni, ricette, «parlami di…», «fammi delle domande». Di solito Aria e' breve (e' una chiacchierata a voce), ma se glielo chiedi deve distendersi.
_LONG_QUIZ = re.compile(r"\b(?:fammi (?:delle |qualche |un po di |due |tre )?domande|fammi un quiz|interrogami|intervistami|chiedimi (?:qualcosa|delle cose|cose|pure)|fai(?:mi)? tu (?:le )?domande|"
                        r"giochiamo a (?:indovinelli|domande|quiz)|fammi indovinare|fammi un indovinello|quiz)\b")
_LONG_EXPLAIN = re.compile(r"\b(?:spiegami|spiegamelo|spiegarmi|raccontami|raccontamelo|parlami|dimmi tutto|dimmi di piu|dimmi qualcosa di piu|approfondisci|approfondiamo|in dettaglio|nel dettaglio|"
                           r"passo passo|come si prepara|come si cucina|descrivimi|illustrami|fammi capire|insegnami|dimmi qualcosa di interessante|qualcosa di interessante|intrattienimi|parla tu|"
                           r"parlami tu|raccontami qualcosa|spiegazione)\b|\b(?:dimmi|dammi|inventa\w*|leggimi)\b.*\b(?:una storia|una favola|una fiaba|una curiosita)\b")
_LONG_RECIPE = re.compile(r"\b(?:dimmi|dammi|dai|dici|passami|fammi|suggeriscimi|proponi\w*|insegnami|vorrei|voglio|hai|conosci|sai|cercami|mi serve|ho bisogno)\b.*\bricett[ae]\b")
_LONG_CONT = re.compile(r"^(?:e poi|e quindi|continua|vai avanti|vai pure|dimmi altro|vai con il resto|prosegui|continua pure)\s*$")


# «senza manco spiegarmi perché», «non mi ha dato nessuna spiegazione»: lo sta raccontando, non lo sta chiedendo
_NARRATED = re.compile(r"\b(?:senza|non|nessun[ao]?|manco|nemmeno|neanche|mai|ne)\b[^.?!]{0,25}\b(?:spiegarmi|spiegarmelo|spiegazione|spiegazioni|spiegato|raccontarmi|parlarmi)\b")


def long_kind(text: str) -> str | None:
    """«quiz» (vuole che sia lei a fargli domande), «explain» (spiegare, raccontare, una ricetta, parlare di qualcosa a lungo) oppure None (chiacchiera: poche parole)."""
    t = normalize(text)
    if not t:
        return None
    if _LONG_QUIZ.search(t):
        return "quiz"
    if _NARRATED.search(t) and not _LONG_RECIPE.search(t) and not re.match(r"^(?:spiegami|raccontami|parlami|dimmi)\b", t):
        return None
    if (_LONG_EXPLAIN.search(t) or _LONG_RECIPE.search(t) or _LONG_CONT.match(t)) and not re.search(r"\b(?:in breve|in poche parole|brevemente|riassumi|riassunto|in una frase)\b", t):
        return "explain"
    return None


# l'umore con cui Aria si presenta in una giornata: la fa sembrare viva, non una macchina uguale a se' stessa ogni giorno
TONES = ["Oggi sei di buonumore e un po' giocherellona.", "Oggi sei pacata e riflessiva, con la voce di chi ha tempo.", "Oggi sei curiosa di tutto, fai domande strane e simpatiche.",
         "Oggi sei tenera e un po' coccolona.", "Oggi sei ironica e pronta alla battuta, ma sempre gentile.", "Oggi sei serena, di poche parole ma calda.",
         "Oggi sei vivace e piena di energia."]


def detect_mood(text: str) -> str | None:
    t = normalize(text)
    for name, rx, _hint in _MOODS:
        if rx.search(t):
            return name
    return None


def mood_hint(mood: str | None) -> str:
    for name, _rx, hint in _MOODS:
        if name == mood:
            return hint
    return ""


def session_tone(now: dt.datetime | None = None, salt: str = "") -> str:
    n = now or dt.datetime.now()
    return TONES[zlib.crc32(f"{n.date().isoformat()}{salt}".encode()) % len(TONES)]


def _assistant_texts(history: list[dict]) -> list[str]:
    return [m["content"].strip() for m in history if m.get("role") == "assistant" and m.get("content", "").strip()]


def _first_word(text: str) -> str:
    m = re.match(r"[^\wÀ-ÿ]*([\wÀ-ÿ']+)", text)
    return m.group(1).lower() if m else ""


def ends_with_question(text: str) -> bool:
    return text.rstrip().endswith("?")


def turn_hint(history: list[dict], user_text: str, gender: str | None = None, examples: bool = True, turn: "rhythm.Turn | None" = None) -> str:
    """Poche righe per QUESTO turno, da aggiungere in fondo al prompt di sistema (con due esempi del tono giusto per la situazione).
    `turn` e' la mossa decisa da rhythm.plan (parere, spiega, risonanza, traino, attrito): se c'e', sostituisce le note generiche su lunghezza e domande."""
    notes: list[str] = []
    words = len(user_text.split())
    kind = None if turn else long_kind(user_text)
    if kind == "quiz":
        gnote = ("Parli con un uomo: usa il maschile per lui." if gender == "m" else "Parli con una donna: usa il femminile per lei." if gender == "f" else "Non sai se è un uomo o una donna: evita aggettivi che lo dicano.")
        return ("Per questa risposta: ti chiede di fargli delle domande. Falle UNA domanda alla volta, interessante e specifica, e poi aspetta la sua risposta (non fare elenchi di domande). "
                "Se ti ha appena risposto a una tua domanda, commentala con una frase calda e poi fai la prossima. " + gnote)
    if kind == "explain":
        gnote = ("Parli con un uomo: usa il maschile per lui." if gender == "m" else "Parli con una donna: usa il femminile per lei." if gender == "f" else "Non sai se è un uomo o una donna: evita aggettivi che lo dicano.")
        return ("Per questa risposta fai un'ECCEZIONE alla regola delle poche parole: ti chiede di spiegare, raccontare o parlare di qualcosa, quindi rispondi per ESTESO, "
                "con dieci o quindici frasi parlate BREVI (al massimo venti parole ciascuna, mai una frase lunga con tante virgole), un'idea o un passaggio per frase, in ordine («prima», «poi», «infine»), in italiano semplice, da amica che sa le cose. "
                "Tutto a voce: niente elenchi puntati, niente numeri di punto elenco, niente asterischi, niente titoli. Se è una ricetta di' prima gli ingredienti con le quantità a parole, poi i passaggi, "
                "poi un consiglio finale. Racconta solo cose che sai davvero, senza inventare esperienze tue. Non fare domande finché non hai detto tutto. " + gnote)
    mood = None if turn else detect_mood(user_text)
    if turn:
        notes.append(rhythm.hint(turn))
    if mood:
        notes.append(mood_hint(mood))
        from . import examples as ex
        r = ex.reflex(user_text, mood) if not any(m.get("role") == "assistant" and m.get("content", "").startswith(r_) for m in history[-2:] for r_ in sum(ex.REFLEX.values(), [])) else None
        if r:                                                                      # niente apertura "a stampo" due turni di fila
            notes.append(f"Comincia la risposta esattamente con queste parole: «{r}». Poi UNA sola frase, che mostri che hai ascoltato un dettaglio di quello che ha detto.")
    t = normalize(user_text)
    if not mood and not turn:
        if _QUESTION_WORDS.match(t):
            notes.append("Ti chiede di spiegare o raccontare: rispondi chiaro in tre o quattro frasi parlate, da amica che sa le cose, non da enciclopedia.")
        elif words <= 3:
            notes.append("Ha detto poche parole: rispondi con una frase breve ma calda, non una parola sola.")
        elif words >= 28:
            notes.append("Ha parlato a lungo: fagli capire che hai ascoltato riprendendo UN dettaglio preciso di quello che ha detto, senza riassumere tutto.")
        else:
            notes.append("Rispondi in una o due frasi.")
    from . import dialog
    if dialog.is_ack(user_text):
        notes.append("Ha risposto solo «ok»: non insistere, una frase breve e calda, senza nuove domande.")
    prev = _assistant_texts(history)
    recent = prev[-3:]
    if turn:
        pass                                                                       # la regola sulle domande e' gia' dentro la mossa
    elif recent and ends_with_question(recent[-1]):
        notes.append("Nella tua risposta precedente hai fatto una domanda: stavolta NON farne, chiudi con un'affermazione o un pensiero tuo.")
    elif len(recent) >= 2 and sum(ends_with_question(r) for r in recent) >= 2:
        notes.append("Hai fatto troppe domande di fila: niente domanda in questa risposta.")
    openers = [w for w in (_first_word(r) for r in prev[-2:]) if w]
    if openers:
        notes.append("Non cominciare con " + " né con ".join(f"«{w}»" for w in dict.fromkeys(openers)) + ": cambia attacco.")
    if mood not in ("triste", "malato", "arrabbiato", "ansioso", "insonnia") and not turn and random.random() < 0.25:
        notes.append("Se ti viene naturale, comincia con un piccolo intercalare («" + random.choice(["ah", "eh", "beh", "mmh", "ecco", "dai", "oh"]) + "») invece che con una parola qualunque.")
    if gender in ("m", "f"):
        notes.append("Parli con " + ("un uomo: usa il maschile per lui." if gender == "m" else "una donna: usa il femminile per lei."))
    else:
        notes.append("Non sai se è un uomo o una donna: evita aggettivi che lo dicano (stanco/stanca, contento/contenta), usa giri neutri.")
    out = "Per questa risposta: " + " ".join(notes)
    if examples:
        from . import examples as ex
        shown = ex.render(ex.pick_mode(turn.shots) if turn else ex.pick(user_text, mood))
        if shown:
            out += "\n" + shown
    return out


# ---- ripulire quello che esce dal chatbot, prima della voce
_BOILERPLATE = re.compile(r"^(?:certamente|assolutamente|ottima domanda|bella domanda|ma certo|sicuramente|capisco perfettamente|comprendo|come assistente[^.!?]*|come intelligenza artificiale[^.!?]*)[,!.:]?\s+", re.I)
_LABEL = re.compile(r"^\s*(?:aria|assistente|risposta|tu)\s*:\s*", re.I)


_ENGLISH = [(re.compile(r"\bwow\b[!,]?", re.I), "Caspita"), (re.compile(r"\bhey\b", re.I), "ehi"), (re.compile(r"\bhello\b", re.I), "ciao"), (re.compile(r"\bokay\b|\bok\b", re.I), "va bene"),
            (re.compile(r"\bwell\b", re.I), "beh"), (re.compile(r"\bsorry\b", re.I), "scusa"), (re.compile(r"\bthanks\b", re.I), "grazie"), (re.compile(r"\bno problem\b", re.I), "nessun problema"),
            (re.compile(r"\bnice\b", re.I), "bello"), (re.compile(r"\bgood\b", re.I), "bene"), (re.compile(r"\byes\b", re.I), "sì")]
_ASSISTANT_TAIL = re.compile(r"\s*(?:facci|fammi|dimmi se)\s+(?:sapere\s+)?se\s+(?:hai|ti|c'è|serve)[^.!?]*[.!?]?\s*$", re.I)


def strip_markdown(text: str) -> str:
    """Elenchi puntati, grassetti, titoli: a voce non si leggono. Via i simboli; le voci di un elenco diventano frasi."""
    t = re.sub(r"(?<![\w*])\*(?!\*)[^*\n]{18,}?(?<!\*)\*(?![\w*])", " ", text)       # «*La voce si abbassa, calda e morbida*»: una didascalia, non si dice (le enfasi sono di 1-3 parole)
    t = re.sub(r"\((?:[^()\n]{0,3}\s)?(?:sorride|ride|sospira|annuisce|ridacchia|pausa|silenzio|con voce|in tono|a bassa voce|sottovoce)[^()\n]*\)", " ", t, flags=re.I)
    t = re.sub(r"\*\*|__|`", "", t)
    t = re.sub(r"(?<![\w*])\*(?!\*)([^*\n]+?)(?<!\*)\*(?![\w*])", r"\1", t)                   # *enfasi* -> enfasi
    t = re.sub(r"(?m)^\s*#+\s*", "", t)
    t = re.sub(r"(?m)^\s*(?:[-*•]|\d{1,2}[.)])\s+", "", t)
    t = re.sub(r"(?<=[^.!?…:;,\s])[ \t]*\n+[ \t]*", ". ", t)               # a capo senza punteggiatura -> punto
    t = re.sub(r"\s*\n+\s*", " ", t)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"^[.,;:\s]+", "", t)).strip()                                          # (resta un punto davanti se la frase era tutta una didascalia)


def clean_reply(text: str) -> str:
    """Toglie le etichette («Aria:»), le formule da assistente con cui i modelli piccoli aprono o chiudono una risposta e le parole inglesi."""
    t = _LABEL.sub("", text)
    t = re.sub(r"(?:(?<=…)|(?<=\.\.\.)|^)\s*(?:sospira|sorride|ridacchia|annuisce|fa una pausa|fa spallucce)\b[.,…]*\s*", " ", t, flags=re.I).strip() or t      # «Domani… sospira Ma davvero?»
    for rx, rep in _ENGLISH:
        t = rx.sub(lambda m, rep=rep: rep.capitalize() if m.group(0)[:1].isupper() else rep, t)
    t = _ASSISTANT_TAIL.sub("", t) or t
    for _ in range(2):
        t2 = _BOILERPLATE.sub("", t)
        if t2 == t or not t2.strip():
            break
        t = t2[:1].upper() + t2[1:]
    return t


# ---- l'italiano da tema scolastico e le chiusure da assistente/psicologo, a ogni frase (clean_reply guarda solo la prima: qui si guarda tutto)
_OPENER_SENTENCE = re.compile(r"^(?:capisco (?:bene |perfettamente )?come ti senti|comprendo (?:bene |perfettamente )?come ti senti|mi dispiace (?:molto )?(?:sentire|sapere) che[^.!?]*|domanda interessante|con piacere|ecco (?:a te|qui)(?: un riassunto)?)[.!:,]?\s*", re.I)
_CLOSER_SENTENCE = re.compile(
    r"^(?:spero (?:che )?(?:questo|questa|la risposta|ti)[^.!?]*|fammi sapere[^.!?]*|facci sapere[^.!?]*|"
    r"(?:io )?(?:sono|resto|rimango) qui(?: (?:per te|ad ascoltarti|con te|se[^.!?]*|quando[^.!?]*))?|io ci sono(?:,? se[^.!?]*)?|ci sono io,? se[^.!?]*|"
    r"se (?:ti va|vuoi|hai voglia|senti il bisogno)[^.!?]{0,60}(?:parlarne|sfogarti|raccontarmi|dirmi|chiacchierare|parlare|aggiungere|dirmelo)[^.!?]*|"
    r"(?:se (?:ti va|vuoi|hai voglia|senti il bisogno)|quando vuoi)[^.!?]{0,60},?\s*(?:io )?(?:ci sono|sono qui|ti ascolto)[^.!?]*|"
    r"ti ascolto|sono qui ad ascoltarti|come ti fa sentire (?:tutto )?questo|tu cosa ne pensi a riguardo|qual è la tua opinione in merito|c'è altro in cui posso aiutarti(?: oggi)?)[.!?…]*$", re.I)
_BUROCRATESE = [(re.compile(r"\bInoltre,\s*"), "E poi "), (re.compile(r"\bTuttavia,\s*"), "Però "), (re.compile(r"\bCiononostante,\s*"), "Comunque "), (re.compile(r"\bPertanto,\s*"), "Quindi "),
                (re.compile(r"\bIn conclusione,\s*", re.I), "Alla fine "), (re.compile(r"\bIn sintesi,\s*", re.I), "In soldoni, "), (re.compile(r"\bPer quanto riguarda\s+"), "Su "),
                (re.compile(r"\bÈ importante sottolineare che\s+", re.I), "Conta che "), (re.compile(r"\bVale la pena notare che\s+", re.I), "Tra l'altro "),
                (re.compile(r"\bcruciale\b"), "decisivo"), (re.compile(r"\bsfaccettato\b"), "complesso"), (re.compile(r"\bimmergiamoci\b"), "entriamo"),
                (re.compile(r"\bnavigare questa situazione\b"), "uscirne")]


def polish(text: str, prior: bool = False) -> str:
    """Per ogni frase: via i connettivi da tema («Inoltre,» -> «E poi»), via le frasi-formula da assistente o da psicologo («sono qui se vuoi parlarne»,
    «mi dispiace sentire che…») purche' resti altro da dire. `prior`: qualcosa e' gia' stato detto prima di questo pezzo."""
    parts = [p for p in re.split(r"(?<=[.!?…])\s+", text.strip()) if p]
    out: list[str] = []
    for i, p in enumerate(parts):
        p2 = _OPENER_SENTENCE.sub("", p).strip() if not prior and not out else p
        if p2 != p:
            p = (p2[:1].upper() + p2[1:]) if p2 else ""
            if not p:
                continue
        if _CLOSER_SENTENCE.match(p.strip()) and (prior or out or any(not _CLOSER_SENTENCE.match(q.strip()) for q in parts[i + 1:])):
            continue                                                         # chiusura di cortesia: non e' mai la cosa piu' importante (se dopo c'e' dell'altro, nemmeno in testa)
        for rx, rep in _BUROCRATESE:
            p = rx.sub(rep, p)
        out.append(p)
    return " ".join(out) if out else text


# ---- esperienze e curiosita' inventate: «ho letto che…», «stavo sistemando i fili…» (un'IA non fa cose mentre l'utente non c'e')
_FABRICATED = re.compile(r"\bho (?:appena )?(?:letto|scoperto|sentito dire|sentito che|visto|trovato|mangiato|bevuto|dormito|guardato)\b|\bmentre (?:ti )?aspettavo\b|"
                         r"\bstavo (?:giusto )?(?:sistemando|leggendo|guardando|pensando|ascoltando|cercando)\b|\bieri sera (?:ho|sono)\b|\bil mio (?:weekend|fine settimana)\b|\bmi (?:hanno|è stato) (?:detto|raccontato)\b", re.I)
# «Fatto! Ho aggiunto il latte alla lista»: se nessuno strumento e' partito, il chatbot sta mentendo. Meglio dirlo che far finta.
_CLAIM = re.compile(r"\b(?:ho|l ho|te l ho|gliel ho)\s+(?:appena\s+|gia\s+)?(?:aggiunto|aggiunta|creato|creata|impostato|impostata|aperto|aperta|salvato|salvata|segnato|segnata|programmato|programmata|eseguito|eseguita|avviato|avviata|inviato|mandato|attivato|fissato|prenotato|acceso|spento|messo\s+(?:in|il|la|un|una|su)|scritto\s+(?:il|la|un|una))\b|^\s*fatto\b|\b(?:va bene|ok|certo|perfetto|subito)[,!.]?\s+(?:fatto|ci penso io|lo faccio|la faccio|provvedo)\b|\bfatto[!.]|\btutto impostato\b|\bti ricordiamo\b|\bte lo ricordo\b|\bti ricorder[oò]\b|\b(?:sveglia|timer|promemoria|evento|appuntamento|nota|lista|musica|volume)\s+(?:e\s+)?(?:stat[oa]\s+)?(?:impostat|creat|aggiunt|segnat|salvat|mess|fissat|abbassat|alzat|avviat|partit)[oae]\b|\bpromemoria (?:creato|impostato)\b|\b(?:e|è)\s+stat[oa]\s+(?:aggiunt|creat|impostat|salvat|segnat)[oa]\b", re.I)
_CLAIM_NOW = re.compile(r"\b(?:metto|scrivo|salvo|creo|preparo|aggiungo|segno|ti scrivo|te l[ao] scrivo|te l[ao] salvo|ti salvo|ti preparo|ti metto|ti aggiungo)\b[^.!?]{0,70}\b(?:nella tua cartella|nella cartella|in un file|nel file|nella lista|in calendario|nel calendario|nei promemoria|nelle note)\b|"
                        r"\b(?:e|è|sono)\s+(?:gia\s+)?(?:pronta|pronto|pronte|pronti)\s+per\s+essere\s+(?:consultat\w+|lett\w+|salvat\w+)\b", re.I)
# i file: «Ti scrivo subito la ricetta nel tuo file», «Ho messo tutto nella cartella, puoi controllare»: se non e' partito lo strumento della cartella, e' una bugia (testo gia' normalizzato)
_CLAIM_FILE = re.compile(r"\b(?:scrivo|salvo|metto|creo|preparo|butto|carico|aggiungo|copio)\b[^.!?]{0,80}\b(?:file|cartella|documento)\b|"
                         r"\b(?:ho|l ho|te l ho|gliel ho|abbiamo)\s+(?:appena\s+|gia\s+)?(?:mess\w+|scritt\w+|salvat\w+|copiat\w+|inserit\w+|creat\w+|caricat\w+|buttat\w+|preparat\w+)\b[^.!?]{0,80}\b(?:file|cartella|documento)\b|"
                         r"\b(?:sto|la sto|lo sto|ti sto)\s+(?:scrivendo|salvando|mettendo|creando|preparando|caricando)\b|\bin fase di (?:caricamento|scrittura|salvataggio)\b|"
                         r"\b(?:e|sono)\s+(?:gia\s+)?(?:nella|nel|dentro)\s+(?:tua\s+)?(?:cartella|file)\b|\bpuoi (?:controllare|vedere|guardare|trovarl[oa]|aprirl[oa])\b[^.!?]{0,40}\b(?:cartella|file)\b")
# lo schermo: «Ti indico subito dove compare «Somnium»», «e' proprio li' che appare il riquadro luminoso»: se non e' partito SCHERMO e' una bugia (testo gia' normalizzato)
_CLAIM_SCREEN = re.compile(r"\bti (?:indico|segno|evidenzio)\b|\b(?:ti\s+)?(?:indico|segno|evidenzio|mostro)\b[^.!?]{0,70}\b(?:schermo|riquadro|scritta|parola|compare|dove)\b|\briquadro luminoso\b|\bho (?:evidenziato|indicato|segnato)\b|\be proprio li\b")
_FACT_PUSH = re.compile(r"\b(?:sai che|sapevi che|una cosa curiosa|ti dico una cosa|ti racconto una cosa)\b", re.I)
_WANTS_FACTS = re.compile(r"\b(?:curios\w*|raccontami|dimmi qualcosa|lo sapevi|qualcosa di strano|qualcosa che non so|fatto interessante|e gli altri|spiegami|che cos|cos e|come funziona|perche)\b")


def wants_facts(user_text: str) -> bool:
    return bool(_WANTS_FACTS.search(normalize(user_text)))


def has_false_claim(text: str) -> bool:
    return bool(_CLAIM.search(text) or _CLAIM_NOW.search(text) or _CLAIM_FILE.search(normalize(text)) or _CLAIM_SCREEN.search(normalize(text)))


NOT_UNDERSTOOD = "Non ho capito bene cosa volevi che facessi. Prova a dirmelo in modo più semplice, ad esempio: ricordami domani alle nove di chiamare Mario."


def strip_vocative(text: str, name: str) -> str:
    """Toglie il nome dell'utente quando e' solo un'appellativo («Ciao Mario!», «Certo che si', Mario.», «Mario, a volte…»): una persona non ripete il nome a ogni frase,
    e il chatbot, anche se glielo si dice, lo mette in meta' delle risposte."""
    if not name:
        return text
    n = re.escape(name)
    end = r"(?=\s*[.!?…,;:]|\s*$)"
    t = re.sub(rf"\s*,\s*{n}{end}", "", text)                                   # «Certo che sì, Mario!» -> «Certo che sì!»
    t = re.sub(rf"\s+{n}{end}", "", t)                                           # «Ciao Mario!» -> «Ciao!»
    t = re.sub(rf"(^|(?<=[.!?…]\s)){n}\s*,\s*", r"\1", t)                      # «Mario, a volte…» -> «A volte…»
    t = t.strip()
    if t and text[:1].isupper() and t[0].islower():
        t = t[0].upper() + t[1:]
    return t


def drop_fabrications(chunk: str, user_text: str) -> str:
    """Toglie dalle frasi di Aria quelle in cui racconta cose che non puo' aver fatto, e le «curiosita'» non richieste. Se la persona le ha chieste restano."""
    keep_facts = wants_facts(user_text)
    out = []
    for sent in re.split(r"(?<=[.!?…])\s+", chunk.strip()):
        if not sent:
            continue
        if _FABRICATED.search(sent) or has_false_claim(sent) or (not keep_facts and _FACT_PUSH.search(sent)):
            continue
        out.append(sent)
    return " ".join(out)
