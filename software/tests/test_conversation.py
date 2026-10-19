"""Prova end-to-end del ciclo di conversazione con componenti finti (niente audio, niente modelli)."""
import asyncio

import numpy as np

from aria.config import load
from aria.conversation import Aria, strip_wake
from aria.memory import Memory
from aria.router import Router
from aria.state import Hub, State
from aria.textutil import ToolCall
from aria.tools import Tools

LOUD = np.full(512, 6000, dtype=np.int16)
QUIET = np.zeros(512, dtype=np.int16)


class FakeMic:
    """Consegna una sceneggiatura di frame (LOUD = voce, QUIET = silenzio); poi silenzio all'infinito."""

    def __init__(self, script):
        self.script = list(script)

    async def start(self):
        pass

    async def stop(self):
        pass

    def flush(self):
        pass

    async def frames(self):
        while True:
            await asyncio.sleep(0)
            yield self.script.pop(0) if self.script else QUIET


class FakeVAD:
    def reset(self):
        pass

    def prob(self, frame):
        return 0.95 if int(np.abs(frame).max()) > 1000 else 0.0


class FakeWake:
    def feed(self, frame):
        return True


class FakeSpeaker:
    def __init__(self):
        self.played, self.level, self.stopped = [], 0.0, 0

    def start(self):
        pass

    def close(self):
        pass

    def play(self, pcm, sr):
        self.played.append(len(pcm))
        self.level = 0.5

    def stop(self):
        self.stopped += 1

    async def wait_done(self):
        await asyncio.sleep(0)


class RecHub(Hub):
    def __init__(self):
        super().__init__()
        self.seen = []

    def set_state(self, state):
        self.seen.append(state.value)
        super().set_state(state)


class FakeSTT:
    def __init__(self, lines):
        self.lines = list(lines)

    async def transcribe(self, pcm, sr=16000):
        return self.lines.pop(0) if self.lines else ""


class FakeTTS:
    def __init__(self):
        self.said = []

    async def synthesize(self, text):
        self.said.append(text)
        return np.zeros(160, dtype=np.int16), 16000


class FakeLLM:
    """Primo giro: chiede il meteo con un comando. Secondo giro (dopo il risultato): risponde."""

    def __init__(self):
        self.calls = []

    async def stream(self, messages):
        self.calls.append(messages)
        last = messages[-1]["content"]
        if last.startswith("(Dati dal sistema"):
            for t in ["Domani ", "a Roma ", "piove un po'. ", "Prendi la giacca."]:
                yield t
        elif "meteo" in last.lower() or "tempo" in last.lower():
            for t in ["Vediamo. ", "[[METEO: ", "Roma domani", "]]"]:
                yield t
        else:
            for t in ["Ciao! ", "Dimmi pure."]:
                yield t


class FakeTools(Tools):
    async def run(self, call):
        self.last = call
        return "Roma, domani: pioggia debole, minima 8, massima 15."


def build(script, stt_lines, barge_in=False):
    cfg = load()
    cfg["audio"]["barge_in"] = barge_in
    cfg.setdefault("human", {})["tts_chunk_chars"] = 10_000                  # le frasi lunghe si dicono intere (si spezzano solo nei test apposta)
    cfg["turn"].update(follow_up_timeout_s=1.0, first_turn_timeout_s=1.0, filler_after_ms=0)
    llm, tts, stt = FakeLLM(), FakeTTS(), FakeSTT(stt_lines)
    router = Router([{"name": "t", "llm": {"kind": "piper"}, "stt": {"kind": "piper"}, "tts": {"kind": "piper"}}],
                    lambda stage, c: {"llm": llm, "stt": stt, "tts": tts}[stage])
    hub, mem, spk = RecHub(), Memory(), FakeSpeaker()
    tools = FakeTools(cfg, mem)
    a = Aria(cfg, hub, FakeMic(script), spk, FakeWake(), FakeVAD(), router, tools, mem, "Sei Aria.")
    a._bi_stt = False                                                       # niente interruzione a parole nei test (userebbe il programma vero del Mac)
    a._voice_check = False                                                  # niente riascolto della voce (Apple) nei test: userebbe il programma vero del Mac
    a._hour = lambda: 15                                                    # di pomeriggio: di notte Aria non fa domande personali (e i test non devono dipendere da quando girano)
    return a, hub, llm, tts, spk, tools


