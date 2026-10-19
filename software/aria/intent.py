"""Riconoscimento "a monte" delle richieste che richiedono uno strumento.

I modelli piccoli (1-4B) sbagliano spesso la decisione "uso uno strumento o no?" e scrivono prima del testo inutile.
Qui le richieste ovvie (meteo, timer, calcoli, "ricordati che...", "chi e'...") vengono riconosciute con regole semplici:
lo strumento parte subito e il modello deve solo trasformare il risultato in una frase a voce. Per tutto il resto
resta valido il protocollo [[COMANDO: ...]] scritto dal modello.
"""
from __future__ import annotations

import datetime as dt
import os
import re

from .phrasing import canonical
from .textutil import ToolCall, normalize
from .tools import it_number, parse_duration
from .timeparse import parse_when
from .workspace import match_file

_UNITS = {"zero": 0, "uno": 1, "un": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7, "otto": 8,
          "nove": 9, "dieci": 10, "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14, "quindici": 15, "sedici": 16,
          "diciassette": 17, "diciotto": 18, "diciannove": 19}
_TENS = {"venti": 20, "trenta": 30, "quaranta": 40, "cinquanta": 50, "sessanta": 60, "settanta": 70, "ottanta": 80, "novanta": 90}
_OPS = [("diviso", "/"), ("fratto", "/"), ("moltiplicato per", "*"), ("moltiplicato", "*"), ("per", "*"), ("volte", "*"), ("piu", "+"), ("meno", "-")]


def number_it(text: str) -> int | None:
    """'centoventi' -> 120, 'duecentotrentacinque' -> 235, 'mille' -> 1000, '15' -> 15 (fino a 999.999); '2punto5' -> 2.5."""
    w = normalize(text).replace(" ", "")
    if not w:
        return None
    if w.isdigit():
        return int(w)
    if "punto" in w:
        a, _, b = w.partition("punto")
        ai, bi = (number_it(a) if a else 0), number_it(b)
        if isinstance(ai, int) and isinstance(bi, int) and b:
            return float(f"{ai}.{bi}")
        return None
    total = 0
    if "mila" in w or w.startswith("mille") or w == "mille":
        head, _, tail = w.partition("mila") if "mila" in w else ("", "", w[len("mille"):])
        thousands = 1 if not head else _under_1000(head)
        if thousands is None:
            return None
        total += thousands * 1000
        w = tail
        if not w:
            return total
    rest = _under_1000(w)
    return None if rest is None else total + rest


def _under_1000(w: str) -> int | None:
    if not w:
        return 0
    total = 0
    if "cento" in w:
        before, _, w = w.partition("cento")
        mult = 1 if not before else _UNITS.get(before)
        if mult is None:
            return None
        total += 100 * mult
    if not w:
        return total
    n = it_number(w)
    if n is not None and n < 100:
        return total + n
    return None


def parse_math(text: str) -> str | None:
    """'quanto fa centoventi diviso otto' -> '120/8'. Piu' operatori, numeri a parole o a cifre, anche con la virgola («2,5 per 4», «due virgola cinque per quattro»)."""
    from .everyday import decimals_to_words
    t = normalize(decimals_to_words(text))
    m = re.search(r"(?:il\s+)?(\d+|[a-z]+(?: [a-z]+)?)\s+(?:per cento|percento)\s+di\s+(\d+|[a-z]+(?: [a-z]+)?)\b", t)             # «il 20 per cento di 350»
    if m:
        a, b = number_it(m.group(1)), number_it(m.group(2))
        if a is not None and b is not None:
            return f"{b}*{a}/100"
    m = re.search(r"\b(somma|differenza|prodotto)\s+(?:di|tra|fra)\s+(\d+|[a-z]+(?: [a-z]+)?)\s+e\s+(\d+|[a-z]+(?: [a-z]+)?)\b", t)    # «la somma di 45 e 78»
    if m:
        a, b = number_it(m.group(2)), number_it(m.group(3))
        if a is not None and b is not None:
            return f"{a}{ {'somma': '+', 'differenza': '-', 'prodotto': '*'}[m.group(1)] }{b}"
    m = re.search(r"\b(?:la meta|il doppio|il triplo|il quadruplo|la radice quadrata|il quadrato)\s+(?:di|del)\s+(\d+|[a-z]+(?: [a-z]+)?)\b", t)
    if m:
        a = number_it(m.group(1))
        if a is not None:
            kind = re.search(r"la meta|il doppio|il triplo|il quadruplo|la radice quadrata|il quadrato", t).group(0)
            return {"la meta": f"{a}/2", "il doppio": f"{a}*2", "il triplo": f"{a}*3", "il quadruplo": f"{a}*4", "la radice quadrata": f"sqrt({a})", "il quadrato": f"{a}*{a}"}[kind]
    m = re.search(r"\b(\d+(?:punto\d+)?|[a-z]+)\s+al\s+(quadrato|cubo)\b", t)
    if m:
        a = number_it(m.group(1))
        if a is not None:
            return f"{a}*{a}" if m.group(2) == "quadrato" else f"{a}*{a}*{a}"
    for rx, op, swap in ((r"\b(?:metti insieme|sommami|somma|addiziona|addizionami|aggiungi)\s+(.+?)\s+(?:e|con|a)\s+(.+)$", "+", False),
                         (r"\b(?:sottrai|sottraimi|togli|leva|levami)\s+(.+?)\s+da\s+(.+)$", "-", True),
                         (r"\b(?:dividi|dividimi|dividere|se divido|divido)\s+(.+?)\s+(?:per|in)\s+(.+?)(?:\s+parti)?(?:\s+quanto.*)?$", "/", False),
                         (r"\b(?:moltiplica|moltiplicami|se moltiplico|moltiplico)\s+(.+?)\s+(?:per|e|con)\s+(.+?)(?:\s+quanto.*)?$", "*", False)):
        m = re.search(rx, t)
        if m:
            a, b = number_it(m.group(1).strip()), number_it(m.group(2).strip())
            if a is not None and b is not None:
                return f"{b}{op}{a}" if swap else f"{a}{op}{b}"
    m = re.search(r"(?:quanto fanno|quanto fa|quanto viene|quanto vengono|quanto da|quant e|calcolami|calcolatemi|calcola|fammi il calcolo di|fammi il conto di|fammi un conto|fammi un calcolo|fai un conto|facci un conto|fa)\s+(.+)", t)
    body = m.group(1) if m else t
    for word, sym in _OPS:
        parts = re.split(rf"\b{word}\b", body, maxsplit=1)
        if len(parts) == 2:
            a, b = number_it(parts[0].strip()), number_it(parts[1].strip())
            if a is not None and b is not None:
                return f"{a}{sym}{b}"
    parts = re.split(r"\b(diviso|fratto|moltiplicato per|moltiplicato|per|volte|piu|meno)\b", body)          # «due per tre piu quattro»: piu' operatori, precedenza di una calcolatrice
    if len(parts) >= 5:
        sym = {"diviso": "/", "fratto": "/", "moltiplicato per": "*", "moltiplicato": "*", "per": "*", "volte": "*", "piu": "+", "meno": "-"}
        nums = [number_it(x.strip()) for x in parts[0::2]]
        if all(n is not None for n in nums):
            return "".join(f"{n}{sym[o]}" for n, o in zip(nums, parts[1::2])) + str(nums[-1])
    return None


_TIME = re.compile(r"\b(che ora si e fatta|che ore si sono fatte|sai che ora|mi sai dire l ora|che ore sono|che ora e|che ore fa|che ora fa|sai che ore|mi dici l ora|dimmi l ora|l ora esatta|che ora siamo|ma che ora siamo|che ore abbiamo|orario attuale|l orario)\b")
_DATE = re.compile(r"\b(che giorno e|che data e|quanti ne abbiamo|che giorno della settimana|che giorno siamo|in che giorno siamo|a che data siamo|siamo a che data|che data abbiamo|data di oggi|che giorno abbiamo|a che giorno siamo|che giorno del mese)\b")
# ---- la cartella di Aria: scrivere, ricerche salvate, liste, note, leggere
_DOC = (r"(?:testo|articolo|riassunto|tema|saggio|poesia|lettera|email|e mail|mail|post|appunti|scaletta|schema|relazione|ricetta|storia|racconto|discorso|descrizione|presentazione|"
        r"piano|guida|documento|lista|elenco|bozza|messaggio|biglietto|auguri|augurio|frase|filastrocca|paragrafo|recensione|annuncio|curriculum|commento|canzone|favola|barzelletta)")
_ON = r"(?:su|sul|sull|sulla|sullo|sui|sugli|sulle|riguardo a|riguardo|a proposito di|di|del|dell|della|dello|dei|degli|delle|per|con|a|ad)"
_POLITE = r"(?:per favore |per piacere |puoi |potresti |mi puoi |mi potresti |ti va di )?"
_ADJ = r"(?:breve|piccol[oa]|cort[oa]|lung[oa]|semplice|bel|bell[oa]|veloce|rapid[oa]|simpatic[oa]|formale|informale)?\s*"
_WRITE = re.compile(rf"^{_POLITE}(?:scrivi|scrivimi|scrivermi|scrivere|prepara|preparami|prepararmi|preparare|stendi|redigi|crea|creami|crearmi|creare|componi|inventa|inventami)\s+(?:un|una|uno|il|la|lo|dei|delle|degli)?\s*{_ADJ}({_DOC})\s+(?:{_ON}\s+)?(.+)$")
_RESEARCH = re.compile(rf"^{_POLITE}(?:fai|fammi|fare|fa|crea|creami|prepara|preparami|voglio|mi serve|mi serve fare)\s+(?:una\s+)?ricerca\s+(?:veloce\s+|rapida\s+|approfondita\s+|breve\s+)?{_ON}\s+(.+)$")
_RESEARCH0 = re.compile(r"^(?:fai|fammi|fare|fa)\s+(?:una\s+|la\s+|quella\s+)?ricerca(?:\s+(?:veloce|rapida|approfondita|breve))?(?:\s*,?\s*e\s+.*|\s+(?:nella|in)\s+(?:mia\s+|tua\s+)?cartella.*|\s+per\s+me)?$")
_SAVE_LAST = re.compile(r"^(?:salva|salvami|mettil[ao]|buttal[ao]|scrivil[ao]|metti|scrivi|butta)\w*\s+(?:la\s+|il\s+|questa\s+|questo\s+|tutta\s+la\s+|tutto\s+il\s+)?(?:ricerca|risultato|risultati|risposta|testo)?\s*(?:nella|in|dentro la|nel)\s+(?:mia\s+|tua\s+)?(?:cartella|file)\b|^(?:scrivi|metti|salva)\w*\s+(?:in\s+)?(?:un\s+)?file(?:\s+di\s+testo)?\s+(?:con\s+)?(?:scritto\s+)?(?:tutta\s+la\s+|la\s+)?ricerca")
_RESEARCH2 = re.compile(r"^(?:cerca|cercami|ricerca|ricercami|informati su|informati)\s+(.+?)[,\s]+e\s+(?:poi\s+)?(?:salva|mettil|metti|scrivil|segnat|appunt)\w*\b.*$")
_SAVE_TAIL = re.compile(r"\s+(?:e\s+)?(?:poi\s+)?(?:mettil\w*|salvil\w*|metti\w*|salva\w*|scrivil\w*|segnatel\w*)\b.*$|\s+(?:nella|in)\s+(?:mia\s+|tua\s+)?cartella.*$|\s+in\s+un\s+file.*$|\s+per\s+me$|[,\s]*per\s+(?:favore|piacere)$")
_LISTADD = re.compile(r"^(?:aggiungi|aggiungimi|aggiungiamo|metti|mettimi|segna|segnami|scrivi|inserisci)\s+(?:anche\s+|pure\s+)?(.+?)\s+(?:alla|nella|sulla|in)\s+(?:mia\s+)?(?:lista(?:\s+(.+))?|(spesa))$")
_LISTADD2 = re.compile(r"^(?:aggiungi|aggiungimi|metti|mettimi|segna|segnami|scrivi|inserisci)\s+(?:nella|sulla|in|alla|sulle|nelle)\s+(?:mia\s+)?lista\s+((?:della|dei|delle|degli|del|dello)\s+[a-z]+)\s+(.+)$")
_LISTADD4 = re.compile(r"^(?:aggiungi|aggiungimi|metti|mettimi|segna|segnami|scrivi|inserisci)\s+(?:nella|sulla|in|alla)\s+(?:mia\s+)?(?:lista|spesa)(?:\s*[:,]\s*|\s+(?!(?:della|delle|dei|degli|del|dello|di)\b))(.+)$")
_LISTADD3 = re.compile(r"^(?:per|nella|sulla|alla)\s+(?:la\s+)?(spesa|lista(?: della spesa)?)[,:]?\s+(?:aggiungi|aggiungimi|inserisci|metti|mettimi|segna|segnami|scrivi|prendi)\s+(?:anche\s+|pure\s+)?(.+)$")
_LISTBARE = re.compile(r"^(?:aggiungi|aggiungimi|segna|segnami|inserisci|scrivi anche|metti anche|segna anche|metti pure|scrivi pure)\s+(?:anche\s+|pure\s+)?(.+)$")
_NOTE2 = re.compile(r"^(?:salva|salvami|metti da parte|tieni da parte|appunta|appuntami)\s+(.+)$")
_NOTE_BARE = re.compile(r"^(?:annota|annotami|appunta|appuntami)\s+(?!(?:pure|anche|ora|adesso)\b)(?:che\s+)?(?!(?:una|un|questa|questo)\s+(?:nota|appunto)\b)(.+)$")
_NOTE_BLOC = re.compile(r"^(?:metti|mettimi|scrivi|scrivimi|segna|segnami|aggiungi|aggiungimi|annota|appunta)\s+(?:sul|nel|sullo|nello|sulle|nelle|sul mio|nel mio)\s+(?:bloc notes|block notes|blocknotes|blocco note|blocco appunti|taccuino|quaderno|quaderno degli appunti|note|appunti)\s*(?:che\s+|:\s*|,\s*)?(.+)$")
_NOTE_COLON = re.compile(r"^(?:annota|annotami|appunta|appuntami|segna|segnami|segnati)\s*:\s*(.+)$")
_NOTE = re.compile(r"^(?:(?:segna|segnami|annota|annotami|appunta|appuntami|scrivi|salva|aggiungi|crea)\s+(?:una\s+|un\s+|questa\s+|questo\s+|quest\s+|quell\s+|quella\s+|quel\s+)?(?:nota|appunto)|prendi\s+nota|fai\s+una\s+nota)\s*(?:che\s+|:\s*|,\s*)?(.*)$")
_LS = re.compile(r"\b(?:che|quali|quanti)\s+file\b.*\b(?:cartella|ci sono|hai)\b|\b(?:cosa|che cosa)\s+(?:c e|ci sta|hai)\s+nella\s+(?:tua\s+)?cartella\b|\belenca(?:mi)?\s+(?:i\s+)?(?:file|documenti)\b|\bmostrami\s+i\s+file\b")
_FILEWORD = r"(?:file|documento|testo|nota|note|ricerca|lista)"
_FILE_BY_NAME = re.compile(r"^(riassum\w+|sintetizz\w+|leggimi|leggi|leggermi)\s+(?:ad alta voce\s+)?(?:il\s+|lo\s+|la\s+|l\s+|i\s+|le\s+|quel\s+|quella\s+)?(.+)$")
_LIST_Q0 = re.compile(r"^(?:dimmi\s+|mi dici\s+|ricordami\s+)?(?:cosa|che cosa|che|quali cose)\s+(?:devo|dobbiamo|ci serve|mi serve|manca|manca in casa|c e da|e da)\s+(?:comprare|prendere|acquistare|portare)?\s*$|^(?:cosa|che cosa)\s+manca(?:\s+(?:in casa|nella spesa|alla spesa))?$")
_LIST_Q = re.compile(r"^(?:dimmi\s+|mi dici\s+)?(?:cosa|che cosa|che|quali cose|quanto)\s+(?:c e|ho|abbiamo|ci ho|ce|ci sta|ci sono|devo comprare)\s+(?:scritto\s+|segnato\s+|ancora\s+)?(?:nella|sulla|in|dentro la|dentro)\s+(?:mia\s+|tua\s+)?lista(?:\s+((?:della|di|dei|delle|degli|del)\s+\w+))?$|^(?:leggimi|leggi|dimmi)\s+(?:tutta\s+)?la\s+lista(?:\s+((?:della|di|dei|delle|degli|del)\s+\w+))?$")
_READ_BARE = re.compile(r"^(?:per favore )?(?:leggimi|leggi|dimmi|rileggimi)\s+(?:la\s+|le\s+|il\s+|i\s+)?(nota|note|appunti|lista|lista della spesa|la spesa)$")
_READ = re.compile(rf"^(?:per favore )?(?:leggimi|leggi|leggimi ad alta voce)\s+(?:il\s+|lo\s+|la\s+|l\s+|i\s+|le\s+)?{_FILEWORD}\s+(.+)$")
_SUMMARIZE = re.compile(rf"^(?:per favore )?(?:riassumi|riassumimi|sintetizza|sintetizzami)\s+(?:il\s+|lo\s+|la\s+|l\s+)?{_FILEWORD}\s+(.+)$")
_OPENDIR = re.compile(r"\b(?:apri|aprimi|mostrami)\b.*\bcartella\b")
_MEMORY = re.compile(r"\b(?:cosa ti ho detto (?:di|su) me|che ti ho detto (?:di|su) me|cosa ti ho raccontato di me|(?:cosa|che cosa|che) (?:sai|ricordi|ti ricordi) (?:di|su|sul conto di) me|cosa sai su di me|come mi chiamo|ti ricordi (?:di me|come mi chiamo|il mio nome)|dove abito|ti ricordi dove abito)\b")
_WEATHER = re.compile(r"\b(?:che tempo|com e il tempo|come e il tempo|come sara il tempo|meteo|previsioni|quanti gradi|temperatura (?:fuori|di oggi|di domani|a)|che temperatura|temperatura c e|temperatura ci sono|qual e la previsione|la previsione|condizioni atmosferiche|condizioni meteo|temperatura (?:massima|minima|prevista|attuale)|che clima|com e il clima|clima di oggi|clima di domani|il clima)\b")
# parole di meteo che sono una domanda solo con un giorno accanto («domani piove?», «devo portare l'ombrello?»): «ogni volta che piove mi sento meglio» e' una chiacchiera
_WEATHER_SOFT = re.compile(r"\b(?:sara (?:bello|brutto|nuvoloso|soleggiato|sereno|coperto|bel tempo|brutto tempo)|fa (?:bel|brutto|cattivo) tempo|ci sara (?:bel|brutto|cattivo) tempo|che vento|c e vento|tira vento|soffia il vento|piove|piovera|nevica|nevichera|fa freddo|fa caldo|fara (?:freddo|caldo|bel tempo|brutto|fresco)|ci sara (?:vento|nebbia|pioggia|neve|un temporale|temporale|sole|il sole)|c e (?:vento|nebbia)|c e il sole|ci sara il sole|nuvol\w*)\b|\b(?:devo|serve|mi serve|conviene|porto|prendo|portare|prendere|porta|prendi)\b.*\bombrello\b")
_SUN = re.compile(r"\b(?:a che ora|quando|che ora)\s+(?:sorge|tramonta|spunta|cala|sara l alba|sara il tramonto|e l alba|e il tramonto)\b.*|\b(?:alba|tramonto)\b.*\b(?:oggi|domani|stasera|stamattina)\b|\b(?:orario|ora) (?:dell alba|del tramonto|di alba|di tramonto)\b|\bquando (?:fa|si fa) (?:buio|notte)\b|\ba che ora (?:fa|si fa) buio\b|\ba che ora (?:si leva|sorge) il sole\b")
_WEATHER_CHAT = re.compile(r"^(?:mi sa|credo|penso|spero|speriamo|temo|secondo me|pare|sembra|e probabile|magari|sai che|uffa|accidenti)\b|\bche (?:noia|palle|schifo|brutto|bello|barba|pizza)\b|\bmi (?:sa|pare|sembra)\b")
_WEATHER_GRUMBLE = re.compile(r"\b(?:che (?:noia|palle|schifo|barba|pizza)|uffa|mi sa che|accidenti)\b")
_WEATHER_DAY = re.compile(r"\b(?:oggi|domani|dopodomani|stasera|stanotte|stamattina|questo weekend|nel weekend|adesso|ora|fuori|in questo momento|sabato|domenica|lunedi|martedi|mercoledi|giovedi|venerdi|settimana)\b")
# "ho dimenticato l'ombrello a casa", "mi piace il sole d'estate": parole di meteo, ma niente richiesta
_WEATHER_NOT = re.compile(r"\bmi sento\b|\bmalinconic\w*|\bimprevedibil\w*|\be sempre\b|\bsono sempre\b|\bsai\s*$|\b(?:ho|hai|ha|abbiamo|avevo|aveva|ho gia)\s+(?:dimenticato|scordato|perso|lasciato|preso|portato)\b|\bmi piace\b|\bmi piacciono\b|\bpiu bello\b|\bbel sole\b|\bhai mai\b|\badoro\b|\bamo\b")
_CITY = re.compile(r"\b(?i:a|di|su|per|in)\s+([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+)?)")
_TIMER_WORD = r"(?:timer|sveglia|sveglie|conto alla rovescia|countdown|cronometro|allarme)"
_TIMER_STATUS = re.compile(rf"\b(?:(?:tra|fra) quanto (?:suona|scatta|finisce|scade|squilla|mi avvisa|mi avvisi|parte)|quanto (?:tempo )?(?:manca|resta|rimane|rimangono)(?: ancora)?(?: (?:al|allo|alla|all|per il|per la|per lo|prima del|prima della|allo scadere del|allo scadere della|alla fine del|alla fine della|al termine del|al termine della)\s+{_TIMER_WORD}\b.*)?$|quanto tempo (?:ci vuole )?ancora$|"
                           rf"(?:che|quali|quanti) {_TIMER_WORD} (?:ho|ci sono|hai|ho attiv\w+|sono attiv\w+)|ho (?:dei |dei miei |qualche |ancora |dei {_TIMER_WORD} )?{_TIMER_WORD}(?: attiv\w+| in corso| impostat\w+)?$|ci sono (?:dei |ancora )?{_TIMER_WORD}|"
                           rf"{_TIMER_WORD} (?:attiv\w+|in corso|impostat\w+)|(?:elenca\w*|dimmi|leggi\w*|fammi sentire|mostra\w*) i (?:miei )?{_TIMER_WORD}|quando (?:suona|scatta|finisce|scade|squilla) (?:il|la|lo) {_TIMER_WORD}|a che punto (?:e|siamo con) (?:il|la|lo) {_TIMER_WORD})\b")
