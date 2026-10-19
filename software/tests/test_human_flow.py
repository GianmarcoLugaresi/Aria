"""Il filo della conversazione come lo condurrebbe una persona: saluti, ringraziamenti, richieste a meta', frasi interrotte, tetto di lunghezza."""
import asyncio

import pytest

import numpy as np

from aria import conversation, dialog
from aria.textutil import ToolCall
from aria.tools import Tools
from tests.test_conversation import FakeLLM, QUIET, LOUD, build, utterance


class Script:
    """Un chatbot che dice quello che vogliamo (una risposta per ogni turno)."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    async def stream(self, messages, max_tokens=None):
        self.calls.append(messages)
        text = self.replies.pop(0) if self.replies else "Ok."
        for i in range(0, len(text), 12):
            yield text[i:i + 12]


class ScriptedTools(Tools):
    def __init__(self, cfg, mem, results):
        super().__init__(cfg, mem)
        self.results, self.seen = list(results), []

    async def run(self, call):
        self.seen.append(call)
        return self.results.pop(0) if self.results else "Fatto."


def build_flow(stt_lines, replies, tool_results=None, turns=4, known=True):
    a, hub, llm, tts, spk, tools = build(sum((utterance() for _ in range(turns)), []), stt_lines)
    script = Script(replies)
    a.router.llm_stream = lambda messages, max_tokens=None, temperature=None: script.stream(messages)
    if known:
        a.memory.set_profile("name", "Mario")                              # se non lo sapesse, dopo la prima risposta lo chiederebbe (altri test)
        a.memory.set_profile("city", "Roma")
    if tool_results is not None:
        a.tools = ScriptedTools(a.cfg, a.memory, tool_results)
        a.tools.generate = a._generate_text
    return a, hub, script, tts, spk


async def test_thanks_gets_a_short_human_reply_without_the_chatbot():
    a, hub, script, tts, spk = build_flow(["ciao come stai", "grazie mille"], ["Ciao, bene. E tu."])
    await asyncio.wait_for(a.session(), 40)
    assert len(script.calls) == 1                                           # «grazie» non passa dal chatbot
    assert any(s in tts.said for s in dialog.THANKS_REPLIES)


async def test_asking_where_a_button_is_looks_at_the_screen_and_says_so_first_only_if_it_is_switched_on():
    a, hub, script, tts, spk = build_flow(["non trovo il pulsante Esporta"], [], tool_results=["Vedo «Esporta» in alto a destra."])
    a.tools.cfg["powers"] = {"screen_mac": True}
    await asyncio.wait_for(a.session(), 40)
    assert [(c.name, c.arg) for c in a.tools.seen] == [("SCHERMO", "dove|Esporta")] and not script.calls          # niente chatbot che inventa
    assert tts.said[0] in conversation.WORKING_SCREEN and "in alto a destra" in tts.said[-1]                      # «guardo lo schermo» e poi la risposta
    a2, hub2, script2, tts2, spk2 = build_flow(["non trovo il pulsante Esporta"], [], tool_results=["Non guardo lo schermo: l'ho lasciato spento."])
    await asyncio.wait_for(a2.session(), 40)
    assert not any(x in tts2.said for x in conversation.WORKING_SCREEN) and "spento" in tts2.said[-1]              # spento: niente «guardo…» a vuoto


async def test_asked_to_switch_off_she_goes_back_to_the_background_without_the_chatbot():
    for t in ("spegniti", "Aria, puoi spegnerti?", "ok vai in background", "mettiti in disparte per favore"):
        assert dialog.is_dismissal(t), t
    for t in ("spegni la musica", "spegni la luce", "vado a dormire", "metti in background la musica", "chiudi la finestra"):
        assert not dialog.is_dismissal(t), t                                # le altre «spegni» sono altri poteri
    a, hub, script, tts, spk = build_flow(["ciao come stai", "spegniti"], ["Ciao, bene. E tu."])
    await asyncio.wait_for(a.session(), 40)
    assert len(script.calls) == 1 and not a.in_session                      # niente chatbot: la conversazione e' finita
    assert tts.said[-1] in dialog.DISMISS_REPLIES and hub.state.value == "idle"      # e l'overlay torna a riposo (l'app resta nella barra dei menu)
    a2, hub2, script2, tts2, spk2 = build_flow(["spegniti"], [])             # anche come primissima frase
    await asyncio.wait_for(a2.session(), 40)
    assert tts2.said[-1] in dialog.DISMISS_REPLIES and not script2.calls


async def test_goodbye_ends_the_conversation_with_a_fitting_farewell():
    a, hub, script, tts, spk = build_flow(["ciao come stai", "ok, a dopo"], ["Ciao, bene. E tu."])
    await asyncio.wait_for(a.session(), 40)
    assert len(script.calls) == 1 and not a.in_session
    last = tts.said[-1]
    assert any(w in last for w in ("Buon", "dopo", "presto", "sentiamo", "Dormi", "Sogni", "Ciao"))      # un congedo, non una risposta da chatbot


async def test_an_ok_after_a_statement_gets_silence_but_after_a_question_it_is_an_answer():
    a, hub, script, tts, spk = build_flow(["ciao come stai", "ok", "e tu?"], ["Sto bene, grazie.", "Anch'io."])
    await asyncio.wait_for(a.session(), 40)
    assert len(script.calls) == 2                                           # il secondo «ok» non e' arrivato al chatbot
    n_spoken = len(tts.said)
    a2, hub, script2, tts2, spk2 = build_flow(["ciao come stai", "ok"], ["Bene! Che fai di bello?", "Bene."])
    await asyncio.wait_for(a2.session(), 40)
    assert len(script2.calls) == 2                                          # dopo una domanda «ok» e' la risposta: va al chatbot


async def test_a_request_left_half_done_is_completed_by_the_next_answer():
    a, hub, script, tts, spk = build_flow(["ricordami di chiamare Mario", "domani alle nove"], [], tool_results=["@CHIEDI|PROMEMORIA|chiamare Mario|Per quando te lo ricordo?", "Fatto: ti ricorderò Chiamare Mario domani alle nove."])
    await asyncio.wait_for(a.session(), 40)
    assert [c.name for c in a.tools.seen] == ["PROMEMORIA", "PROMEMORIA"]
    assert a.tools.seen[1] == ToolCall("PROMEMORIA", "chiamare Mario domani alle nove")        # la risposta completa il promemoria
    assert any("Per quando te lo ricordo" in s for s in tts.said) and any("Fatto" in s for s in tts.said)
    assert len(script.calls) == 0


async def test_changing_subject_drops_the_pending_question():
    a, hub, script, tts, spk = build_flow(["ricordami di chiamare Mario", "che ore sono"], [], tool_results=["@CHIEDI|PROMEMORIA|chiamare Mario|Per quando te lo ricordo?", "Sono le tre."])
    await asyncio.wait_for(a.session(), 40)
    assert [c.name for c in a.tools.seen] == ["PROMEMORIA", "ORA"] and a.pending_slot is None


async def test_add_also_continues_the_same_list():
    a, hub, script, tts, spk = build_flow(["aggiungi il latte alla lista della spesa", "e aggiungi anche le uova"], [], tool_results=["Aggiunto latte.", "Aggiunto uova."])
    await asyncio.wait_for(a.session(), 40)
    assert a.tools.seen[0].name == "LISTA" and a.tools.seen[1] == ToolCall("LISTA", "della spesa|le uova")


async def test_calling_her_by_voice_gets_a_greeting_but_the_hotkey_does_not():
    a, hub, script, tts, spk = build_flow([""], [], turns=1)
    a._voice_wake = True
    await asyncio.wait_for(a.session(), 40)
    assert tts.said and any(w in tts.said[0] for w in ("Ciao", "Buon", "Eccomi", "Ehi", "Dimmi", "Rieccomi", "Sì"))
    b, hub, script, tts2, spk = build_flow([""], [], turns=1)
    b._voice_wake = False
    await asyncio.wait_for(b.session(), 40)
    assert tts2.said == []


async def test_greeting_asks_about_a_past_event_once():
    import time
    a, hub, script, tts, spk = build_flow([""], ["Com'è andato l'esame di ieri?"], turns=1)
    a.memory.add_fact("ha un esame di analisi", importance=4, due=time.time() - 86400, kind="evento")
    a._voice_wake = True
    await asyncio.wait_for(a.session(), 40)
    assert any("andato" in s or "andata" in s for s in tts.said)
    assert a.memory.pending_followups() == []                               # fatto una volta: non lo richiede


async def test_a_half_finished_sentence_gets_a_moment_to_continue():
    script_frames = [LOUD] * 14 + [QUIET] * 27 + [LOUD] * 14 + [QUIET] * 40
    a, hub, llm, tts, spk, tools = build(script_frames, ["Mi racconti una cosa su", "Mi racconti una cosa sui polpi"])
    script = Script(["Certo. Sai che hanno tre cuori?"])
    a.router.llm_stream = lambda messages, max_tokens=None, temperature=None: script.stream(messages)
    await asyncio.wait_for(a.session(), 40)
    users = [m["content"] for m in a.history if m["role"] == "user"]
    assert users == ["Mi racconti una cosa sui polpi"]                      # ha atteso e ha riunito le due meta'


async def test_a_long_reply_is_cut_at_three_sentences_and_boilerplate_is_dropped():
    long = "Certamente! Ecco la prima. Poi la seconda. Poi la terza. Poi la quarta. Poi la quinta."
    a, hub, script, tts, spk = build_flow(["come va la vita"], [long])
    await asyncio.wait_for(a.session(), 40)
    spoken = [s for s in tts.said]
    assert spoken[0].startswith("Ecco la prima") and "Certamente" not in " ".join(spoken)
    assert "terza" in spoken[-1] and "quarta" not in " ".join(spoken)         # il tetto: tre frasi, una chiacchiera non e' un monologo


async def test_numbers_in_a_reply_are_spoken_as_words_but_shown_as_written():
    a, hub, script, tts, spk = build_flow(["raccontami una cosa buffa"], ["Ci sono 18°C e il 40% di umidità."])
    sub = hub.subscribe()
    await asyncio.wait_for(a.session(), 40)
    assert "diciotto gradi" in tts.said[0] and "quaranta per cento" in tts.said[0]


async def test_gender_is_learned_from_how_the_user_speaks_about_themself():
    a, hub, script, tts, spk = build_flow(["sono stanchissima oggi", "e adesso?"], ["Ahi, che giornata.", "Boh."])
    await asyncio.wait_for(a.session(), 40)
    assert a.memory.get_profile("gender") == "f"
    assert "femminile" in script.calls[-1][0]["content"]                       # dal secondo turno il chatbot lo sa


class ConfSTT:
    """Un Whisper finto che, oltre al testo, dice quanto era sicuro."""

    def __init__(self, items):
        self.items, self.last_conf = list(items), None

    async def transcribe(self, pcm, sr=16000):
        text, lp = self.items.pop(0) if self.items else ("", -0.3)
        self.last_conf = {"avg_logprob": lp, "no_speech": 0.0, "compression": 1.0}
        return text


async def test_when_whisper_is_unsure_aria_asks_to_repeat_instead_of_answering_nonsense():
    a, hub, script, tts, spk = build_flow([""], ["Eccomi qua."], turns=3)
    stt = ConfSTT([("Corriva.", -0.98), ("come va", -0.45)])
    a.router.objects = lambda stage: [stt] if stage == "stt" else []
    a.router.transcribe = stt.transcribe
    await asyncio.wait_for(a.session(), 40)
    assert any(s in tts.said for s in dialog.UNCLEAR)                        # la prima frase (incerta) non e' arrivata al chatbot
    users = [m["content"] for m in a.history if m["role"] == "user"]
    assert users == ["come va"]                                              # la seconda, chiara, si'


async def test_the_first_call_by_voice_is_an_introduction_and_the_next_words_are_the_name():
    a, hub, script, tts, spk = build_flow(["Mario"], [], turns=1, known=False)
    a._voice_wake = True
    await asyncio.wait_for(a.session(), 40)
    assert "come ti chiami" in tts.said[0].lower() and "Aria" in tts.said[0]
    assert a.memory.get_profile("name") == "Mario" and any(s.startswith("Piacere, Mario") for s in tts.said)


async def test_she_does_not_ask_personal_questions_to_someone_who_is_down_or_awake_at_night():
    a, hub, script, tts, spk = build_flow(["sono giù di morale oggi"], ["Mi dispiace tanto."], turns=2, known=False)
    await asyncio.wait_for(a.session(), 40)
    assert not any("come ti chiami" in s.lower() for s in tts.said)


async def test_a_false_claim_of_having_done_something_is_replaced_by_an_honest_line():
    from aria import style
    a, hub, script, tts, spk = build_flow(["sistemami la faccenda dei colori"], ["Fatto! Ho aggiunto tutto alla lista."])
    await asyncio.wait_for(a.session(), 40)
    assert style.NOT_UNDERSTOOD in tts.said[0] or "capito" in tts.said[0]
    assert not any("Ho aggiunto" in s for s in tts.said)


async def test_a_sentence_with_nothing_to_say_does_not_break_the_voice():
    a, hub, script, tts, spk = build_flow(["raccontami una cosa buffa"], ["(sorride)"])
    await asyncio.wait_for(a.session(), 40)                                   # nessuna eccezione: la «frase» di soli simboli diventa un attimo di silenzio
    assert tts.said == []


async def test_an_action_request_the_rules_do_not_get_is_not_answered_by_the_chatbot():
    a, hub, script, tts, spk = build_flow(["cancella il promemoria del caffè"], ["Va bene, fatto! Cancellato."])
    await asyncio.wait_for(a.session(), 40)
    assert script.calls == []                                                 # il chatbot non e' stato nemmeno interpellato
    assert any("non so ancora" in s for s in tts.said) and not any("Cancellato" in s for s in tts.said)


async def test_a_tool_call_invented_by_the_chatbot_is_refused_and_not_claimed():
    """Il 4B, davanti a una richiesta che non capiva, si inventava [[TIMER: 10:00 | caffè]] e poi diceva «fatto»."""
    a, hub, script, tts, spk = build_flow(["raccontami una cosa sul mare"], ["[[TIMER: 6 ottobre 2026 10:00 | Ricordati di prendere il caffè!]]"], tool_results=["@CHIEDI|TIMER||Per quanto tempo?"])
    await asyncio.wait_for(a.session(), 40)
    assert a.tools.seen == []                                                   # lo strumento non e' partito
    assert any("per quanto tempo" in s.lower() for s in tts.said) and not any("caffè" in s for s in tts.said)


async def test_a_complaint_about_aria_gets_an_honest_short_reply_without_the_chatbot():
    a, hub, script, tts, spk = build_flow(["ciao come stai", "però ti mangi le parole"], ["Ciao, bene. E tu."])
    await asyncio.wait_for(a.session(), 40)
    assert len(script.calls) == 1                                           # la lamentela non passa dal chatbot (che inventerebbe «farfeggiare»)
    assert any(s.replace("«", "").replace("»", "") in tts.said for s in dialog.COMPLAINT_REPLIES["voice"]), tts.said


async def test_the_users_name_is_not_repeated_in_every_reply():
    a, hub, script, tts, spk = build_flow(["ciao come stai", "oggi ho mangiato fuori", "poi sono tornato a casa"], ["Ciao Mario! Bene, e tu?", "Che bello, Mario. Dove sei stato?", "Certo, Mario! Una bella giornata."])
    await asyncio.wait_for(a.session(), 40)
    said = " ".join(tts.said)
    assert said.count("Mario") == 1                                        # lo dice la prima volta, poi lo lascia stare
    assert "Che bello." in said and "Certo!" in said


async def test_asked_to_explain_aria_speaks_at_length_but_in_chitchat_she_stays_short():
    ricetta = " ".join(f"Passaggio {n} della ricetta, fatto con calma." for n in range(1, 9))
    a, hub, script, tts, spk = build_flow(["dimmi una ricetta della carbonara"], [ricetta])
    await asyncio.wait_for(a.session(), 40)
    assert len(tts.said) >= 8                                               # tutte le otto frasi (il tetto di una chiacchiera e' 3)
    chiacchiera = " ".join(f"Frase numero {n} della risposta." for n in range(1, 9))
    a2, hub, script2, tts2, spk2 = build_flow(["oggi sono andato al mare"], [chiacchiera])
    await asyncio.wait_for(a2.session(), 40)
    assert len(tts2.said) <= 3


async def test_after_a_recipe_asking_to_write_it_in_a_file_saves_what_she_just_said():
    ricetta = " ".join(f"Passaggio {n} della ricetta, fatto con calma e attenzione." for n in range(1, 9))
    a, hub, script, tts, spk = build_flow(["dimmi la ricetta degli gnocchi", "mi scriveresti tutta la ricetta all'interno di un file?"], [ricetta],
                                          tool_results=["Fatto: l'ho salvato in «Gnocchi», nella tua cartella."])
    await asyncio.wait_for(a.session(), 40)
    assert [c.name for c in a.tools.seen] == ["SALVA"]
    import json
    d = json.loads(a.tools.seen[0].arg)
    assert d["kind"] == "ricetta" and "Passaggio 8" in d["source"]            # il testo intero che aveva appena detto...
    assert "scriveresti tutta la ricetta" in d["request"] and any("gnocchi" in m["content"] for m in d["history"])      # ...la richiesta e la conversazione
    assert any("salvato" in s for s in tts.said)


async def test_asking_for_a_file_as_the_first_thing_writes_a_new_document_and_never_just_promises():
    a, hub, script, tts, spk = build_flow(["Mi scriveresti all'interno del file all'interno di una cartella, la ricetta delle degli gnocchi alla romana."],
                                          ["Certo. Ti scrivo subito la ricetta degli gnocchi alla romana nel tuo file."],
                                          tool_results=["Fatto: ho scritto «Ricetta - gnocchi alla romana» nella tua cartella."])
    await asyncio.wait_for(a.session(), 40)
    assert [(c.name, c.arg) for c in a.tools.seen] == [("SCRIVI", "ricetta|gnocchi alla romana")]
    assert any("ho scritto" in s for s in tts.said) and not any("Ti scrivo subito" in s for s in tts.said)


async def test_a_file_request_the_rules_cannot_parse_is_not_dictated_by_the_chatbot():
    a, hub, script, tts, spk = build_flow(["scrivi un file"], ["Ti racconto volentieri la ricetta: prima prendi la semola, poi il latte."])
    await asyncio.wait_for(a.session(), 40)
    assert any("Non ho capito bene cosa scrivere nel file" in s for s in tts.said) and not any("semola" in s for s in tts.said)


async def test_a_slow_tool_shows_a_progress_bar_that_goes_away_when_it_is_done():
    a, hub, script, tts, spk = build_flow(["Mi scriveresti la ricetta degli gnocchi alla romana in un file?"], [],
                                          tool_results=["Fatto: ho scritto «Ricetta - gnocchi alla romana» nella tua cartella."])
    sub = hub.subscribe()
    await asyncio.wait_for(a.session(), 40)
    msgs = []
    while True:
        try:
            msgs.append(sub.get_nowait())
        except Exception:                                                  # noqa: BLE001
            break
    prog = [m for m in msgs if m.get("type") == "progress"]
    assert prog and prog[0]["active"] is True and "documento" in prog[0]["label"] and prog[0]["fraction"] is None      # parte: barra che scorre
    assert prog[-1] == {"type": "progress", "active": False} and hub.prog is None                                       # e a lavoro finito sparisce


def test_hub_progress_stages_are_sent_clamped_and_late_listeners_get_them_in_the_snapshot():
    from aria.state import Hub
    hub = Hub()
    sub = hub.subscribe()
    hub.progress("Scrivo la bozza", 0.3, 1.7, 40)
    m = sub.get_nowait()
    assert m == {"type": "progress", "active": True, "label": "Scrivo la bozza", "fraction": 0.3, "until": 1.0, "eta": 40}
    assert hub.snapshot()["progress"]["label"] == "Scrivo la bozza"
    hub.progress_done()
    assert sub.get_nowait() == {"type": "progress", "active": False} and "progress" not in hub.snapshot()
    hub.progress_done()                                                    # due volte non manda niente
    with pytest.raises(Exception):
        sub.get_nowait()


async def test_asking_to_save_with_nothing_to_save_says_so_instead_of_promising():
    a, hub, script, tts, spk = build_flow(["Vai, mettilo nella cartella."], ["Ho messo tutto nella cartella, puoi controllare quando vuoi."])
    await asyncio.wait_for(a.session(), 40)
    assert not getattr(a.tools, "seen", [])
    assert any("niente da mettere" in s for s in tts.said) and not any("Ho messo" in s for s in tts.said)


async def test_a_long_sentence_is_spoken_in_pieces_because_the_voice_cuts_long_ones():
    frase = "Non dimenticare il ragù di carne, che aggiunge profondità e quel tocco rustico che rende questo piatto unico."
    a, hub, script, tts, spk = build_flow(["ciao come stai"], [frase])
    a.cfg["human"]["tts_chunk_chars"] = 44
    await asyncio.wait_for(a.session(), 40)
    pezzi = [x for x in tts.said if "ragù" in x or "tocco" in x or "unico" in x]
    assert len(pezzi) >= 2 and " ".join(pezzi).replace(",", "").strip(" .").endswith("piatto unico")        # a pezzi, ma tutta


async def test_a_sentence_the_voice_cut_short_is_synthesized_again():
    class Heard:                                                           # il «revisore»: la prima volta sente la frase tagliata, la seconda intera
        def __init__(self):
            self.n = 0

        async def transcribe(self, pcm, sr):
            self.n += 1
            return "Il commercialista ti aspetta nel suo studio." if self.n == 1 else "Il commercialista ti aspetta nel suo studio domani alle 9."
    a, hub, script, tts, spk = build_flow(["ciao come stai"], ["Il commercialista ti aspetta nel suo studio domani alle nove."])
    a._voice_check = Heard()
    await asyncio.wait_for(a.session(), 40)
    frase = [s for s in tts.said if "commercialista" in s]
    assert len(frase) == 2 and a._voice_check.n == 2                       # sintetizzata due volte, la seconda risulta completa


async def test_a_broken_voice_checker_is_switched_off_without_stopping_aria():
    class Broken:
        async def transcribe(self, pcm, sr):
            raise RuntimeError("niente programma di supporto")
    a, hub, script, tts, spk = build_flow(["ciao come stai"], ["Il commercialista ti aspetta nel suo studio domani alle nove."])
    a._voice_check = Broken()
    await asyncio.wait_for(a.session(), 40)
    assert a._voice_check is not False and any("commercialista" in s for s in tts.said)        # un errore solo non lo spegne
    pcm = np.zeros(2400, dtype=np.float32)
    for _ in range(5):
        await a._verify_voice("Il commercialista ti aspetta nel suo studio.", pcm, 24000)
    assert a._voice_check is False                                                            # cinque di fila si'


async def test_a_calculation_the_user_never_asked_for_is_refused():
    """Dal vivo: «controlla se funziona» -> il chatbot ha lanciato [[CALCOLA: 10 - 0]] e poi ha parlato di «intoppo»."""
    a, hub, script, tts, spk = build_flow(["controlla se funziona"], ["[[CALCOLA: 10 - 0]]"], tool_results=["10 meno 0 fa 10."])
    await asyncio.wait_for(a.session(), 40)
    assert a.tools.seen == []
    assert any("che calcolo" in s.lower() for s in tts.said)


async def test_a_calculation_made_of_the_users_own_numbers_runs():
    a, hub, script, tts, spk = build_flow(["mi serve un conto: dodici per sette"], ["[[CALCOLA: 12 * 7]]", "Fa ottantaquattro."], tool_results=["12 per 7 fa 84."])
    await asyncio.wait_for(a.session(), 40)
    assert [c.name for c in a.tools.seen] == ["CALCOLA"]


async def test_a_reminder_can_be_converted_after_an_event_and_changed_by_replacing_words():
    a, hub, script, tts, spk = build_flow(["mi crei un evento per domani alle 10 con scritto prendere il caffè", "lo metti come promemoria, non come evento", "cambia caffè con tabacco"], [],
                                          tool_results=["Fatto: «Prendere il caffè» è in calendario domani alle dieci.", "Fatto: ti ricorderò «Prendere il caffè» domani alle dieci.", "Fatto: ti ricorderò «Prendere il tabacco» domani alle dieci."], turns=4)
    await asyncio.wait_for(a.session(), 60)
    names = [c.name for c in a.tools.seen]
    assert names == ["EVENTO", "PROMEMORIA", "PROMEMORIA"]
    assert a.tools.seen[1].arg == a.tools.seen[0].arg                         # stesso testo, strumento diverso
    assert "tabacco" in a.tools.seen[2].arg and "caffè" not in a.tools.seen[2].arg
    assert any("resta in calendario" in s for s in tts.said) and any("non lo so cancellare" in s for s in tts.said)    # onesta: il vecchio resta


async def test_save_the_last_search_without_repeating_the_topic():
    a, hub, script, tts, spk = build_flow(["cerca gemma 2 nove miliardi", "fammi una ricerca e salvala nella cartella"], ["Gemma 2 è del 2024."], tool_results=["Risultati: Gemma 2...", "Fatto: ho salvato la ricerca."])
    await asyncio.wait_for(a.session(), 60)
    assert [c.name for c in a.tools.seen] == ["CERCA", "RICERCA"]
    assert a.tools.seen[1].arg == a.tools.seen[0].arg                         # la ricerca salvata e' quella di cui stavano parlando


async def test_when_the_rules_miss_an_action_the_chatbot_can_decode_it_but_only_with_the_users_own_words():
    from tests.test_human_flow import Script  # noqa: F401
    a, hub, script, tts, spk = build_flow(["prepara un promemoria domani alle nove per chiamare Mario"], ["PROMEMORIA | domani alle nove chiamare Mario"],
                                          tool_results=["Fatto: ti ricorderò «Chiamare Mario» domani alle nove."])
    await asyncio.wait_for(a.session(), 40)
    assert [c.name for c in a.tools.seen] == ["PROMEMORIA"] and "chiamare" in a.tools.seen[0].arg.lower()      # decodificato dal chatbot, eseguito dagli strumenti di sempre
    assert any("Fatto" in s for s in tts.said)


async def test_a_decoding_with_invented_details_is_discarded_and_the_answer_is_honest():
    a, hub, script, tts, spk = build_flow(["mettimi da parte un promemoria per domani"], ["PROMEMORIA | domani alle 10 prendere il caffè"], tool_results=["Fatto."])
    await asyncio.wait_for(a.session(), 40)
    assert a.tools.seen == []                                                                              # «alle 10» e «il caffè» non li ha detti l'utente
    assert any("Non sono sicura di aver capito" in s for s in tts.said)


async def test_the_content_of_a_reminder_that_starts_with_a_calling_verb_completes_it():
    a, hub, script, tts, spk = build_flow(["prova a creare un promemoria per domani alle nove", "chiamare il commercialista"], [],
                                          tool_results=["@CHIEDI|PROMEMORIA|domani alle nove|Cosa devo ricordarti?", "Fatto: ti ricorderò «Chiamare il commercialista» domani alle nove."])
    await asyncio.wait_for(a.session(), 40)
    assert [c.name for c in a.tools.seen] == ["PROMEMORIA", "PROMEMORIA"]
    assert "chiamare il commercialista" in a.tools.seen[1].arg                  # non «telefonare non so farlo»
    assert not any("Telefonare" in s for s in tts.said)