def utterance(n_voice=14):
    return [LOUD] * n_voice + [QUIET] * 40


async def test_full_turn_with_tool_then_follow_up_timeout():
    a, hub, llm, tts, spk, tools = build(utterance(), ["Hey Aria dimmi del tempo là fuori"])
    await asyncio.wait_for(a.session(), 20)
    states = hub.seen
    # ha chiamato lo strumento giusto e ha parlato il risultato frase per frase
    assert tools.last == ToolCall("METEO", "Roma domani")
    assert tts.said[0].startswith("Vediamo")
    assert any("piove" in s for s in tts.said) and any("giacca" in s for s in tts.said)
    assert len(spk.played) >= 3
    # il testo dell'utente ha perso il "Hey Aria"
    assert not llm.calls[0][-1]["content"].lower().startswith("hey aria")
    # cronologia: utente + risposta di Aria (senza il comando)
    assert a.history[-1]["role"] == "assistant" and "[[" not in a.history[-1]["content"]
    # ha attraversato gli stati giusti e alla fine e' tornata a riposo (follow-up scaduto)
    assert "thinking" in states and "speaking" in states and "listening" in states
    assert hub.state == State.IDLE and not a.in_session


async def test_stop_command_ends_session_silently():
    a, hub, llm, tts, spk, tools = build(utterance(), ["basta"])
    await asyncio.wait_for(a.session(), 20)
    assert tts.said == [] and a.history == []


async def test_barge_in_stops_speech_and_carries_audio():
    # la voce dell'utente riparte mentre Aria parla: la sceneggiatura continua a dare LOUD durante la risposta
    script = utterance() + [LOUD] * 30 + [QUIET] * 60
    a, hub, llm, tts, spk, tools = build(script, ["che tempo fa domani", "no aspetta, un'altra cosa"], barge_in=True)
    waits = {"n": 0}

    async def slow_wait_done():
        waits["n"] += 1
        await asyncio.sleep(5 if waits["n"] == 1 else 0)      # solo la prima risposta e' abbastanza lunga da essere interrotta
    spk.wait_done = slow_wait_done
    await asyncio.wait_for(a.session(), 30)
    assert spk.stopped >= 1
    users = [m["content"] for m in a.history if m["role"] == "user"]
    assert users == ["che tempo fa domani", "no aspetta, un'altra cosa"]


def test_strip_wake():
    assert strip_wake("Ciao Aria, che ore sono?", "ciao aria") == "che ore sono?"
    assert strip_wake("ciao area che ore sono", "ciao aria") == "che ore sono"
    assert strip_wake("che ore sono", "ciao aria") == "che ore sono"
    assert strip_wake("ciao", "ciao aria") == "ciao"                 # un saluto da solo resta un saluto
    for said in ("Hey Aria, che ore sono?", "Ehi Aria che ore sono", "hey, aria. che ore sono?", "Hei Aria che ore sono", "Ei Aria, che ore sono?"):
        assert strip_wake(said, "hey aria") == "che ore sono" or strip_wake(said, "hey aria") == "che ore sono?", said
    assert strip_wake("ciao Aria che ore sono", "hey aria") == "ciao Aria che ore sono"      # col nuovo modo di chiamarla, «ciao aria» non e' piu' la chiamata
    assert strip_wake("hey", "hey aria") == "hey"


async def test_wake_by_stt_keeps_the_command_said_in_one_breath():
    # "Hey Aria che tempo fa domani" tutto insieme: la frase di attivazione sveglia, il resto e' il primo comando
    a, hub, llm, tts, spk, tools = build(utterance(), ["Hey Aria, dimmi del tempo là fuori"])
    a.cfg["wake"]["mode"] = "stt"
    await asyncio.wait_for(a.wait_for_wake(), 20)
    assert a.pending_text == "dimmi del tempo là fuori"
    await asyncio.wait_for(a.session(), 20)
    assert tools.last == ToolCall("METEO", "Roma domani") and a.history[0]["content"] == "dimmi del tempo là fuori"


