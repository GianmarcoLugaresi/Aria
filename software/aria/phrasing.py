"""Dal parlato alla forma "da comando".

Una persona non dice «ricordami di chiamare Mario»: dice «Ehi, puoi ricordarmi di chiamare Mario?», «Mi ricordi di…», «Vorrei un promemoria…».
`canonical()` toglie i giri di parole (saluti, «puoi/potresti», «vorrei», «per favore»…) e porta il primo verbo all'imperativo, cosi' le regole
di intent.py devono conoscere UNA forma sola. Il testo resta quello dell'utente (maiuscole, accenti, virgole): si cambia solo l'involucro.
"""
from __future__ import annotations

import re

_ACCENTS = str.maketrans("àáâäèéêëìíîïòóôöùúûüñç’'", "aaaaeeeeiiiioooouuuunc  ")


def fold(raw: str) -> str:
    """Minuscolo e senza accenti, della STESSA lunghezza dell'originale (si ritagliano le parti dal testo vero)."""
    return raw.lower().translate(_ACCENTS)


# ---- involucro iniziale e finale
_LEAD_WORDS = ("ehi", "ehila", "ehm", "mh", "ah", "oh", "ok", "okay", "beh", "allora", "dai(?!\\s+un(?:a|o)?\\b)", "senti", "ascolta", "scusa", "scusami", "ma", "e", "poi",
               "quindi", "ciao", "salve", "hey", "buongiorno", "buonasera", "buonanotte", "buon pomeriggio", "aria", "ancora", "ecco", "sentimi", "dunque",
               "per favore", "per piacere", "per cortesia", "scusa se disturbo", "se puoi", "senti una cosa", "no", "si", "tipo", "cioe", "diciamo", "magari", "guarda(?: che)?(?!\\s+(?:su|sul|nel|in|lo schermo|la pagina|la schermata|quello|cosa)\\b)", "bene", "perfetto",
               "un attimo", "aspetta", "ecco", "mi raccomando", "ti prego", "ti supplico", "senti un po", "scusa eh", "eh", "vabbe", "insomma",
               "quando hai un momento(?: libero)?", "quando hai un attimo", "quando hai tempo", "quando avrai un attimo", "quando puoi", "se non e troppo disturbo", "se non e un disturbo", "se non e troppo per te", "se non e un problema",
               "se ti e possibile", "se hai un attimo", "se hai un minuto", "se hai un momento", "se hai tempo", "se non ti dispiace", "se non sei occupata", "se non sei impegnata", "gentilmente", "cortesemente",
               "volentieri", "per caso", "eventualmente", "senza fretta", "appena puoi", "quando vuoi", "per piacere se puoi", "scusa il disturbo", "scusa se ti disturbo", "mi scusi")
_LEAD = re.compile(r"^(?:(?:" + "|".join(sorted(_LEAD_WORDS, key=len, reverse=True)) + r")\b[\s,.!:;\-]*)+")
_TRAIL = re.compile(r"(?:[\s,.;!?]*\b(?:per favore|per piacere|per cortesia|grazie mille|grazie|se puoi|se riesci|se non ti dispiace|ti prego|aria)\b)+[\s.!?]*$")

# ---- "puoi mettere", "vorrei sapere", "ho bisogno di un..."
_POLITE_FULL = re.compile(r"^(?:mi faresti il (?:gentile |grande |piccolo )?favore di|mi fai il (?:gentile |grande |piccolo )?favore di|vorrei chiederti se (?:potresti|puoi|riesci a|sarebbe possibile)|avrei bisogno di chiederti se (?:potresti|puoi)|"
                          r"mi chiedo se (?:potresti|puoi|potrebbe|riesci a)|mi chiedevo se (?:potessi|potresti|puoi)|sarebbe possibile che tu|sarebbe (?:carino|bello|utile|gradito|perfetto|bene|meglio|fantastico|gentile) se(?: tu)?|se(?: tu)? potessi|se(?: tu)? riuscissi a|sarebbe possibile|ti andrebbe di|ti spiacerebbe|ti dispiacerebbe|"
                          r"avrei bisogno che tu|ho bisogno che tu|mi servirebbe che tu|vorrei chiederti se e possibile|vorrei sapere se e possibile|vorrei sapere se potresti|vorrei sapere se puoi|e possibile che tu|e possibile|si puo|potrebbe essere possibile|sarebbe possibile se tu|potresti essere cosi gentile da|saresti cosi gentile da|sarebbe cosi gentile da)\s+")
