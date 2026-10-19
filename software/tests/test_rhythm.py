"""Il «ritmo» della conversazione (aria/rhythm.py): riconoscere il tipo di turno, dare al chatbot UNA mossa, far rispettare lunghezza e regola sulle domande."""
import random

from aria import examples, rhythm, style


def plan(text, history=(), rng=None, prev=None):
    return rhythm.plan(list(history), text, style.detect_mood(text), style.long_kind(text), rng or random.Random(1), prev=prev)


def asked(q=True):
    return [{"role": "user", "content": "ciao"}, {"role": "assistant", "content": "Come va?" if q else "Bene."}]


def test_each_kind_of_turn_is_recognised():
    assert plan("Secondo te meglio lavorare con due monitor o con un ultrawide?").mode == "parere"
    assert plan("Mi conviene comprare un portatile o un fisso?").mode == "parere"
    assert plan("Ma come funziona davvero una cache?").mode == "spiega"
    assert plan("E perché le foglie sono verdi?").mode == "spiega"
    assert plan("Ok e il modificatore booleano in 3D cos'è?").mode == "spiega"
    assert plan("Lascia stare, faccio schifo a progettare, gli altri hanno già finito e io sono in alto mare.").mode == "attrito"
    assert plan("Sicuramente andrà male, non risponde nessuno alla mail da tre ore.").mode == "attrito"
    assert plan("Mah niente, serata vuota come al solito.").mode == "traino"
    assert plan("Boh, giornata piatta.").mode == "traino"
    long = "Oggi sono andato a parlare col professore per il progetto, ho aspettato due ore fuori dalla porta e quando sono entrato mi ha liquidato in trenta secondi."
    assert plan(long).mode == "risonanza"


def test_turns_that_have_their_own_rules_are_left_alone():
    assert plan("Spiegami come funziona un motore") is None                    # l'ha chiesto per esteso: parla a lungo (style.long_kind)
    assert plan("Raccontami una storia") is None
    assert plan("Fammi delle domande") is None
    assert plan("Sono stanchissimo, riunioni tutto il giorno.") is None        # emozioni: style.mood
    assert plan("Mi sento solo.") is None
    assert plan("Ho un mal di testa assurdo.") is None
    assert plan("Ok") is None and plan("grazie") is None and plan("ahah") is None
    assert plan("Perché ogni tanto ti blocchi?") is None                       # si parla di lei, non di un concetto
    assert plan("Che ne pensi di questo? Approfondisci in dettaglio") is None or plan("Che ne pensi di questo? Approfondisci in dettaglio").mode != "parere"
    assert plan("Ciao Aria, come stai?") is None
    assert plan("") is None


def test_never_two_questions_in_a_row():
    for _ in range(40):
        t = plan("Secondo te meglio il mare o la montagna?", asked(True), random.Random(_))
        assert t.mode == "parere" and not t.allow_question
    seen = {plan("Secondo te meglio il mare o la montagna?", asked(False), random.Random(i)).allow_question for i in range(60)}
    assert seen == {True, False}                                              # senza domanda prima, ogni tanto la chiede (non sempre)


def test_modes_without_questions_never_allow_them():
    assert not plan("Boh, giornata piatta.").allow_question
    assert not plan("Faccio schifo a tutto, sono sempre indietro.").allow_question
    long = "Ho aspettato due ore fuori dalla porta del professore e quando sono entrato mi ha detto in trenta secondi che devo rifare tutto da capo."
    assert not plan(long, asked(True)).allow_question
    assert any(plan(long, asked(False), random.Random(i)).allow_question for i in range(30))


def test_hint_carries_move_budget_and_question_rule():
    t = plan("Boh, giornata piatta.")
    h = rhythm.hint(t)
    assert "Non fargli domande" in h and "parole" in h and "nessun punto interrogativo" in h
    t = plan("Meglio il gatto o il cane?", asked(False), random.Random(0))
    assert "Mai «dipende»" in rhythm.hint(t)


def test_temperature_moves_around_the_base_and_stays_sane():
    explain, opinion = plan("Come funziona una cache?"), plan("Meglio il gatto o il cane?")
    assert rhythm.temperature(explain, 0.65) < 0.65 < rhythm.temperature(opinion, 0.65)
    assert rhythm.temperature(None, 0.65) is None
    assert 0.2 <= rhythm.temperature(explain, 0.0) and rhythm.temperature(opinion, 5.0) <= 1.0