_TIMER_CANCEL = re.compile(rf"\b(?:annull\w+|cancell\w+|elimin\w+|tog\w+|ferm\w+|stopp\w+|interromp\w+|disattiv\w+|spegn\w+|rimuov\w+|butt\w+|fai(?:mi)? sparire)\s+(?:pure |anche )?(?:(?:tutti|tutte|tutto)\s+)?(?:(?:il|lo|la|l|i|le|quel|quello|quella|questo|questa|ogni)\s+)*(?:i |le )?{_TIMER_WORD}\b|"
                           rf"\b(?:non mi serve piu|non serve piu|lascia (?:stare|perdere)|non importa piu|dimentica) (?:il|la|lo|l|i|le)\s*{_TIMER_WORD}\b|"
                           rf"^basta\s+(?:col|con il|con la|con lo|con i|con le|con)\s+{_TIMER_WORD}\b")
_TIMER = re.compile(r"\b(timer|sveglia|svegliami|avvisami|avvertimi|ricordami tra|conto alla rovescia|countdown|cronometro)\b")
_TIMER_NOT = re.compile(r"^(?:una|la|quella|questa|quel|il)\s+(?:sveglia|timer)\s+(?:che|e|era|non|di)\b|\b(?:crudele|detesto|odio|insopportabile)\b|\b(?:timer|sveglia)\s+(?:del forno|del telefono)\s+(?:e|era)\s+(?:rott\w+|guast\w+)\b|\b(?:e|era)\s+rott\w+\b")
_REMEMBER = re.compile(r"^(?:ricordati|ricorda|tieni a mente|segnati)\s+(?:che\s+)?(.+)", re.I)
_FORGET = re.compile(r"^(?:dimentica|scordati)\s+(?:di\s+|che\s+)?(.+)", re.I)
_WHO = re.compile(r"^(?:chi\s+(?:è|e|era|sono stati)|che\s+cos[’']?\s*[èe]|cos[’']?\s*[èe]|che cosa\s+[èe]|cosa significa|"
                  r"chi ha (?:scritto|dipinto|inventato|fondato|scoperto))\s+(.+?)[?.!]*$", re.I)
_LIVE = re.compile(r"\b(?:chi ha vinto|risultat\w+ (?:di|della|del|dell|delle)|classifica (?:di|della|del|dell)|com e il traffico|c e traffico|traffico (?:a|su|per|verso|in)|prezzo (?:di|del|dell|della|attuale)|quanto costa (?:oggi|adesso|ora)|quotazione|"
                  r"(?:bitcoin|dollaro|oro|petrolio|euro) (?:oggi|adesso|ora)|valore (?:del|dell|di) (?:bitcoin|dollaro|euro|oro|petrolio)|orari (?:dei|del|di|della|delle|di apertura)|che orari (?:fa|ha|hanno|fanno|ci sono)|a che ora (?:apre|chiude|passa|parte|arriva|inizia|finisce)|"
                  r"farmacia di turno|stato del volo|volo (?:per|da) |quando esce|e uscito|aperto adesso|aperta adesso|aperto oggi|aperta oggi|ultime notizie|notizie (?:di oggi|su|sul|sulla)|cosa e successo)\b")
_SEARCH = re.compile(r"\b(notizie|ultime notizie|risultati di|quanto costa)\b|^(?:(?:ok|allora|poi|dai|su|forza|ehi|aria|senti|scusa|vai|bene|adesso|ora|subito)\s+)*(?:cerca|cercami)\b")
_SEARCH_NOT = re.compile(r"\b(?:raccontarti|ti racconto|ti dico|ti spiego|ti posso dire|potrei dirti|volevo raccontarti)\b|\bcerca(?:re)?\s+di\s+\w+(?:are|ere|ire)\b|\bcercare\b")                  # "cerca di capire", "devo cercare di dormire": non e' una ricerca sul web


_ACCENTS = str.maketrans("àáâäèéêëìíîïòóôöùúûüñç’'", "aaaaeeeeiiiioooouuuunc  ")


def _fold(raw: str) -> str:
    """Il testo per il riconoscimento: minuscolo e senza accenti MA con la stessa lunghezza dell'originale, cosi' le parti trovate si
    possono ritagliare da quello che l'utente ha detto davvero (con maiuscole, accenti e virgole: nomi, voci di una lista, note)."""
    return raw.lower().translate(_ACCENTS)


def _span(raw: str, folded_off: int, m, g: int) -> str:
    return raw[folded_off + m.start(g):folded_off + m.end(g)].strip(" .,;:!?")


_FR_VERB = re.compile(r"\b(?:i?scriv\w*|mett\w*|butt\w*|salv\w*|cre\w*|prepar\w*|copi\w*|trascriv\w*|inserisc\w*|registr\w*|redig\w*|compon\w*|stend\w*|fammi|fare|faresti|fai)\b")
_FR_FILE = re.compile(r"\b(?:file|cartella|documento|document[oi]|foglio)\b")
_FR_ART = r"(?:(?:un|una|uno|il|la|lo|l|i|le|gli|mio|mia|tuo|tua|nuovo|nuova|quel|quella|questo|questa)\s+)*"
_FR_DEST = re.compile(r"\b(?:all|dentro|in|nel|nella|nello|nei)\s+(?:interno\s+)?(?:(?:di|del|della|dello|dei|d|un|una|uno|il|la|lo|l|i|le|gli|mio|mia|tuo|tua|nuovo|nuova|quel|quella|questo|questa)\s+)*(?:file|cartella|documento|document[oi]|foglio)(?:\s+(?:di testo|word|txt|pdf|nuovo|nuova))?\b")
_FR_TELL = re.compile(r"\b(?:dimmi|dirmi|dici|diresti|dirmela|raccontami|racconteresti|spiegami|spiegheresti|dammi|daresti)\b")                # «dimmi la ricetta in un file» (o «scrivimi» sentito male)
_FR_PAST = re.compile(r"\b(?:ho|hai|ha|abbiamo|avete|hanno|avevo|aveva)\s+(?:\w+\s+){0,2}(?:mess|scritt|salvat|creat|copiat|buttat)\w*")        # «ho messo la ricetta nel file ieri» e' un racconto
_FR_KIND = re.compile(rf"\b({_DOC[:-1]}|spiegazione|ricerca|sintesi|lezione|traduzione|riepilogo|itinerario|esercizi|dialogo|copione|trama|biografia|analisi|ricette|storie))\b")
_FR_REF = re.compile(r"\b(?:quello|quella|quanto|questo|questa|appena|prima|detto|detta|hai|abbiamo|ci siamo|stiamo|tutto|tutta|tutti|tutte|intero|intera|quest|sopra)\b")
_FR_TAIL = re.compile(r"(?:[,;]\s*|\s+)(?:e\s+|poi\s+)?(?:(?:me|te|ce|mi|ti|ci|li|lo|la|le)\s+)*(?:mett\w*|salv\w*|scriv\w*|butt\w*|copi\w*|inserisc\w*)\b.*$|\s+(?:per favore|per piacere|grazie)\s*$|\s+(?:e\s+)?(?:poi\s+)?(?:per me)\s*$")
_FR_LEADON = re.compile(rf"^(?:{_ON}\s+|(?:(?:un|una|uno|il|la|lo|l|i|le|gli)\s+))+")


def file_request(text: str) -> tuple[str, str | None] | None:
    """«mi scriveresti, all'interno del file, la ricetta degli gnocchi alla romana?», «in un file nella cartella scrivimi la storia di Roma», «mi creeresti un file con…»:
    una richiesta di SCRIVERE UN DOCUMENTO nella cartella, comunque sia ordinata la frase. Restituisce (tipo, argomento): senza argomento («scrivimi tutta la ricetta in un file»)
    argomento e' None e significa «quello di cui stavamo parlando»."""
    raw = canonical(text)
    folded = _fold(raw)
    if not _FR_FILE.search(folded) or _FR_PAST.search(folded):
        return None
    dest = list(_FR_DEST.finditer(folded))
    if not (_FR_VERB.search(folded) or (dest and _FR_TELL.search(folded))):
        return None
    f2, r2, last = "", "", 0
    for m in dest:                             # toglie «nel file», «all'interno di una cartella»: sono la destinazione, non l'argomento
        f2, r2, last = f2 + folded[last:m.start()] + " ", r2 + raw[last:m.start()] + " ", m.end()
    f2, r2 = f2 + folded[last:], r2 + raw[last:]                    # f2 e r2 restano della stessa lunghezza: i pezzi trovati nel primo si ritagliano dal secondo
    i = len(f2) - len(f2.lstrip(" .!?,;:"))
    f2, r2 = f2[i:].rstrip(" .!?,;:"), r2[i:i + len(f2[i:].rstrip(" .!?,;:"))]
    if not f2:
        return None
    km = _FR_KIND.search(f2)
    if not km:                                                      # nessun tipo di testo: «mettilo nella cartella»: lo salva (Aria sa di cosa si parla)
        return ("testo", None) if _SV_THING.search(f2) else None
    kind, tf, tr = km.group(1), f2[km.end():], r2[km.end():]
    tm = _FR_TAIL.search(tf)
    if tm:
        tf, tr = tf[:tm.start()], tr[:tm.start()]
    lm = _FR_LEADON.match(tf.lstrip(" ,;:"))
    cut = len(tf) - len(tf.lstrip(" ,;:")) + (lm.end() if lm else 0)
    tf, tr = tf[cut:], tr[cut:]
    tf, tr = " ".join(tf.split()).strip(" .,;:!?"), " ".join(tr.split()).strip(" .,;:!?")
    if len(tf) < 3 or _FR_REF.search(tf) or _FR_FILE.search(tf):
        return (kind, None)
    return (kind, tr)


# ---- guardare lo schermo: «non trovo il pulsante Esporta», «guarda lo schermo e dimmi…», «cosa ne pensi di quello che vedo?»
_SCR_NOUN = r"(?:pulsante|tasto|bottone|menu|voce|scheda|opzione|link|collegamento|icona|campo|casella|scritta|parola|titolo|nome|numero)"
_SCR_WHERE = r"(?:(?:qui\s+)?(?:sul|nel|sullo|nello)\s+(?:mio\s+)?(?:schermo|computer|mac|desktop|monitor)|sullo schermo|nello schermo|lo schermo|qui sullo schermo|in questa (?:pagina|schermata|finestra)|nella pagina|nella schermata|qui)"
_SCR_ART = r"(?:(?:il|lo|la|l|i|le|gli|un|una|uno|quel|quella|questo|questa)\s+)?"
_SCR_FIND = [
    re.compile(rf"^(?:(?:ma|senti|aria|scusa)\s+)*(?:non\s+(?:trovo|riesco a trovare|vedo)|dov e|dove e|dove si trova|dove sta|dove trovo|dove vedo|(?:mi\s+)?(?:indichi|indicami|mostrami|dimmi|segnami|evidenziami|fammi vedere|fammi trovare|fammi capire)\s+(?:dove\s+(?:e|si trova|sta)|dov e)|(?:mi\s+)?(?:indichi|indicami|mostrami|segnami|evidenziami)|(?:mi\s+)?(?:trovi|trovami|trova|trovarmi|indicarmi|mostrarmi|segnarmi|evidenziarmi))\s+{_SCR_ART}{_SCR_NOUN}\s+(?:chiamato\s+|chiamata\s+|con scritto\s+|che dice\s+)?(?P<t>.+?)(?:\s+{_SCR_WHERE})?$"),
    re.compile(rf"^(?:non\s+(?:trovo|riesco a trovare|vedo)|dov e|dove e|dove si trova|dove sta|(?:mi\s+)?(?:trovi|trovami|indicami|mostrami))\s+{_SCR_ART}(?P<t>.+?)\s+{_SCR_WHERE}$"),
    re.compile(r"^(?:(?:ma|senti|aria)\s+)*(?:come\s+(?:faccio a|posso|si fa a|devo)\s+(?:trovare|vedere|raggiungere|accedere a|aprire|arrivare a)|dove\s+(?:trovo|vedo))\s+(?:il\s+|lo\s+|la\s+|l\s+|i\s+|le\s+|gli\s+)?(?:" + _SCR_NOUN + r"\s+)(?:chiamato\s+|chiamata\s+|con scritto\s+)?(?P<t>.+)$"),
    re.compile(r"^(?:(?:ma|senti|aria|scusa)\s+)*(?:mi\s+)?(?:mostri|mostrami|indicami|indichi|dimmi|dici)\s+(?:dove\s+(?:devo\s+)?(?:clicco|cliccare|premo|premere|tocco|toccare|schiaccio|schiacciare)|su cosa\s+(?:devo\s+)?(?:clicco|cliccare|premere|premo))\s+(?:per|se voglio|per poter)\s+(?P<t>.+)$"),
    re.compile(r"^(?:(?:ma|senti|aria|scusa)\s+)*(?:su\s+(?:quale|che|quel)\s+(?:pulsante|tasto|bottone|icona|voce|link)|quale\s+(?:pulsante|tasto|bottone|icona|voce|link))\s+(?:devo\s+)?(?:premere|cliccare|toccare|schiacciare|selezionare|usare|uso|premo|clicco)\s+(?:per|se voglio)\s+(?P<t>.+)$"),
    re.compile(r"^(?:(?:ma|senti|aria)\s+)*(?:dove\s+(?:devo\s+)?(?:clicco|cliccare|premo|premere|tocco|toccare)|su cosa\s+(?:devo\s+)?(?:clicco|cliccare|premere|premo)|che (?:pulsante|tasto|bottone) (?:devo )?(?:premere|premo|cliccare|clicco))\s+(?:per|se voglio|per poter)\s+(?P<t>.+)$"),
]
_SCR_SOFT = [re.compile(r"^(?:(?:ok|ma|senti|allora|aria|scusa|dai|e)\s+)*(?:(?:mi\s+)?(?:di|dici|dimmi|dirmi|dicami|sai dirmi|sai dire|mi sai dire|diresti|indichi|indicami|mostrami|segnami|trovami|evidenziami)\s+)?"
                        r"(?:(?:nel|sul|sullo|nello)\s+(?:mio\s+)?(?:schermo|computer|mac|desktop|monitor),?\s+)?"
                        r"(?:dove\s+(?:c e|si legge|vedi|trovi|e|sta|si vede)|dov e|in che punto (?:c e|e|sta))\s+(?:scritto|scritta|la scritta|la parola|la frase|scritta la parola)\s+(?P<t>.+?)(?:\s+" + _SCR_WHERE + r")?$")]