async def test_wake_by_stt_ignores_other_speech():
    a, hub, llm, tts, spk, tools = build(utterance() + utterance(), ["che aria fredda oggi", "hey aria"])
    a.cfg["wake"]["mode"] = "stt"
    await asyncio.wait_for(a.wait_for_wake(), 20)
    assert a.pending_text is None                          # solo il wake word, nessun comando


class NeverWake:
    def feed(self, frame):
        return False


async def test_wake_by_hotkey_command():
    a, hub, llm, tts, spk, tools = build([QUIET] * 5, [])
    a.wake = NeverWake()
    t = asyncio.create_task(a.wait_for_wake())
    await asyncio.sleep(0.05)
    assert not t.done()                                    # nessuno ha parlato: resta in attesa
    hub.dispatch_command({"cmd": "wake"})                  # tasto ⌥Space / menu
    await asyncio.wait_for(t, 2)
    assert hub.state == State.LISTENING


async def test_muted_ignores_wake_word_but_not_hotkey():
    a, hub, llm, tts, spk, tools = build([QUIET] * 30, [])
    hub.dispatch_command({"cmd": "mute"})
    assert a.muted and hub.info["muted"] is True
    t = asyncio.create_task(a.wait_for_wake())             # FakeWake dice sempre "scattato", ma e' silenziata
    await asyncio.sleep(0.05)
    assert not t.done()
    hub.dispatch_command({"cmd": "wake"})
    await asyncio.wait_for(t, 2)


async def test_stop_command_interrupts_speech_and_ends_session():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao come stai"])

    async def long_wait():
        await asyncio.sleep(10)
    spk.wait_done = long_wait                              # sta "parlando" a lungo
    task = asyncio.create_task(a.session())
    for _ in range(200):                                   # aspetta che inizi a parlare
        await asyncio.sleep(0.02)
        if spk.played:
            break
    hub.dispatch_command({"cmd": "stop"})
    await asyncio.wait_for(task, 5)
    assert spk.stopped >= 1 and not a.in_session


async def test_transcripts_are_published_for_the_overlay():
    a, hub, llm, tts, spk, tools = build(utterance(), ["Hey Aria, dimmi del tempo là fuori"])
    sub = hub.subscribe()
    await asyncio.wait_for(a.session(), 20)
    msgs = []
    while not sub.empty():
        msgs.append(sub.get_nowait())
    tr = [(m["role"], m["text"]) for m in msgs if m["type"] == "transcript"]
    assert tr[0] == ("user", "dimmi del tempo là fuori")
    assert any(r == "aria" and "giacca" in t for r, t in tr)


async def test_obvious_requests_run_the_tool_before_the_model_speaks():
    """"Che tempo fa domani?" lancia il meteo a monte: il modello non scrive niente prima, riceve solo i dati."""
    a, hub, llm, tts, spk, tools = build(utterance(), ["che tempo fa domani a Roma"])
    await asyncio.wait_for(a.session(), 20)
    assert tools.last == ToolCall("METEO", "Roma domani")
    assert llm.calls == []                                      # meteo: la risposta si legge direttamente, il modello non serve
    assert any("pioggia debole" in s for s in tts.said)
    assert any(m["role"] == "assistant" and "pioggia debole" in m["content"] for m in a.history)


async def test_wiki_goes_through_the_model_to_be_summarised():
    a, hub, llm, tts, spk, tools = build(utterance(), ["chi è Leonardo da Vinci"])
    await asyncio.wait_for(a.session(), 20)
    assert tools.last.name == "WIKI"
    assert len(llm.calls) == 1 and llm.calls[0][-1]["content"].startswith("(Dati dal sistema")


# ---------------------------------------------------------------- memoria: imparare e chiedere
from aria.tools import NEED_CITY          # noqa: E402


class CityTools(Tools):
    """Come il meteo vero: senza una citta' (detta dall'utente o nell'argomento) non sa rispondere."""

    async def run(self, call):
        self.last = call
        if call.name == "METEO":
            home = self.memory.get_profile("city") if self.memory else None
            if not home and "milano" not in call.arg.lower():
                return NEED_CITY
            return f"{home or 'Milano'}, domani: sole."
        return "ok"


def two_turns(stt_lines, **kw):
    return build(utterance() + utterance() + utterance(), stt_lines, **kw)


