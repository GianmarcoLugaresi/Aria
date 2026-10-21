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

from . import i18n
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

SYSTEM_EN = """You are the command decoder of an English-speaking voice assistant. You receive ONE sentence spoken aloud (it may contain speech recognition errors) and answer with ONE line only:
TOOL | argument
or
NONE
if the sentence is NOT a request to do one of these things (chit-chat, general-knowledge question, opinion, story, venting).

Tools and arguments (the tool names stay exactly as written; the argument is in English):
PROMEMORIA | when and what, in the words that were said (reminders)
EVENTO | what, day and time (calendar)
AGENDA | the day (today, tomorrow, monday, week)
TIMER | duration or time | name
TIMER_STATO | (how long is left on the timer, which timers are running)
TIMER_ANNULLA | name of the timer, or all (cancel, stop, remove a timer or an alarm)
METEO | place and day as said (may be empty)
ORA | ora (the time) or data (the date)
CALCOLA | the operation with digits and symbols (15*16, 350*20/100)
CONVERTI | (conversion between units: kilometers and miles, kilos and pounds, Celsius and Fahrenheit, liters and gallons…)
DATA | (date calculations: how many days until a holiday or a date, what day it will be in n days, when Easter is, which weekday a date falls on)
CASO | (roll a die, flip a coin, pick a random number or thing)
AIUTO | (what the assistant can do, how to use it, help)
MUSICA | play, pause, next, previous, now, track:<title/artist/genre>
VOLUME | up, down, mute, unmute, set:<0-100>, get
APRI_APP | name of the app or website
WEB | engine (youtube, google, amazon, wikipedia) | what to search for
MAPPA | the place (also "pharmacy near me")
LISTA | name of the list | item
NOTA | text of the note
SCRIVI | kind of text | topic (write a document in the folder)
RICERCA | topic (in-depth research)
LEGGI | name of the file
RIASSUMI | name of the file
ELENCO |
SISTEMA | batteria, spazio, versione, accensione, wifi, ip, memoria (information about the Mac)
BRIEFING |
PROMEMORIA_LISTA |
SCHERMO | one of: dove|<label or button to find> (point at / find something on the screen), leggi| (look at / read the screen), parere|<the sentence> (questions about what is visible: summarise, translate, explain this error, what do you think), indica|
NON_SO | call (phone calls), message (messages, whatsapp, mail), home (lights, tv, heating), buy (order, book, buy), print, download (download, install), system (wifi, bluetooth, brightness, restart), media (photos, video, recordings), share (share, publish), files (move, copy, delete files), app (close apps), money (payments), inbox (read mail or messages)

Rules: in the argument use ONLY words and numbers that were said in the sentence, never invent dates, times, names or reasons; if a piece of data is missing, leave it missing. One line only.

Sentence: try to create a reminder for tomorrow
PROMEMORIA | tomorrow
Sentence: put the dentist in my calendar on thursday at three pm
EVENTO | thursday at three pm dentist
Sentence: what do I have on tomorrow
AGENDA | tomorrow
Sentence: what does tomorrow look like
AGENDA | tomorrow
Sentence: put on some relaxing music
MUSICA | track:relaxing
Sentence: pause it
MUSICA | pause
Sentence: louder
VOLUME | up
Sentence: silence the computer
VOLUME | mute
Sentence: open the calculator for me
APRI_APP | calculator
Sentence: search youtube for guitar tutorials
WEB | youtube | guitar tutorials
Sentence: where is the nearest pharmacy
MAPPA | pharmacy near me
Sentence: add eggs to the shopping
LISTA | shopping|eggs
Sentence: make a note: buy batteries
NOTA | buy batteries
Sentence: wake me up at seven
TIMER | at seven
Sentence: tell me what the weather is like today
METEO | today
Sentence: what time did we get there
ORA | ora
Sentence: how much is twenty percent of three hundred and fifty
CALCOLA | 350*20/100
Sentence: write me a poem about the sea
SCRIVI | poem|the sea
Sentence: where do I find the button to share
SCHERMO | dove|share
Sentence: which icon do I click for the settings
SCHERMO | dove|settings
Sentence: take a look at what I'm doing
SCHERMO | leggi|
Sentence: can you explain what this error means
SCHERMO | parere|can you explain what this error means
Sentence: how much charge do I have left
SISTEMA | batteria
Sentence: call my mother
NON_SO | call
Sentence: send a message to Luke
NON_SO | message
Sentence: turn on the bathroom light
NON_SO | home
Sentence: what a nice day today
NONE
Sentence: I like jazz music
NONE
Sentence: tell me a joke
NONE
Sentence: I have an exam tomorrow and I'm nervous
NONE
Sentence: who wrote pride and prejudice
NONE"""

_LINE = re.compile(r"^\s*([A-Z_]+)\s*(?:\|\s*(.*))?$")


def prompt(text: str) -> tuple[str, str]:
    if i18n.is_en():
        return SYSTEM_EN, f"Sentence: {text.strip()}"
    return SYSTEM, f"Frase: {text.strip()}"


