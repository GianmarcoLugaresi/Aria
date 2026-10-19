"""Settima raccolta: frasi lunghe, indirette e gentili («vorrei sapere se», «mi faresti il piacere»…), ultima verifica a freddo della notte.
Stesso formato delle altre raccolte."""

from intent_corpus2 import FILES  # noqa: F401

POS7 = [
    ("Vorrei sapere se domani pioverà a Bologna", {"METEO"}, ["bologna"]),
    ("Mi faresti il piacere di dirmi che ore sono?", {"ORA"}, []),
    ("Sarebbe possibile avere un timer di venti minuti per la pizza?", {"TIMER"}, ["venti"]),
    ("Ti dispiace ricordarmi domani mattina di annaffiare le piante?", {"PROMEMORIA"}, ["piante"]),
    ("Potresti mettere in calendario il colloquio di lunedì alle 11?", {"EVENTO"}, ["colloquio"]),
    ("Avrei bisogno di sapere che impegni ho dopodomani", {"AGENDA"}, []),
    ("Mi piacerebbe che mettessi un po' di musica jazz", {"MUSICA"}, ["jazz"]),
    ("Scusami, potresti abbassare un po' il volume?", {"VOLUME"}, []),
    ("Mi sapresti dire quanto fa 35 per 4?", {"CALCOLA"}, ["35"]),
    ("Se non ti dispiace, aprimi la calcolatrice", {"APRI_APP"}, ["calcolatrice"]),
    ("Vorrei che tu cercassi su internet le ultime notizie sul Mondiale", {"CERCA", "WEB"}, []),
    ("Per piacere, mi indichi la strada per la stazione?", {"MAPPA"}, ["stazione"]),
    ("Potresti scrivermi una breve lettera di ringraziamento?", {"SCRIVI"}, ["ringraziamento"]),
    ("Mi prepareresti un riassunto sulla fotosintesi in un file?", {"SCRIVI", "RICERCA"}, ["fotosintesi"]),
    ("Mi faresti la cortesia di aggiungere il pane alla lista della spesa?", {"LISTA"}, ["pane"]),
    ("Ti andrebbe di dirmi cosa c'è nella cartella?", {"ELENCO"}, []),
    ("Vorrei sapere quanti giorni mancano a Pasqua", {"DATA"}, []),
    ("Ti chiedo di tradurre buonanotte in francese", {"TRADUCI"}, ["francese"]),
    ("Mi dici quanti chilometri sono 15 miglia, per favore?", {"CONVERTI"}, []),
    ("Mi diresti cosa sai fare, così capisco come usarti?", {"AIUTO"}, []),
    ("Vorrei che mi ricordassi tra tre ore di prendere il pane", {"PROMEMORIA", "TIMER"}, ["pane"]),
    ("Ti prego, non mi far dimenticare l'appuntamento col dentista di giovedì", {"PROMEMORIA", "EVENTO"}, ["dentista"]),
    ("Potresti dirmi com'è il tempo a Napoli sabato?", {"METEO"}, ["napoli"]),
    ("Sapresti indicarmi dove si trova il pulsante per salvare?", {"SCHERMO"}, ["salvare"]),
    ("Potresti leggermi cosa c'è scritto in questa pagina?", {"SCHERMO"}, []),
    ("Mi faresti vedere dov'è l'icona delle impostazioni?", {"SCHERMO"}, ["impostazioni"]),
    ("Vorrei telefonare a mia sorella, puoi farlo tu?", {"NON_SO"}, []),
    ("Sarebbe carino se accendessi le luci del salotto", {"NON_SO"}, []),
    ("Mi potresti stampare questo documento?", {"NON_SO"}, []),
    ("Avrei voglia di un po' di musica rilassante", {"MUSICA"}, []),
]

NEG7 = [
    "Vorrei tanto che fosse già domani",
    "Mi faresti ridere se ci riuscissi",
    "Sarebbe bello andare al mare questo weekend",
    "Ti dispiace se non rispondo subito? Sono un po' stanco",
    "Potrei raccontarti cosa è successo oggi al lavoro",
    "Avrei bisogno di dormire dieci ore",
    "Mi piacerebbe imparare a suonare il pianoforte",
    "Sapresti immaginare una città sott'acqua?",
    "Per favore, dimmi che andrà tutto bene",
    "Ti prego, parlami di qualcosa di bello",
]
