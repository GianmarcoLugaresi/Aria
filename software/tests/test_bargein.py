"""Interrompere Aria con la voce mentre parla (anche con le casse): le parole dell'utente si distinguono dall'eco della sua voce."""
import asyncio

import numpy as np

from aria import bargein
from tests.test_conversation import build, utterance


def test_the_echo_of_her_own_voice_is_ignored_but_stop_words_and_new_words_are_not():
    said = "Prima scalda il latte con il burro e il sale, poi aspetta che bolla e versa la semola a pioggia mescolando."
    assert bargein.interruption("Prima scalda il latte con il burro e il sale poi aspetta che", said) is None            # eco (anche con «aspetta», che dice lei)
    assert bargein.interruption("scalda il latte con il burro e il", said) is None
    assert bargein.interruption("prima scalda il latte basta", said) == "stop"                                           # eco + «basta» dell'utente
    assert bargein.interruption("Aria fermati", said) == "stop"
    assert bargein.interruption("un attimo", said) == "stop"
    assert bargein.interruption("no volevo chiederti un'altra cosa", said) == "talk"
    assert bargein.interruption("", said) is None and bargein.interruption("ah eh mh", said) is None
    assert bargein.interruption("Marrio Perché la semola", said) is None                                                  # errori di riconoscimento dell'eco non bastano a interrompere


class FakeBi:
    def __init__(self, heard):
        self.heard, self.n, self.closed = heard, 0, 0

    async def transcribe(self, pcm, sr):
        self.n += 1
        h = self.heard[min(self.n - 1, len(self.heard) - 1)]
        if isinstance(h, Exception):
            raise h
        return h

    def close(self):
        self.closed += 1


class FakeMic:
    def __init__(self, n=200):
        self.n, self.flushed = n, 0

    def flush(self):
        self.flushed += 1

    async def frames(self):
        for _ in range(self.n):
            await asyncio.sleep(0)
            yield np.zeros(512, dtype=np.int16)


async def test_the_word_monitor_returns_only_when_the_user_says_something_new():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    a._said_now = ["Prima scalda il latte con il burro e il sale.", "Poi versa la semola a pioggia."]
    a._bi_stt = FakeBi(["Prima scalda il latte con il burro", "versa la semola a pioggia", "semola a pioggia basta"])
    a.mic = FakeMic()
    carry = await asyncio.wait_for(a._monitor_barge_in_words(), 10)
    assert carry and a._bi_stt.n == 3                                       # le prime due volte era solo l'eco, la terza «basta»
    assert a.mic.flushed == 1                                               # parte da zero: le parole che l'utente ha appena detto restano nel microfono, non sono un'interruzione


async def test_one_failed_recognition_does_not_switch_voice_interruption_off_for_good():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    a._said_now = ["Prima scalda il latte."]
    a._bi_stt = FakeBi([RuntimeError("ExtAudioFileOpenURL"), "aspetta basta"])
    a.mic = FakeMic()
    carry = await asyncio.wait_for(a._monitor_barge_in_words(), 10)
    assert carry and a._bi_stt.closed == 1 and a._bi_stt is not False         # sbaglia una volta, riparte, e la volta dopo sente «basta»
    a._bi_stt = FakeBi([RuntimeError("x")])
    a.mic = FakeMic()
    assert await asyncio.wait_for(a._monitor_barge_in_words(), 10) is None and a._bi_stt is not False      # tre errori di fila: per questa risposta lascia perdere, non per sempre


async def test_while_a_document_is_being_written_only_stop_interrupts_not_just_talking():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    a._said_now = ["Certo, lo scrivo con calma."]
    a._tool_busy = True
    a._bi_stt = FakeBi(["no volevo chiederti un'altra cosa", "no volevo chiederti un'altra cosa", "aspetta fermati"])
    a.mic = FakeMic()
    carry = await asyncio.wait_for(a._monitor_barge_in_words(), 10)
    assert carry and a._bi_stt.n == 3


async def test_without_the_helper_the_word_monitor_does_nothing():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    a._bi_stt = False
    assert await a._monitor_barge_in_words() is None


class FakeVoice:
    """Rilevatore di voce finto: dice «voce» dal blocco `start` in poi."""

    def __init__(self, start):
        self.start, self.i = start, 0

    def reset(self):
        self.i = 0

    def prob(self, frame):
        self.i += 1
        return 0.95 if self.i >= self.start else 0.05