_MODAL = re.compile(r"^(?:(?:per favore|per piacere|gentilmente|cortesemente)\s+)?(?:mi\s+|ci\s+)?(?:(?:puoi|potresti|potrebbe)(?:\s+(?:gentilmente|cortesemente|per favore|per piacere|magari))?|riesci a|riusciresti a|sapresti|saresti cosi gentile da|ti dispiace|"
                    r"ti va di|potrei chiederti di|ti chiedo di|ti chiederei di|vorrei che tu|voglio che tu|mi piacerebbe che tu|dovresti|devi|vuoi|vorresti|"
                    r"riesci|puoi anche|prova a|prova ad|proveresti a|proveresti ad|potresti provare a|puoi provare a|mi provi a|provi a|proviamo a|proviamo ad|prova|provami a)\s+")
_DESIRE = re.compile(r"^(?:(?:vorrei|voglio|vorremmo|devo|dovrei|dobbiamo|mi piacerebbe|ho bisogno di|avrei bisogno di|mi serve|mi servirebbe|mi occorre|mi andrebbe di|mi andrebbe|ho voglia di|avrei voglia di|avrei voglia|mi va di|mi verrebbe voglia di)\s+)")
_WISH = r"^(?:vorrei|voglio|mi piacerebbe|gradirei|desidero|vorremmo)\s+che\s+(?:tu\s+)?"
_WISH_REM2 = re.compile(_WISH + r"mi\s+(?:ricordassi|ricordi|rammentassi|rammenti)\s+(?P<when>(?:tra|fra|domani|stasera|stamattina|dopodomani|oggi|alle|lunedi|martedi|mercoledi|giovedi|venerdi|sabato|domenica)\b.*?)\s+(?:di|che)\s+(?P<what>.+)$")
_NONMIFAR = re.compile(r"^non\s+(?:mi\s+far|mi\s+fare|farmi|fammi)\s+(?:dimenticare|scordare|scordarmi|dimenticarmi)\s+(?P<what>.+)$")
_WISH_REM = re.compile(_WISH + r"(?:(?P<when>.*?)\s+)?mi\s+(?:ricordassi|ricordi|rammentassi|rammenti)\s+(?:di\s+|che\s+)?(?P<what>.+)$")
_WISH_PLAY = re.compile(_WISH + r"(?:mettessi|metta|suonassi|suoni|facessi\s+partire|faccia\s+partire|partisse|parta|si\s+sentisse|ci\s+fosse)\s+(?P<what>.+)$")
_ARTICLE_NOUN = re.compile(r"^(?:un|una|uno|l)\b")