# «indicami tutti i punti dove c'è scritto AVS», «segnami tutti i posti in cui compare la parola Aria», «mostrami ogni punto con scritto Salva», «tutte le volte che compare…»
_SCR_ALL = re.compile(r"^(?:(?:ok|ma|senti|allora|aria|scusa|dai|e)\s+)*(?:mi\s+)?(?:indichi|indicami|mostrami|segnami|trovami|evidenziami|fammi vedere)\s+"
                      r"(?:(?:tutt[ie]|ogni)\s+)?(?:(?:i|le|gli|il|la)\s+)?(?:punti|punto|posti|posto|posizioni|luoghi|zone|parti|occorrenze|volte|volta|scritte|parole)\s+"
                      r"(?:in cui|dove|nei quali|nelle quali|con|nel quale|che)\s+(?:(?:c e|compare|appare|si legge|e scritto|e scritta|si vede|si trova)\s+)?(?:scritto\s+|scritta\s+)?(?:la scritta\s+|la parola\s+|la frase\s+|le parole\s+)?"
                      r"(?P<t>.+?)(?:\s+" + _SCR_WHERE + r")?$")
_SCR_SOFT.append(_SCR_ALL)
_SCR_FIND.append(_SCR_ALL)                                                       # pronta anche a schermo spento: lo strumento risponde onesto che e' spento (e non cerca «AVS» in una ricetta)
_SCR_SOFT.append(re.compile(r"^(?:(?:ma|senti|aria|scusa)\s+)*non\s+(?:trovo|riesco a trovare|vedo)\s+(?:il\s+|lo\s+|la\s+|l\s+|i\s+|le\s+|gli\s+)?(?P<t>(?:\w+\s+){0,2}(?:barra|menu|pulsante|tasto|bottone|icona|scheda|campo|opzione|link|casella|impostazioni|cestino|collegamento)\b.*)$"))
_SCR_SOFT.append(re.compile(r"^(?:(?:ok|ma|senti|allora|aria|scusa|dai|e)\s+)*(?:aiutami a|mi aiuti a|aiutami con|mi aiuti con|vorrei)\s+(?:trovare|cercare|individuare|localizzare)\s+(?P<t>(?:l\s+|il\s+|la\s+|lo\s+|le\s+|i\s+|un\s+|una\s+)?(?:\w+\s+){0,2}(?:impostazioni|preferenze|menu|pulsante|tasto|bottone|opzione|opzioni|funzione|icona|scheda|barra|campo|collegamento|link|cestino|esporta\w*|salva\w*|stampa|condivid\w*|invia|annulla|chiudi|cerca)\b.*)$"))
# «dov'e' scritto X?» / «indicami dove c'e' scritto X» valgono per lo schermo SOLO se la lettura dello schermo e' accesa: altrimenti sono domande su un documento («c'e' scritto che…?»)
_SCR_FIND.append(re.compile(r"^(?:cerca|cercami|trova|trovami)\s+(?P<t>.+?)\s+" + _SCR_WHERE + r"$"))
_SCR_FIND.append(re.compile(rf"^(?:(?:ma|senti|aria|scusa|ok)\s+)*(?:indicami|mostrami|segnami|evidenziami|trovami|cercami|indica|mostra|segna|evidenzia|trova|cerca|fammi vedere|fammi trovare)\s+{_SCR_WHERE}\s+{_SCR_ART}(?:{_SCR_NOUN}|parole|scritte|pulsanti|tasti|icone)\s+(?:chiamato\s+|chiamata\s+|con scritto\s+|che dice\s+)?(?P<t>.+)$"))      # «indicami sullo schermo la parola Salva»
_SCR_TAILCMD = re.compile(r"[\s,;:]*\b(?:indicamel[oa]|indicamel[ie]|mostramel[oa]|segnamel[oa]|evidenziamel[oa]|trovamel[oa]|fammel[oa] (?:vedere|trovare)|per favore|per piacere|grazie)\W*$", re.I)                                                                          # «trova Esporta sullo schermo»
_SCR_POINT = re.compile(r"^(?:(?:ok|ma|senti|allora|aria|scusa|dai|e)\s+)*(?:(?:puoi|potresti|riesci a)\s+)?(?:indicamel[oa]|indicarmel[oa]|mostramel[oa]|mostrarmel[oa]|segnamel[oa]|segnarmel[oa]|evidenzial[oa]|evidenziamel[oa]|me l[oa] (?:indichi|mostri|segni|evidenzi|fai vedere)|fammel[oa] vedere|fammel[oa] vedere dove|fammi vedere dove|"
                        r"indicami dove|mostrami dove|segnalo|segnala|dove di preciso|dov e di preciso)(?:\s+(?:sullo schermo|con un cerchio|per favore|per piacere|pure|ora|adesso))*$")
_SCR_CUE = re.compile(r"\b(?:sullo schermo|nello schermo|dallo schermo|lo schermo|dello schermo|allo schermo|a schermo|(?:questa|quella) (?:schermata|pagina|finestra)|la (?:schermata|pagina)|(?:quello|cio) che (?:vedi|c e scritto|c e|sto guardando|sto leggendo|sto vedendo|vedo|hai davanti|ho davanti|sto facendo|faccio|ho aperto|ho sul computer|ho sul mac)|"
                      r"cosa sto guardando|cosa sto leggendo|cosa c e scritto qui)\b")
# la frase e' una richiesta (non un racconto) e non parla di altro («spegni lo schermo», «lo schermo del telefono e' rotto», «registra lo schermo»)
_SCR_REQ = re.compile(r"\b(?:fai|fammi|fammene|farmi|faresti|fare|dammi|dai|dici|dimmi|diresti|puoi|potresti|riesci|vorrei|voglio|devi|dovresti|mi serve|mi servirebbe|guard\w+|controll\w+|legg\w+|riassum\w+|descriv\w+|spieg\w+|aiut\w+|"
                      r"cosa|che cosa|come|secondo te|ti piace|ti sembra|dove|quale|quali|quanti|c e)\b")
_SCR_NOT = re.compile(r"\b(?:stamp\w*|spegn\w*|chiud\w*|abbass\w*|alz\w*|luminosita|oscur\w*|rott\w*|crepat\w*|blocc\w*|condivid\w*|registr\w*|screenshot|cattur\w*|ho (?:guardato|visto|letto)|schermo del (?:telefono|cellulare|computer|pc|mac|tv|televisore)|schermo (?:intero|blu|nero))\b")
_SCR_DEIXIS = re.compile(r"\b(?:questo|questa|quest|quel|quella|quello|questi|queste)\s+(?:errore|messaggio|avviso|popup|pop up|finestra|pagina|sito|articolo|email|e[ -]?mail|mail|grafico|tabella|immagine|foto|schermata|pulsante|menu|app|programma|modulo|form|link|post|notifica|video|fattura|dati|schema|diagramma|slide|presentazione)\b")
_SCR_DEIXIS_STRONG = re.compile(r"\b(?:questo|questa|quest|quel|quella|quello)\s+(?:errore|avviso|popup|pop up|finestra|schermata|pulsante|notifica)\b")
_SCR_DEIXIS_WEAK = re.compile(r"\b(?:questo|questa|quest|quel|quella|quello)\s+(?:testo|frase|paragrafo|titolo|codice|elenco|numero|risultato)\b")
_SCR_DOCNOUN = re.compile(r"\b(?:file|documento|pdf|contratto|bolletta|fattura|lezione|manuale|relazione|tesi|verbale|preventivo|ricevuta|referto|polizza|ricetta)\b")
_SCR_ASKV = re.compile(r"\b(?:riassum\w+|riassunt\w+|spieg\w+|traduc\w+|tradur\w+|legg\w+|cosa significa|che significa|che cosa significa|vuol dire|cosa dice|che dice|cosa c e scritto|che ne pensi|che ne dici|secondo te|descriv\w+|analizz\w+|commenta\w*|valuta\w*|giudica\w*|corregg\w+|controll\w+|aiut\w+|e chiar[oa]|e corrett[oa]|e giust[oa]|e sicur[oa]|e affidabile|e leggibile|c e (?:un|qualche|qualcosa)|cosa non va|cosa cambieresti|come lo trovi|ti piace|cosa vedi|dimmi (?:cosa|se|di cosa)|di cosa parla|di cosa si tratta|cos e)\b")
_SCR_BARE = re.compile(r"^(?:(?:ok|ma|senti|allora|aria|scusa|dai|per favore|per piacere)\s+)*(?:(?:mi\s+)?(?:guarda|guardami|guardi|dai (?:un )?occhiata a|controlla|leggi|leggimi|riassumi|riassumimi|descrivi|descrivimi)\s+(?:un po |un attimo |pure )?(?:lo schermo|la schermata|questa schermata|questa pagina|la pagina|questa finestra|quello che vedi|tutto|cosa c e)|"
                       r"(?:che cosa|cosa) (?:vedi|c e|c e scritto)(?: qui| sullo schermo| nello schermo| sulla pagina)?|cosa sto (?:guardando|leggendo)|cosa c e (?:sullo schermo|nello schermo|scritto qui|qui)|(?:puoi|riesci a|sei in grado di) vedere (?:lo schermo|quello che (?:vedo|ho davanti|c e)))$")


_SCR_POINTWORD = re.compile(r"\b(?:indic\w+|mostr\w+|segn\w+|evidenzi\w+|trov\w+|cerc\w+)\b")
_SCR_THING = re.compile(r"\b(?:scritta|parola|pulsante|tasto|bottone|icona|voce di menu|link|schermo|schermata)\b")


def screen_attempt(text: str) -> tuple[str, str, bool] | None:
    """Chiede di indicare/trovare qualcosa «sullo schermo» ma nessuna regola l'ha capita: il chatbot, lasciato solo, direbbe «ti indico subito…» senza fare niente."""
    c = canonical(text)
    f, t = _fold(c), normalize(c)
    if not t or len(t.split()) > 30 or _QUESTION_START.match(t) or _SCR_NOT.search(f):
        return None
    if _SCR_POINTWORD.search(f) and _SCR_THING.search(f):
        return ("schermo", "«non trovo il pulsante Esporta» o «dov'è la scritta Salva»", False)
    return None


_SCR_PEEL = re.compile(r"^(?:(?:tutt[ie]|ogni)\s+)?(?:(?:i|le|gli|il|la)\s+)?(?:punti|punto|posti|posto|posizioni|luoghi|zone|parti|occorrenze|volte|volta|scritte|parole)\s+(?:in cui|dove|nei quali|nelle quali|con|nel quale|che)\s+"
                       r"(?:(?:c['’ ]?[eè]|compare|appare|si legge|[eè] scritt[oa]|si vede|si trova)\s+)?(?:scritt[oa]\s+)?(?:la scritta\s+|la parola\s+|la frase\s+|le parole\s+)?", re.I)


def _last_sentence(text: str) -> str | None:
    """L'ultima frase, se quelle prima sono solo un commento breve («Ok, figo.», «Bene, grazie!»)."""
    parts = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]
    if len(parts) >= 2 and sum(len(p.split()) for p in parts[:-1]) <= 8:
        return parts[-1]
    return None


def screen_request(text: str, screen_on: bool = False) -> ToolCall | None:
    """«non trovo il pulsante Esporta» -> SCHERMO(dove|Esporta); «cosa vedi sullo schermo?» -> SCHERMO(leggi|); «cosa ne pensi di quello che vedo?» -> SCHERMO(parere|<la frase>).
    Serve un riferimento esplicito allo schermo (o a «quello che vedo/sto leggendo»): «dov'è Roma?» e «cosa ne pensi di mio cugino?» non sono richieste sullo schermo."""
    last = _last_sentence(text)                                                                     # «Ok, figo. Indicami dove c'e' scritto AVS»: la richiesta e' l'ultima frase, prima c'e' solo un commento
    cands = [(raw, _fold(raw).strip(" .!?")) for raw in (canonical(text), text.strip()) + ((canonical(last), last) if last else ())]          # «guarda lo schermo»: canonical() toglie «guarda» e «puoi» come intercalari, quindi si prova anche la frase com'e'
    cands = [(r, f) for r, f in cands if f and len(f.split()) <= 40]
    for raw, f in cands:
        for rx in (_SCR_FIND + _SCR_SOFT if screen_on else _SCR_FIND):
            m = rx.match(f)
            if m:
                t = raw.strip()[m.start("t"):m.end("t")].strip(" .,;:!?\"'«»")
                t = re.sub(r"^(?:(?:di|del|della|dello|dei|degli|delle|per|da|a)\s+)+", "", t, flags=re.I).strip()
                t = _SCR_TAILCMD.sub("", t).strip(" .,;:!?")                                   # «non trovo la scritta Salva, indicamela»: «indicamela» non fa parte di cio' che si cerca
                t = _SCR_PEEL.sub("", t).strip(" .,;:!?") or t                                  # «ogni punto dove si legge Salva» -> «Salva»
                if rx in _SCR_SOFT and re.search(r"\b(?:document\w*|file|pdf|contratto|manuale|nel testo|nella ricetta)\b", _fold(t)):
                    continue                                                                    # «dov'e' scritto il prezzo nel contratto»: e' un documento
                if t and len(t.split()) <= 6:
                    return ToolCall("SCHERMO", f"dove|{t}")
    if screen_on and any(re.match(r"^(?:che|quale|quali)\s+(?:scritta|scritte|testo|parola|parole|titolo|voce|voci|pulsanti|icone)\s+c e(?:no)?\s+(?:nella|sulla|sul|nel|in|nello|sullo)\s+\w+", f) for _r, f in cands):
        return ToolCall("SCHERMO", f"parere|{text.strip(' .!?')}")                              # «che scritta c'e' nella barra in alto?»
    for _raw, f in cands:                                                                # «cosa significa questo errore?», «leggimi questa email», «secondo te questo grafico e' chiaro?»: parlano di quello che si vede
        given = bool(re.search(r"[:\"«“]", _raw))                                          # «traduci questa frase in inglese: buongiorno a tutti»: il testo e' nella frase, non sullo schermo
        if given and not screen_on:
            continue
        deixis = _SCR_DEIXIS.search(f) if screen_on else _SCR_DEIXIS_STRONG.search(f)       # a schermo spento solo le cose che esistono SOLO sullo schermo («questo errore», «questo pulsante»): lo strumento risponde onesto «l'ho lasciato spento» invece di far inventare al chatbot
        if (deixis or (screen_on and _SCR_DEIXIS_WEAK.search(f) and not given)) and _SCR_ASKV.search(f) and not _SCR_NOT.search(f) and not _SCR_DOCNOUN.search(f):
            return ToolCall("SCHERMO", f"parere|{text.strip(' .!?')}")
    if any(_SCR_POINT.match(f) for _r, f in cands):
        return ToolCall("SCHERMO", "indica|")
    if any(_SCR_BARE.match(f) for _r, f in cands):
        return ToolCall("SCHERMO", "leggi|")
    for _raw, f in cands:
        if _SCR_CUE.search(f) and not _SCR_NOT.search(f) and (text.rstrip().endswith("?") or _SCR_REQ.search(f)):
            return ToolCall("SCHERMO", f"parere|{text.strip(' .!?')}")                       # la domanda com'e' stata detta, non «ripulita»
    return None