def parse(output: str) -> ToolCall | None:
    """La prima riga utile della risposta -> ToolCall, oppure None (NESSUNO, formato strano, strumento non ammesso)."""
    for line in (output or "").strip().splitlines():
        line = line.strip().strip("`*«»\"")
        if not line:
            continue
        line = re.sub(r"^(?:risposta|output|answer)\s*:\s*", "", line, flags=re.I)
        m = _LINE.match(line)
        if not m:
            return None
        name = m.group(1).upper()
        if name == "NONE":
            return None
        if name not in ALLOWED:
            return None
        return ToolCall(name, (m.group(2) or "").strip())
    return None


_STRUCT = {"track", "playlist", "set", "play", "pause", "next", "previous", "now", "up", "down", "mute", "unmute", "get", "della", "spesa", "youtube", "google", "amazon", "wikipedia",
           "shopping", "todo", "weekend", "today", "tomorrow", "week", "ora", "data"}
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


_PAST_STORY_EN = re.compile(r"\b(?:yesterday|i forgot|i remembered|i was|i had|i used to|last night|the other day|i just remembered|it occurred to me|i have been|i ve been|i did|i went)\b")
_CUES_EN = {
    "PROMEMORIA": r"\b(?:remind\w*|reminders?|alert\w*|notes?|note down|remember|forget|wake|let me know|memori[sz]e|set|put|create|ping|notify)\b",
    "EVENTO": r"\b(?:calendar|agenda|appointments?|events?|meetings?|schedule|book|add|put|set up|create|block|entry)\b",
    "CONVERTI": r"\b(?:how (?:many|much)|convert\w*|change|is|are|in|equals?|make|makes|to)\b",
    "DATA": r"\b(?:days?|weeks?|months?|years?|when|date|day|easter|christmas|new year|how long|until|till|falls?|left|remaining)\b",
    "CASO": r"\b(?:die|dice|coin|heads|tails|random\w*|pick|choose|draw|number|card|flip|roll|toss|lottery)\b",
    "AIUTO": r"\b(?:help|what can you do|can you do|how (?:do|to) (?:i )?use|features?|commands?|abilities|capabilities)\b",
    "TIMER_STATO": r"\b(?:timers?|alarms?|countdowns?|left|remaining|running)\b",
    "TIMER_ANNULLA": r"\b(?:timers?|alarms?|countdowns?|stopwatch)\b",
    "TIMER": r"\b(?:timers?|alarms?|wake|alert\w*|countdowns?|stopwatch|minutes?|hours?|seconds?|ring|buzz|remind|ping|notify|beep)\b",
    "METEO": r"\b(?:weather|rain\w*|umbrella|sun\w*|temperature|degrees|cold|hot|warm|climate|wind\w*|cloud\w*|snow\w*|forecast|sunrise|sunset|storm\w*)\b",
    "ORA": r"\b(?:time|date|day|today|what day|o clock)\b",
    "CALCOLA": r"(?:\d|\b(?:times|divided|plus|minus|sum|difference|product|percent|half|double|triple|root|squared|cubed|calculate|how much is|what is|multiply|add|subtract|divide)\b)",
    "SCHERMO": r"\b(?:screen|page|window|button|key|icon|menu|field|link|label|this|that|see|look|read|click|press|computer|mac|doing|in front|display|showing)\b",
    "NON_SO": r"\b(?:call\w*|phone|ring|send|message\w*|text|whatsapp|mail|email|turn|switch|light\w*|tv|television|heating|air|order|book|buy|contact\w*|food|eat|pay\w*|print\w*|download|install|photo|picture|video|record\w*|share|post|close|quit|stopwatch|bookmark)\b",
    "MUSICA": r"\b(?:music|songs?|tracks?|tunes?|playlist|album|play\w*|listen|put on|pause|stop|skip|next|previous|back|artist|band|genre|spotify|resume|continue)\b",
    "VOLUME": r"\b(?:volume|audio|sound|mute|unmute|silence|quiet|louder|softer|up|down|higher|lower|turn|raise|lower|level|loud|noise|max|full)\b",
}


def plausible(call: ToolCall, user_text: str) -> bool:
    """False se il risultato non ha niente a che fare con quello che e' stato detto (o se e' un racconto al passato): meglio non fare niente che fare la cosa sbagliata."""
    t = normalize(user_text)
    if i18n.is_en():
        if call.name in ("PROMEMORIA", "EVENTO", "TIMER", "CASO", "CONVERTI", "DATA") and _PAST_STORY_EN.search(t):
            return False
        if call.name in ("CASO", "CONVERTI", "DATA", "AIUTO") and re.search(r"\b(?:i|we|they|he|she)\s+(?:rolled|threw|flipped|tossed|played|won|lost|made|converted|calculated|picked|chose|asked|saw)\b", t):
            return False
        cue = _CUES_EN.get(call.name)
        return bool(cue is None or re.search(cue, t))
    if call.name in ("PROMEMORIA", "EVENTO", "TIMER", "CASO", "CONVERTI", "DATA") and _PAST_STORY.search(t):
        return False
    if call.name in ("CASO", "CONVERTI", "DATA", "AIUTO") and re.search(r"\b(?:ho|hai|ha|abbiamo|hanno|avevo|aveva)\s+(?:tirato|lanciato|giocato|vinto|perso|fatto|convertito|calcolato|scelto|chiesto|visto)\b", t):
        return False                                                                         # un racconto («ho tirato un dado e ho vinto»), non una richiesta
    cue = _CUES.get(call.name)
    return bool(cue is None or re.search(cue, t))