# infinito (o forma con "mi") -> imperativo che le regole conoscono
_VERBS = {
    "ricordare": "ricorda", "ricordarmi": "ricordami", "mettere": "metti", "mettermi": "mettimi", "aggiungere": "aggiungi", "aggiungermi": "aggiungimi",
    "segnare": "segna", "segnarmi": "segnami", "aprire": "apri", "aprirmi": "aprimi", "cercare": "cerca", "cercarmi": "cercami", "alzare": "alza",
    "abbassare": "abbassa", "eseguire": "esegui", "eseguirmi": "eseguimi", "lanciare": "lancia", "lanciarmi": "lanciami", "avviare": "avvia", "avviarmi": "avviami",
    "scrivere": "scrivi", "scrivermi": "scrivimi", "fare": "fai", "farmi": "fammi", "leggere": "leggi", "leggermi": "leggimi", "controllare": "controlla",
    "dire": "dimmi", "dirmi": "dimmi", "mostrare": "mostra", "mostrarmi": "mostrami", "suonare": "suona", "suonarmi": "suonami", "creare": "crea",
    "crearmi": "creami", "fissare": "fissa", "fissarmi": "fissami", "inserire": "inserisci", "inserirmi": "inseriscimi", "impostare": "imposta",
    "impostarmi": "impostami", "riassumere": "riassumi", "riassumermi": "riassumimi", "spegnere": "spegni", "riprendere": "riprendi", "passare": "passa",
    "saltare": "salta", "fermare": "ferma", "portare": "porta", "portarmi": "portami", "preparare": "prepara", "prepararmi": "preparami", "guardare": "guarda",
    "chiedere": "chiedi", "prenotare": "prenota", "prenotarmi": "prenotami", "ascoltare": "ascolta", "sapere": "dimmi", "dare": "dammi", "darmi": "dammi",
    "far": "fai", "riempire": "riempi", "elencare": "elenca", "elencarmi": "elencami", "stendere": "stendi", "redigere": "redigi", "programmare": "programma",
    "silenziare": "silenzia", "mutare": "muta", "togliere": "togli", "rimettere": "rimetti", "riattivare": "riattiva", "attivare": "attiva",
    "mandare": "manda", "mandarmi": "mandami", "inviare": "invia", "spedire": "spedisci", "telefonare": "telefona", "chiamare": "chiama", "accendere": "accendi",
    "ordinare": "ordina", "comprare": "compra", "videochiamare": "videochiama", "azzerare": "azzera", "salire": "sali", "scendere": "scendi", "aumentare": "aumenta", "diminuire": "diminuisci", "usare": "usa", "riprovare": "riprendi",
    "salvare": "salva", "salvarmi": "salvami", "appuntarmi": "appuntami", "buttare": "butta", "cambiare": "cambia", "annotare": "annota", "appuntare": "appunta", "sintetizzare": "sintetizza", "trovare": "trova", "cercarmi": "cercami", "sentire": "fammi sentire", "ascoltare": "ascolta", "alzassi": "alza", "abbassassi": "abbassa", "mettessi": "metti", "aprissi": "apri", "cercassi": "cerca", "ricordassi": "ricorda", "scrivessi": "scrivi", "leggessi": "leggi", "facessi": "fai", "dicessi": "dimmi", "accendessi": "accendi", "spegnessi": "spegni", "chiamassi": "chiama", "mandassi": "manda", "segnassi": "segna", "aggiungessi": "aggiungi", "suonassi": "suona", "riproducessi": "riproduci", "fermassi": "ferma", "saltassi": "salta", "silenziassi": "silenzia", "indicassi": "indica", "mostrassi": "mostra", "trovassi": "trova", "preparassi": "prepara", "creassi": "crea", "impostassi": "imposta", "svegliassi": "svegliami", "avvisassi": "avvisami", "riassumessi": "riassumi", "salvassi": "salva", "cancellassi": "cancella", "alzi": "alza", "abbassi": "abbassa", "metta": "metti", "apra": "apri", "cerchi": "cerca", "scriva": "scrivi", "legga": "leggi", "faccia": "fai", "dica": "dimmi", "accenda": "accendi", "spenga": "spegni", "indicarmi": "indicami", "indicare": "indica", "spiegarmi": "spiegami", "spiegare": "spiega",
}
_FIRST_WORD = re.compile(r"[a-z]+")
_INF = sorted((k for k in _VERBS if k.endswith(("are", "ere", "ire", "arre", "urre")) and not k.endswith(("rmi", "rti"))), key=len, reverse=True)
# «fammi mettere…», «mi fai riprendere…»: l'infinito dice cosa fare (ma «fammi vedere/sentire» restano come sono)
_FAMMI_INF = re.compile(r"^(?:fammi|farmi|mi fai|mi faresti|mi fate|mi farebbe|fai|far)\s+(?=(?:" + "|".join(_INF) + r")\b)")
_RICORDAR = re.compile(r"^(?:fammi|farmi|mi fai|mi faresti|mi farebbe)\s+ricordar(?:e)?\b|^ricordar(?:e|mi)?\b")

# "mi ricordi di…", "mi apri…": richiesta gentile alla seconda persona -> imperativo
_MI_TU = {"traduci": "traducimi", "metti": "mettimi", "apri": "aprimi", "leggi": "leggimi", "cerchi": "cercami", "scrivi": "scrivimi", "prepari": "preparami", "segni": "segnami",
          "aggiungi": "aggiungimi", "fai": "fammi", "dici": "dimmi", "mostri": "mostrami", "porti": "portami", "suoni": "suonami", "alzi": "alza", "abbassi": "abbassa",
          "elenchi": "elencami", "fissi": "fissami", "inserisci": "inseriscimi", "crei": "creami", "imposti": "impostami", "riassumi": "riassumimi", "passi": "passa",
          "ricordi": "ricordami", "prenoti": "prenotami", "salvi": "salva", "avvii": "avviami", "lanci": "lanciami", "esegui": "eseguimi", "controlli": "controlla", "indichi": "indicami", "trovi": "trovami", "annoti": "annotami", "registri": "registrami",
          "sistemi": "sistemami", "organizzi": "organizzami", "pianifichi": "pianificami", "spieghi": "spiegami", "consigli": "consigliami"}