def _file_intent(raw: str, files: list[str] | None = None) -> ToolCall | None:
    """Gli strumenti della cartella di Aria. Gli argomenti si prendono dal testo originale, non da quello normalizzato."""
    folded = _fold(raw)
    ft = folded.lstrip()
    off = len(folded) - len(ft)
    ft = ft.rstrip(" .!?")
    fr = file_request(raw)
    if fr and fr[1]:                                                                    # «mi scriveresti, all'interno del file, la ricetta degli gnocchi?»: un documento nuovo su quell'argomento
        return ToolCall("SCRIVI", f"{fr[0]}|{fr[1]}")
    m = _WRITE.match(ft)
    if m:
        f_top, r_top = ft[m.start(2):m.end(2)], raw[off + m.start(2):off + m.end(2)]
        tm = _SAVE_TAIL.search(f_top)
        topic = (r_top[:tm.start()] if tm else r_top).strip(" .,;:!?")
        return ToolCall("SCRIVI", f"{m.group(1)}|{topic}")
    if _RESEARCH0.match(ft):
        return ToolCall("RICERCA", "")                                                  # «fammi una ricerca e salvala»: su cosa? lo sa dal discorso (conversation) o lo chiede
    m = _RESEARCH.match(ft) or _RESEARCH2.match(ft)
    if m:
        f_top, r_top = ft[m.start(1):m.end(1)], raw[off + m.start(1):off + m.end(1)]
        tm = _SAVE_TAIL.search(f_top)
        return ToolCall("RICERCA", (r_top[:tm.start()] if tm else r_top).strip(" .,;:!?"))
    ftq = re.sub(r"[\"“”«»]", " ", ft)                                                    # le virgolette non servono (stessa lunghezza: gli intervalli restano validi)
    mrb = _READ_BARE.match(ft)
    if mrb:
        return ToolCall("LEGGI", "lista della spesa" if "spesa" in mrb.group(1) or mrb.group(1) == "lista" else "note")
    if _LIST_Q0.match(ft):
        return ToolCall("LEGGI", "lista della spesa")                                       # «cosa devo comprare?»
    ml = _LIST_Q.match(ft)
    if ml:
        return ToolCall("LEGGI", ("lista " + _span(raw, off, ml, 1)).strip() if ml.group(1) else "lista della spesa")
    mf = _FILE_BY_NAME.match(ft)
    if mf and files and not _DOC_Q4.match(ft) and not re.search(r"\b(?:e|poi)\s+(?:dimmi|dammi|spiegami|vedi|guarda|controlla|trova|dici)\b|\?", ft):
        hit = match_file(_span(raw, off, mf, 2), files)
        if hit and not re.search(r"\b(?:schermo|schermata|pagina|email|mail|messaggio)\b", ft):
            return ToolCall("RIASSUMI" if re.match(r"(?:riassum|sintetizz)", mf.group(1)) else "LEGGI", _span(raw, off, mf, 2))
    m = _LISTADD.match(re.sub(r"[,;]\s*(?:per|che|perche|cosi|mi serve|mi servono|abbiamo|ne abbiamo|e urgente)\b.*$", "", ftq))
    if m:
        which = _span(raw, off, m, 2).lower() if m.group(2) else "della spesa"
        return ToolCall("LISTA", f"{which}|{_span(raw, off, m, 1)}")
    m = _LISTADD3.match(ftq)
    if m:
        return ToolCall("LISTA", f"della spesa|{_span(raw, off, m, 2)}")
    m = _LISTADD4.match(ftq)
    if m:
        return ToolCall("LISTA", f"della spesa|{_span(raw, off, m, 1)}")
    m = _LISTADD2.match(ftq)
    if m:
        return ToolCall("LISTA", f"{_span(raw, off, m, 1).lower()}|{_span(raw, off, m, 2)}")
    if files and any("spesa" in normalize(f) for f in files):                          # c'e' una «Lista della spesa»: «aggiungi il latte» e' per quella
        mb = _LISTBARE.match(re.sub(r"[,;]\s*(?:per|che|perche|cosi|mi serve|mi servono|abbiamo|ne abbiamo|e urgente)\b.*$", "", ftq))
        if mb and 0 < len(mb.group(1).split()) <= 5 and not re.search(r"\b(?:calendario|agenda|promemoria|nota|appunto|musica|volume|timer|sveglia|cartella|file|documento|appuntamento|evento|a posto|in ordine)\b", mb.group(1)):
            return ToolCall("LISTA", f"della spesa|{_span(raw, off, mb, 1)}")
        mn = _NOTE2.match(ftq)
        if mn and 0 < len(mn.group(1).split()) <= 12 and not re.search(r"\b(?:file|documento|ricerca|il testo|la lista|la cartella)\b", mn.group(1)):
            return ToolCall("NOTA", _span(raw, off, mn, 1).strip(_Q))
    elif files is not None:
        mn = _NOTE2.match(ftq)
        if mn and 0 < len(mn.group(1).split()) <= 12 and not re.search(r"\b(?:file|documento|ricerca|il testo|la lista|la cartella)\b", mn.group(1)):
            return ToolCall("NOTA", _span(raw, off, mn, 1).strip(_Q))
    m = _NOTE_BLOC.match(ft)
    if m:
        return ToolCall("NOTA", _span(raw, off, m, 1))
    m = _NOTE_COLON.match(ft)
    if m:
        return ToolCall("NOTA", _span(raw, off, m, 1))
    m = _NOTE_BARE.match(ft)
    if m and not _TIMEWORD.search(ft):                                                      # «annota comprare un regalo per Anna» (Apple toglie i due punti); con un orario sarebbe un promemoria
        return ToolCall("NOTA", _span(raw, off, m, 1))
    m = _NOTE.match(ft)
    if m:
        body = _span(raw, off, m, 1) if m.group(1) else ""
        if re.fullmatch(r"(?:per\s+\w+|per\s+favore|per\s+piacere|sulla?\s+\w+(?:\s+\w+)?|di\s+\w+)?", body.lower()) and not re.search(r"\b(?:nota|appunto)\s*[:,]", ft):
            body = ""                                                                        # «salva questa nota per domani»: il contenuto lo dira' dopo
        return ToolCall("NOTA", body)
    m = _READ.match(ft)
    if m:
        return ToolCall("LEGGI", _span(raw, off, m, 1))
    m = _SUMMARIZE.match(ft)
    if m:
        return ToolCall("RIASSUMI", _span(raw, off, m, 1))
    if _LS.search(ft):
        return ToolCall("ELENCO", "")
    if _OPENDIR.search(ft):
        return ToolCall("APRI", "")
    return None


# ---- i poteri sul Mac (promemoria, calendario, musica, volume, app e siti, scorciatoie, documenti, briefing)
# Le frasi arrivano gia' in forma "da comando" (phrasing.canonical): «puoi ricordarmi di…» e' diventato «ricordami di…».
_DAYW = r"(?:oggi|domani|dopodomani|stasera|stamattina|stanotte|lunedi|martedi|mercoledi|giovedi|venerdi|sabato|domenica)"
_CAL = r"(?:calendario|agenda)"
_IN_CAL = rf"(?:in|sul|nel|al|sull|nell)\s+(?:il\s+|mio\s+|il mio\s+)?{_CAL}"
_Q = "\"'«»“” "
_SC_RUN = re.compile(r"^(?:esegui|eseguimi|lancia|lanciami|avvia|avviami|fai partire|attiva|usa|fai)\s+(?:la\s+|lo\s+|quella\s+)?(?:scorciatoia|automazione)\s+(.+)$")
_SC_QUOTED = re.compile(r"^(?:(?:esegui|eseguimi|lancia|lanciami|avvia|avviami|attiva|usa|fai partire|fai)\s+(?:la\s+|quella\s+)?|(?:la\s+)?scorciatoia\s+)[\"«“](.+?)[\"»”]")
_SC_LIST = re.compile(r"\b(?:che|quali)\s+scorciatoie\s+(?:ho|hai|ci sono|esistono)\b|\belenca(?:mi)?\s+le\s+scorciatoie\b|\bmostrami\s+le\s+scorciatoie\b")
_MKV = (r"(?:crea|creami|fai|fammi|prepara|preparami|sistema|sistemami|annota|annotami|scrivi|scrivimi|registra|registrami|aggiungi|aggiungimi|metti|mettimi|segna|segnami|"
        r"imposta|impostami|salva|salvami|programma|programmami|inserisci|inseriscimi|fissa|fissami|genera|generami|organizza|organizzami|pianifica|pianificami|dammi|nuovo|memorizza|memorizzami|registrami|buttami giu|butta giu|buttaci|scrivimi giu|scrivi giu|appuntami giu)")
_MKV_CAL = (r"(?:crea|creami|prepara|preparami|sistema|sistemami|annota|annotami|scrivi|scrivimi|registra|registrami|aggiungi|aggiungimi|metti|mettimi|segna|segnami|"
            r"inserisci|inseriscimi|fissa|fissami|prenota|prenotami|programma|programmami|pianifica|pianificami|organizza|organizzami)")
_REM = re.compile(rf"^(?:ricordami|ricordarmi|{_MKV}\s+(?:un\s+)?promemoria|promemoria)\b[\s:,]*(?:di |che |per )?(.*)$")
_REM_LIST = re.compile(r"\b(?:quali|che|elenca(?:mi)?|leggimi|dimmi|mostrami)\b.*\bpromemoria\b|\bpromemoria\b.*\b(?:ho|da fare|in sospeso)\b|\b(?:cosa|che cosa|cos)\s+ho\b.*\bpromemoria\b|"
                       r"\b(?:quali|che)\s+(?:sono\s+)?(?:le\s+)?cose\s+(?:che\s+)?(?:devo\s+|ho\s+da\s+)?fare\b.*\b(?:sospeso|segnat\w+|ricordat\w+)\b|\b(?:cose|cosa)\s+(?:da fare\s+)?(?:che\s+)?ho\s+in\s+sospeso\b|\bcosa\s+ho\s+in\s+sospeso\b|\bcose\s+da\s+fare\b.*\b(?:ho|oggi)\b")
_EVENT = re.compile(rf"^(?:{_MKV_CAL}\s+(?:(?:una\s+cosa|qualcosa|una\s+roba)\s+)?{_IN_CAL}"
                    rf"|{_MKV_CAL}\s+(?:un\s+|l\s+)?(?:appuntamento|evento|impegno))"
                    r"\s*(?:che\s+|per\s+|di\s+|il\s+|la\s+)?(.*)$")
_EVENT_NOUN = re.compile(rf"^{_MKV_CAL}\s+(?:un\s+|una\s+|l\s+)?((?:riunione|visita|incontro)\b.*)$")
_EVENT_GENERIC = re.compile(rf"^(?:{_MKV_CAL})\s+(?:(?:un|una|l|il|lo|la)\s+)?(.+)$")
_DATE_WORD = re.compile(rf"\b(?:il\s+\d{{1,2}}\b|\d{{1,2}}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)|{_DAYW}\b|prossim[oa]\s+\w+)")
_EVENT_NOT = re.compile(r"\b(?:promemoria|lista|nota|appunto|musica|canzone|brano|volume|timer|sveglia|file|documento|cartella|ricord\w+|spesa|allarme|playlist|album|testo|poesia|lettera|email|mail|messaggio)\b")
_EVENT_TAIL = re.compile(rf"^(?:metti|mettimi|segna|segnami|inserisci|inseriscimi|aggiungi|aggiungimi|scrivi|scrivimi)\s+(?:l\s+|il\s+|la\s+|lo\s+|un\s+|una\s+)?(?P<w>.+?)\s+{_IN_CAL}$")
_EVENT_REV = re.compile(rf"^(.+?)[\s,;:.]+(?:mettil[oa]|segnal[oa]|aggiungil[oa]|inseriscil[oa]|fissal[oa]|prenotal[oa]|mettimel[oa]|segnamel[oa])\s+{_IN_CAL}$")
_AGENDA_WEEK = re.compile(r"\b(?:com e messa|come e messa|come ho|come si presenta|com e|che programma ho|cosa ho|che impegni ho|ho impegni|e piena|e libera|sono libero|sono occupato)\b.*\b(?:settimana|prossimi giorni|weekend|fine settimana)\b|\b(?:settimana|prossimi giorni)\b.*\b(?:impegni|agenda|calendario|appuntamenti|programma)\b")
_AGENDA_ANY = re.compile(r"^(?:(?:che|quali)\s+(?:impegn[oi]|appuntament[oi]|event[oi]|riunion[ei])\b|(?:che|quali)\s+(?:cose\s+|impegni\s+|appuntamenti\s+|eventi\s+|riunioni\s+)?(?:ho|abbiamo|ci sono|c e|devo fare)|cosa\s+(?:ho|abbiamo|c e|mi aspetta|devo fare|ci aspetta)|ho\s+(?:qualcosa|impegni?|appuntamenti|riunion\w+|event\w+|roba|cose)|sono\s+(?:libero|libera|occupat[oa]|impegnat[oa])|(?:ho|hai|c e)\s+qualche\s+\w+)\b(?!.*\b(?:tempo|meteo|piov\w+|sole|freddo|caldo|neve|nuvol\w+|temperatur\w+|vento|timer|sveglia|promemoria)\b)")
_AGENDA_C = re.compile(rf"^(?:per\s+)?({_DAYW})[,\s]+(?:cosa|che(?:\s+cosa)?)\s+(?:ho|mi aspetta|c e|devo fare|abbiamo)\b|^(?:per\s+)?({_DAYW})[,\s]+ho\s+(?:qualcosa|impegni|appuntamenti)\b|^(?:ho|c e)\s+qualcosa\s+(?:per\s+)?({_DAYW})\b|^(?:che|cosa)\s+ho\s+(?:per\s+)?({_DAYW})\b|^ho\s+(?:un\s+)?(?:appuntamento|impegno)\s+(?:per\s+)?({_DAYW})\b|^(?:ho|hai|c e)\s+(?:qualcosa|impegni?|appuntamenti|riunion\w+|event\w+|roba|cose|qualche\s+\w+)\s+(?:da fare\s+)?(?:per\s+|di\s+|in\s+|a\s+)?(?:questa\s+)?(oggi|domani|dopodomani|stasera|{_DAYW})\b|^({_DAYW})[,\s]+sono\s+(?:libero|libera|occupat\w+|impegnat\w+)\b")
_AGENDA_A = re.compile(rf"\b(?:agenda|calendario|impegni|appuntamenti|il programma|programma (?:di|per|del))\b.*\b({_DAYW})\b|\b({_DAYW})\b.*\b(?:agenda|calendario|impegni|appuntamenti)\b")
_AGENDA_B = re.compile(rf"\bcosa ho in agenda\b|\bcosa ho in programma\b|\bcosa ho ({_DAYW})\b|\b(?:ho|hai) (?:degli |dei )?(?:impegni|appuntamenti)\b|\bcos ho\b.*\b(?:programma|agenda|calendario|{_DAYW})\b|"
                       rf"\b(?:che|quali) (?:impegn[oi]|appuntament[oi]|event[oi]) ho\b|\bho qualcosa (?:in|sul|nel) {_CAL}\b|\bsono libero\b.*\b{_DAYW}\b|\bcosa (?:c e|ho) (?:in|sul|nel) {_CAL}\b|"
                       rf"\bcontrolla (?:il\s+|lo\s+)?(?:mio\s+)?{_CAL}\b|\bho qualcosa in programma\b|\bho (?:qualcosa|impegni|roba) (?:in programma|da fare)\b|\bcosa mi e segnato\b|\bho qualcosa di (?:fisso|importante) per\b|\bcosa mi aspetta ({_DAYW})\b|"
                       rf"\b(?:controlla|vedi|guarda)\b.*\b(?:impegni|appuntamenti)\b.*\b{_DAYW}\b|\b(?:che|cosa|quali?)\s+(?:mi\s+)?(?:hai\s+)?(?:messo|segnato|programmato|fissato|scritto)\b.*\b{_DAYW}\b|\bcosa c e scritto per ({_DAYW})\b|\bhai (?:visto )?il mio (?:calendario|programma)\b")
_MUS_VERBS = r"(?:metti su|metti|mettimi|butta su|butta|spara|fai andare|fai partire|fammi sentire|suona|suonami|riproduci|ascolta|ascolterei(?: volentieri)?|ascoltiamo|fai ascoltare)"
_MUS_NAMED = re.compile(rf"^{_MUS_VERBS}\s+(?:la |il |lo |l |un |una )?(canzone|brano|pezzo|album|disco|playlist)\s+(?:di |dei |dell |degli |delle )?(.+)$")
_MUS_QTY = r"(?:(?:un\s+po\s+di|un\s+po|della|delle|dei|degli|di|qualche|alcune|alcuni|la|le|su\s+la|su)\s+)?"
_MUS_PLAY_X = re.compile(rf"^({_MUS_VERBS})\s+(?:(?:un\s+po\s+di|un\s+po|della|delle|di|qualche|alcune|le|la|i|gli)\s+)?((?:musica|canzoni|brani|qualcosa)\s+(?:di\s+|dei\s+|del\s+|dello\s+|della\s+|delle\s+)?|qualcosa\s+di\s+)?(.+)$")
_MUS_PLAY = re.compile(rf"^(?:(?:metti su|metti|mettimi|fai partire|fai ripartire|riprendi|avvia|accendi|riavvia|rimetti|rimettimi|ricomincia|butta su|suona|suonami|riproduci|fammi sentire|fammi ascoltare|ascolta)\s+{_MUS_QTY}(?:musica|canzoni|brani|qualcosa)|riprendi|riprendila|riprendilo|play|rimettila|(?:riprendi|fai ripartire|rimetti|riavvia|fai continuare)\s+(?:la\s+|il\s+)?(?:canzone|brano|pezzo|musica|riproduzione|playlist))$")
_MUS_APP = re.compile(r"\s+(?:su|con|in|da|dal|dalla|tramite|usando|attraverso)\s+(apple\s+music|spotify|musica|itunes|youtube\s+music)\s*$")
_MUS_PAUSE = re.compile(r"^(?:metti in pausa|mettila in pausa|pausa|pausa musica|stop musica)\b|\b(?:zitt[ao]|basta|stop|silenzio)\s+(?:con\s+)?(?:la\s+)?musica\b|\b(?:metti in pausa|mettiamo in pausa|ferma|fermiamo|stoppa|stoppiamo|spegni|spegniamo|interrompi|interrompiamo|sospendi|sospendiamo|togli|metti via|basta con)\s+(?:(?:per\s+)?(?:un\s+)?(?:attimo|momento|secondo)\s+)?(?:la\s+|il\s+|lo\s+)?(?:musica|canzone|brano|riproduzione|player)\b|"
                        r"\bmetti\s+(?:la\s+|il\s+)?(?:musica|canzone|brano)\s+in\s+pausa\b|\bmetti tutto in pausa\b")
_MUS_NEXT = re.compile(r"\b(?:prossima|successiva|prossimo|successivo)\s+(?:canzone|traccia|brano|pezzo)\b|\b(?:canzone|traccia|brano|pezzo)\s+(?:successiva|successivo|dopo)\b|"
                       r"\bsalta\s+(?:questa\s+|questo\s+|quella\s+|quello\s+)?(?:canzone|traccia|brano|pezzo)\b|\bpassa\s+(?:alla\s+|al\s+)?(?:prossima|successiva|prossimo|successivo)\b|\bpassa alla (?:canzone|traccia) che viene dopo\b|"
                       r"^(?:salta|prossima|successiva|avanti|next|skip|cambia canzone|cambia brano|cambia)$")
