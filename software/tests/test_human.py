"""Le parti "umane" di Aria: parlato (numeri, pause), saluti e ringraziamenti, note di regia per il chatbot."""
import datetime as dt

import numpy as np

from aria import dialog, style
from aria.phrasing import canonical
from aria.speech import num_words, shape_pause, speechify


def test_numbers_become_words():
    assert [num_words(n) for n in (0, 13, 21, 28, 33, 100, 180, 1985, 2026, 12500)] == [
        "zero", "tredici", "ventuno", "ventotto", "trentatré", "cento", "centottanta", "millenovecentottantacinque", "duemilaventisei", "dodicimilacinquecento"]
    assert num_words(1250000) == "un milione duecentocinquantamila"


def test_speechify_makes_text_sayable():
    assert speechify("Fuori ci sono 18°C e il 40% di umidità.") == "Fuori ci sono diciotto gradi e il quaranta per cento di umidità."
    assert speechify("Ci vediamo alle 18:30, ok?") == "Ci vediamo alle diciotto e mezza, ok?"
    assert speechify("Costa 3,5 euro, anzi €12.") == "Costa tre virgola cinque euro, anzi dodici euro."
    assert speechify("Sono 5 km a 12 km/h.") == "Sono cinque chilometri a dodici chilometri orari."
    assert speechify("Il 1° gennaio.") == "Il primo gennaio."
    assert speechify("*sorride* Beh dipende (forse)!!") == "Beh, dipende!"                 # azioni, parentesi e punti esclamativi doppi spariscono; l'intercalare ha la sua pausa
    assert speechify("Ah che bello, eh già. Dunque vediamo.") == "Ah, che bello, eh già. Dunque, vediamo."
    assert "…" in speechify("Boh... non so.") and "..." not in speechify("Boh... non so.")


def test_pauses_follow_the_punctuation_and_trim_random_silence():
    sr = 24000
    voice = (np.sin(np.linspace(0, 400, sr)) * 8000).astype(np.int16)                        # 1 s di "voce"
    lazy = np.concatenate([voice, np.zeros(int(0.55 * sr), dtype=np.int16)])                 # con mezzo secondo di silenzio casuale in coda
    q = shape_pause(lazy, sr, "Davvero?")
    d = shape_pause(lazy, sr, "Sì, certo.")
    e = shape_pause(lazy, sr, "Mah…")
    assert len(q) < len(lazy) and len(d) < len(lazy)                                         # il silenzio casuale e' stato tolto
    assert len(e) > len(q) > len(d)                                                          # «…» pausa lunga, «?» media, «.» corta
    assert shape_pause(np.zeros(0, dtype=np.int16), sr, "x").size == 0


def test_canonical_form_strips_the_politeness_wrapper():
    cases = {
        "Ehi, ricordami di portare l'ombrello domani": "ricordami di portare l'ombrello domani",
        "Puoi ricordarmi di comprare il latte stasera?": "ricordami di comprare il latte stasera?",
        "Ho bisogno di un promemoria per domani, chiamare il dentista": "crea un promemoria per domani, chiamare il dentista",
        "Mi ricordi di chiamare la mamma stasera alle otto?": "ricordami di chiamare la mamma stasera alle otto?",
        "Mi ricordi tanto mia nonna.": "Mi ricordi tanto mia nonna.",                       # NON e' una richiesta
        "Mi apri le impostazioni?": "aprimi le impostazioni?",
        "Fammi mettere un po' di musica classica.": "metti un po' di musica classica.",
        "Per favore ricordami di annaffiare le piante": "ricordami di annaffiare le piante",
        "Abbassa un po' il volume, grazie": "Abbassa un po' il volume",
    }
    for src, want in cases.items():
        assert canonical(src) == want, src


def test_dialog_acts():
    assert dialog.is_farewell("Ciao ciao") and dialog.is_farewell("ok, a dopo, grazie") and dialog.is_farewell("Buonanotte Aria") and dialog.is_farewell("devo andare")
    assert not dialog.is_farewell("ciao come stai") and not dialog.is_farewell("a domani devo fare la spesa")
    assert dialog.is_thanks("Grazie mille!") and dialog.is_thanks("ok perfetto grazie") and dialog.is_thanks("sei gentile")
    assert not dialog.is_thanks("grazie ma non era quello che volevo")
    assert dialog.is_ack("va bene") and dialog.is_ack("Ah ok.") and dialog.is_ack("Perfetto") and not dialog.is_ack("va bene ma non mi piace")
    assert dialog.is_laugh("Ahahah") and dialog.is_laugh("ah ah ah") and not dialog.is_laugh("ah ho capito")
    assert dialog.is_repeat_request("come?") and dialog.is_repeat_request("puoi ripetere") and not dialog.is_repeat_request("come stai")
    assert dialog.is_presence_check("Aria?") and dialog.is_presence_check("ci sei?") and dialog.is_presence_check("mi senti") and not dialog.is_presence_check("aria che ore sono")
    assert dialog.is_apology("scusa") and dialog.is_apology("Scusami!") and not dialog.is_apology("scusa ma non era quello")