_MI_TU_RE = re.compile(r"^mi\s+(" + "|".join(_MI_TU) + r")\b")
_MI_FARESTI = re.compile(r"^mi\s+(?:faresti|farebbe|fate)\s+(?:(?:un|il|la)\s+(?:gentile\s+|grande\s+|piccolo\s+)?(?:favore|piacere|cortesia|gentilezza|carita)\s+(?:a|ad|di)\s+)?")
_RICORDI_OK = re.compile(r"^mi\s+ricordi\s+(?=di\s+[a-z]+(?:are|ere|ire)\b|che\b|domani\b|stasera\b|alle\b|tra\b|fra\b)")


def _strip_prefix(raw: str, rx: re.Pattern) -> tuple[str, bool]:
    f = fold(raw)
    m = rx.match(f)
    if m and m.end() < len(raw.strip()):
        return raw[m.end():], True
    return raw, False


def _map_first_verb(raw: str) -> str:
    f = fold(raw)
    m = _FIRST_WORD.match(f)
    if not m:
        return raw
    w, rest = m.group(0), f[m.end():].lstrip()
    if w == "far" and rest.startswith(("partire", "sentire")):                                  # "far partire la musica", "far sentire un po' di jazz"
        return ("fammi " if rest.startswith("sentire") else "fai ") + raw[m.end():].lstrip()
    new = _VERBS.get(w)
    return new + raw[m.end():] if new else raw



# ---- giri di frase che mettono le cose in un altro ordine: li riporta alla forma «ricordami <quando> di <cosa>» / «metti un timer di <quanto>»
_WHEN_FIRST = (r"(?:domani(?:\s+(?:mattina|pomeriggio|sera|notte))?|dopodomani|stasera|stamattina|stanotte|oggi|questa sera|questo pomeriggio|lunedi|martedi|mercoledi|giovedi|venerdi|sabato|domenica|"
               r"domattina|stamani|stamane|dopo pranzo|dopo cena|prima di pranzo|prima di cena|a pranzo|a cena|appena torno(?: a casa)?|quando torno(?: a casa)?|appena arrivo(?: a casa)?|piu tardi|tra poco|fra poco|a mezzogiorno|a mezzanotte|"
               r"alle\s+\S+(?:\s+e\s+\S+)?|tra\s+\S+\s+\S+|fra\s+\S+\s+\S+)(?:\s+(?:alle|verso le|entro le)\s+\S+(?:\s+e\s+\S+)?)?(?:\s+(?:di\s+)?(?:mattina|pomeriggio|sera|notte))?")