async def test_aria_asks_the_name_after_the_first_answer_and_remembers_it():
    a, hub, llm, tts, spk, tools = two_turns(["ciao come stai", "Mario"])
    await asyncio.wait_for(a.session(), 40)
    assert any("come ti chiami" in s.lower() for s in tts.said)
    assert a.memory.get_profile("name") == "Mario"
    assert any(s.startswith("Piacere, Mario") for s in tts.said)
    assert len(llm.calls) == 1                                       # la presentazione non passa dal modello: niente invenzioni
    assert a.pending is None
    assert a.memory.times_asked("name")[0] == 1


async def test_introducing_yourself_inside_a_longer_sentence_keeps_the_conversation_going():
    a, hub, llm, tts, spk, tools = build(utterance(), ["Mi chiamo Mario e domani ho un esame di analisi"])
    await asyncio.wait_for(a.session(), 30)
    assert a.memory.get_profile("name") == "Mario"
    assert len(llm.calls) == 1 and "si chiama Mario" in llm.calls[0][0]["content"]       # il modello lo sa gia' per rispondere
    assert not any(s.startswith("Piacere") for s in tts.said)
    ev = a.memory.upcoming()
    assert len(ev) == 1 and "ha un esame di analisi" in ev[0][0] and ev[0][1] == 1
    assert not any("come ti chiami" in s.lower() for s in tts.said)                         # il nome lo sa: non lo chiede


async def test_declining_the_question_is_respected():
    a, hub, llm, tts, spk, tools = two_turns(["ciao come stai", "preferisco non dirtelo"])
    await asyncio.wait_for(a.session(), 40)
    assert "Va bene, nessun problema." in tts.said and a.memory.get_profile("name") is None


async def test_a_wrong_name_can_be_corrected():
    a, hub, llm, tts, spk, tools = build(utterance(), ["non mi chiamo Luca"])
    a.memory.set_profile("name", "Luca")
    await asyncio.wait_for(a.session(), 30)
    assert a.memory.get_profile("name") is None and any("Come ti chiami" in s for s in tts.said)


async def test_it_does_not_nag():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao come stai"])
    a.memory.mark_asked("name")                                      # chiesto da poco: oggi non lo richiede
    a.memory.mark_asked("city")
    await asyncio.wait_for(a.session(), 30)
    assert not any("come ti chiami" in s.lower() or "città" in s for s in tts.said)
    a2, *_rest = build(utterance(), ["ciao come stai"])
    a2.memory.mark_asked("name", count=3)                            # gia' chiesto 3 volte: smette
    a2.memory.mark_asked("city", count=3)
    tts2 = _rest[2]
    await asyncio.wait_for(a2.session(), 30)
    assert not any("come ti chiami" in s.lower() for s in tts2.said)


async def test_weather_without_a_city_asks_for_it_and_then_answers():
    a, hub, llm, tts, spk, tools = two_turns(["che tempo fa domani", "Milano"])
    a.cfg["location"] = {"city": None, "lat": None, "lon": None}
    a.tools = CityTools(a.cfg, a.memory)
    await asyncio.wait_for(a.session(), 40)
    assert any("dove abiti" in s for s in tts.said)
    assert a.memory.get_profile("city") == "Milano"
    assert a.tools.last.name == "METEO" and any("sole" in s for s in tts.said)               # rifatto da solo con la citta' appena detta
    assert llm.calls == []


async def test_what_do_you_know_about_me_reads_the_memory_aloud():
    a, hub, llm, tts, spk, tools = build(utterance(), ["cosa sai di me"])
    a.tools = Tools(a.cfg, a.memory)
    a.memory.set_profile("name", "Mario")
    a.memory.add_fact("Ha un cane che si chiama Briciola", 4)
    await asyncio.wait_for(a.session(), 30)
    said = " ".join(tts.said)
    assert "ti chiami Mario" in said and "cane" in said and llm.calls == []


async def test_facts_are_learned_only_from_what_the_user_says():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ho un cane che si chiama Briciola"])
    await asyncio.wait_for(a.session(), 30)
    assert a.memory.all_facts() == ["Ha un cane che si chiama Briciola"]
    assert a.memory.get_profile("name") is None and a.memory.get_profile("city") is None     # niente nomi/citta' inventati


async def test_session_end_no_longer_invents_facts_from_the_model():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    await a._remember_session([{"role": "user", "content": "ciao"}, {"role": "assistant", "content": "Ciao Luca!"}])
    assert a.memory.all_facts() == [] and a.memory.last_session() is None