def test_the_gap_listener_hears_the_user_only_when_the_speakers_are_silent_and_never_before_she_spoke():
    loud, quiet = np.full(512, 0.1, np.float32), np.zeros(512, np.float32)
    mic = np.zeros(512, dtype=np.int16)
    g = bargein.GapListener(FakeVoice(1))                                  # voce da subito
    assert not any(g.push(mic, quiet) for _ in range(30))                  # Aria non ha ancora detto niente (sta pensando): non e' un'interruzione
    assert not any(g.push(mic, loud) for _ in range(20))                   # parla: l'eco copre tutto, anche se il rilevatore «sente» una voce
    fired = [i for i in range(20) if g.push(mic, quiet)]                   # pausa: respiro di riverbero (4 blocchi) + 4 blocchi di voce
    assert fired and fired[0] == 7
    g.reset()
    assert not any(g.push(mic, None) for _ in range(30))                   # senza sapere cosa suonano le casse non si decide niente
    g2 = bargein.GapListener(FakeVoice(10 ** 6))                           # nessuna voce: silenzio vero
    assert not any(g2.push(mic, loud if i < 10 else quiet) for i in range(60))


async def test_the_monitor_returns_when_the_user_speaks_in_a_pause_of_her_voice():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    a._bi_stt = False                                                       # niente riconoscimento di parole: solo l'ascolto nelle pause
    a.vad = FakeVoice(25)

    class Spk:
        def __init__(self):
            self.i = 0

        def ref_at(self, t, n=512, rate=16000):
            self.i += 1
            return np.full(512, 0.1, np.float32) if self.i < 20 else np.zeros(512, np.float32)       # parla per 20 blocchi, poi una pausa

    a.speaker = Spk()
    a.mic = FakeMic(200)
    carry = await asyncio.wait_for(a._monitor_barge_in_words(), 10)
    assert carry is not None and len(carry) <= 22


def test_sentence_ends_get_a_longer_breath_when_the_speakers_are_on_and_the_tails_of_the_voice_are_trimmed():
    from aria.speech import shape_pause, trim_silence
    x = np.concatenate([np.zeros(8000), (np.sin(np.arange(16000) * 0.1) * 8000), np.zeros(22000)]).astype(np.int16)        # 0,5 s di niente + 1 s di voce + 1,4 s di coda (come Pocket TTS)
    t = trim_silence(x, 16000)
    assert 16000 <= len(t) <= 16000 + 2000 + 3000                          # resta la voce con un respiro di ~40 ms davanti e ~100 ms dietro
    short = shape_pause(x, 16000, "Va bene.")
    long = shape_pause(x, 16000, "Va bene.", min_gap_ms=480)
    assert len(long) - len(short) == int((480 - 300) / 1000 * 16000)       # la pausa dopo il punto passa da 300 a 480 ms
    assert len(shape_pause(x, 16000, "Va bene,", min_gap_ms=480)) == len(shape_pause(x, 16000, "Va bene,"))               # le virgole restano come erano


def test_captions_follow_the_voice_word_by_word_and_only_the_sentence_being_said():
    from aria.audio import Speaker
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    sp = Speaker(rate=16000)
    sp.next_text = "Prima frase di prova, con due parti."                 # 2 s di audio
    sp.play(np.zeros(32000, dtype=np.int16), 16000)
    sp.next_text = "Seconda frase che arriva dopo."                       # altri 2 s
    sp.play(np.zeros(32000, dtype=np.int16), 16000)
    a.speaker = sp
    got = []
    hub._emit = lambda m: got.append(m) if m.get("type") == "transcript" else None
    a._cap_sent = {}
    sp.played_samples = 0
    a._sync_captions()
    assert got and got[0]["text"].startswith("Prima") and len(got[0]["text"]) < len("Prima frase di prova, con due parti.") and got[0]["id"] == 32000
    assert not any(m["text"].startswith("Seconda") for m in got)           # la seconda frase e' pronta ma la voce non c'e' ancora arrivata
    sp.played_samples = 16000                                              # a meta' della prima
    a._sync_captions()
    mid = [m for m in got if m["id"] == 32000][-1]["text"]
    assert 10 < len(mid) < len("Prima frase di prova, con due parti.") and not mid.endswith(" ")
    sp.played_samples = 33000                                              # entrata nella seconda
    a._sync_captions()
    assert [m for m in got if m["id"] == 32000][-1]["text"] == "Prima frase di prova, con due parti."      # la prima e' completa
    assert any(m["text"].startswith("Seconda") for m in got)
    n = len(got)
    a._sync_captions()
    assert len(got) == n                                                   # nulla da aggiungere se la voce non e' avanzata
    sp.stop()
    assert not sp.captions