def test_replies_fit_the_moment_and_do_not_repeat():
    night = dt.datetime(2026, 10, 6, 23, 40)
    morning = dt.datetime(2026, 10, 6, 9, 0)
    for _ in range(20):
        r = dialog.farewell_reply(night, "Mario", "ciao").lower()
        assert any(w in r for w in ("notte", "dormi", "sogni")), r                           # di notte: «buonanotte», non «buona giornata»
        r = dialog.farewell_reply(morning, None, "a dopo")
        assert any(w in r for w in ("giornata", "dopo", "presto", "sentiamo")), r
    seen = {dialog.thanks_reply("Figurati!") for _ in range(30)}
    assert "Figurati!" not in seen and len(seen) >= 3                                         # mai la stessa frase due volte di fila
    for _ in range(30):
        g = dialog.greeting(morning, "Mario")
        assert "Mario" in g or "buongiorno" in g.lower() or "Dimmi" in g, g
    assert "Com'è andato" in dialog.greeting(morning, "Mario", followup="Com'è andato l'esame?")
    assert dialog.greeting(morning, None, since_last_s=120) in ("Rieccomi!", "Eccomi di nuovo.", "Dimmi pure.", "Sì, dimmi.")


def test_turn_hints_react_to_what_just_happened():
    h = style.turn_hint([], "Sono stanchissimo, riunioni tutto il giorno.")
    assert "poche energie" in h or "dolce" in h
    h = style.turn_hint([], "Ho preso trenta all'esame!")
    assert "festeggia" in h
    hist = [{"role": "user", "content": "ciao"}, {"role": "assistant", "content": "Ciao! Tutto bene?"}]
    h = style.turn_hint(hist, "sì bene")
    assert "NON farne" in h and "Non cominciare con «ciao»" in h                              # ha appena fatto una domanda e un attacco: non li ripete
    assert "maschile" in style.turn_hint([], "ok", "m") and "femminile" in style.turn_hint([], "ok", "f")
    assert "neutri" in style.turn_hint([], "ok")                                              # non sa se e' uomo o donna: giri neutri
    assert "tre o quattro frasi" in style.turn_hint([], "Che cos'è la fotosintesi?")
    assert style.session_tone(dt.datetime(2026, 10, 6)) == style.session_tone(dt.datetime(2026, 10, 6, 22))      # lo stesso umore per tutta la giornata


def test_clean_reply_drops_assistant_boilerplate():
    assert style.clean_reply("Aria: Certamente! Eccomi qui.") == "Eccomi qui."
    assert style.clean_reply("Ottima domanda, direi di sì.") == "Direi di sì."
    assert style.clean_reply("Beh, dipende.") == "Beh, dipende."


def test_invented_experiences_and_unasked_curiosities_are_dropped():
    assert style.drop_fabrications("Che peccato. Sai, ho letto che le formiche non dimenticano mai. Non è poco.", "Mi pagano poco e mi annoio.") == "Che peccato. Non è poco."
    assert style.drop_fabrications("Stavo sistemando i fili qui. Tu come stai?", "ciao") == "Tu come stai?"
    assert style.drop_fabrications("Sai che i koala hanno impronte digitali?", "Mi racconti una cosa curiosa?") == "Sai che i koala hanno impronte digitali?"     # richiesta: resta
    assert style.drop_fabrications("Sai che i koala hanno impronte digitali?", "Sono stanco.") == ""                                                        # non richiesta: via


def test_history_alternates_user_and_assistant_for_gemma_templates():
    from aria.conversation import alternating
    hist = [{"role": "assistant", "content": "Ciao!"}, {"role": "user", "content": "Ho preso trenta."}, {"role": "assistant", "content": "Che bello."},
            {"role": "assistant", "content": "Come ti chiami?"}, {"role": "user", "content": "Mario"}]
    out = alternating(hist)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]                       # il saluto iniziale cade, le due risposte di Aria si uniscono
    assert out[1]["content"] == "Che bello. Come ti chiami?"