async def test_chatbot_is_primed_with_the_character_only():
    """All'avvio Aria scalda il chatbot interno con due prompt che differiscono SOLO in data e memoria: il prefisso in cache e' il carattere."""
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    seen = {}

    async def prime(sys_a, sys_b):
        seen["a"], seen["b"] = sys_a, sys_b
        return 600
    llm.prime, llm.model = prime, object()
    async for _ in a.router.candidates("llm"):                       # crea l'adattatore, come il riscaldamento dell'app
        pass
    await asyncio.wait_for(a._prime_llm(), 10)
    a_, b_ = seen["a"], seen["b"]
    assert a_ != b_ and a_.startswith("Sei Aria.") and b_.startswith("Sei Aria.")
    common = 0
    while a_[common] == b_[common]:
        common += 1
    assert common >= len("Sei Aria.\n\nAdesso è: ")                  # il carattere + l'inizio della riga data sono uguali, poi cambia solo la data
    assert "2000" in a_ and "2031" in b_


async def test_changing_voice_plays_a_short_sample_right_away():
    from aria.conversation import VOICE_SAMPLE
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    set_to = []
    tts.set_voice = lambda name: set_to.append(name)
    async for _ in a.router.candidates("tts"):                      # crea l'adattatore della voce, come il riscaldamento
        pass
    a._on_command({"cmd": "voice", "name": "vera"})
    await asyncio.sleep(0.2)
    assert set_to == ["vera"] and tts.said == [VOICE_SAMPLE] and len(spk.played) == 1
    assert "speaking" in hub.seen and hub.state == State.IDLE        # la schermata compare e poi si spegne
    assert "hey aria" not in VOICE_SAMPLE.lower() and "ciao aria" not in VOICE_SAMPLE.lower()                  # la prova non deve riattivare Aria dal microfono


async def test_voice_sample_is_skipped_during_a_conversation_and_restarted_when_changed_again():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    async for _ in a.router.candidates("tts"):
        pass
    a.in_session = True
    a._on_command({"cmd": "voice", "name": "vera"})
    await asyncio.sleep(0.2)
    assert tts.said == []                                           # sta parlando con l'utente: niente prova
    a.in_session = False
    slow = {"n": 0}
    orig = tts.synthesize

    async def slow_synth(text):
        slow["n"] += 1
        if slow["n"] == 1:
            await asyncio.sleep(5)                                  # la prima prova e' lenta: la seconda scelta la sostituisce
        return await orig(text)
    tts.synthesize = slow_synth
    a._on_command({"cmd": "voice", "name": "eve"})
    await asyncio.sleep(0.05)
    a._on_command({"cmd": "voice", "name": "paul"})
    await asyncio.sleep(0.3)
    assert slow["n"] == 2 and len(spk.played) == 1 and spk.stopped >= 1     # una sola prova sentita (l'ultima), l'altra e' stata annullata


def test_the_voice_detector_gets_more_volume_when_the_user_speaks_softly():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    quiet = (np.sin(np.linspace(0, 400, 16000)) * 300).astype(np.int16)          # circa -39 dB: una persona che parla piano
    loud = (np.sin(np.linspace(0, 400, 16000)) * 9000).astype(np.int16)           # circa -11 dB
    for _ in range(6):
        a._learn_level(quiet)
    assert 3.5 <= a._vad_gain <= 4.0                                              # tetto 4x
    assert int(np.abs(a._boost(np.full(512, 1000, dtype=np.int16))).max()) >= 3500
    for _ in range(8):
        a._learn_level(loud)
    assert a._vad_gain < 1.2 and int(np.abs(a._boost(np.full(512, 1000, dtype=np.int16))).max()) == 1000    # voce forte: nessun aumento
    a.cfg["vad"]["gain"] = 1
    a._vad_gain = 4.0
    assert int(np.abs(a._boost(np.full(512, 1000, dtype=np.int16))).max()) == 1000                          # spento da config


def test_the_default_preroll_keeps_enough_audio_for_soft_word_onsets():
    from aria.config import load
    assert load()["turn"]["preroll_ms"] >= 600