_REM_TIME_FIRST = re.compile(rf"^(?P<when>{_WHEN_FIRST})[\s,;:]+(?:e\s+)?(?:ricordami|ricordamelo|ricordamela|ricorda|avvisami|fammi ricordare)\s+(?:di\s+|che\s+)?(?P<what>.+)$")
_REM_DONT_FORGET = re.compile(r"^(?:non voglio|non devo|non vorrei|non posso|devo evitare di)\s+(?:dimenticare|dimenticarmi|scordare|scordarmi)\s+(?:di\s+|che\s+)?(?P<what>[^,;]+?)[\s,;:]+(?:ricordamel[oa]|segnamel[oa]|ricordami|puoi ricordarmel[oa])(?:\s+(?P<when>.+))?$")
_REM_FAIN = re.compile(r"^(?:fai in modo che|fai che|assicurati che|cerca di far si che|fai si che)\s+(?:io\s+)?mi\s+(?:ricordi|ricordo|rammenti)\s+(?:di\s+|che\s+)?(?P<what>.+)$")
_REM_NOTE_THAT = re.compile(r"^(?:segnami|segna|segnati|annotami|annota|annotati|scrivimi|scrivi|appuntami|appunta|appuntati)\s+che\s+(?P<when>.+?)\s+(?:devo|dovrei|ho da|bisogna|dobbiamo)\s+(?P<what>.+)$")
_REM_NOTE_PLAN = re.compile(rf"^(?:segnami|segna|segnati|annotami|annota|appuntami|appunta|ricordami|ricorda)\s+che\s+(?P<when>{_WHEN_FIRST})\s+(?!(?:devo|dovrei|ho da|bisogna|dobbiamo)\b)(?P<what>.+)$")
_REM_NEI = re.compile(r"^(?:aggiungimi|aggiungi|mettimi|metti|inserisci|inseriscimi|segnami|segna|scrivimi|scrivi)\s+(?:nei|nel|tra i|ai|a)\s+(?:miei\s+)?promemoria\s*[:,]?\s*(?:di\s+|che\s+|per\s+)?(?P<what>.+)$")
_REM_AVVISAMI = re.compile(rf"^(?:fammi sapere|fammelo sapere|avvisami|avvertimi|dimmi|fammi avere un avviso)\s+(?P<when>{_WHEN_FIRST})\s+che\s+(?:devo|dovrei|ho da|bisogna|dobbiamo)\s+(?P<what>.+)$")
_REM_DAMMI = re.compile(r"^(?:mi\s+dai|dammi|mi\s+dai\s+un|dammi\s+un)\s+(?:un\s+)?promemoria\b")
_REM_AVVISO = re.compile(r"^(?P<v>aggiungi|aggiungimi|metti|mettimi|crea|creami|fai|fammi|imposta|impostami|inserisci)\s+(?:un\s+)?(?:avviso|allarme|segnale)\s+(?P<rest>(?:per|alle|entro|domani|stasera|tra|fra).*)$")
_TIMER_SYN = re.compile(r"^(?:fammi|farmi|mi fai|dammi|mi dai|mandami|mi manda)\s+(?:suonare|squillare|uno?\s+squillo|un\s+colpo|un\s+fischio|un\s+trillo|un\s+segnale|un\s+avviso|un\s+suono|un\s+campanello)(?:\s+(?:qualcosa|il telefono|il computer))?\s+(?P<when>(?:tra|fra|dopo|entro)\s+.+)$")
_TIMER_ALARM = re.compile(rf"^(?P<when>{_WHEN_FIRST})[\s,;:]+(?:fammi|dammi|mandami|fai)\s+(?:uno\s+|un\s+)?(?:squillo|fischio|colpo|trillo|segnale|suonare|squillare)(?:\s+(?:di telefono|al telefono))?[\s.!?]*$")
_EVT_PER = re.compile(rf"^per\s+(?P<when>{_WHEN_FIRST}(?:\s+prossim[oa])?)[\s,;:]+(?P<verb>segna|segnami|metti|mettimi|fissa|fissami|inserisci|inseriscimi|aggiungi|aggiungimi|prenota|prenotami)\s+(?P<what>.+)$")
_REM_NONFARMI = re.compile(rf"^(?P<when>{_WHEN_FIRST})[\s,;:]+non\s+(?:farmi|fammi|farmelo)\s+(?:dimenticare|scordare|scordarmi|dimenticarmi)\s+(?:di\s+|che\s+)?(?P<what>.+)$")
_REM_FISCHIO = re.compile(rf"^(?:fammi|dammi|mandami|mi fai|mi dai|mi manda|mi mandi)\s+(?:un\s+|uno\s+)?(?:fischio|squillo|colpo|trillo|segnale|avviso|richiamo|colpo di telefono|colpetto|colpo di campanello)\s+(?P<when>{_WHEN_FIRST})[\s,;:]+(?:che|per|perche)\s+(?:devo\s+|dovrei\s+|ho da\s+)?(?P<what>.+)$")
_REM_TIENI = re.compile(r"^(?:tienimi|tieni|tienilo|tienila)\s+a\s+mente\s+(?P<kind>di|che)\s+(?P<what>.+)$")
_REM_PRESENTE = re.compile(r"^(?:tienimi|tieni)\s+presente\s+(?:che\s+)?(?P<what>.+)$")
_REM_APPUNTATI = re.compile(r"^(?:appuntati|annotati|scrivitelo|segnatelo|appuntatelo|annotatelo)(?:\s+che)?[\s:,]+(?P<what>.+)$")
_REM_PRENDIMI = re.compile(r"^(?:prendimi|prenotami|bloccami|riservami)\s+(?:un\s+|l\s+)?(?P<what>(?:appuntamento|impegno|visita|incontro)\b.*)$")
_EVT_BLOCCA = re.compile(rf"^(?:blocca|bloccami|riserva|riservami|tieni libero|tienimi libero|lascia libero)\s+(?:il\s+|la\s+|lo\s+|l\s+)?(?P<what>.*\b(?:{_WHEN_FIRST})\b.*)$")
_TIMER_CRONO = re.compile(r"^(?:cronometra|cronometrami|conta|contami|fai il conto alla rovescia di|conto alla rovescia di|conto alla rovescia per|conto alla rovescia|countdown di|countdown)\s+(?P<q>(?:\d+|[a-z]+)(?:\s+e\s+(?:mezza|mezzo|\S+))?\s+(?:secondi|secondo|minuti|minuto|ore|ora)\b.*)$")