def test_the_sentence_cap_never_cuts_a_sentence_in_half():
    from aria.conversation import _clip_sentences
    # il primo pezzo puo' finire a una virgola (per partire prima): non e' una frase finita
    text, done, open_frag, capped = _clip_sentences("Ma davvero? Congratulazioni! Dopo tutto quel lavoro,", 3, 0, False)
    assert text.endswith("lavoro,") and done == 2 and open_frag and not capped
    text, done, open_frag, capped = _clip_sentences("ti sei guadagnato un riposo. E poi basta.", 3, done, open_frag)
    assert text == "ti sei guadagnato un riposo." and done == 3 and capped                  # completa la frase aperta e si ferma


def test_a_long_explanation_sentence_is_not_taken_for_a_name():
    from aria import learn
    assert learn.parse_name("Era analisi due, studiavo da un mese.", expect=True) is None
    assert learn.parse_name("Mario", expect=True) == "Mario"
    assert learn.parse_name("Sono Mario", expect=True) == "Mario"


def test_claims_of_actions_that_never_happened_are_dropped():
    assert style.has_false_claim("Fatto! Ho aggiunto il latte alla lista.") and style.has_false_claim("Ho aperto Safari per te.") and style.has_false_claim("Ti ricorderò di chiamare Mario.")
    assert not style.has_false_claim("Ho una bella notizia per te.") and not style.has_false_claim("Mi ricordo che domani hai il dentista.")
    assert style.drop_fabrications("Fatto! Ho aggiunto il latte alla lista.", "aggiungi il latte") == ""


def test_a_command_is_never_taken_for_the_answer_to_what_is_your_name():
    from aria import learn
    for cmd in ("metti della musica", "chiamare il commercialista alle nove", "apri Safari", "che ore sono", "abbassa il volume"):
        assert learn.parse_name(cmd, expect=True) is None, cmd
    assert learn.parse_name("Mario", expect=True) == "Mario" and learn.parse_name("Marco Rossi", expect=True) == "Marco Rossi"


def test_complaints_about_aria_are_recognized_only_when_directed_at_her():
    assert dialog.complaint_kind("Però ti mangi le parole.") == "voice"
    assert dialog.complaint_kind("Non ti sento bene") == "voice"
    assert dialog.complaint_kind("Parli troppo veloce") == "voice"
    assert dialog.complaint_kind("Perché ogni tanto ti buggi?") == "glitch"
    assert dialog.complaint_kind("Ti sei bloccata") == "glitch"
    assert dialog.complaint_kind("Sei lenta oggi") == "glitch"
    assert dialog.complaint_kind("Non hai capito niente") == "wrong"
    assert dialog.complaint_kind("Rispondi a caso") == "wrong"
    for t in ("Mi sono bloccato col lavoro", "Il wifi non funziona", "Oggi mi mangio una pizza", "Mia sorella parla troppo veloce al telefono, mi stanca", "Non ho capito la lezione di oggi",
              "Ho sentito che il treno è lento", "Il computer di mio padre si blocca sempre e ci metto una vita a spiegargli come si riavvia, che nervoso"):
        assert dialog.complaint_kind(t) is None, t


def test_the_users_name_is_stripped_when_it_is_only_a_vocative():
    f = style.strip_vocative
    assert f("Ciao Mario! Che bello averti qui oggi.", "Mario") == "Ciao! Che bello averti qui oggi."
    assert f("Certo che sì, Mario! Almeno non si lamenterà più.", "Mario") == "Certo che sì! Almeno non si lamenterà più."
    assert f("Ah, scusa Mario. Va benissimo così!", "Mario") == "Ah, scusa. Va benissimo così!"
    assert f("Mario, a volte le piante hanno bisogno di luce.", "Mario") == "A volte le piante hanno bisogno di luce."
    assert f("Beh, dimmi Mario, come stai stamattina?", "Mario") == "Beh, dimmi, come stai stamattina?"
    assert f("Eccomi di nuovo Mario.", "Mario") == "Eccomi di nuovo."
    assert f("Che bella giornata.", "Mario") == "Che bella giornata."
    assert f("Mario è un bel nome.", "Mario") == "Mario è un bel nome."                  # non e' un'appellativo: resta


