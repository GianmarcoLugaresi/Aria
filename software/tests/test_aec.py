"""Cancellazione dell'eco: la voce di Aria che rientra nel microfono si sottrae, cosi' si sente l'utente che la interrompe."""
import asyncio

import numpy as np
import pytest

from aria.aec import EchoCanceller
from aria.audio import Frame, Speaker
from tests.test_conversation import build, utterance

B = 512


def speech_like(n, seed=0):
    """Un segnale colorato e a «parole» (ampiezza che varia), come la voce: piu' realistico del rumore bianco."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    x = np.convolve(x, np.hanning(24), mode="same")
    env = np.repeat(rng.uniform(0.05, 1.0, n // 3000 + 1), 3000)[:n]
    return (x * env * 0.2).astype(np.float32)


def room(ref, delay=2400, level=0.2, seed=1):
    rng = np.random.default_rng(seed)
    ir = np.concatenate([np.zeros(delay), rng.standard_normal(1500) * np.exp(-np.arange(1500) / 500)])
    ir /= np.abs(ir).sum() * 0.8
    return (np.tanh(np.convolve(ref, ir)[:len(ref)] * 2) / 2 * level).astype(np.float32)


def db(x):
    return 20 * np.log10(np.sqrt(np.mean(np.square(x))) + 1e-12)


def run(aec, mic, ref):
    out = np.zeros(len(mic) // B * B, dtype=np.float32)
    for k in range(len(out) // B):
        out[k * B:(k + 1) * B] = aec.process(mic[k * B:(k + 1) * B], ref[k * B:(k + 1) * B])
    return out


def test_the_filter_learns_the_room_and_removes_most_of_the_echo():
    ref = speech_like(16000 * 14)
    mic = room(ref)
    aec = EchoCanceller(B, 16)
    out = run(aec, mic, ref)
    late = slice(len(out) // 2, None)
    assert db(mic[late]) - db(out[late]) > 10                                     # almeno 10 dB di eco in meno (nel simulatore, con distorsione delle casse, ~15)
    assert aec.resets == 0


def test_the_users_voice_survives_and_the_trained_filter_is_kept_between_replies():
    ref = speech_like(16000 * 14)
    mic = room(ref)
    aec = EchoCanceller(B, 16)
    run(aec, mic, ref)
    aec.soft_reset()                                                                # nuova risposta: la storia e' vecchia, il filtro (la stanza) no
    ref2 = speech_like(16000 * 3, seed=3)
    echo2 = room(ref2)
    user = speech_like(16000 * 3, seed=7)
    user = user * (np.sqrt(np.mean(echo2 ** 2)) / np.sqrt(np.mean(user ** 2)))      # la voce dell'utente, alla pari con l'eco
    mic2 = echo2 + user
    out = run(aec, mic2, ref2)
    n = len(out)
    corr_raw = np.corrcoef(mic2[:n][16000:], user[:n][16000:])[0, 1]
    corr_clean = np.corrcoef(out[16000:], user[:n][16000:])[0, 1]
    assert corr_clean > corr_raw + 0.15 and corr_clean > 0.8                       # dopo il filtro quasi solo la voce dell'utente


def test_a_diverging_filter_resets_instead_of_shouting():
    aec = EchoCanceller(B, 4, mu=3.0)                                               # passo esagerato: diverge
    ref = speech_like(16000 * 6)
    out = run(aec, room(ref), ref)
    assert np.isfinite(out).all() and db(out) < db(room(ref)) + 12                  # non sale mai oltre l'ingresso (si azzera quando peggiora)


class FakeStream:
    pass


def make_speaker(rate=24000):
    sp = Speaker(rate=rate)
    return sp


def feed(sp, seconds, freq=300.0, t0=1000.0, block=512):
    """Simula i blocchi di uscita: un tono continuo, ogni blocco con il suo orario di uscita dalle casse."""
    total = int(seconds * sp.rate)
    n = 0
    while n < total:
        idx = np.arange(sp.out_count, sp.out_count + block)
        out = (np.sin(2 * np.pi * freq * idx / sp.rate) * 12000).astype(np.int16)
        sp.blocks.append((t0 + sp.out_count / sp.rate, sp.out_count))
        sp.ring[idx % len(sp.ring)] = out
        sp.out_count += block
        n += block


def test_the_speaker_tells_what_it_played_at_a_given_time_even_at_another_rate():
    sp = make_speaker(24000)
    feed(sp, 3.0, freq=300.0)
    t = 1000.0 + 1.5                                                                # a 1,5 s dall'inizio
    ref = sp.ref_at(t, 512, 16000)
    expect = np.sin(2 * np.pi * 300.0 * (1.5 + np.arange(512) / 16000)) * 12000 / 32768
    assert ref is not None and np.max(np.abs(ref - expect)) < 0.02                  # lo stesso tono, ricampionato a 16 kHz e al momento giusto
    assert sp.ref_at(1000.0 + 5.0, 512, 16000) is None and sp.ref_at(None) is None  # il futuro non c'e'
    assert make_speaker().ref_at(1000.0) is None


def test_the_speaker_knows_which_sentence_is_audible_now():
    sp = make_speaker(16000)
    for text, secs in (("prima frase", 2.0), ("seconda frase", 2.0), ("terza frase", 2.0)):
        sp.next_text = text
        sp.play(np.zeros(int(secs * 16000), dtype=np.int16), 16000)
    sp.played_samples = int(2.5 * 16000)                                            # siamo a meta' della seconda
    assert sp.recent_text(0.4) == "seconda frase"                                   # (la terza e' ancora in coda e non e' ancora nell'aria)
    assert "prima frase" in sp.recent_text(2.4) and "seconda frase" in sp.recent_text(2.4)
    sp.stop()
    assert sp.recent_text() == ""


class EchoSpeaker:
    """Casse finte che dicono cosa suonano: la stessa cosa che il microfono finto risente come eco."""
    rate = 16000

    def __init__(self, ref):
        self.ref, self.played, self.level = ref, [], 0.0

    def ref_at(self, t, n=512, rate=16000):
        i = int(round(t * 16000))
        return self.ref[i:i + n] if t is not None and 0 <= i and i + n <= len(self.ref) else None

    def recent_text(self, back_s=2.4):
        return "Per prima cosa porta il latte a bollore"

    def start(self): pass
    def close(self): pass
    def play(self, pcm, sr): pass
    def stop(self): pass


async def test_the_monitor_hears_the_user_through_the_cleaned_audio_not_the_echo():
    a, hub, llm, tts, spk, tools = build(utterance(), ["ciao"])
    ref = speech_like(16000 * 30)
    mic = room(ref, delay=1600)
    a.speaker = EchoSpeaker(ref)
    heard_levels = []

    class Bi:
        n = 0

        async def transcribe(self, pcm, sr):
            self.n += 1
            heard_levels.append(db(pcm.astype(np.float32) / 32768.0))
            return "aspetta fermati" if self.n > 8 else ""

        def close(self): pass

    a._bi_stt = Bi()

    class Mic:
        def flush(self): pass

        async def frames(self):
            for k in range(len(mic) // B):
                await asyncio.sleep(0)
                f = (mic[k * B:(k + 1) * B] * 32768).astype(np.int16).view(Frame)
                f.adc = k * B / 16000
                yield f
    a.mic = Mic()
    a._said_now = ["Per prima cosa porta il latte a bollore"]
    carry = await asyncio.wait_for(a._monitor_barge_in_words(), 60)
    assert carry                                                                    # ha riconosciuto «aspetta fermati»
    raw_db = db(mic[: 16000 * 4])
    assert min(heard_levels[4:]) < raw_db - 8                                       # a riconoscimento arriva audio dove l'eco e' molto piu' bassa dell'ingresso