def _reorder(s: str) -> str:
    f = fold(s).strip()
    m = _TIMER_ALARM.match(f)                                     # «domattina alle sette fammi uno squillo»
    if m:
        return "metti una sveglia " + s[m.start("when"):m.end("when")].strip()
    m = _EVT_PER.match(f)                                         # «per giovedi' prossimo segna la visita oculistica alle 16»
    if m:
        return f"{s[m.start('verb'):m.end('verb')]} {s[m.start('what'):m.end('what')].strip()} {s[m.start('when'):m.end('when')].strip()}"
    m = _REM_NONFARMI.match(f)                                    # «stasera non farmi scordare di mandare la mail a Giulia»
    if m:
        return f"ricordami {s[m.start('when'):m.end('when')].strip()} di {s[m.start('what'):m.end('what')].strip()}"
    m = _REM_FISCHIO.match(f)                                     # «fammi un fischio domani alle sette che devo svegliare Marco»
    if m:
        return f"ricordami {s[m.start('when'):m.end('when')].strip()} di {s[m.start('what'):m.end('what')].strip()}"
    m = _REM_TIENI.match(f)                                       # «tienimi a mente di comprare le pile domani»
    if m:
        return ("ricordami di " if m.group("kind") == "di" else "ricordati che ") + s[m.start("what"):m.end("what")].strip()
    m = _REM_PRESENTE.match(f)                                    # «tieni presente che sono allergico alle noci»
    if m:
        return "ricordati che " + s[m.start("what"):m.end("what")].strip()
    m = _REM_APPUNTATI.match(f)                                   # «appuntati che la password e' nel cassetto»
    if m and not re.match(r"(?:devo|dobbiamo)\b", fold(s[m.start('what'):])):
        return "prendi nota: " + s[m.start("what"):m.end("what")].strip()
    m = _REM_PRENDIMI.match(f)                                    # «prendimi un appuntamento dal medico lunedi»
    if m:
        return "fissami un " + s[m.start("what"):m.end("what")].strip()
    m = _EVT_BLOCCA.match(f)                                      # «blocca il pomeriggio di venerdi per la visita»
    if m:
        return "metti in calendario " + s[m.start("what"):m.end("what")].strip()
    m = _REM_TIME_FIRST.match(f)                                  # «domani alle otto ricordami di prendere le chiavi»
    if m:
        return f"ricordami {s[m.start('when'):m.end('when')].strip()} di {s[m.start('what'):m.end('what')].strip()}"
    m = _REM_DONT_FORGET.match(f)                                 # «non voglio dimenticare di chiamare il medico, ricordamelo domani mattina»
    if m:
        when = s[m.start("when"):m.end("when")].strip() if m.group("when") else ""
        return f"ricordami {when} di {s[m.start('what'):m.end('what')].strip()}".replace("  ", " ")
    m = _REM_FAIN.match(f)                                        # «fai in modo che mi ricordi di innaffiare le piante domani»
    if m:
        return "ricordami di " + s[m.start("what"):m.end("what")].strip()
    m = _REM_NOTE_THAT.match(f)                                   # «segnami che venerdì alle cinque devo andare in banca»
    if m:
        return f"ricordami {s[m.start('when'):m.end('when')].strip()} di {s[m.start('what'):m.end('what')].strip()}"
    m = _REM_NOTE_PLAN.match(f)                                   # «segna che sabato mattina vado dal barbiere»
    if m:
        return f"ricordami {s[m.start('when'):m.end('when')].strip()} di {s[m.start('what'):m.end('what')].strip()}"
    m = _REM_NEI.match(f)                                         # «aggiungimi nei promemoria: chiamare l'idraulico»
    if m:
        return "ricordami di " + s[m.start("what"):m.end("what")].strip()
    m = _REM_AVVISAMI.match(f)                                    # «fammi sapere domani alle nove che devo mandare la fattura»
    if m:
        return f"ricordami {s[m.start('when'):m.end('when')].strip()} di {s[m.start('what'):m.end('what')].strip()}"
    m = _REM_DAMMI.match(f)                                       # «mi dai un promemoria per domani…»
    if m:
        return "fammi un promemoria" + s[m.end():]
    m = _REM_AVVISO.match(f)                                      # «metti un avviso per le quattro: riunione»
    if m:
        return f"{s[m.start('v'):m.end('v')]} un promemoria " + s[m.start("rest"):m.end("rest")]
    m = _TIMER_SYN.match(f)                                       # «fammi uno squillo fra un'ora», «dammi un colpo tra due ore»
    if m:
        return "metti un timer " + s[m.start("when"):m.end("when")].strip()
    m = _TIMER_CRONO.match(f)                                     # «cronometra tre minuti», «conto alla rovescia di cinque minuti»
    if m:
        return "metti un timer di " + s[m.start("q"):m.end("q")].strip()
    return s


