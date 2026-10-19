"""Il chatbot come ULTIMA rete per capire una richiesta d'azione che le regole (intent.py) non hanno riconosciuto.

Perche' non sempre: le regole sono istantanee, precise e non inventano. Ma una persona puo' dire una cosa in mille modi: quando una frase ha tutta l'aria
di una richiesta («metti…», «crea…» + promemoria, musica, volume…) e nessuna regola l'ha capita, si chiede al chatbot di «decodificarla» in UNA riga:

    STRUMENTO | argomento          oppure          NESSUNO

Garanzie:
  - il chatbot vede SOLO la frase dell'utente (mai testi trovati sul web o nei documenti): non c'e' modo di far impartire ordini da un contenuto altrui;
  - puo' scegliere solo tra gli strumenti elencati qui, e il risultato passa dagli stessi strumenti di sempre (conferme, domande, limiti compresi);
  - l'argomento deve essere FATTO DI PAROLE E NUMERI DETTI DALL'UTENTE (`grounded`): un orario, un nome o una data che il modello si inventa
    («domani alle 10 per il caffe'», mai chiesto) fanno scartare la risposta, e Aria dice onestamente che non ha capito.
"""
from __future__ import annotations

import re

from .speech import num_words
from .textutil import ToolCall, normalize

# gli strumenti che si possono ottenere da una frase libera. Tutti passano dagli stessi strumenti di sempre (conferme, domande, limiti): il decodificatore sceglie solo QUALE
ALLOWED = {"PROMEMORIA", "EVENTO", "AGENDA", "TIMER", "MUSICA", "VOLUME", "APRI_APP", "WEB", "MAPPA", "LISTA", "NOTA", "SCRIVI", "RICERCA", "BRIEFING", "PROMEMORIA_LISTA",
           "METEO", "ORA", "CALCOLA", "SCHERMO", "NON_SO", "LEGGI", "RIASSUMI", "ELENCO", "SISTEMA", "TIMER_STATO", "TIMER_ANNULLA", "CONVERTI", "DATA", "CASO", "AIUTO"}

SYSTEM = """Sei il decodificatore di comandi di un assistente vocale italiano. Ricevi UNA frase detta a voce (puo' avere errori del riconoscimento vocale) e rispondi con UNA riga sola:
STRUMENTO | argomento
oppure
NESSUNO
se la frase NON e' una richiesta di fare una di queste cose (chiacchiera, domanda di cultura generale, opinione, racconto, sfogo).

Strumenti e argomento:
PROMEMORIA | quando e cosa, con le parole dette
EVENTO | cosa, giorno e ora (calendario)
AGENDA | il giorno (oggi, domani, lunedi, settimana)
TIMER | durata o ora | nome
TIMER_STATO | (quanto manca al timer, che timer ho attivi)
TIMER_ANNULLA | nome del timer, oppure tutti (annullare, fermare, togliere un timer o una sveglia)
METEO | luogo e giorno detti (anche vuoto)
ORA | ora oppure data
CALCOLA | l'operazione con cifre e simboli (15*16, 350*20/100)
CONVERTI | (conversione tra unita' di misura: chilometri e miglia, chili e libbre, gradi Celsius e Fahrenheit, litri e galloni…)
DATA | (calcoli con le date: quanti giorni mancano a una festa o a una data, che giorno sara' tra tot giorni, quando cade Pasqua, che giorno della settimana e' una data)
CASO | (tirare un dado, lanciare una moneta, scegliere un numero o una cosa a caso)
AIUTO | (che cosa sa fare l'assistente, come si usa, aiuto)
MUSICA | play, pause, next, previous, now, track:<titolo/artista/genere>
VOLUME | up, down, mute, unmute, set:<0-100>, get
APRI_APP | nome dell'app o del sito
WEB | motore (youtube, google, amazon, wikipedia) | cosa cercare
MAPPA | il luogo (anche «farmacia vicino a me»)
LISTA | nome della lista | voce
NOTA | testo della nota
SCRIVI | tipo di testo | argomento (scrivere un documento nella cartella)
RICERCA | argomento (ricerca approfondita)
LEGGI | nome del file
RIASSUMI | nome del file
ELENCO |
SISTEMA | batteria, spazio, versione, accensione, wifi, ip, memoria (informazioni sul Mac)
BRIEFING |
PROMEMORIA_LISTA |
SCHERMO | uno tra: dove|<scritta o pulsante cercato> (indicare/trovare qualcosa sullo schermo), leggi| (guarda/leggi lo schermo), parere|<la frase> (domande su quello che si vede: riassumi, traduci, spiega questo errore, cosa ne pensi), indica|
NON_SO | call (telefonare), message (messaggi, whatsapp, mail), home (luci, tv, riscaldamento), buy (ordinare, prenotare, comprare), print (stampare), download (scaricare, installare), system (wifi, bluetooth, luminosita, riavvio), media (foto, video, registrazioni), share (condividere, pubblicare), files (spostare, copiare, cancellare file), app (chiudere app), money (pagamenti), inbox (leggere mail o messaggi)

Regole: nell'argomento usa SOLO parole e numeri detti nella frase, non inventare mai date, orari, nomi o motivi; se manca un dato lascialo mancare. Una sola riga.

Frase: prova a creare un promemoria per domani
PROMEMORIA | domani
Frase: mi segni in calendario il dentista giovedi alle quindici
EVENTO | giovedi alle quindici dentista
Frase: che impegni ho domani
AGENDA | domani
Frase: domani cosa mi aspetta
AGENDA | domani
Frase: metti della musica rilassante
MUSICA | track:rilassante
Frase: mettila in pausa
MUSICA | pause
Frase: piu forte
VOLUME | up
Frase: silenzia il computer
VOLUME | mute
Frase: aprimi la calcolatrice
APRI_APP | calcolatrice
Frase: cerca su youtube tutorial di chitarra
WEB | youtube | tutorial di chitarra
Frase: dov'e la farmacia piu vicina
MAPPA | farmacia vicino a me
Frase: aggiungi le uova alla spesa
LISTA | della spesa|le uova
Frase: segna una nota: comprare le pile
NOTA | comprare le pile
Frase: svegliami alle sette
TIMER | alle sette
Frase: dimmi com'e il clima oggi
METEO | oggi
Frase: a che ora siamo arrivati
ORA | ora
Frase: quanto viene il venti per cento di trecentocinquanta
CALCOLA | 350*20/100
Frase: scrivimi una poesia sul mare
SCRIVI | poesia|mare
Frase: dove trovo il tasto per condividere
SCHERMO | dove|condividere
Frase: su quale icona devo cliccare per le impostazioni
SCHERMO | dove|impostazioni
Frase: dai un'occhiata a cosa sto facendo
SCHERMO | leggi|
Frase: mi spieghi cosa significa questo errore
SCHERMO | parere|mi spieghi cosa significa questo errore
Frase: quanta carica mi resta
SISTEMA | batteria
Frase: chiama mia madre
NON_SO | call
Frase: manda un messaggio a Luca
NON_SO | message
Frase: accendi la luce del bagno
NON_SO | home
Frase: che bella giornata oggi
NESSUNO
Frase: mi piace la musica jazz
NESSUNO
Frase: mi racconti una barzelletta
NESSUNO
Frase: domani ho un esame e sono agitato
NESSUNO
Frase: chi ha scritto i promessi sposi
NESSUNO"""