# ---------------------------------------------------------------- il microfono con l'eco gia' tolto dal Mac (aria-vpmic)
def _fake_helper(tmp_path, frames_before_exit=None, ready=True):
    import os
    import stat
    import sys
    p = tmp_path / "aria-vpmic"
    body = f'''#!{sys.executable}
import os, sys, threading, time
import numpy as np
threading.Thread(target=lambda: (sys.stdin.read(), os._exit(0)), daemon=True).start()
if {ready!r}:
    sys.stdout.buffer.write(b"READY 16000\\n"); sys.stdout.buffer.flush()
else:
    sys.exit(3)
x = (np.arange(512) % 100).astype(np.int16)
n = 0
while True:
    sys.stdout.buffer.write(x.tobytes()); sys.stdout.buffer.flush(); time.sleep(0.005); n += 1
    if {frames_before_exit!r} is not None and n >= {frames_before_exit!r}:
        sys.exit(2)
'''
    p.write_text(body)
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return str(p)


class _PlainMic:
    """Il microfono normale finto: conta quante volte si apre e si chiude (senza scheda audio)."""

    def __init__(self, monkeypatch):
        from aria import audio
        self.opened = self.closed = 0
        me = self

        def start(self_):
            me.opened += 1
            self_.stream = object()

        def close(self_):
            if self_.stream is not None:
                me.closed += 1
            self_.stream = None
        monkeypatch.setattr(audio.Mic, "start_sync", start)
        monkeypatch.setattr(audio.Mic, "close_sync", close)


async def test_the_echo_filter_is_on_only_during_a_conversation_and_the_plain_mic_covers_the_switch(tmp_path, monkeypatch):
    """A riposo il filtro eco del Mac costava ~12 % di un core + ~11 % di coreaudiod di continuo: ora si accende con la conversazione e si spegne alla fine."""
    from aria.audio import Frame, VoiceMic
    plain = _PlainMic(monkeypatch)
    m = VoiceMic(helper=_fake_helper(tmp_path))
    await m.start()
    assert plain.opened == 1 and not m.cleaned and m.proc is None                 # a riposo: solo il microfono normale, nessun programma di supporto
    m.engage()
    got = []
    async for f in m.frames():
        got.append(f)
        if len(got) == 5:
            break
    assert m.cleaned and all(isinstance(f, Frame) and len(f) == 512 and f.dtype == np.int16 and f.adc is None for f in got)
    assert plain.closed == 1                                                       # il filtro manda audio: il microfono normale si chiude (niente doppioni)
    proc = m.proc
    m.release()
    assert not m.cleaned and plain.opened == 2                                    # fine conversazione: torna il microfono normale
    for _ in range(100):
        if proc.poll() is not None:
            break
        await asyncio.sleep(0.05)
    assert proc.poll() is not None                                                 # e il programma di supporto non resta in giro
    m.engage()                                                                    # la conversazione dopo: si riaccende
    async for f in m.frames():
        if m.cleaned:
            break
    assert m.cleaned
    m.close_sync()
    assert not m.cleaned and m.stream is None


async def test_the_clean_mic_falls_back_to_the_normal_one_when_the_helper_is_missing_or_keeps_failing(tmp_path, monkeypatch):
    from aria import audio
    plain = _PlainMic(monkeypatch)
    m = audio.VoiceMic(helper=str(tmp_path / "non-esiste"))
    await m.start()
    m.engage()
    for _ in range(100):
        if m._skip_until:
            break
        await asyncio.sleep(0.02)
    assert m._skip_until and not m.cleaned and m.stream is not None               # niente programma: resta il microfono normale, aperto
    m2 = audio.VoiceMic(helper=_fake_helper(tmp_path, ready=False))             # parte e subito esce (permesso negato, macOS vecchio...)
    await m2.start()
    m2.engage()
    for _ in range(300):
        if m2._skip_until:
            break
        await asyncio.sleep(0.02)
    assert m2._skip_until and not m2.cleaned and m2.stream is not None
    n = plain.opened
    m2.engage()                                                                   # poco dopo: non ritenta (non si martella il sistema audio)
    await asyncio.sleep(0.2)
    assert m2.proc is None and plain.opened == n


class CleanMic(FakeMic):
    cleaned = True