_ARIA_OBJECT = re.compile(r"\b((?:scritt[aeio]|parol[ae]|chiamat[ao]|intitolat[ao]|nome|titolo|testo|logo|icona|tasto|pulsante|cartella|file|documento|app|applicazione|dice|dicono|leggo|vedi)\s+(?:(?:la|il|lo|di|con)\s+)?)([Aa])ria\b")


def canonical(raw: str) -> str:
    """«Ehi Aria, puoi ricordarmi di chiamare Mario domani alle nove?» -> «ricordami di chiamare Mario domani alle nove».
    «Dove c'e' scritta Aria?»: li' «Aria» e' la parola cercata, non il richiamo che si toglie in coda (la si protegge con una lettera finta della stessa lunghezza)."""
    safe = _ARIA_OBJECT.sub(lambda m: m.group(1) + m.group(2) + "r1a", raw)
    return re.sub(r"\b([Aa])r1a\b", r"\1ria", _canonical(safe))


def _canonical(raw: str) -> str:
    s = re.sub(r"\bpro memoria\b", "promemoria", raw.strip(), flags=re.I)
    s = re.sub(r"^(?:mi|ci|ma|e|allora|dunque|ehm|uhm|eh|mmm|mh)\s*(?:\.{2,}|…)\s*", "", s, flags=re.I)                  # «Mi... proveresti a…»: una esitazione, non una parola
    s = re.sub(r"\s*(?:\.{2,}|…)\s*", ", ", s) if re.match(r"^[^.?!]*(?:\.{2,}|…)", s) else s
    s = re.sub(r",\s*Aria\s*(?=,|\?|!|$)", "", s, flags=re.I)                                 # «Scrivi, Aria, un testo…»: il nome e' un richiamo, non fa parte della richiesta
    for _ in range(3):                                          # saluti e intercalari iniziali
        s, cut = _strip_prefix(s, _LEAD)
        if not cut:
            break
    for _ in range(3):                                          # coda di cortesia
        m = _TRAIL.search(fold(s))
        if not m or m.start() == 0:
            break
        s = s[:m.start()]
    s = s.strip()
    # «promemoria, prova a crearne uno…»: il nome del potere detto davanti al comando non fa parte della richiesta
    s = re.sub(r"^(?:promemoria|evento|appuntamento|sveglia|timer|nota|musica|volume)[,:]?\s+(?=(?:prova|proveresti|puoi|potresti|crea|creami|fammi|fai|metti|mettimi|imposta|impostami|aggiungi|aggiungimi|segna|segnami|vorrei|voglio)\b)", "", s, flags=re.I)
    s = _reorder(s)
    f = fold(s)
    m = _WISH_REM2.match(f)                                     # «vorrei che mi ricordassi tra tre ore di prendere il pane»
    if m:
        return f"ricordami {s[m.start('when'):m.end('when')].strip()} di {s[m.start('what'):m.end('what')].strip()}"
    m = _NONMIFAR.match(f)                                      # «non mi far dimenticare l'appuntamento col dentista di giovedi'»
    if m:
        what = s[m.start("what"):m.end("what")].strip()
        fw = fold(what)
        return "ricordami " + (what if re.match(r"(?:di|che)\b", fw) else ("di " + what if re.match(r"[a-z]+(?:are|ere|ire)\b", fw) else what))
    m = _WISH_REM.match(f)                                      # «vorrei che domani alle otto mi ricordassi di prendere le medicine»
    if m:
        when = s[m.start("when"):m.end("when")].strip() if m.group("when") else ""
        return ("ricordami " + when + " di " + s[m.start("what"):m.end("what")].strip()).replace("  ", " ")
    m = _WISH_PLAY.match(f)                                     # «vorrei che partisse un po' di jazz»
    if m:
        return "metti " + s[m.start("what"):m.end("what")].strip()
    m = _RICORDI_OK.match(f)                                    # "mi ricordi di chiamare…" e' una richiesta; "mi ricordi tanto mia nonna" no
    if m:
        return "ricordami " + s[m.end():].strip()
    m = _RICORDAR.match(f)
    if m:
        return "ricordami" + s[m.end():]
    m = _MI_FARESTI.match(f)                                    # «mi faresti vedere…», «mi faresti un favore ad aggiungere…»
    if m:
        rest = s[m.end():]
        s = ("fammi " + rest) if re.match(r"(?:vedere|sentire|sapere)\b", fold(rest)) else rest
        f = fold(s)
    m = _MI_TU_RE.match(f)
    if m and m.group(1) != "ricordi":
        s = _MI_TU[m.group(1)] + s[m.end():]
    else:
        s, _c = _strip_prefix(s, _POLITE_FULL)                  # «vorrei chiederti se potresti», «mi faresti il gentile favore di»
        s, cut = _strip_prefix(s, _MODAL)                       # "puoi / potresti / ti va di..." + infinito
        if not cut:
            m = _DESIRE.match(fold(s))                          # "vorrei / ho bisogno di / mi serve..."
            if m:
                rest = s[m.end():]
                first = _FIRST_WORD.match(fold(rest))
                if first and first.group(0) in _VERBS:          # "voglio mettere…", "vorrei sapere…"
                    s = rest
                elif re.match(r"(?:una?\s+)?(?:canzone|brano|pezzo|album|disco|playlist|po\s+di\s+musica|po\s+musica)\b", fold(rest)):
                    return "metti " + rest.strip()                  # «vorrei una canzone di Vasco Rossi» e' musica, non un testo da scrivere
                elif _ARTICLE_NOUN.match(fold(rest)):           # "vorrei un promemoria…", "ho bisogno di un timer…"
                    return "crea " + rest.strip()
    f = fold(s)
    m = re.match(r"non\s+(?:farmi|fammi)\s+(?:dimenticare|scordare)\b", f) or _RICORDAR.match(f)
    if m:
        return "ricordami" + s[m.end():]
    m = re.match(r"(?:fai|far)\s+(alzare|salire|aumentare|abbassare|scendere|diminuire)\b", f)          # «fai alzare il volume»
    if m:
        return _VERBS[m.group(1)] + s[m.end():]
    m = re.match(r"(?:fammi|farmi|mi fai)\s+partire\b", f)                                    # «fammi partire un po' di jazz»
    if m:
        return "fai partire" + s[m.end():]
    m = _FAMMI_INF.match(f)
    if m:
        s = s[m.end():]
    out = _map_first_verb(s).strip()
    out = re.sub(r"^(.{3,40}?)(?:[,.;\s]+)\1[.!?\s]*$", r"\1", out, flags=re.I)                    # «abbassalo, abbassalo»: detto due volte, vale una
    again = _reorder(out)                                         # «mi segni che domani devo…» -> «segnami che domani devo…» -> «ricordami domani di…»
    return again if again != out else out