_MUS_PREV = re.compile(r"\btorna\s+indietro(?:\s+di\s+(?:una|un)\s+(?:canzone|traccia|brano|pezzo))?$|\b(?:canzone|traccia|brano|pezzo)\s+precedente\b|\btorna\s+(?:alla\s+)?(?:canzone\s+)?precedente\b|\bcanzone di prima\b")
_MUS_NOW = re.compile(r"\bche\s+(?:canzone|brano|musica)\s+(?:e|sta suonando|sto ascoltando|stiamo ascoltando|stai suonando)\b|\b(?:cosa|che cosa|che)\s+sto\s+ascoltando\b|\bcosa sta suonando\b|\bche cosa sta suonando\b|\bchi canta\b")
_MUS_GENRES = ("jazz", "rock", "pop", "classica", "rap", "blues", "techno", "house", "reggae", "metal", "lofi", "lo fi", "hip hop", "country", "folk", "opera", "dance", "elettronica",
               "indie", "punk", "soul", "funk", "disco", "cantautori", "cantautorato", "colonne sonore", "rilassante", "rilassanti", "tranquilla", "allegra", "allegro", "energica", "energico", "romantica", "romantico", "tranquillo", "malinconica", "malinconico", "motivante", "carica", "calma", "calmo", "triste",
               "dolce", "da studio", "per studiare", "per dormire", "per lavorare", "di sottofondo", "per allenarmi", "da allenamento", "natalizia", "classico", "strumentale", "chill",
               "ballabile", "da ballare", "per ballare", "per cucinare", "per cenare", "per correre", "per la corsa", "per la spiaggia", "per concentrarmi", "per rilassarmi", "lounge", "trap",
               "latina", "latino", "swing", "bossa", "ambient", "lirica", "sinfonica", "orchestrale", "italiana", "italiano", "straniera", "anni 60", "anni 70", "anni 80", "anni 90", "anni 2000", "anni 2010")
_MUS_NOT = re.compile(r"\b(?:wi[ -]?fi|bluetooth|luce|luci|lampada|riscaldamento|condizionatore|modalita aereo|non disturbare|video|film|serie|campanello|sveglia|allarme|sirena|clacson|citofono|in copia|a posto|da parte|in ordine|a dormire|a letto|il caso|che io|che tu|che lui|che lei|"
                      r"in moto|in funzione|l acqua|la tavola|il tavolo|da salvare|da cercare)\b")
_MUS_STRONG = {"suona", "suonami", "riproduci", "ascolta", "ascolterei", "ascolterei volentieri", "ascoltiamo", "fai ascoltare", "fai partire", "fammi sentire"}      # verbi che parlano solo di musica ("metti" no)
_QT = r"(?:un\s+po|un\s+pochino|un\s+poco|un\s+tantino|appena|ancora)"
_VOL_UP = re.compile(rf"\b(?:alza|alzami|alzalo|aumenta|aumentalo)\b.*\b(?:volume|musica|audio|suono|voce|livello)\b|\bvolume\s+(?:su|piu\s+alto)\b|^(?:{_QT}\s+)?(?:piu\s+forte|piu\s+alto|alza|alzalo|aumenta|aumentalo|su)(?:\s+{_QT})?$|"
                     rf"\bpiu\s+forte\s+per\s+favore\b|\b(?:alza|alzalo|aumenta)\s+{_QT}\b|\bsali\b.*\bvolume\b|^(?:piu|ancora piu|un po piu)\s+(?:volume|audio)$|"
                     rf"^parl\w+\s+(?:un po\s+)?(?:piu\s+)?(?:forte|alto)\b|\bnon ti sento\b|\bti sento\s+(?:poco|male|a malapena|pochissimo)\b|\bnon si sente\b|^parl\w+\s+a\s+voce\s+piu\s+alta\b")
_VOL_DOWN = re.compile(rf"\b(?:abbassa|abbassami|abbassalo|diminuisci|riduci)\b.*\b(?:volume|musica|audio|suono|voce|livello)\b|\bvolume\s+(?:giu|piu\s+basso)\b|^(?:{_QT}\s+)?(?:piu\s+piano|piu\s+basso|abbassa|abbassalo|giu)(?:\s+{_QT})?$|"
                       rf"\b(?:abbassa|abbassalo|diminuisci)\s+{_QT}\b|\bscendi\b.*\bvolume\b|^(?:meno|un po meno|ancora meno)\s+(?:volume|audio)$|"
                       rf"^parl\w+\s+(?:un po\s+)?(?:piu\s+)?(?:piano|basso)\b|^parl\w+\s+a\s+voce\s+piu\s+bassa\b")
_VOL_LOUD = re.compile(r"\btroppo\s+(?:alto|forte)\b")
_VOL_SOFT = re.compile(r"\btroppo\s+(?:basso|piano|debole)\b")
_VOL_SET = re.compile(r"\b(?:volume|audio)\s+(?:a|al|su|sul|sullo|sulla|alla|all|alle)\s+(?:un\s+|il\s+|lo\s+)?(\d{1,3}|[a-z]+(?: [a-z]+)?)\b|\b(massimo|minimo) volume\b|\bvolume\s+(zero|massimo|minimo)\b|\b(azzera)\s+(?:il\s+)?(?:volume|audio)\b")
_VOL_MUTE = re.compile(r"\b(?:muta|silenzia|togli l audio|zittisci|metti in muto|metti il muto|mettere in muto|in modalita silenziosa|metti in silenzioso)\b")
_VOL_UNMUTE = re.compile(r"\b(?:riattiva|riaccendi|rimetti)\s+(?:l audio|il volume)\b|\btogli il muto\b")
_VOL_GET = re.compile(r"\b(?:a che volume|quanto e il volume|che volume)\b")
_ENGINES = r"(youtube|google|wikipedia|amazon|spotify|github)"
_WEB_SEARCH = re.compile(rf"^(?:cerca|cercami|ricerca|trova|trovami|controlla|guarda|fammi vedere|mostrami|dai un occhiata)\s+(?:su|in|con|nel|sul)\s+{_ENGINES}[:,\s]+(?:per\s+(?:vedere|capire|sapere)\s+(?:se\s+)?|a\s+)?(.+)$")
_WEB_OPENSEARCH = re.compile(rf"^(?:apri|aprimi|vai su|portami su|vai a)\s+{_ENGINES}\s+e\s+(?:cerca|cercami|trova|trovami|metti|mettimi|guarda)\s+(.+)$")
_WEB_LINK = re.compile(rf"^(?:dammi|mandami|passami)\s+(?:un\s+)?link\s+(?:su|a|di)\s+{_ENGINES}\s+(?:per|di|su)\s+(.+)$")
_WEB_IFTHERE = re.compile(rf"^(?:controlla|vedi|cerca)\s+se\s+c\s+e\s+(.+?)\s+(?:su|in)\s+{_ENGINES}\b.*$")
_WEB_SEARCH2 = re.compile(rf"^(?:cerca|cercami|ricerca|trova|trovami)\s+[\"«“](.+?)[\"»”]\s+(?:su|in|con|nel|sul)\s+{_ENGINES}$|^(?:cerca|cercami|ricerca|trova|trovami)\s+(.+?)\s+(?:su|in|con|nel|sul)\s+{_ENGINES}$")
_MAPS_ON = r"(?:su|sulla|sulle|nella|nelle|in|con|con le|con la|usando|tramite|su google|su apple)\s+(?:le\s+|la\s+)?(?:mappa|mappe|maps)"
_MAPS = re.compile(rf"^(?:mostrami|portami|fammi vedere|apri|cerca|trova|indicami|guidami|vedere)\s+(?:dov e |dove si trova |la strada per |il percorso per |la posizione di |la zona dove si trova )?(.+?)\s+{_MAPS_ON}$")
_MAPS_ON2 = re.compile(rf"^(?:mostrami|fammi vedere|controlla|vedi)\s+(?:su\s+|sulla\s+|sulle\s+)(?:google\s+|apple\s+)?(?:maps|mappe|mappa)\s+(?:se c e traffico (?:per|verso|a)\s+|dov e\s+)?(.+)$")
_MAPS_THING = re.compile(r"^(?:mostrami|fammi vedere|dammi|apri|indicami)\s+(?:la\s+)?(?:mappa|posizione|zona|indirizzo|percorso)\s+(?:di|del|della|dello|dei|dell|per|dove si trova)\s+(.+)$")
_MAPS_NEAR = re.compile(r"^(?:dov e|dove si trova|dove trovo|dov e che trovo|trovami|trova|cercami|cerca|indicami|mostrami|portami a|portami in|dimmi dov e|dimmi dove si trova)\s+(?:la\s+|il\s+|lo\s+|l\s+|un\s+|una\s+|uno\s+|un po di\s+)?(?P<t>.+?)\s+(?:piu vicin[oa]|vicino a me|qui vicino|nei dintorni|nelle vicinanze|intorno a me|qui intorno|nelle mie vicinanze|vicino casa|vicino a casa|piu vicini|nei paraggi|qui nei paraggi)$")
_MAPS_HOW = re.compile(r"^(?:come|in che modo)\s+(?:si\s+)?(?:arrivo|arriva|arrivare|posso arrivare|raggiungo|raggiungere|si raggiunge|vado|andare|faccio ad arrivare|faccio a raggiungere|faccio ad andare|faccio a trovare|faccio ad andare|trovo)\s+(?:a|ad|in|da|verso|per|alla|al|allo|all|alle|ai)\s+(.+)$|"
                       r"^(?:(?:dammi |indicami |mostrami |fammi vedere )?(?:le )?indicazioni(?: stradali)? per|(?:indicami|mostrami|fammi vedere|dammi) (?:la strada|il percorso|la via) (?:per|verso|fino a|a)|naviga verso|navigami verso|portami|accompagnami|guidami)\s+(?:(?:arrivare|andare|raggiungere)\s+)?(?:(?:a|ad|in|verso|per|fino a|alla|al|allo|all)\s+)?(.+)$|"
                       r"^(?:fammi vedere|mostrami)\s+(?:dove si trova|dov e|dove sta)\s+(.+)$")
_PLACE_WORD = re.compile(r"\b(?:piazza|via|viale|corso|largo|stazione|aeroporto|ospedale|universita|centro|stadio|museo|parco|porto|ristorante|hotel|albergo|negozio|supermercato|farmacia|chiesa|teatro|cinema|"
                         r"ufficio|scuola|palazzo|castello|lago|mare|spiaggia|ponte|duomo|municipio|banca|posta|biblioteca|mercato|panificio|bar|pizzeria|giardino|cattedrale|galleria|quartiere|zona|"
                         r"benzinaio|distributore|parcheggio|fermata|ambulatorio|clinica|pasticceria|libreria|palestra|piscina|campo|colosseo)\b")
_MAPS_NOT = re.compile(r"^(?:essere|avere|fare|dire|capire|stare|andare|finire|sapere|riuscire|fine|il fine|soldi|stipendio|tempo|capo|casa mia|dormire|mangiare|lavorare)\b")
_OPEN_STRONG = re.compile(r"^(?:apri|aprimi|avvia|avviami|lancia|lanciami)\s+(?:l app\s+|l applicazione\s+|il programma\s+|il\s+|lo\s+|la\s+|l\s+)?(.+)$")
_OPEN_SITE = re.compile(r"^(?:apri|aprimi|vai su|vai a|portami su|portami a|lancia)\s+(?:il\s+)?sito\s+(?:web\s+)?(?:di\s+|del\s+|della\s+|dei\s+|dello\s+)?(.+)$")
_OPEN_SHOW = re.compile(r"^(?:fammi vedere|mostrami|fammi dare un occhiata a)\s+(?:l\s+|il\s+|lo\s+|la\s+)?(calendario|calcolatrice|promemoria|note|mail|posta|messaggi|mappe|safari|orologio|foto)$")
_OPEN_WEAK = re.compile(r"^(?:vai su|vai a|portami su|portami a)\s+(?:il\s+|lo\s+|la\s+|l\s+)?(.+)$")
_DOC_Q1 = re.compile(r"^(?:nel|sul|dal|nello|nella)\s+(?:mio\s+)?(?:file|documento|pdf|testo|contratto|manuale|libro|articolo)\s+(.+?)\s*[,:]\s*(.+)$")
_DOC_Q2 = re.compile(r"^(?:chiedi|domanda)\s+(?:al|sul)\s+(?:file|documento|pdf)\s+(.+?)\s*[,:]\s*(.+)$")
_DOC_Q3 = re.compile(r"^(?:cosa|che cosa)\s+dice\s+(?:il\s+|la\s+)?(?:file|documento|pdf|testo|contratto)\s+(.+?)\s+(?:su|sul|sulla|riguardo a|a proposito di)\s+(.+)$")
_DOC_Q4 = re.compile(r"^(?:leggi|guarda|controlla|apri)\s+(?:il\s+|la\s+|lo\s+|l\s+)?(?:file\s+|documento\s+|pdf\s+)?(.+?)\s+e\s+(?:dimmi|dammi|spiegami|vedi|guarda|controlla|trova)\s+(.+)$")
_DOC_CUE = re.compile(r"\b(?:file|documento|pdf|word|docx|contratto|bolletta|fattura|manuale|libro|articolo|appunti|relazione|tesi|lezione|dispensa|verbale|preventivo|ricevuta|referto|capitolo|polizza|clausola)\b")
_DOC_ASK = re.compile(r"\b(?:occhiata|cosa|che cosa|cos e|quanto|quando|dove|chi|come|quale|quali|perche|c e scritto|e scritto|dice|dicono|parla|riporta|indica|spiega|spiegami|leggi|leggimi|guarda|controlla|dimmi|chiedi|domanda|si dice|vedi|trova|cerca)\b")
_DOC_DEIXIS = re.compile(r"\b(?:(?:questo|quest|quel|quello|il)\s+(?:documento|file|pdf|contratto|testo|articolo|libro|manuale|verbale|preventivo|referto|paragrafo|capitolo)|(?:questa|quest|quella|la)\s+(?:bolletta|fattura|lezione|relazione|polizza|ricevuta|clausola|pagina|tesi|dispensa))\b")
_REAL_WORLD = re.compile(r"\b(?:sul|sulla|sullo|sui|sulle|nel|nella|nello|in)\s+(?:muro|muri|cartello|cartellone|insegna|porta|maglietta|maglia|felpa|cappello|etichetta|confezione|scatola|lavagna|striscione|manifesto|bottiglia|cancello|tazza|strada|lapide|targa|pacco|vetrina|bar|negozio|ristorante)\b")
_DOC_SAYS = re.compile(r"\b(?:c e scritto|e scritto|cosa dice|dice che|sta scritto|prevede|indica)\b")
_BRIEFING = re.compile(r"\b(?:briefing|riepilogo del mattino|riepilogo della mattina|riepilogo mattutino|resoconto del mattino|riepilogo della giornata|riassunto della giornata|com e la giornata|come si presenta la giornata|come si presenta la mia giornata|com e la mia giornata|cosa c e oggi|programma di oggi|programma della giornata|"
                       r"che programma ho|riepilogo di oggi|cosa mi aspetta oggi|quadro generale della giornata)\b|"
                       r"\b(?:riepilogo|riassunto|quadro|panoramica|aggiornamento|sintesi)\b.*\b(?:giornata|oggi|impegni|cose da fare|devo fare|programma|meteo)\b|"
                       r"\bcosa devo fare (?:oggi|stasera)\b|\b(?:cosa|che cosa|quali)\b.*\b(?:mi hai|hai)\b.*\b(?:ricordato|programmato|segnato|registrato)\b.*\boggi\b|\bcosa mi hai ricordato\b|"
                       r"\bcosa (?:devo|dovrei|mi serve|mi serve di|ho bisogno di) sapere\b.*\b(?:oggi|stamattina|stasera|giornata)\b|\bdammi il (?:quadro|punto) (?:della situazione|di oggi)\b|\bcosa c e di nuovo oggi\b|\bcosa devo sapere\b|\bcosa mi tocca\b|\b(?:cosa|che cosa|che) (?:ho|devo|mi resta) da fare\b(?!.*\b(?:domani|dopodomani|lunedi|martedi|mercoledi|giovedi|venerdi|sabato|domenica)\b)")
_VOLWORDS = {"zero": 0, "azzera": 0, "meta": 50, "massimo": 100, "minimo": 5, "cento": 100}
_TIMEWORD = re.compile(r"\b(?:domani|dopodomani|stasera|stamattina|stanotte|alle|alle ore|tra|fra|lunedi|martedi|mercoledi|giovedi|venerdi|sabato|domenica|\d+)\b")
# «Apri Safari, devo controllare la mail»: dopo il comando una spiegazione. Per le azioni semplici si guarda solo il comando.
_REASON = re.compile(r"[,;]\s*(?:per favore|per piacere|per cortesia|che|perche|cosi|devo|voglio|vorrei|mi serve|mi servirebbe|ho bisogno|ho voglia|sto|sono|mi sto|mi sono|e urgente|altrimenti|senno|visto che|dato che|tanto|ho|non|ti ho|ora|adesso|dai|eh|ok|mi|ci)\b.*$|"
                     r"[.?!]\s+(?:voglio|volevo|devo|ho bisogno|mi serve|vorrei|ho voglia|mi sto|sto|ho|e urgente|grazie)\b.*$|"
                     r"\s+che\s+(?:devo|voglio|vorrei|mi serve|mi servirebbe|ho bisogno|sto|mi sto|mi sono|ho|mi annoia|mi disturba|mi distrae)\b.*$")


def _app_like(target: str) -> bool:
    """Il nome di un'app o di un sito e' corto e senza giri di frase: «apri il tuo cuore con me» o «vai a dormire, che e' tardi» no."""
    return 0 < len(target.split()) <= 3 and "," not in target and not re.search(r"\b(?:tuo|tua|tuoi|tue|bene|con me|con te|che|perche)\b", target.lower())


def _known_target(folded: str) -> bool:
    from .macos import APP_ALIASES, SITES
    t = folded.strip()
    return t in SITES or t in APP_ALIASES or bool(re.search(r"\.[a-z]{2,}$", t))


def _is_specific(what: str) -> bool:
    """«qualcosa di rilassante» e' un genere/umore (cerca); «qualcosa» e basta e' solo «metti musica»."""
    return bool(what.strip())