async def test_stop_ends_the_conversation_at_once_even_when_the_voice_interruption_monitor_never_returns():
    """Con l'ascolto dell'interruzione a voce attivo, dopo lo stop respond() restava appeso finche' l'utente non diceva qualcosa: la voce si fermava ma Aria restava «sta parlando»."""
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao come stai"])

    async def never():
        await asyncio.sleep(1000)
    a._monitor_barge_in_words = never                      # come dal vivo: il monitor ascolta all'infinito
    a.cfg["audio"]["barge_in"] = False
    a.cfg["audio"]["barge_in_words"] = True

    async def long_wait():
        await asyncio.sleep(10)
    spk.wait_done = long_wait
    task = asyncio.create_task(a.session())
    for _ in range(200):
        await asyncio.sleep(0.02)
        if spk.played:
            break
    t0 = asyncio.get_running_loop().time()
    hub.dispatch_command({"cmd": "stop"})
    await asyncio.wait_for(task, 3)
    assert asyncio.get_running_loop().time() - t0 < 1.0 and not a.in_session and hub.state == State.IDLE


async def test_the_key_while_aria_speaks_stops_her_even_if_the_app_thinks_she_is_idle_and_sends_wake():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao come stai"])

    async def long_wait():
        await asyncio.sleep(10)
    spk.wait_done = long_wait
    task = asyncio.create_task(a.session())
    for _ in range(200):
        await asyncio.sleep(0.02)
        if spk.played:
            break
    assert hub.state == State.SPEAKING
    hub.dispatch_command({"cmd": "wake"})                  # l'app aveva uno stato vecchio e ha mandato «wake» invece di «stop»
    await asyncio.wait_for(task, 3)
    assert not a._wake_req and not a.in_session


async def test_stop_while_she_listens_closes_the_conversation_and_one_pressed_while_thinking_is_not_lost():
    a, hub, llm, tts, spk, tools = build([QUIET] * 4000, [])

    class SlowMic(FakeMic):
        async def frames(self):                            # un microfono vero: un blocco ogni 32 ms
            while True:
                await asyncio.sleep(0.01)
                yield QUIET
    a.mic = SlowMic([])
    task = asyncio.create_task(a.session())
    for _ in range(100):
        await asyncio.sleep(0.02)
        if hub.state == State.LISTENING:
            break
    assert hub.state == State.LISTENING
    hub.dispatch_command({"cmd": "stop"})                  # il tasto mentre aspetta che tu parli
    await asyncio.wait_for(task, 3)
    assert not a.in_session
    a2, hub2, llm2, tts2, spk2, tools2 = build(utterance(), ["ciao come stai"])
    a2._stop_evt.set()                                     # uno stop vecchio: la conversazione nuova non ne risente
    t2 = asyncio.create_task(a2.session())
    await asyncio.sleep(0.3)
    assert not t2.done() or spk2.played                    # (parte normalmente)
    t2.cancel()
    await asyncio.gather(t2, return_exceptions=True)


async def test_waiting_for_the_wake_word_uses_the_light_detector_and_the_conversation_the_normal_one():
    a, hub, llm, tts, spk, tools = build(utterance(), ["hey aria"])
    used = []

    class Spy(FakeVAD):
        def __init__(self, tag):
            self.tag = tag

        def prob(self, frame):
            used.append(self.tag)
            return super().prob(frame)
    a.vad, a.idle_vad = Spy("normale"), Spy("leggero")
    a.cfg["wake"]["mode"] = "stt"
    await asyncio.wait_for(a.wait_for_wake(), 20)
    assert used and set(used) == {"leggero"}


def test_with_the_echo_free_mic_sentences_keep_their_normal_rhythm():
    a, hub, llm, tts, spk, tools = build(utterance(), [])
    a.cfg["audio"]["barge_in"] = False
    assert a._listen_gap_ms() == 480                       # senza filtro eco: un respiro piu' lungo per poterla interrompere nelle pause
    a.mic.cleaned = True
    assert a._listen_gap_ms() == 0                         # col filtro eco del Mac l'interruzione non aspetta le pause


