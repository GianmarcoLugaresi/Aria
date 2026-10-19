import numpy as np

from aria.vad import FRAME, Endpointer, EnergyVAD


def run(ep, probs):
    return [ep.push(p) for p in probs]


def test_start_and_end():
    ep = Endpointer(32, 96, 750, 250, 20, 6)
    ev = run(ep, [0] * 5 + [0.9] * 20 + [0.0] * 30)
    assert "start" in ev and "end" in ev and ev.index("start") < ev.index("end")


def test_click_is_ignored_and_timeout_fires():
    ep = Endpointer(32, 96, 320, 400, 20, 1.0)
    ev = run(ep, [0.9] * 4 + [0.0] * 40)                  # 128 ms di rumore: troppo breve per essere una frase
    assert "start" in ev and "end" not in ev
    assert "timeout" in run(Endpointer(32, 96, 750, 250, 20, 1.0), [0.0] * 40)


def test_max_utterance():
    ep = Endpointer(32, 96, 750, 250, 1.0, 6)
    assert "end" in run(ep, [0.9] * 100)


def test_energy_vad_separates_speech_from_noise():
    rng = np.random.default_rng(0)
    vad = EnergyVAD()
    noise = lambda a: (rng.standard_normal(FRAME) * a).astype(np.int16)
    for _ in range(40):
        p_quiet = vad.prob(noise(40))
    p_voice = max(vad.prob(noise(4000)) for _ in range(5))
    assert p_quiet < 0.3 and p_voice > 0.8


def test_the_light_silero_for_the_wake_word_hears_speech_and_not_silence_and_keeps_its_memory_per_block():
    """Il Silero su un solo thread (onnxruntime, modello di faster-whisper) per l'attesa di «hey aria»: costa ~1,6 % di un core invece di 11-14 %."""
    import pytest
    from aria.vad import OnnxSileroVAD, _silero_onnx_path, make_idle_vad
    if _silero_onnx_path() is None:
        pytest.skip("faster-whisper (con il modello ONNX) non installato qui")
    v = OnnxSileroVAD()
    rng = np.random.default_rng(0)
    quiet = [v.prob((rng.standard_normal(FRAME) * 15).astype(np.int16)) for _ in range(30)]
    assert max(quiet) < 0.2
    t = np.arange(FRAME * 40) / 16000                                                   # una «voce» finta: vocale con armoniche e un po' di modulazione
    voice = (sum(np.sin(2 * np.pi * f * t) / k for k, f in enumerate((180, 360, 540, 720, 900), 1)) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t)) * 6000).astype(np.int16)
    v.reset()
    assert v.ctx.shape == (64,) and float(np.abs(v.h).sum()) == 0.0
    ps = [v.prob(voice[i:i + FRAME]) for i in range(0, len(voice), FRAME)]
    assert np.isfinite(ps).all() and 0.0 <= min(ps) and max(ps) <= 1.0
    assert make_idle_vad("energy") is None and isinstance(make_idle_vad("auto"), OnnxSileroVAD)