def _music_ok(verb: str, lead: str, target_raw: str, target_folded: str) -> bool:
    """«metti Vasco Rossi» si': e' musica. «metti a posto la stanza» no."""
    if _MUS_NOT.search(target_folded):
        return False
    if verb in _MUS_STRONG:
        return True
    if any(ch.isupper() for ch in target_raw if ch.isalpha()) and not target_raw[:1].isdigit():
        return True
    return any(g in target_folded for g in _MUS_GENRES)


def _place_ok(folded: str, original: str) -> bool:
    """«come arrivo a Piazza Bra / al nuovo cinema»: un luogo. «come arrivo a essere felice / a fine mese»: no."""
    if _MAPS_NOT.match(folded) or len(folded.split()) > 7:
        return False
    return bool(_PLACE_WORD.search(folded)) or bool(re.match(r"[A-Z]", original.strip(_Q)))


def _power_intent(raw: str, files: list[str] | None = None) -> ToolCall | None:
    """Gli strumenti sul Mac. Gli argomenti si prendono dal testo originale (maiuscole, accenti, virgole)."""
    folded = _fold(raw)
    ft = folded.lstrip()
    off = len(folded) - len(ft)
    ft = ft.rstrip(" .!?")
    # ---- prima i comandi il cui testo conta per intero (promemoria, calendario, documenti)
    m = _SC_RUN.match(ft) or _SC_QUOTED.match(ft)
    if m:
        return ToolCall("SCORCIATOIA", _span(raw, off, m, 1).strip(_Q))
    if _SC_LIST.search(ft):
        return ToolCall("SCORCIATOIE", "")
    m = _EVENT_REV.match(ft)
    if m:
        return ToolCall("EVENTO", _span(raw, off, m, 1))
    m = _EVENT_TAIL.match(ft)
    if m and not _EVENT_NOT.search(m.group("w")):                                          # «metti la partita di sabato in agenda»
        return ToolCall("EVENTO", raw[off + m.start("w"):off + m.end("w")].strip(" .,;:!?"))
    m = _EVENT.match(ft)
    if m:
        return ToolCall("EVENTO", _span(raw, off, m, 1))
    m = _EVENT_NOUN.match(ft)
    if m:
        return ToolCall("EVENTO", _span(raw, off, m, 1))
    m = _EVENT_GENERIC.match(ft)
    if m and _DATE_WORD.search(ft) and re.search(r"\balle\s+\S+|\bore\s+\d|\ball\s+una\b", ft) and not _EVENT_NOT.search(ft):
        return ToolCall("EVENTO", _span(raw, off, m, 1))
    m = _REM.match(ft)
    if m and not re.match(r"(?:tra|fra)\s+\S+\s+(?:minut|or)", m.group(1)):             # "ricordami tra 10 minuti" resta un timer
        return ToolCall("PROMEMORIA", _span(raw, off, m, 1) if m.group(1) else "")
    if _REM_LIST.search(ft) and not re.match(r"(?:aggiungi|crea|metti|imposta|fammi|segna)", ft):
        return ToolCall("PROMEMORIA_LISTA", "")
    for pat in (_DOC_Q1, _DOC_Q2, _DOC_Q4):
        m = pat.match(ft)
        if m and (files is None or match_file(_span(raw, off, m, 1), files)):
            return ToolCall("DOCUMENTO", f"{_span(raw, off, m, 1)}|{_span(raw, off, m, 2)}")
    m = _DOC_Q3.match(ft)
    if m:
        return ToolCall("DOCUMENTO", f"{_span(raw, off, m, 1)}|Cosa dice su {_span(raw, off, m, 2)}?")
    says = _DOC_SAYS.search(ft)
    if says and says.group(0) in ("dice che", "prevede", "indica") and not (_DOC_CUE.search(ft) or _DOC_DEIXIS.search(ft)):
        says = None                                                                         # «mia moglie dice che russo»: non e' un documento
    if files and ((_DOC_CUE.search(ft) and _DOC_ASK.search(ft)) or says):   # "cosa dice il contratto sull'affitto?": il file si riconosce dai nomi veri
        hit = match_file(ft, files)
        on_screen = bool(_SCR_CUE.search(ft) or re.search(r"\b(?:schermo|schermata|computer|mac|desktop|monitor)\b", ft)         # «dov'e' scritto aria nel mio schermo»: non e' un documento
                         or _REAL_WORLD.search(ft))                                                                              # «sul muro del bar c'e' scritto…»: neppure questo
        if hit is None and (_DOC_DEIXIS.search(ft) or says) and not _DOC_Q4.match(ft) and not on_screen:   # «guarda questo PDF» / «c'e' scritto che…?»: l'ultimo documento della cartella
            docs = [f for f in files if f.lower().endswith((".pdf", ".docx"))]
            hit = (docs or files)[0]
        if hit:
            return ToolCall("DOCUMENTO", f"{os.path.splitext(hit)[0]}|{raw.strip(' .?!')}")
    # ---- da qui in poi conta solo il comando: la spiegazione dopo la virgola si scarta
    ft0 = ft                                                                                # (la frase intera: «domani che ho di bello in agenda» perderebbe «che ho…» come se fosse una spiegazione)
    short = _REASON.sub("", ft)
    ft = short if short.strip() else ft
    nwords = len(ft.split())
    music_app = ""
    ma = _MUS_APP.search(ft)
    if ma and re.search(r"\b(?:musica|canzon\w*|brano|brani|playlist|album|disco|pezzo|suona|suonami|metti|mettimi|riproduci|ascolta|riprendi|pausa)\b", ft[:ma.start()]):
        music_app = "Spotify" if "spotify" in ma.group(1) else "Music"                    # «metti della musica con Apple Music»: l'app scelta a voce
        ft = ft[:ma.start()]
    if _BRIEFING.search(ft):
        return ToolCall("BRIEFING", "")
    if (_AGENDA_A.search(ft0) or _AGENDA_B.search(ft0)) and not _BRIEFING.search(ft0) and not re.search(r"\b(?:tempo|meteo|piov\w+|sole|freddo|caldo|neve|temperatur\w+|vento|promemoria|timer|sveglia)\b", ft0):
        dm0 = re.search(rf"\b({_DAYW})\b", ft0)
        if dm0 or not _AGENDA_WEEK.search(ft0):
            from . import everyday as _ev
            wp0 = _ev.when_phrase(raw)
            return ToolCall("AGENDA", ("weekend" if re.search(r"weekend|fine settimana", wp0, re.I) else _fold(wp0)) if wp0 else (dm0.group(1) if dm0 else "oggi"))
    mfree = re.search(r"\bsono\s+(?:libero|libera|occupat[oa]|impegnat[oa])\b", ft0)
    if mfree and not re.search(r"\b(?:tempo|meteo|piov\w+)\b", ft0):
        from . import everyday as _ev2
        wpf = _ev2.when_phrase(raw)
        if wpf:
            return ToolCall("AGENDA", "weekend" if re.search(r"weekend|fine settimana", wpf, re.I) else _fold(wpf))
    if _AGENDA_WEEK.search(ft) and not re.search(rf"\b{_DAYW}\b", ft) and not re.search(r"\b(?:tempo|meteo|piov\w+|sole|soleggiat\w+|freddo|caldo|neve|nuvol\w+|temperatur\w+|vento)\b", ft):
        return ToolCall("AGENDA", "weekend" if re.search(r"\b(?:weekend|fine settimana)\b", ft) else "settimana")
    ma = _AGENDA_ANY.match(ft)
    if ma:                                                                                 # «cosa ho il 15 ottobre / tra tre giorni / fra due settimane / nel weekend?»
        from . import everyday
        wp = everyday.when_phrase(raw)
        if wp:
            return ToolCall("AGENDA", "weekend" if re.search(r"weekend|fine settimana", wp, re.I) else wp)
    if re.match(r"^(?:ho|hai|c e)\s+(?:qualcosa|impegni?|appuntamenti|riunion\w+|event\w+|roba|cose|qualche\s+\w+)\b.*\b(?:questa settimana|la settimana|settimana prossima|prossima settimana|prossimi giorni|weekend|fine settimana)\b", ft):
        return ToolCall("AGENDA", "settimana")
    mc = _AGENDA_C.match(ft)
    if mc:
        return ToolCall("AGENDA", next(g for g in mc.groups() if g))
    if _AGENDA_A.search(ft) or _AGENDA_B.search(ft):
        dm = re.search(rf"\b({_DAYW})\b", ft)
        return ToolCall("AGENDA", dm.group(1) if dm else "oggi")
    # volume (prima della musica: «abbassa la musica» e' il volume)
    m = _VOL_SET.search(ft)
    if m:
        v = next(g for g in m.groups() if g)
        n = None
        for cand in (v, v.split()[0]):                                                 # «cinquanta per cento»: conta la prima parola
            n = int(cand) if cand.isdigit() else _VOLWORDS.get(cand, number_it(cand))
            if n is not None:
                break
        if n is not None:
            return ToolCall("VOLUME", f"set:{max(0, min(100, n))}")
    m = re.search(r"\b(?:alza|alzalo|aumenta|aumentalo|abbassa|abbassalo|porta|portalo|metti|mettilo|imposta)\w*\s+(?:il\s+)?(?:volume\s+)?(?:fino\s+)?(?:a|al)\s+(\d{1,3})\b(?!\s*(?:minut|ore|second|gradi|per cento\s+di))", ft)
    if m and not re.search(r"\b(?:timer|sveglia|luminosita|riscaldamento|temperatura|gradi)\b", ft):
        return ToolCall("VOLUME", f"set:{max(0, min(100, int(m.group(1))))}")
    if re.search(r"\b(?:alza|aumenta)\b.*\bal massimo\b", ft):
        return ToolCall("VOLUME", "set:100")
    if _VOL_UP.search(ft) or (_VOL_SOFT.search(ft) and nwords <= 5):
        return ToolCall("VOLUME", "up")
    if _VOL_DOWN.search(ft) or (_VOL_LOUD.search(ft) and nwords <= 4):
        return ToolCall("VOLUME", "down")
    if _VOL_UNMUTE.search(ft):
        return ToolCall("VOLUME", "unmute")
    if _VOL_MUTE.search(ft) and "microfono" not in ft:
        return ToolCall("VOLUME", "mute")
    if _VOL_GET.search(ft):
        return ToolCall("VOLUME", "get")
    # musica ("|Spotify" / "|Music" in fondo se l'app e' stata scelta a voce)
    app = f"|{music_app}" if music_app else ""
    m = _MUS_NAMED.match(ft)
    if m:
        return ToolCall("MUSICA", f"{'playlist' if m.group(1) == 'playlist' else 'track'}:{_span(raw, off, m, 2).strip(_Q)}{app}")
    if _MUS_PLAY.match(ft):
        return ToolCall("MUSICA", "play" + app)
    if _MUS_PAUSE.search(ft):
        return ToolCall("MUSICA", "pause" + app)
    if _MUS_NEXT.search(ft):
        return ToolCall("MUSICA", "next" + app)
    if _MUS_PREV.search(ft):
        return ToolCall("MUSICA", "previous" + app)
    if _MUS_NOW.search(ft):
        return ToolCall("MUSICA", "now" + app)
    m = _MUS_PLAY_X.match(ft)
    if m and re.search(r"\b(?:timer|sveglia|cronometro|conto alla rovescia|countdown)\b", ft):
        m = None                                                                       # «fai partire un timer di un quarto d'ora»: non e' musica
    if m and not m.group(2) and normalize(_span(raw, off, m, 3)) in ("spotify", "apple music", "musica", "itunes", "youtube music", "l app musica", "app musica", "l app spotify"):
        return ToolCall("APRI_APP", "Music" if "musica" in normalize(_span(raw, off, m, 3)) or "apple" in normalize(_span(raw, off, m, 3)) else "Spotify")    # «fai partire Spotify»: apre l'app
    if m and _music_ok(m.group(1), m.group(2) or "", _span(raw, off, m, 3), m.group(3)):
        what = _span(raw, off, m, 3).strip(_Q)
        what = re.sub(r"^(?:della|delle|di|del|dei|dello)\s+", "", what, flags=re.I)
        if m.group(2) and re.match(r"qualcosa", m.group(2)) and not _is_specific(what):
            return ToolCall("MUSICA", "play" + app)
        return ToolCall("MUSICA", f"track:{what}{app}")
    m = _WEB_SEARCH.match(ft)
    if m:
        return ToolCall("WEB", f"{m.group(1)}|{_span(raw, off, m, 2).strip(_Q)}")
    m = _WEB_OPENSEARCH.match(ft)
    if m:
        return ToolCall("WEB", f"{m.group(1)}|{_span(raw, off, m, 2).strip(_Q)}")
    m = _WEB_LINK.match(ft)
    if m:
        return ToolCall("WEB", f"{m.group(1)}|{_span(raw, off, m, 2).strip(_Q)}")
    m = _WEB_IFTHERE.match(ft)
    if m:
        return ToolCall("WEB", f"{m.group(2)}|{_span(raw, off, m, 1).strip(_Q)}")
    m = _WEB_SEARCH2.match(ft)
    if m:
        if m.group(1):
            return ToolCall("WEB", f"{m.group(3)}|{_span(raw, off, m, 1).strip(_Q)}")
        return ToolCall("WEB", f"{m.group(4)}|{_span(raw, off, m, 2).strip(_Q)}")
    m = _MAPS.match(ft) or _MAPS_ON2.match(ft) or _MAPS_THING.match(ft)
    if m:
        return ToolCall("MAPPA", re.sub(r"\s+(?:da qui|partendo da qui)$", "", _span(raw, off, m, 1).strip(_Q), flags=re.I))
    m = _MAPS_NEAR.match(ft)
    if m and _PLACE_WORD.search(m.group("t")):                                            # «dov'e' la farmacia piu' vicina?» -> cerca nelle mappe «farmacia vicino a me»
        return ToolCall("MAPPA", _span(raw, off, m, 1).strip(_Q) + " vicino a me")
    m = _MAPS_HOW.match(ft)
    if m:
        g = next(i for i in (1, 2, 3) if m.group(i))
        place = _span(raw, off, m, g)
        place = re.sub(r"\s+(?:con|su|sulle?|nelle?|usando|tramite)\s+(?:google\s+|apple\s+)?(?:le\s+|la\s+)?(?:mappe|mappa|maps)$|\s+(?:da qui|partendo da qui)$", "", place, flags=re.I)
        if _place_ok(_fold(place), place):                                               # "come arrivo a Piazza Bra": si', "come arrivo a essere felice": no
            return ToolCall("MAPPA", place.strip(_Q))
    m = _OPEN_SITE.match(ft)
    if m and _app_like(_span(raw, off, m, 1)):
        return ToolCall("APRI_APP", "sito:" + _span(raw, off, m, 1))                      # sito noto -> lo apre; sconosciuto -> lo cerca su Google
    m = _OPEN_STRONG.match(ft)
    if m and not re.search(r"\b(?:timer|sveglia|cronometro|cartella|finestra|porta|conto alla rovescia)\b", ft) and _app_like(_span(raw, off, m, 1)):
        return ToolCall("APRI_APP", _span(raw, off, m, 1))
    m = _OPEN_SHOW.match(ft)
    if m:
        return ToolCall("APRI_APP", _span(raw, off, m, 1))
    m = _OPEN_WEAK.match(ft)
    if m and _app_like(_span(raw, off, m, 1)) and (re.match(r"[A-Z]", _span(raw, off, m, 1)) or _known_target(m.group(1))):
        return ToolCall("APRI_APP", "~" + _span(raw, off, m, 1))                           # "~": agisce solo se trova davvero quell'app o quel sito
    return None


# ---- le richieste a meta': «ricordami di chiamare Mario» -> «Per quando?» -> «domani alle nove»
_SLOT_CANCEL = re.compile(r"^(?:no|niente|annulla|annullalo|lascia stare|lascia perdere|non importa|fa niente|non fa niente|stop|lascia|dimenticalo|non serve)\b")
_SLOT_NOTIME = re.compile(r"^(?:senza (?:orario|ora|data)|non importa quando|quando vuoi|non so|va bene cosi|cosi va bene|anche senza|senza|nessun orario|mettilo e basta)\b")


def slot_cancelled(answer: str) -> bool:
    return bool(_SLOT_CANCEL.match(normalize(answer)))


def merge_slot(slot: ToolCall, answer: str) -> ToolCall:
    """Completa una richiesta lasciata a meta' con la risposta data a voce: la parte gia' detta + quella nuova."""
    ans = answer.strip(" .!?")
    if slot.name == "PROMEMORIA" and _SLOT_NOTIME.match(normalize(ans)):
        return ToolCall("PROMEMORIA", "!" + slot.arg)                                      # «senza orario»: lo crea senza data
    if slot.name in ("PROMEMORIA", "EVENTO"):
        return ToolCall(slot.name, f"{slot.arg} {ans}".strip())
    if slot.name in ("LISTA", "SCRIVI"):
        return ToolCall(slot.name, f"{slot.arg}|{ans}")
    return ToolCall(slot.name, ans)                                                        # NOTA, RICERCA, TIMER: la risposta e' tutto il contenuto


_LIST_MORE = re.compile(r"^(?:e\s+)?(?:(?:aggiungi|metti|segna|scrivi|inserisci)\s+)?anche\s+(.+)$|^(?:e\s+)?(?:aggiungi|aggiungimi|metti|mettimi|segna|segnami|inserisci)\s+(.+)$")


def list_followup(text: str, which: str) -> ToolCall | None:
    """«aggiungi anche le uova» subito dopo aver aggiunto qualcosa a una lista: continua la stessa lista (senza dover ripetere «alla lista della spesa»)."""
    raw = canonical(text).strip(" .!?")
    m = _LIST_MORE.match(_fold(raw))
    if not m:
        return None
    g = 1 if m.group(1) else 2
    item = raw[m.start(g):m.end(g)].strip(" .,;:!?")
    if not item or re.search(r"\b(?:alla|nella|sulla|in|su|a)\s+(?:mia\s+)?(?:lista|cartella|calendario|agenda|promemoria)\b|\bpromemoria\b|\bcalendario\b", _fold(item)) or len(item.split()) > 8:
        return None
    return ToolCall("LISTA", f"{which}|{item}")