def test_governor_strips_questions_where_not_allowed():
    t = plan("Boh, giornata piatta.")
    out = rhythm.enforce("Certe giornate sono così. Ma tu cosa fai di bello? Domani sarà meglio.", t)
    assert "?" not in out and out == "Certe giornate sono così. Domani sarà meglio."
    assert rhythm.enforce("Certo che sì, vero?", t) == "Certo che sì."          # una sola frase ed e' una coda retorica: diventa affermazione
    ok = plan("Meglio il gatto o il cane?", asked(False), random.Random(0))
    ok = rhythm.Turn(**{**ok.__dict__, "allow_question": True})
    assert rhythm.enforce("Gatto. Tu quale hai?", ok) == "Gatto. Tu quale hai?"


def test_governor_respects_sentence_and_word_budget():
    t = plan("Come funziona una cache?")                                      # al massimo quattro frasi, 75 parole
    five = "Prima frase di prova. Seconda frase di prova. Terza frase di prova. Quarta frase di prova. Quinta frase di prova."
    assert rhythm.enforce(five, t).count(".") == 4
    wordy = " ".join(["Questa è una frase lunga con parecchie parole dentro che non finisce mai troppo presto davvero."] * 6)     # 15 parole l'una
    out = rhythm.enforce(wordy, t)
    assert 60 <= len(out.split()) <= 100 and out.endswith(".")                # si ferma a fine frase appena passato il budget (con un po' di margine)


def test_governor_works_on_streamed_pieces():
    t = plan("Boh, giornata piatta.")
    g = rhythm.Governor(t)
    spoken = [g.take("Certe giornate"), g.take("sono così, e va bene. Come stai? "), g.take("Domani è un altro giorno. "), g.take("Questa è la terza. "), g.take("Questa la quarta.")]
    text = " ".join(p for p in spoken if p)
    assert "Come stai" not in text and "Domani è un altro giorno" in text and "quarta" not in text
    assert g.done
    assert g.take("altro ancora.") == ""                                      # a limite raggiunto non esce piu' niente


def test_governor_does_not_cut_a_question_started_in_an_earlier_piece():
    t = plan("Boh, giornata piatta.")
    g = rhythm.Governor(t)
    first = g.take("Aspetta, ma te l'ha")                                     # frase ancora aperta: non finisce a un punto
    second = g.take("detto davanti a tutti?")                                 # il seguito di una frase gia' cominciata: non si taglia a meta'
    assert first and second == "detto davanti a tutti?"


def test_governor_without_a_turn_is_transparent():
    g = rhythm.Governor(None)
    assert g.take("Una frase? Due frasi. Tre frasi.") == "Una frase? Due frasi. Tre frasi." and not g.done


def test_turn_hint_uses_the_move_and_its_own_examples():
    t = plan("Secondo te meglio il mare o la montagna?", asked(False), random.Random(0))
    h = style.turn_hint(asked(False), "Secondo te meglio il mare o la montagna?", None, True, turn=t)
    assert "Prendi subito posizione" in h and "Persona:" in h
    assert "Rispondi in una o due frasi" not in h                              # le note generiche cedono il posto alla mossa
    shown = {u for u, _a in examples.BANK["parere"]}
    assert any(u in h for u in shown)
    plain = style.turn_hint(asked(False), "Ciao Aria, come stai?", None, True)
    assert "Prendi subito posizione" not in plain


def test_every_rhythm_example_obeys_its_own_rules():
    """Gli esempi che mostriamo al chatbot sono il suo modello: se violassero le regole (domande dove non si fanno, elenchi, parole inglesi) le insegneremmo noi."""
    spec = {m: rhythm._turn(m, True) for m in ("parere", "spiega", "risonanza", "traino", "attrito")}
    for mode, t in spec.items():
        for _user, answer in examples.BANK[t.shots]:
            words = len(answer.split())
            assert t.min_words * 0.6 <= words <= t.max_words, (mode, answer, words)
            assert answer.count("?") <= (1 if mode == "risonanza" else 0), (mode, answer)
            assert not style._BOILERPLATE.match(answer) and "dipende" not in answer.lower(), answer
    assert all(answer.rstrip().endswith("?") for _u, answer in examples.BANK["risonanza"])


def test_polish_turns_school_connectives_into_speech_and_drops_courtesy_closers():
    assert style.polish("Inoltre, la luce serve. Tuttavia, non basta.") == "E poi la luce serve. Però non basta."
    assert style.polish("Mi dispiace sentire che hai avuto una giornata pesante. Ti capisco. Sono qui se vuoi parlarne.") == "Ti capisco."
    assert style.polish("Io ci sono.") == "Io ci sono."                         # se e' tutto quello che dice, resta
    assert style.polish("Ti ascolto.", prior=True) == "Ti ascolto."             # non e' una chiusura se e' la frase sola di un pezzo
    assert style.polish("Il caffè è pronto. Fammi sapere se ti serve altro.") == "Il caffè è pronto."
    assert style.polish("Ti ascolto. Se vuoi aggiungere un dettaglio, io ci sono. La giornata è lunga.") == "La giornata è lunga."