async def test_on_battery_with_the_screen_off_she_stops_listening_so_the_mac_can_sleep_and_comes_back(monkeypatch):
    """Con il microfono aperto macOS non manda mai il Mac in stop da solo: a batteria e schermo spento Aria chiude il microfono e lo riapre quando serve."""
    from aria import power
    a, hub, llm, tts, spk, tools = build([QUIET] * 10, [])
    spk.playing = False
    state = {"batt": True, "dark": True}
    monkeypatch.setattr(power, "on_battery", lambda: state["batt"])
    monkeypatch.setattr(power, "display_asleep", lambda: state["dark"])
    calls = []
    a.mic.close_sync = lambda: calls.append("chiuso")
    a.mic.start_sync = lambda: calls.append("aperto")
    t = asyncio.create_task(a._power_saver(every=0.01, after=0.05))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if a._paused:
            break
    assert a._paused and calls == ["chiuso"] and hub.info.get("paused") is True
    state["dark"] = False                                                         # lo schermo si riaccende
    for _ in range(100):
        await asyncio.sleep(0.01)
        if not a._paused:
            break
    assert not a._paused and calls == ["chiuso", "aperto"]
    state["dark"] = True
    for _ in range(100):
        await asyncio.sleep(0.01)
        if a._paused:
            break
    hub.dispatch_command({"cmd": "wake"})                                           # il tasto la risveglia subito
    assert not a._paused and a._wake_req and calls[-1] == "aperto"
    state["batt"] = False                                                         # all'alimentatore non si chiude mai
    a._wake_req = False
    await asyncio.sleep(0.2)
    assert not a._paused
    t.cancel()
    await asyncio.gather(t, return_exceptions=True)


async def test_the_battery_saver_never_closes_the_mic_during_a_conversation_or_when_switched_off(monkeypatch):
    from aria import power
    a, hub, llm, tts, spk, tools = build([QUIET] * 10, [])
    spk.playing = False
    monkeypatch.setattr(power, "on_battery", lambda: True)
    monkeypatch.setattr(power, "display_asleep", lambda: True)
    a.mic.close_sync = lambda: None
    a.mic.start_sync = lambda: None
    a.in_session = True
    t = asyncio.create_task(a._power_saver(every=0.01, after=0.02))
    await asyncio.sleep(0.2)
    assert not a._paused
    t.cancel()
    await asyncio.gather(t, return_exceptions=True)
    a.in_session = False
    a.cfg["audio"]["sleep_on_battery"] = False
    t = asyncio.create_task(a._power_saver(every=0.01, after=0.0))                 # spento: a batteria non chiude mai il microfono
    await asyncio.sleep(0.2)
    assert not a._paused
    t.cancel()
    await asyncio.gather(t, return_exceptions=True)


async def test_a_failing_recognizer_while_waiting_does_not_retry_the_same_sentence_at_every_block():
    """Il 7 ottobre: 1157 «riconoscimento (attesa) fallito» in 47 s. Dopo un errore l'attesa ricomincia pulita (e respira mezzo secondo)."""
    a, hub, llm, tts, spk, tools = build(utterance() + [QUIET] * 200, [])
    a.cfg["wake"]["mode"] = "stt"
    calls = []

    class Broken:
        async def transcribe(self, pcm, sr):
            calls.append(len(pcm))
            raise RuntimeError("nessun riconoscimento vocale disponibile")
    a.wake_stt = Broken()
    t = asyncio.create_task(a.wait_for_wake())
    await asyncio.sleep(1.5)
    t.cancel()
    await asyncio.gather(t, return_exceptions=True)
    assert len(calls) == 1                                  # una frase -> un tentativo (prima: uno per ogni blocco dopo la fine della frase)


async def test_a_microphone_that_does_not_open_at_startup_is_retried_not_a_crash(monkeypatch):
    """Il 6 ottobre, al primo avvio senza permesso: il backend cadeva con un errore e ripartiva 109 volte. Ora riprova finche' non si apre."""
    a, hub, llm, tts, spk, tools = build([QUIET] * 5, [])
    tries = []

    class Mic:
        async def start(self):
            tries.append(1)
            if len(tries) < 3:
                raise RuntimeError("Error opening InputStream: Internal PortAudio error [PaErrorCode -9986]")
    a.mic = Mic()
    real_sleep = asyncio.sleep
    monkeypatch.setattr("aria.conversation.asyncio.sleep", lambda s: real_sleep(0))
    await asyncio.wait_for(a._open_mic(), 5)
    assert len(tries) == 3