# informazioni sul Mac che sa dire (solo letture: batteria, spazio, versione, accensione, wifi, IP, memoria)
_SYS_INFO = [
    (re.compile(r"\b(?:quanta batteria|batteria (?:ho|c e|rimane|resta|mi resta|e carica)|livello (?:della |di )?batteria|quanta carica|sono sotto carica|si sta caricando|il mac si sta caricando|e sotto carica|percentuale (?:della )?batteria)\b"), "batteria"),
    (re.compile(r"\b(?:quanto spazio (?:libero |disponibile )?(?:ho|c e|rimane|mi rimane|resta|mi resta)|spazio (?:libero|disponibile|sul disco|rimasto)|disco (?:pieno|libero)|quanto e pieno il disco|quanta memoria di archiviazione)\b"), "spazio"),
    (re.compile(r"\b(?:che versione di macos|quale versione di macos|versione di macos|che macos ho|quale macos)\b"), "versione"),
    (re.compile(r"\b(?:da quanto (?:tempo )?(?:e acceso|sei accesa|sei accesso)|da quanto tempo e acceso il (?:mac|computer)|uptime)\b"), "accensione"),
    (re.compile(r"\b(?:a che wifi|a quale wifi|a quale rete|nome del wifi|nome della rete|sono collegato al wifi|che wifi ho|che rete wifi)\b"), "wifi"),
    (re.compile(r"\b(?:sono (?:connesso|collegato|online)|siamo (?:connessi|collegati|online)|c e (?:la )?(?:connessione|internet|rete)|funziona (?:internet|la rete|il wifi)|ho internet|ho la connessione|internet funziona|sono su internet|ho la rete)\b"), "wifi"),
    (re.compile(r"\b(?:indirizzo ip|il mio ip|ip del mac|ip del computer)\b"), "ip"),
    (re.compile(r"\b(?:quanta ram|quanta memoria (?:ho|sto usando|e libera|libera)|memoria libera|uso della ram|stato della memoria)\b"), "memoria"),
]

# cose che Aria NON sa fare: lo dice chiaro invece di far finta (o di far parlare il chatbot)
_NO_SO = [
    (re.compile(r"^(?:telefona|telefonami|chiama|chiamami|fai una telefonata|fammi una telefonata|videochiama|videochiamami|(?:fai|fammi|avvia|inizia|fammi fare|facciamo)\s+(?:una\s+)?(?:video)?chiamata|(?:fai|facciamo)\s+una\s+videochiamata)\b"), "call"),
    (re.compile(r"^(?:leggimi|leggi|controlla|apri|dimmi|mostrami|cerca|guarda|fammi vedere)\s+(?:le\s+|la\s+|i\s+|gli\s+|il\s+)?(?:mail|email|e mail|posta|messaggi|messaggio|sms|whatsapp|chat|notifiche)\b(?!.*\b(?:file|cartella|documento)\b)"), "inbox"),
    (re.compile(r"^(?:mandagli|mandale|inviagli|inviale|spediscigli|spediscile|mandamelo|mandalo a|mandagli un|digli|dille|diglielo|dillo a|avvisa|avvisalo|avvisala|avvisali|informa|informalo|informala|rispondigli|rispondile|scrivigli|scrivile|salutalo|salutala|inoltra|girale|girali|girami)\b"), "message"),
    (re.compile(r"^(?:manda|mandami|invia|inviami|spedisci|spediscimi)\s+(?:un\s+|una\s+|questa\s+|quella\s+|la\s+|l\s+|quest\s+)?(?:messaggio|sms|whatsapp|mail|email|e mail|vocale|messaggino)\b"), "message"),
    (re.compile(r"^(?:togli|toglimi|rimuovi|rimuovimi|cancella|cancellami|elimina|eliminami|depenna|barra|spunta|cassa|leva|levami)\s+.+\s+(?:dalla|dal|nella|sulla|dall|dalle)\s+(?:mia\s+)?(?:lista|spesa|elenco)\b"), "listremove"),
    (re.compile(r"^(?:scrivi|scrivimi|scrivigli|scrivile|rispondi|rispondigli|rispondile)\s+(?:un\s+|una\s+)?(?:(?:messaggio|sms|messaggino|vocale|mail|email|e mail)\s+)?(?:a|ad|su|via|tramite|con)\s+(?:whatsapp|telegram|sms|messenger|instagram|signal|mail|email|[a-z]+)\b.*\b(?:whatsapp|telegram|sms|messenger|messaggio|mail|email)\b|^(?:scrivi|scrivimi)\s+(?:un\s+)?(?:messaggio|sms|messaggino)\s+(?:a|ad)\s+[a-z]+\b"), "message"),
    (re.compile(r"^(?:scrivi|scrivimi)\s+.*\b(?:su|via|tramite)\s+(?:whatsapp|telegram|sms|messenger)\b"), "message"),
    (re.compile(r"^(?:fai partire|avvia|avviami|metti|mettimi|attiva|fammi partire|parti con|usa)\s+(?:il\s+|un\s+|lo\s+)?cronometro\b|^(?:cronometro|cronometra)$"), "stopwatch"),
    (re.compile(r"^(?:salva|salvami|aggiungi|aggiungimi|metti|mettimi|segna|segnami)\s+(?:questa|quella|la|il)\s+(?:pagina|sito|link|scheda|indirizzo)\s+(?:nei|tra i|ai|nei miei|sui|nel)\s+(?:preferiti|segnalibri|segnalibro)\b|^(?:aggiungi|metti|salva)\s+(?:ai|nei)\s+(?:preferiti|segnalibri)\b"), "bookmark"),
    (re.compile(r"^(?:apri|aprimi|chiudi|chiudimi|blocca|sblocca)\s+(?:la\s+|il\s+|le\s+|lo\s+|l\s+)?(?:porta|portone|cancello|garage|serranda|serrande|tapparella|tapparelle|serratura|portone di casa|porta di casa|porta d ingresso)\b"), "home"),
    (re.compile(r"^(?:accendi|spegni|alza|abbassa|metti)\s+(?:la\s+|le\s+|il\s+)?(?:luce|luci|lampada|lampadina|tv|televisione|televisore|riscaldamento|condizionatore|stufa|caldaia|ventilatore|tapparelle|tapparella|presa)\b"), "home"),
    (re.compile(r"^(?:stampa|stampami|stampare)\b"), "print"),
    (re.compile(r"^(?:scarica|scaricami|installa|installami|disinstalla|disinstallami)\s+\w+|^aggiorna\s+(?:il\s+|lo\s+|la\s+|l\s+)?(?:sistema|mac|computer|software|macos|app|programma|programmi)\b"), "download"),
    (re.compile(r"^(?:riavvia|riavviati|riavviami|blocca|sblocca|spegni|spegniamo)\s+(?:il\s+|lo\s+|la\s+|l\s+)?(?:mac|computer|pc|portatile|macbook|sistema|schermo|wifi|wi fi|bluetooth)\b|^(?:attiva|disattiva|accendi|spegni|metti)\s+(?:il\s+|la\s+|lo\s+|l\s+)?(?:wifi|wi fi|bluetooth|non disturbare|modalita aereo|modalita scura|dark mode|luminosita|retroilluminazione|night shift)\b|^(?:alza|abbassa|aumenta|diminuisci)\s+(?:la\s+)?luminosita\b"), "system"),
    (re.compile(r"^(?:fai|scatta|scattami|fammi|fotografa|fotografami|registra|registrami|filma|filmami)\s+(?:una\s+|un\s+|uno\s+)?(?:foto|fotografia|screenshot|schermata|video|registrazione|selfie|audio|filmato|cattura|nota vocale|nota audio|memo vocale|memo|messaggio vocale)\b|^(?:registra|registrami|filma|filmami)\s+(?:lo\s+schermo|l\s+audio|la\s+voce|la\s+riunione|la\s+chiamata|quello che)\b"), "media"),
    (re.compile(r"^(?:condividi|condividimi|pubblica|posta|twitta|tagga|inoltra)\b"), "share"),
    (re.compile(r"^(?:sposta|rinomina|copia|duplica|comprimi|zippa|cancella|elimina|rimuovi|trascina)\s+(?:il\s+|lo\s+|la\s+|i\s+|le\s+|gli\s+)?(?:file|cartella|cartelle|documento|documenti|foto|immagine|immagini|pdf)\b(?!.*\b(?:nella cartella|nel file|in un file|in un documento|nella tua cartella|all interno)\b)"), "files"),
    (re.compile(r"^(?:chiudi|chiudimi|esci da|termina|forza l uscita di|killa)\s+(?:l app\s+|l applicazione\s+|il programma\s+|la finestra\s+|la scheda\s+)?(?:safari|chrome|firefox|musica|spotify|mail|note|calendario|promemoria|finder|word|excel|zoom|teams|slack|discord|whatsapp|telegram|finestra|scheda|programma|app|applicazione)\b|^(?:chiudi|chiudimi)\s+(?:la\s+finestra|la\s+scheda|il\s+programma|l\s+app|l\s+applicazione|tutte le finestre|questa finestra|questa scheda)\b"), "app"),
    (re.compile(r"^(?:vai|sii|fai|sei)\s+(?:un po\s+)?piu\s+(?:veloce|lenta|lento|rapida|in fretta|lentamente)\b|^(?:parla|parlami|parlare|leggi|leggimi|dimmelo|dilo|di|rispondi)\s+(?:un po\s+)?(?:piu\s+)?(?:lentamente|lento|veloce|velocemente|in fretta|rapidamente|adagio|con calma)\b|^(?:rallenta|accelera|velocizzati|sbrigati)\b.*\b(?:parlare|voce|parlato)\b|^rallenta$"), "speed"),
    (re.compile(r"^(?:paga|pagami|trasferisci|fai un bonifico|bonifico|manda dei soldi|invia soldi|ricarica)\b"), "money"),
    (re.compile(r"^(?:ordina|ordinami|compra|comprami|prenota|prenotami)\s+(?:un|una|il|la|dei|delle|due|tre|quattro|cinque|\d+)?\s*(?:pizza|tavolo|taxi|volo|biglietto|biglietti|hotel|albergo|ristorante|cena|pranzo|viaggio|treno|cibo|spesa)\b"), "buy"),
]
_PREAMBLE = re.compile(r"^(?:indicami|mostrami|spiegami|insegnami|fammi capire|dimmi(?: un po)?|mi dici(?: un attimo| un po)?|mi devi dire|mi puoi dire|puoi dirmi|sai dirmi|mi spieghi(?: un po)?|vorrei sapere|voglio sapere|mi serve sapere|mi serve capire|devo sapere|"
                       r"controlla se|guarda se|vedi se|sai se|sai|stavo pensando|mi stai dicendo|mi vuoi (?:mostrare|fare vedere)|mi hai detto|dai|ok)[\s,:]+", re.I)


_MATH_ASK = re.compile(r"\b(?:quanto\s+(?:fa|viene|da|dà)|quant['’ ]?\s*[eè]|calcola\w*|fammi (?:il )?(?:calcolo|conto)|risultato di|fa)\b", re.I)
_MATH_SYM_ALWAYS = (("÷", " diviso "), ("×", " per "), ("−", " meno "), ("+", " più "), ("%", " per cento "))
_MATH_SYM_ASKED = (("/", " diviso "), (":", " diviso "), ("*", " per "), ("-", " meno "), ("–", " meno "))