_LINE = re.compile(r"^\s*([A-Z_]+)\s*(?:\|\s*(.*))?$")


def prompt(text: str) -> tuple[str, str]:
    return SYSTEM, f"Frase: {text.strip()}"


def parse(output: str) -> ToolCall | None:
    """La prima riga utile della risposta -> ToolCall, oppure None (NESSUNO, formato strano, strumento non ammesso)."""
    for line in (output or "").strip().splitlines():
        line = line.strip().strip("`*«»\"")
        if not line:
            continue
        line = re.sub(r"^(?:risposta|output)\s*:\s*", "", line, flags=re.I)
        m = _LINE.match(line)
        if not m:
            return None
        name = m.group(1).upper()
        if name not in ALLOWED:
            return None
        return ToolCall(name, (m.group(2) or "").strip())
    return None


_STRUCT = {"track", "playlist", "set", "play", "pause", "next", "previous", "now", "up", "down", "mute", "unmute", "get", "della", "spesa", "youtube", "google", "amazon", "wikipedia"}
_NUM = re.compile(r"\d+")


def _norm_with_numbers(text: str) -> str:
    """Il testo dell'utente normalizzato, con in piu' i numeri a cifre scritti anche a parole («10» -> «dieci»): cosi' il confronto non dipende da come li ha scritti Whisper."""
    t = normalize(text)
    extra = " ".join(num_words(int(n)) for n in _NUM.findall(t) if len(n) <= 6)
    return t + " " + extra


def grounded(call: ToolCall, user_text: str) -> bool:
    """True se l'argomento e' fatto di parole e numeri detti davvero dall'utente (anche in forma un po' diversa: «chiamare»/«chiama»)."""
    arg_n = normalize(call.arg)
    if not arg_n:
        return True
    user_n = _norm_with_numbers(user_text)
    user_words = set(user_n.split())
    for n in _NUM.findall(arg_n):
        v = int(n)
        if v == 0 or n in user_n.split() or num_words(v) in user_words:
            continue
        if call.name == "VOLUME" and call.arg.startswith("set:"):
            continue                                                                         # «metti il volume a metà» -> set:50
        return False
    toks = [w for w in arg_n.split() if len(w) >= 4 and w not in _STRUCT and not w.isdigit()]
    if not toks:
        return True
    ok = 0
    for w in toks:
        if w in user_words or any(len(w) >= 5 and len(u) >= 5 and (w[:5] == u[:5]) for u in user_words) or any(w in u or u in w for u in user_words if len(u) >= 4):
            ok += 1
    return ok >= max(1, int(0.8 * len(toks) + 0.5))