async def test_with_the_echo_removed_the_monitor_recognises_only_when_there_is_voice_and_sooner():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    a._said_now = ["Prima scalda il latte con il burro e il sale."]
    a._bi_stt = FakeBi(["aspetta basta"])
    a.vad = FakeVoice(10 ** 6)                                              # nessuna voce: silenzio vero
    a.mic = CleanMic(120)
    assert await asyncio.wait_for(a._monitor_barge_in_words(), 10) is None and a._bi_stt.n == 0       # senza voce non si chiama nemmeno il riconoscimento
    a.vad = FakeVoice(30)                                                   # l'utente comincia a parlare al blocco 30
    a._bi_stt = FakeBi(["aspetta basta"])
    a.mic = CleanMic(200)
    carry = await asyncio.wait_for(a._monitor_barge_in_words(), 10)
    assert carry and a._bi_stt.n == 1                                       # la prima volta che c'e' voce basta: niente attesa delle pause, niente filtro nostro


async def test_a_helper_that_says_ready_but_sends_no_audio_makes_the_mic_fall_back_and_stay_there_for_a_while(tmp_path, monkeypatch):
    import stat
    import sys
    from aria import audio
    p = tmp_path / "aria-vpmic"
    p.write_text(f"#!{sys.executable}\nimport sys, time\nsys.stdout.buffer.write(b'READY 16000\\n'); sys.stdout.buffer.flush()\ntime.sleep(30)\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    plain = _PlainMic(monkeypatch)
    m = audio.VoiceMic(helper=str(p))
    m.first_frame_timeout = 0.3
    await m.start()
    m.engage()
    for _ in range(300):
        if m._skip_until:
            break
        await asyncio.sleep(0.05)
    assert m._skip_until and not m.cleaned and m.stream is not None                # (due tentativi senza audio e poi microfono normale)
    n = plain.opened
    m.release()
    m.engage()                                                                      # la conversazione dopo: per ora si resta sul microfono normale, senza ritentare
    await asyncio.sleep(0.2)
    assert m.proc is None


async def test_the_audio_watchdog_slows_down_instead_of_reopening_every_seven_seconds_forever(monkeypatch):
    import time as _t
    from aria import audio
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    sleeps, reinit = [], []
    real_sleep = asyncio.sleep

    async def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) > 14:
            raise asyncio.CancelledError
        await real_sleep(0)
    monkeypatch.setattr("aria.conversation.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(audio, "default_devices", lambda: (1, 2))
    monkeypatch.setattr(audio, "reinit_audio", lambda mic, spk: reinit.append(1))

    class M:
        last_frame = _t.monotonic() - 100.0                                  # il microfono non manda niente da sempre

        def start_sync(self): ...
    a.mic = M()
    a.speaker.start = lambda: None
    a.speaker.playing = False
    try:
        await a._audio_watchdog()
    except asyncio.CancelledError:
        pass
    assert len(reinit) >= 3 and max(sleeps) >= 20.0                          # dopo qualche tentativo aspetta sempre di piu'


def test_with_the_echo_removed_one_real_word_or_two_short_ones_are_enough_to_interrupt():
    said = "Scrivi pure quello che ti viene in mente, e ci penso io."
    assert bargein.interruption("Indicami", said) is None                                   # con l'eco in mezzo una parola sola non basta
    assert bargein.interruption("Indicami", said, clean=True) == "talk"                     # ... con il microfono pulito si'
    assert bargein.interruption("no scusa", said, clean=True) == "talk"
    assert bargein.interruption("ok", said, clean=True) is None and bargein.interruption("eh", said, clean=True) is None
    assert bargein.interruption("scrivi pure quello che", said, clean=True) is None         # le parole di Aria (eco residuo) non interrompono


async def test_aria_switches_the_echo_filter_on_for_a_conversation_and_off_when_it_goes_back_to_waiting():
    a, hub, llm, tts, spk, tools = build(utterance(), ["hey aria"])
    calls = []

    class M(FakeMic):
        def engage(self):
            calls.append("on")

        def release(self):
            calls.append("off")
    a.mic = M()
    a._mic_filter(True)
    a._mic_filter(False)
    assert calls == ["on", "off"]
    a.mic = FakeMic()                                                              # (un microfono senza filtro, come nei test o col collaudo da file: non succede niente)
    a._mic_filter(True)
    a._mic_filter(False)


def test_the_speaker_output_runs_only_while_aria_speaks(monkeypatch):
    """Un'uscita audio sempre aperta che suona silenzio tiene sveglio l'audio del Mac (coreaudiod ~7 % di un core): si ferma dopo qualche secondo e riparte con la frase dopo."""
    import sys
    import types
    from aria import audio

    class CallbackStop(Exception):
        pass

    class FakeStream:
        def __init__(self, **kw):
            self.cb, self.active, self.starts, self.stops = kw["callback"], False, 0, 0

        def start(self):
            self.active = True
            self.starts += 1

        def stop(self):
            self.active = False
            self.stops += 1

        def close(self):
            self.active = False
    fake = types.SimpleNamespace(OutputStream=FakeStream, CallbackStop=CallbackStop)
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(audio, "resolve_device", lambda spec, kind: None)

    def run_blocks(sp, n):
        for i in range(n):
            if not sp.stream.active:
                break
            out = np.zeros((512, 1), dtype=np.int16)
            try:
                sp.stream.cb(out, 512, types.SimpleNamespace(outputBufferDacTime=float(i)), None)
            except CallbackStop:
                sp.stream.active = False
    sp = audio.Speaker(None, 16000, 1.0)
    sp.idle_stop_s = 1.0
    sp.start()
    assert sp.stream.active
    run_blocks(sp, 100)                                                         # ~3 s di silenzio
    assert not sp.stream.active                                                 # si e' fermata da sola
    sp.play(np.full(4000, 1000, dtype=np.int16), 16000)
    assert sp.stream.active and sp.stream.starts == 2                           # la frase la fa ripartire
    run_blocks(sp, 8)
    assert sp.played_samples == 4000
    run_blocks(sp, 100)
    assert not sp.stream.active
    sp.play(np.full(100, 1000, dtype=np.int16), 16000)
    assert sp.stream.active


# ---- dal log del 14 ottobre (01:11-01:12): stanza in silenzio, Aria si fermava da sola perche' il microfono pulito lasciava un residuo della sua voce capito male
SAID_1 = "Se non sai da dove cominciare, possiamo parlarne della musica che hai scritto, oppure di qualunque cosa ti passi per la testa in questo momento."
SAID_2 = "Vedendo queste immagini così vive, potresti rendere ancora più palpabile quel contrasto tra il desiderio enorme e la resistenza iniziale."
SAID_3 = "Se volessi affinare ulteriormente, potresti provare a rendere più immediato il passaggio dal sogno alla realtà che vuoi costruire."


def test_her_own_voice_misheard_in_the_clean_mic_is_not_an_interruption():
    assert bargein.interruption("possiamo farla", SAID_1, clean=True) is None            # «parlarne» capito «farla»
    assert bargein.interruption("Casto tra il desiderio e", SAID_2, clean=True) is None  # «contrasto» capito «casto»
    assert bargein.interruption("Se volessi finale", SAID_3, clean=True) is None         # «affinare» capito «finale»
    assert bargein.interruption("Indicami", SAID_1, clean=True) == "talk"                # una parola vera, senza parole sue intorno: si'
    assert bargein.interruption("basta", SAID_2, clean=True) == "stop"                   # «basta» vale sempre
    assert bargein.interruption("possiamo parlarne ma indicami dove compare avs", SAID_1, clean=True) == "talk"       # tre parole nuove vere: e' l'utente anche se c'e' un po' di eco in mezzo
    assert bargein.interruption("Indicami dove", SAID_1, clean=True) == "talk"          # «dove» c'e' anche nella frase di Aria, ma una paroletta non prova che sia eco


def test_a_weak_decision_needs_the_same_word_twice_in_a_row():
    d = bargein.Interrupter()
    assert d.feed("Indica", "Poi versa la semola a pioggia.", clean=True) is None         # la prima volta si aspetta ~0,2 s
    assert d.feed("Indicami", "Poi versa la semola a pioggia.", clean=True) == "talk"     # ... e la parola c'e' ancora (anche piu' lunga): e' lui
    d = bargein.Interrupter()
    assert d.feed("farla", SAID_1, clean=True) is None and d.feed("parlato", SAID_1, clean=True) is None      # un residuo di eco cambia a ogni finestra
    d = bargein.Interrupter()
    assert d.feed("aspetta", SAID_1, clean=True) == "stop"                                # i comandi di stop non aspettano
    d = bargein.Interrupter()
    assert d.feed("no volevo chiederti un'altra cosa", "Poi versa la semola.", clean=True) == "talk"          # tante parole: subito


async def test_the_monitor_ignores_a_run_of_misheard_echo_windows_and_stops_for_a_repeated_word():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    a._said_now = [SAID_1]
    a.vad = FakeVoice(10)
    a._bi_stt = FakeBi(["possiamo parlarne", "possiamo farla", "farla della musica", "possiamo parlarne della musica"])
    a.mic = CleanMic(120)
    assert await asyncio.wait_for(a._monitor_barge_in_words(), 10) is None and a._bi_stt.n >= 4         # nessuna interruzione: era solo la sua voce
    a._bi_stt = FakeBi(["Indicami", "Indicami adesso"])
    a.vad = FakeVoice(10)
    a.mic = CleanMic(200)
    carry = await asyncio.wait_for(a._monitor_barge_in_words(), 10)
    assert carry and a._bi_stt.n == 2                                                      # dopo due finestre, non dopo una


async def test_the_audio_watchdog_does_not_forget_its_failures_just_because_a_reopen_makes_the_mic_look_alive_for_a_few_seconds(monkeypatch):
    """Dal log del 14 ottobre: una riapertura ogni 6,3 s per 53 minuti. start_sync() mette last_frame = «adesso» per finta: il microfono ancora muto sembrava sano
    per un giro di controllo, il conteggio dei guasti tornava a zero e l'attesa crescente non scattava mai."""
    import time as _t
    from aria import audio, power
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    sleeps, reinit = [], []
    real_sleep = asyncio.sleep

    async def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) > 24:
            raise asyncio.CancelledError
        await real_sleep(0)
    monkeypatch.setattr("aria.conversation.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(audio, "default_devices", lambda: (1, 2))
    monkeypatch.setattr(audio, "reinit_audio", lambda mic, spk: reinit.append(1))
    monkeypatch.setattr(power, "display_asleep", lambda: False)

    class M:
        n = 0

        @property
        def last_frame(self):                                                 # un giro muto, un giro «sano» (appena riaperto), e cosi' via
            M.n += 1
            return _t.monotonic() - (100.0 if M.n % 2 else 0.0)

        def start_sync(self): ...
    a.mic = M()
    a.speaker.start = lambda: None
    a.speaker.playing = False
    try:
        await a._audio_watchdog()
    except asyncio.CancelledError:
        pass
    assert len(reinit) >= 3 and max(sleeps) >= 40.0                           # le attese crescono (10, 20, 40...) invece di restare a 3 secondi


async def test_with_the_screen_off_a_silent_mic_means_the_mac_is_asleep_so_she_closes_it_and_reopens_when_the_screen_is_back(monkeypatch):
    """Risvegli notturni di macOS (DarkWake) e Mac chiuso: il microfono non manda audio ed e' normale. Riaprirlo ogni 6 secondi accendeva e spegneva l'indicatore del microfono
    e teneva sveglio il Mac (MenuBarAgent al 100 % fino al riavvio)."""
    import time as _t
    from aria import audio, power
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    state = {"dark": True}
    monkeypatch.setattr(audio, "default_devices", lambda: (1, 2))
    reinit, calls = [], []
    monkeypatch.setattr(audio, "reinit_audio", lambda mic, spk: reinit.append(1))
    monkeypatch.setattr(power, "display_asleep", lambda: state["dark"])
    monkeypatch.setattr(power, "on_battery", lambda: False)                    # all'alimentatore: la regola della batteria non c'entra

    class M:
        last_frame = _t.monotonic() - 100.0                                    # muto da sempre

        def close_sync(self):
            calls.append("chiuso")

        def start_sync(self):
            calls.append("aperto")
    a.mic = M()
    a.speaker.start = lambda: None
    a.speaker.playing = False
    real_sleep = asyncio.sleep
    monkeypatch.setattr("aria.conversation.asyncio.sleep", lambda s: real_sleep(0.01))
    w = asyncio.create_task(a._audio_watchdog())
    p = asyncio.create_task(a._power_saver(every=0.01, after=0.05))
    for _ in range(300):
        await real_sleep(0.01)
        if a._paused:
            break
    assert a._paused and a._pause_why == "sleep" and calls == ["chiuso"] and not reinit      # chiuso, e non riaperto per quindici minuti
    await real_sleep(0.3)
    assert a._paused and calls == ["chiuso"] and not reinit                                  # (la regola della batteria non lo riapre: e' ancora tutto buio)
    state["dark"] = False                                                                    # lo schermo si riaccende
    for _ in range(300):
        await real_sleep(0.01)
        if not a._paused:
            break
    assert not a._paused and calls == ["chiuso", "aperto"]
    for t in (w, p):
        t.cancel()
    await asyncio.gather(w, p, return_exceptions=True)