def spoken_math(text: str) -> str:
    """Apple scrive «120 ÷ 4», «5 + 3», «il 20% di 350» invece delle parole: qui tornano parole, cosi' «quanto fa» le calcola. «/», «:», «-», «x» solo dopo «quanto fa…»
    (altrimenti sono date, orari, intervalli: «10/10», «alle 10:30», «3-4 giorni»)."""
    if not re.search(r"\d\s*[÷×−+%*/:\-–xX]", text):
        return text
    out = text
    for sym, word in _MATH_SYM_ALWAYS:
        out = re.sub(rf"(?<=\d)\s*{re.escape(sym)}\s*(?=\d)" if sym != "%" else r"(?<=\d)\s*%", word, out)
    if _MATH_ASK.search(out):
        for sym, word in _MATH_SYM_ASKED:
            out = re.sub(rf"(?<=\d)\s*{re.escape(sym)}\s*(?=\d)", word, out)
        out = re.sub(r"(?<=\d)\s+[xX]\s+(?=\d)", " per ", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def detect(text: str, files: list[str] | None = None, screen_on: bool = False) -> ToolCall | None:
    """Restituisce lo strumento da lanciare per questa frase, oppure None (decide il modello).
    `files` = i file nella cartella di Aria (serve per riconoscere le domande sui documenti dai nomi veri)."""
    text = spoken_math(text)
    sc = screen_request(text, screen_on)                                    # prima di canonical(): «guarda lo schermo» perderebbe il «guarda»
    if sc:
        return sc
    raw = canonical(text)                                                   # «Ehi, puoi ricordarmi di…» -> «ricordami di…»
    hit = _detect(raw, files, text)
    if hit is None:
        stripped = _fold(raw)
        m = _PREAMBLE.match(stripped)
        if m and m.end() < len(raw):
            hit = _detect(canonical(raw[m.end():]), files, text)           # «Dimmi, come si arriva a…» -> «come si arriva a…»
    return hit


def _detect(raw: str, files: list[str] | None = None, orig: str = "") -> ToolCall | None:
    if not raw:
        return None
    t = normalize(raw)
    t_orig = normalize(orig) if orig else t                                       # il testo come l'ha detto (prima di togliere «mi serve», «devo»…)

    m = _REMEMBER.match(raw)
    if m:
        body = m.group(1).strip(" .!")
        if re.match(r"di\s", body, re.I):                                   # «ricordati di chiamare Mario domani» e' un promemoria; «ricordati di respirare» e' solo un consiglio
            if _TIMEWORD.search(normalize(body)) and re.match(r"di\s+[a-z]+(?:are|ere|ire)\b", normalize(body)):
                return ToolCall("PROMEMORIA", body)
            return None
        return ToolCall("RICORDA", body)
    m = _FORGET.match(raw)
    if m:
        return ToolCall("DIMENTICA", m.group(1).strip(" .!"))

    for pat, kind in _NO_SO:
        if kind in ("message", "bookmark", "stopwatch") and pat.match(t):
            return ToolCall("NON_SO", kind)
    from . import everyday                                                             # le piccole cose di ogni giorno: dado, conversioni, date, «cosa sai fare?» (prima degli altri: «lancia una moneta» non e' un'app)
    if everyday.chance_kind(raw):
        return ToolCall("CASO", raw)
    ck = everyday.conversion_kind(raw)
    if ck == "unita":
        return ToolCall("CONVERTI", raw)
    if ck == "valuta":
        return ToolCall("CERCA", normalize(everyday.symbols_to_words(raw)))            # i cambi di oggi non si inventano: si cercano
    if everyday.date_kind(raw):
        return ToolCall("DATA", raw)
    if everyday.help_kind(raw):
        return ToolCall("AIUTO", "")
    tr = everyday.translation_request(orig or raw) or everyday.translation_request(raw)                                       # (sul testo com'e': «come si dice grazie mille» perderebbe «grazie mille» come formula di cortesia)
    if tr:
        return ToolCall("TRADUCI", f"{tr[0]}|{tr[1]}")
    fc = _file_intent(raw, files) or _power_intent(raw, files)
    if fc:
        return fc
    if _MEMORY.search(t):
        return ToolCall("MEMORIA", "")
    if _SUN.search(t) and not _WEATHER_NOT.search(t_orig):
        cm = _CITY.search(raw)
        day = (everyday.when_phrase(orig or raw) or "oggi")
        return ToolCall("METEO", f"@sole {cm.group(1) if cm else ''} {day}".replace("  ", " "))
    if _TIME.search(t):
        from . import worldclock
        if worldclock.find_zone(t):                                           # «che ora e' a Tokyo?»
            return ToolCall("ORA", "citta:" + t)
        return ToolCall("ORA", "ora")
    if _DATE.search(t):
        return ToolCall("ORA", "data")

    if _TIMER_STATUS.search(t) and not _TIMER_NOT.search(t):
        m = re.search(r"\b(?:per|della|del|dello)\s+(?:la |il |lo |le |i |gli |l )?([a-z]+(?: [a-z]+)?)$", t)
        return ToolCall("TIMER_STATO", m.group(1) if m and not re.fullmatch(_TIMER_WORD, m.group(1)) else "")
    if _TIMER_CANCEL.search(t) and not _TIMER_NOT.search(t):
        if re.search(r"\b(?:tutti|tutte|tutto)\b", t):
            return ToolCall("TIMER_ANNULLA", "tutti")
        m = re.search(r"\b(?:della|del|dello|per la|per il|per lo|per l|per i|per le|per|di|dei|delle)\s+(?:la |il |lo |l )?([a-z]+(?: [a-z]+)?)$", t)
        return ToolCall("TIMER_ANNULLA", m.group(1) if m and not re.fullmatch(rf"{_TIMER_WORD}", m.group(1)) else "")
    if _TIMER.search(t) and not _TIMER_NOT.search(t):
        d = parse_duration(t)
        label = ""
        lm = re.search(r"\bper (?:la |il |lo |le |i |gli |l )?([a-z]+)", t.split("timer")[-1] if "timer" in t else t) or re.search(r"\bche (?:la |il |lo |le |i |gli |l )?([a-z]+)\b(?= (?:e|sono|si|va|ha|hanno) )", t)
        if lm and lm.group(1) not in {"dieci", "venti", "trenta", "cinque", "un", "una", "mezz", "le", "ore"} and not lm.group(1).isdigit():
            label = lm.group(1)
        todo = re.search(r"\b(?:ricordami|avvisami|avvertimi|fammi ricordare|ricorda)\b.*?\b(di\s+[a-z]+(?:are|ere|ire|arsi|ersi|irsi|arlo|erlo|irlo|arla|erla|irla)\b.*)$", t)
        if todo:
            label = todo.group(1)                                                            # «ricordami tra dieci minuti di spegnere il forno»: il timer porta con se' COSA ricordare
        if d:
            return ToolCall("TIMER", f"{_duration_phrase(t)} | {label}".rstrip(" |"))
        w = parse_when(raw, dt.datetime.now())
        if w and w.has_time and re.search(r"\b(?:sveglia|svegliami|timer|avvisami|avvertimi)\b", t):          # «sveglia alle 7:30»: un orario, non una durata
            return ToolCall("TIMER", f"{re.sub(chr(10), ' ', raw)} | {label}".rstrip(" |"))
        if re.match(r"(?:metti|mettimi|imposta|impostami|crea|creami|fammi|programma|programmami|attiva|fai)\s+(?:un|una|la|il)\s+(?:timer|sveglia)\b", t):
            return ToolCall("TIMER", "")                                                          # «metti una sveglia»: chiedera' per quando

    if (_WEATHER.search(t) or (_WEATHER_SOFT.search(t_orig) and (_WEATHER_DAY.search(t_orig) or (orig or raw).rstrip().endswith("?") or _CITY.search(orig or raw)) and len(t_orig.split()) <= 9
                                         and (not _WEATHER_CHAT.search(t_orig) or ((orig or raw).rstrip().endswith("?") and not _WEATHER_GRUMBLE.search(t_orig))))) and not _WEATHER_NOT.search(t_orig):
        city = ""
        cm = _CITY.search(raw)                       # serve la maiuscola: "a Roma", non "a casa"
        if cm:
            city = cm.group(1)
        day = everyday.when_phrase(orig or raw) or "oggi"                                  # «sabato», «dopodomani», «tra tre giorni», «nel weekend»
        return ToolCall("METEO", f"{city} {day}".strip())

    if (re.search(r"\b(diviso|fratto|moltiplicato|per|volte|piu|meno)\b", t) and re.search(r"\b(quanto fa|quanto fanno|quanto viene|quanto vengono|quanto da|calcol\w+|quant e|fammi il calcolo di|fammi il conto di|fammi un conto|fammi un calcolo|fai un conto|facci un conto)\b", t)) or (
            re.search(r"\b(?:metti insieme|sommami|somma|addiziona\w*|sottrai|sottraimi|dividi|dividimi|se divido|divido|moltiplica|moltiplicami|se moltiplico)\b", t) and re.search(r"\b(?:\d+|zero|uno|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|cento|mille|venti|trenta)\b", t)) or (
            re.search(r"\bal\s+(?:quadrato|cubo)\b", t) and re.search(r"\b(?:quanto fa|quant e|calcol\w+)\b", t)) or (
            re.search(r"\b(?:per cento|percento|somma di|somma tra|differenza tra|differenza fra|prodotto di|la meta di|il doppio di|il triplo di|la radice quadrata di)\b", t)
            and re.search(r"\b(?:quanto fa|calcol\w+|quant e|quanto|fai|fa|fammi|mi fai|mi fa|dimmi|mi dici|trova|qual e|quale e|qual era)\b", t)):
        expr = parse_math(raw)
        if expr:
            return ToolCall("CALCOLA", expr)

    for pat, kind in _SYS_INFO:
        if pat.search(t):
            return ToolCall("SISTEMA", kind)
    for pat, kind in _NO_SO:
        if pat.match(t):
            return ToolCall("NON_SO", kind)
    m = _WHO.match(raw)
    if m and not re.search(r"\b(?:tuo|tua|tuoi|tue|preferit\w+ tu)\b", normalize(m.group(1))) and not re.match(r"(?:questo|questa|quest|questi|queste|quel|quella|quello|quei|quelle|cio)\b", normalize(m.group(1))):   # «cosa significa questa frase?» non e' una voce di enciclopedia
        return ToolCall("WIKI", m.group(1).strip())
    if _LIVE.search(t) and not _SEARCH_NOT.search(t):                                  # cose che cambiano (risultati, traffico, prezzi, orari): non si inventano, si cercano
        q = re.sub(r"\b(?:cerca|cercami|su internet|dimmi|mi dici|sai|per favore|per piacere)\b", " ", t)
        return ToolCall("CERCA", re.sub(r"\s+", " ", q).strip())
    if _SEARCH.search(t) and not _SEARCH_NOT.search(t):
        q = re.sub(r"\b(cerca|cercami|su internet|per favore|per piacere)\b", " ", t)
        return ToolCall("CERCA", re.sub(r"\s+", " ", q).strip())
    return None


def _duration_phrase(t: str) -> str:
    """Estrae la parte di frase che esprime la durata ("dieci minuti", "un'ora e mezza")."""
    if re.search(r"\bquarto d ora\b", t):
        return "un quarto d'ora"
    if re.search(r"\bmezz ora\b|\bmezzora\b", t):
        return "mezz'ora"
    m = re.search(r"((?:\d+|[a-z]+)(?:\s+e\s+(?:mezza|mezzo|un quarto|\d+|[a-z]+))?\s+(?:secondi|secondo|minuti|minuto|ore|ora)(?:\s+e\s+(?:mezza|mezzo|un quarto|(?:\d+|venti|trenta|quaranta|cinquanta|dieci|quindici|cinque|venticinque|trentacinque|quarantacinque)(?:\s+(?:minuti|minuto|secondi))?))?)", t)      # («un'ora e 20», «un'ora e venti»: prima restava solo «un'ora»)
    if m:
        return m.group(1)
    if "mezz ora" in t or "mezzora" in t:
        return "mezz ora"
    if "quarto d ora" in t:
        return "un quarto d ora"
    return t


# ---- «sembra una richiesta d'azione ma non l'ho capita»: meglio dirlo che lasciar rispondere il chatbot (che dice «va bene, fatto!» e non fa niente)
_ACTION_VERBS = (r"(?:metti|mettimi|imposta|impostami|crea|creami|aggiungi|aggiungimi|segna|segnami|fissa|fissami|programma|prenota|apri|aprimi|avvia|lancia|alza|abbassa|ferma|riprendi|suona|suonami|riproduci|"
                 r"ricordami|annota|salva|salvami|cancella|elimina|togli|rimuovi|cambia|modifica|sposta|manda|invia|chiama|telefona|accendi|spegni|attiva|disattiva|silenzia|muta|cerca|trova|leggi|leggimi|"
                 r"riassumi|prepara|fammi|fai|mostrami)")
_DOMAINS: list[tuple[str, str, str]] = [
    ("promemoria", r"\b(?:promemoria|ricordami|ricordarmi)\b", "«ricordami domani alle nove di chiamare Mario»"),
    ("calendario", r"\b(?:evento|appuntamento|calendario|agenda|riunione)\b", "«metti in calendario la cena con Marco venerdì alle venti»"),
    ("sveglie", r"\b(?:sveglia|timer|conto alla rovescia)\b", "«metti un timer di dieci minuti» o «metti una sveglia alle sette e mezza»"),
    ("musica", r"\b(?:musica|canzone|canzoni|brano|brani|playlist|album|spotify|apple music)\b", "«metti un po' di musica», «pausa», «prossima canzone»"),
    ("volume", r"\b(?:volume|audio)\b", "«alza il volume» o «volume al trenta»"),
    ("liste", r"\b(?:lista|spesa)\b", "«aggiungi il latte alla lista della spesa»"),
    ("note", r"\b(?:nota|appunto|appunti)\b", "«segna una nota: chiamare il commercialista»"),
    ("app e siti", r"\b(?:app|applicazione|sito|safari|youtube|spotify)\b", "«apri Safari» o «apri YouTube»"),
    ("file", r"\b(?:file|cartella|documento|pdf)\b", "«scrivimi un testo sulla fotosintesi» o «leggimi il file della spesa»"),
]
_EDIT_VERBS = re.compile(r"^(?:cancella|elimina|togli|rimuovi|cambia|modifica|sposta)\b")
_QUESTION_START = re.compile(r"^(?:che|cosa|come|perche|quale|quali|quando|dove|chi|quanto|quanti)\b")


def action_like(text: str) -> tuple[str, str, bool] | None:
    """(ambito, esempio, e'_una_modifica) se la frase ha l'aria di una richiesta d'azione («metti…», «crea…» + promemoria, musica, volume…), altrimenti None."""
    c = canonical(text)
    t = normalize(c)
    if not t or len(t.split()) > 22 or _QUESTION_START.match(t) or (c.rstrip().endswith("?") and not re.match(_ACTION_VERBS, t)):
        return None
    if not re.match(_ACTION_VERBS + r"\b", t):
        return None
    for name, rx, example in _DOMAINS:
        if re.search(rx, t):
            return name, example, bool(_EDIT_VERBS.match(t))
    return None


def file_attempt(text: str) -> tuple[str, str, bool] | None:
    """Parla di un file/cartella con un verbo da «scrivere» o «dire» ma nessuna regola l'ha capita (parole sentite male): il chatbot, lasciato solo, la RACCONTEREBBE a voce
    e direbbe di averla messa nel file. Meglio dire che non ha capito."""
    c = canonical(text)
    f, t = _fold(c), normalize(c)
    if not t or len(t.split()) > 30 or _QUESTION_START.match(t) or _FR_PAST.search(f) or not _FR_FILE.search(f):
        return None
    if _FR_VERB.search(f) or _FR_TELL.search(f):
        return ("file", "«scrivimi la ricetta degli gnocchi in un file»", False)
    return None


# ---- «sembra una richiesta»: serve per decidere se vale la pena chiedere al chatbot di decodificarla (costa ~0,3 s): le chiacchiere e le domande di cultura generale no
_REQ_KEYS = re.compile(r"\b(?:promemori\w+|ricord\w+|dimentic\w+|calendario|agenda|appuntament\w+|impegn\w+|event\w+|riunion\w+|timer|sveglia|svegli\w+|conto alla rovescia|countdown|cronomet\w+|minuti|"
                       r"meteo|piov\w+|pioggia|ombrello|temperatur\w+|gradi|clima|previsi\w+|che ore|che ora|che giorno|che data|quanto fa|quanto fanno|calcol\w+|per cento|percento|somma|"
                       r"music\w+|canzon\w+|brano|brani|playlist|album|volume|audio|suono|muto|muta|silenz\w+|zitt\w+|annot\w+|batteria|wifi|apri|aprimi|avvia|lancia|sito|applicazione|\bapp\b|cerca\w*|google|youtube|amazon|wikipedia|"
                       r"mappa|strada|indicazioni|lista|spesa|nota|appunt\w+|scriv\w+|testo|lettera|poesia|file|document\w+|cartella|ricerca|riassum\w+|brief\w+|riepilogo|"
                       r"schermo|schermata|pagina|finestra|pulsante|tasto|bottone|icona|menu|chiam(?:a|ami|are|armi|ala|alo|ata|ate)|telefon\w+|messagg\w+|whatsapp|mail|email|luce|luci|televis\w+|riscaldamento|ordin\w+|prenot\w+|compr(?:a|ami|are|armi))\b")
_REQ_SHAPE = re.compile(r"^(?:dimmi|dammi|fammi|mi\s+(?:fai|dai|dici|puoi|potresti|serve|servirebbe|occorre|aiuti|indichi|mostri|segni|leggi|apri|metti|trovi)|puoi|potresti|riesci|vorrei|voglio|devo|dovrei|"
                        r"ho bisogno|avrei bisogno|mi piacerebbe|c e|ci sono|che|cosa|come|dove|dov e|quanto|quanti|quale|quali|quando|perche non|e possibile|si puo|posso|non trovo|aiutami|spiegami|"
                        r"indicami|mostrami|trovami|cercami|leggimi|riassumimi|traducimi|descrivimi|controllami|segnami|scrivimi|prenotami|ordinami|compra|accendi|spegni|alza|abbassa|metti|mettimi|imposta|"
                        r"crea|aggiungi|apri|avvia|lancia|cerca|trova|leggi|riassumi|traduci|spiega|guarda|dai|fai|manda|invia|chiama|telefona|ricordami|svegliami|avvisami|zitta|zitto|basta|stop|giu|su|piu|silenzi|silenzia|zittisci|muta|togli|"
                        r"domani|dopodomani|stasera|stamattina|stanotte|oggi|alle|tra|fra|lunedi|martedi|mercoledi|giovedi|venerdi|sabato|domenica|per domani|per stasera)\b")
_REQ_STORY = re.compile(r"\b(?:mi sento|mi sono|sono stat[oa]|ho sentito|ho mangiato|ho visto|ho letto|ho guardato|mi piace|mi piacciono|adoro|odio|detesto)\b")
_ACTION_VERBS_ALL = _ACTION_VERBS


def request_like(text: str) -> bool:
    """Ha la forma di una richiesta (comando, domanda, «vorrei…») e parla di una cosa che Aria sa fare o NON sa fare (promemoria, timer, musica, schermo, telefonate…)."""
    c = canonical(text)
    t = normalize(c)
    if not t or len(t.split()) > 30:
        return False
    shape = bool(_REQ_SHAPE.match(t)) or c.rstrip().endswith("?") or bool(re.match(_ACTION_VERBS + r"\b", t))
    return shape and bool(_REQ_KEYS.search(normalize(text))) and not _REQ_STORY.search(t)


def not_understood(domain: tuple[str, str, bool]) -> str:
    name, example, edit = domain
    if name == "file":
        return "Non ho capito bene cosa scrivere nel file. Dimmi, ad esempio: scrivimi la ricetta degli gnocchi alla romana in un file."
    if name == "schermo":
        return "Non ho capito bene cosa vuoi che indichi o cerchi sullo schermo. Dimmi, ad esempio: non trovo il pulsante Esporta, oppure dov'è la scritta Salva."
    if edit and name in ("promemoria", "calendario"):
        return "Cancellare o cambiare promemoria ed eventi non so ancora farlo: posso solo crearne di nuovi. Per toglierli apri l'app Promemoria o Calendario."
    if edit and name in ("liste", "note"):
        return "Posso solo aggiungere righe alle liste e alle note: per toglierle o cambiarle apri il file nella tua cartella."
    return f"Non sono sicura di aver capito cosa vuoi che faccia. Per {name} puoi dirmi, ad esempio: {example}."


def unmatched_action(text: str, files: list[str] | None = None) -> str | None:
    """Se la frase ha tutta l'aria di una richiesta d'azione ma nessuna regola l'ha capita, una risposta ONESTA con un esempio. Il chatbot, lasciato solo,
    direbbe «va bene, fatto!» senza fare niente."""
    d = action_like(text)
    return not_understood(d) if d else None


def is_save_last(text: str) -> bool:
    """«mettila nella cartella», «scrivi in un file tutta la ricerca»: salvare quello che e' appena stato cercato (serve il contesto: lo sa Aria)."""
    ft = _fold(canonical(text)).strip(" .!?")
    return bool(_SAVE_LAST.match(ft))


_SV_VERB = re.compile(r"\b(?:scriv\w*|salv\w*|mett\w*|butt\w*|copi\w*|trascriv\w*|registr\w*|appunt\w*|cre\w*|inserisc\w*|segn\w*|aggiung\w*|trasferisc\w*|i?scriv\w*)\b")
_SV_DEST = re.compile(r"\b(?:file|cartella|documento|document[oi]|foglio)\b")
_SV_THING = re.compile(r"\b(?:tutt[oa]|tutt[oa] quant[oa]|intera|intero|ricetta|ricerca|spiegazione|storia|risposta|testo|quello che (?:hai|mi hai|ci hai)(?: appena)? detto|quanto (?:hai|mi hai) detto|questo|questa|lo|la|li|le)\b|"
                       r"\b(?:i?scriv|mett|butt|salv|copi|trascriv|inserisc|registr|segn|aggiung|trasferisc)\w*(?:lo|la|li|le|melo|mela|telo|tela)\b|\b(?:il|lo|quel|quello|questo)\s+(?:file|documento)\b")


def is_save_reply(text: str) -> str | None:
    """«mi scriveresti tutta la ricetta in un file?», «salvalo nella cartella», «copia tutto in un documento»: salvare in un file quello che Aria ha APPENA detto.
    Restituisce che cosa si vuole salvare («ricetta», «ricerca», «spiegazione», «storia», «testo») oppure None. Si usa solo quando nessuno strumento ha capito la frase."""
    ft = _fold(canonical(text)).strip(" .!?")
    if not (_SV_VERB.search(ft) and _SV_DEST.search(ft) and _SV_THING.search(ft)):
        return None
    for kind in ("ricetta", "ricerca", "spiegazione", "storia"):
        if kind in ft:
            return kind
    return "testo"


_CONVERT = re.compile(r"^(?:no\s+|ma\s+)?(?:(?:lo|la)\s+)?(?:metti|mettilo|mettila|fai|fallo|falla|crea|segna|segnalo|segnala|mettimelo|mettimela)\w*\s+(?:come|in|nei|nel|nella)\s+(promemoria|evento|calendario)\b|^(?:come|un)\s+(promemoria|evento)\b")
_REPLACE = re.compile(r"^(?:cambia|sostituisci|correggi|modifica)\w*\s+(.+?)\s+con\s+(.+)$")


def convert_target(text: str) -> str | None:
    """«lo metti come promemoria, non come evento»: restituisce lo strumento voluto («PROMEMORIA» o «EVENTO»)."""
    ft = _fold(canonical(text)).strip(" .!?")
    m = _CONVERT.match(ft)
    if not m:
        return None
    what = m.group(1) or m.group(2)
    return "EVENTO" if what in ("evento", "calendario") else "PROMEMORIA"


def replace_words(text: str) -> tuple[str, str] | None:
    """«cambia caffè con fogli al tabacchi» -> («caffè», «fogli al tabacchi»), con le maiuscole dette dall'utente."""
    raw = canonical(text).strip(" .!?")
    ft = _fold(raw)
    m = _REPLACE.match(ft)
    if not m:
        return None
    return raw[m.start(1):m.end(1)].strip(" ,.;:\"'"), raw[m.start(2):m.end(2)].strip(" ,.;:\"'")