# ---- sanity check sul risultato: il chatbot, davanti a un racconto o a una chiacchiera, a volte «decodifica» comunque uno strumento
_PAST_STORY = re.compile(r"\b(?:ieri|ho dimenticato|mi sono ricordat\w+|mi ero|avevo|ho ricordato|mi ricordo|ricordo che|l altro giorno|ho scordato|mi e venuto in mente)\b")
_CUES = {
    "PROMEMORIA": r"\b(?:ricord\w+|promemoria|avvis\w+|segn\w+|annot\w+|dimenticar\w+|dimentic\w+|svegl\w+|fammi sapere|memorizz\w+|metti|imposta|crea)\b",
    "EVENTO": r"\b(?:calendario|agenda|appuntament\w+|event\w+|riunion\w+|segn\w+|metti|inserisc\w+|fiss\w+|prenot\w+|aggiung\w+)\b",
    "CONVERTI": r"\b(?:quant\w+|converti\w*|trasform\w+|sono|fanno|vengono|in)\b",
    "DATA": r"\b(?:giorni?|settiman\w+|mes[ei]|anni?|quando|data|giorno|pasqua|natale|capodanno|manca\w*|cade|cadere)\b",
    "CASO": r"\b(?:dado|dadi|moneta|testa|croce|caso|casuale|scegli|sorteggi\w*|carta|numero|estrai)\b",
    "AIUTO": r"\b(?:aiut\w+|sai fare|puoi fare|funzion\w+|servi|poteri|comandi|usarti|usare)\b",
    "TIMER_STATO": r"\b(?:timer|sveglia|sveglie|conto alla rovescia|manca|resta|rimane|rimangono)\b",
    "TIMER_ANNULLA": r"\b(?:timer|sveglia|sveglie|conto alla rovescia|countdown|cronomet\w+)\b",
    "TIMER": r"\b(?:timer|sveglia|svegli\w+|avvis\w+|conto alla rovescia|countdown|cronomet\w+|minuti|ore|secondi|squill\w+|suon\w+|fischi\w+)\b",
    "METEO": r"\b(?:tempo|meteo|piov\w+|pioggia|ombrello|sole|soleggiat\w+|temperatur\w+|gradi|freddo|caldo|clima|vento|nuvol\w+|neve|previsi\w+|atmosferic\w+)\b",
    "ORA": r"\b(?:ora|ore|orario|data|giorno|oggi|quanti ne abbiamo)\b",
    "CALCOLA": r"(?:\d|\b(?:per|diviso|fratto|piu|meno|somma|differenza|prodotto|percento|cento|meta|doppio|triplo|radice|quanto fa|calcol\w+)\b)",
    "SCHERMO": r"\b(?:schermo|schermata|pagina|finestra|pulsante|tasto|bottone|icona|menu|campo|link|scritta|questo|questa|quest|quello|quella|vedo|vedi|leggo|guarda\w*|clicc\w+|premer\w+|premo|computer|mac|sto facendo|davanti)\b",
    "NON_SO": r"\b(?:chiam\w+|telefon\w+|mand\w+|invi\w+|messagg\w+|whatsapp|mail|email|accend\w+|spegn\w+|luce|luci|tv|televis\w+|riscald\w+|condizionator\w+|ordin\w+|prenot\w+|compr\w+|contatt\w+|illuminazion\w+|telefonat\w+|cibo|mangiare)\b",
    "MUSICA": r"\b(?:music\w+|canzon\w+|brano|brani|pezzo|playlist|album|suon\w+|ascolt\w+|metti|riproduc\w+|pausa|ferma\w*|salta\w*|cant\w+|genere|artist\w+|spotify|disco|riprend\w+|avanti|indietro|prossim\w+|precedent\w+|stop)\b",
    "VOLUME": r"\b(?:volume|audio|suono|muto|muta\w*|silenzi\w+|zitt\w+|alz\w+|abbass\w+|forte|piano|livello|su|giu|piu|meno|basso|alto|rumor\w+|tutto)\b",
}


def plausible(call: ToolCall, user_text: str) -> bool:
    """False se il risultato non ha niente a che fare con quello che e' stato detto (o se e' un racconto al passato): meglio non fare niente che fare la cosa sbagliata."""
    t = normalize(user_text)
    if call.name in ("PROMEMORIA", "EVENTO", "TIMER", "CASO", "CONVERTI", "DATA") and _PAST_STORY.search(t):
        return False
    if call.name in ("CASO", "CONVERTI", "DATA", "AIUTO") and re.search(r"\b(?:ho|hai|ha|abbiamo|hanno|avevo|aveva)\s+(?:tirato|lanciato|giocato|vinto|perso|fatto|convertito|calcolato|scelto|chiesto|visto)\b", t):
        return False                                                                         # un racconto («ho tirato un dado e ho vinto»), non una richiesta
    cue = _CUES.get(call.name)
    return bool(cue is None or re.search(cue, t))