def test_long_answers_are_recognized_only_when_asked_for():
    for t in ("Dimmi una ricetta della carbonara", "Spiegami come funziona un motore", "Parlami dei buchi neri", "Raccontami una storia", "Mi dai la ricetta delle lasagne?",
              "Dimmi di più", "Continua", "Parlami di qualcosa di interessante", "Descrivimi la fotosintesi"):
        assert style.long_kind(t) == "explain", t
    for t in ("Fammi delle domande", "Interrogami sulla storia romana", "Intervistami", "Chiedimi qualcosa su di me"):
        assert style.long_kind(t) == "quiz", t
    for t in ("Come stai?", "Ho mangiato la carbonara", "Che ore sono", "Mi sento stanco", "Spiegami in breve cos'è la fotosintesi", "Grazie mille", "Mi piace la ricetta di mia nonna", "E poi sono andato a casa", "Ho una ricetta di mia nonna che adoro", "Il film continua per ore"):
        assert style.long_kind(t) is None, t


def test_the_hint_for_a_recipe_asks_for_a_full_answer_and_for_a_quiz_one_question_at_a_time():
    h = style.turn_hint([], "Dimmi una ricetta della carbonara", None, True)
    assert "ESTESO" in h and "ingredienti" in h and "Rispondi in una o due frasi" not in h
    q = style.turn_hint([], "Fammi delle domande", None, True)
    assert "UNA domanda alla volta" in q and "ESTESO" not in q


def test_markdown_is_removed_before_the_voice():
    assert style.strip_markdown("**Ingredienti**: uova") == "Ingredienti: uova"
    assert style.strip_markdown("- uova\n- farina\n1. Mescola") == "uova. farina. Mescola"
    assert style.strip_markdown("## Titolo\nTesto") == "Titolo. Testo"


def test_voice_check_ignores_a_small_word_the_recognizer_skipped_and_splits_long_sentences_for_the_retry():
    from aria import voicecheck as V
    assert V.score("Fatto: ho salvato il documento nella tua cartella.", "Fatto ho salvato il documento nella cartella")[0] is True      # «tua» saltata: la frase e' intera
    assert V.score("Fatto: ho salvato il documento nella tua cartella.", "Fatto ho salvato il documento nella tua")[0] is False             # «cartella» no: e' tagliata
    assert V.split_long("Va bene, ciao.") == ["Va bene, ciao."] and V.split_sentence("Va bene, ciao.") is None
    frase = "Non dimenticare il ragù di carne, che aggiunge profondità e quel tocco rustico che rende questo piatto unico."
    pezzi = V.split_long(frase, 44)
    assert len(pezzi) >= 2 and all(len(x) <= 60 for x in pezzi) and pezzi[0] == "Non dimenticare il ragù di carne,"              # si spezza dove si respira
    assert " ".join(pezzi).replace(",", "") == frase.replace(",", "")                                                              # senza perdere parole
    assert V.split_long("Fatto: ho scritto Gnocchi alla romana nella tua cartella,", 44) == ["Fatto: ho scritto Gnocchi alla romana nella tua cartella,"]   # poco sopra il limite: intera


def test_voice_check_catches_a_truncated_ending_and_ignores_fillers_numbers_and_the_name():
    from aria import voicecheck as V
    full = "Va bene, ti ricorderò di chiamare il commercialista domani alle nove."
    assert V.score(full, "Va bene, ti ricorderò di chiamare il commercialista.")[0] is False
    assert V.score(full, "Va bene, ti ricorderò di chiamare il commercialista domani alle 9.")[0] is True        # «9» = «nove»
    assert V.score("Ah, ecco Mario! Stai cercando di capire come funziona il mondo, eh?", "Ecco, Marrio, stai cercando di capire come funziona il mondo.", "Mario")[0] is True
    ok, _, missing = V.score("Mi fai venire voglia di fare una partita a scacchi!", "Mi fai venire voglia di fare una partita a sca.")
    assert not ok and missing == ["scacchi"]
    assert V.score("Sì, dimmi.", "")[0] is True                                                                 # troppo corta per giudicare


def test_versions_dotted_times_and_italian_thousands_are_read_properly():
    from aria.speech import speechify
    assert speechify("Versione 1.2.3 del programma") == "Versione uno punto due punto tre del programma"          # prima: «uno virgola due.tre»
    assert speechify("alle 18.30") == "alle diciotto e mezza" and speechify("ore 9.15") == "ore nove e un quarto"    # prima: «diciotto virgola trenta»
    assert speechify("costa 1.250,50 euro") == "costa milleduecentocinquanta virgola cinquanta euro"             # prima: «uno virgola duecentocinquanta,cinquanta»
    assert speechify("sono 1.250.000 persone") == "sono un milione duecentocinquantamila persone"
    assert speechify("misura 2.5 metri") == "misura due virgola cinque metri"