def test_low_energy_needs_the_whole_sentence_to_be_low_energy():
    assert plan("Boh, giornata piatta.").mode == "traino"
    assert plan("Niente di che").mode == "traino"
    assert plan("Una pasta al pesto, niente di speciale.") is None                # risponde a una domanda: ha un contenuto
    assert plan("Boh, adesso ricomincio da capo.") is None
    assert plan("Boh, forse vado a letto presto.") is None


def test_a_defended_opinion_keeps_its_stance_on_the_next_short_turn():
    first = plan("Secondo te meglio il mare o la montagna?")
    assert first.mode == "parere"
    follow = plan("Ma con due schermi ho più finestre aperte.", asked(False), prev="parere")
    assert follow.mode == "posizione" and "tieni la tua posizione" in follow.move
    assert plan("Ma con due schermi ho più finestre aperte.", asked(False)) is None            # senza un parere prima non c'e' niente da difendere
    assert plan("Ok grazie", asked(False), prev="parere") is None
    assert plan("Come funziona una cache?", asked(False), prev="parere").mode == "spiega"       # cambia discorso: si segue il nuovo


def test_big_life_decisions_are_not_flattened_into_a_hot_take():
    assert plan("Secondo te dovrei cambiare lavoro?") is None
    assert plan("Mi conviene lasciare la mia ragazza?") is None
    assert plan("Secondo te meglio un portatile o un fisso?").mode == "parere"


def test_telling_a_story_with_the_word_explain_inside_is_not_asking_for_an_explanation():
    story = ("Oggi sono andato a parlare col professore per il progetto, ho aspettato due ore fuori dalla porta e quando sono entrato l'ha guardato "
             "trenta secondi dicendo che va rifatto da capo senza manco spiegarmi perché.")
    assert style.long_kind(story) is None and plan(story).mode == "risonanza"
    assert style.long_kind("Non mi ha dato nessuna spiegazione") is None
    assert style.long_kind("Spiegami come funziona un motore") == "explain" and style.long_kind("Puoi spiegarmi la fotosintesi?") == "explain"


# ---- dentro la conversazione: la mossa arriva al chatbot (token, temperatura, note) e il filtro ripulisce quello che dice
import asyncio

from tests.test_human_flow import Script, build_flow


def spy(a, script):
    seen = []

    def stream(messages, max_tokens=None, temperature=None):
        seen.append({"max_tokens": max_tokens, "temperature": temperature, "system": messages[0]["content"]})
        return script.stream(messages)
    a.router.llm_stream = stream
    return seen


async def test_a_flat_day_gets_a_pull_answer_without_questions_and_inside_the_budget():
    a, hub, script, tts, spk = build_flow(["boh giornata piatta"], ["Certe giornate sono così, e va bene. Tu come stai? Domani sarà un altro giorno. Questa è la terza. Questa è la quarta."])
    seen = spy(a, script)
    await asyncio.wait_for(a.session(), 40)
    said = " ".join(tts.said)
    assert "?" not in said and "Domani sarà un altro giorno" in said and "quarta" not in said
    assert seen[0]["max_tokens"] == 110 and seen[0]["temperature"] is not None
    assert "Non fargli domande" in seen[0]["system"]
    assert a.history[-1]["role"] == "assistant" and "?" not in a.history[-1]["content"]


async def test_a_concept_question_is_answered_in_one_layer():
    a, hub, script, tts, spk = build_flow(["come funziona una cache"], ["Fai conto che sia il ripiano della cucina. Le cose che usi sempre le tieni lì a portata di mano. Il computer fa lo stesso. Con i dati che servono più spesso. E poi ancora altro."])
    seen = spy(a, script)
    await asyncio.wait_for(a.session(), 40)
    assert seen[0]["max_tokens"] == 150 and seen[0]["temperature"] < 0.65 + 0.001     # le spiegazioni sono piu' ferme
    assert len([s for s in tts.said if s.strip()]) <= 4                              # al massimo quattro frasi


async def test_an_ordinary_chat_turn_is_not_constrained():
    a, hub, script, tts, spk = build_flow(["ciao come stai oggi"], ["Bene, grazie. E tu come va?"])
    seen = spy(a, script)
    await asyncio.wait_for(a.session(), 40)
    assert seen[0]["max_tokens"] is None and seen[0]["temperature"] is None


async def test_rhythm_can_be_switched_off_in_the_settings():
    a, hub, script, tts, spk = build_flow(["boh giornata piatta"], ["Certe giornate sono così. Tu come stai?"])
    a.cfg.setdefault("human", {})["rhythm"] = False
    seen = spy(a, script)
    await asyncio.wait_for(a.session(), 40)
    assert seen[0]["max_tokens"] is None and "Non fargli domande" not in seen[0]["system"]
