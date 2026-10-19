"""Confronta i motori di dettatura su frasi brevi italiane, pulite e degradate (volume basso, rumore).

    python scripts/bench_stt.py [--engines small_vecchio,small_nuovo,turbo_q4]

Le frasi sono sintetizzate con `say` (voci italiane di macOS): non e' parlato vero, ma il confronto tra motori e' significativo.
Con audio veri: metti dei WAV 16 kHz mono in una cartella e usa --wavs CARTELLA (il nome del file e' la frase attesa).
"""
import argparse
import asyncio
import glob
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PHRASES = [
    "come va", "parlami un po' di te", "che tempo fa domani a Roma", "mettimi un timer per la pasta",
    "ho mangiato una piadina con il salmone affumicato e il formaggio", "continuo a parlare per provare il microfono",
    "vorrei sapere come funziona la fotosintesi", "cosa ne pensi della musica classica", "sono stanchissimo oggi riunioni tutto il giorno",
    "mi consigli un film da vedere stasera", "ciao aria come stai", "prova a parlare di nuovo", "mi chiamo Mario e domani ho un esame",
    "dimmi una barzelletta", "che ore sono", "raccontami una storia", "non capisco cosa mi stai dicendo", "domani vado a Milano in treno",
]
VOICES = ["pocket:lola", "pocket:vera", "pocket:giovanni", "say:Alice", "pocket:eve", "pocket:paul"]   # voci credibili: le altre voci di macOS sono troppo sintetiche


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s).split()


def wer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)], len(r)


_POCKET = {}


def say_pcm(text, voice):
    kind, _, name = voice.partition(":")
    if kind == "pocket":
        from pocket_tts import TTSModel
        if "m" not in _POCKET:
            _POCKET["m"] = TTSModel.load_model(language="italian")
        m = _POCKET["m"]
        st = _POCKET.setdefault(name, m.get_state_for_audio_prompt(name))
        a = m.generate_audio(st, text + " ").detach().cpu().numpy().astype(np.float32).squeeze()
        n = int(len(a) * 16000 / m.sample_rate)
        return (np.clip(np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a), -1, 1) * 32767).astype(np.int16)
    voice = name
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "u.wav")
        subprocess.run(["say", "-v", voice, "-o", p, "--file-format=WAVE", "--data-format=LEI16@16000", text], check=True, timeout=40)
        with wave.open(p) as w:
            return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def degrade(pcm, kind, rng):
    x = pcm.astype(np.float32) / 32768.0
    sil = np.zeros(int(0.35 * 16000), np.float32)
    x = np.concatenate([sil, x, sil])
    if kind == "pulito":
        return (x * 32767).astype(np.int16)
    white = rng.standard_normal(len(x)).astype(np.float32)
    pink = np.convolve(white, np.ones(8) / 8, mode="same") * 2.0                  # rumore "di stanza" (passa-basso)
    p_sig = float(np.mean(x ** 2)) + 1e-9
    if kind == "volume basso":                                                  # microfono basso: -26 dB, rumore di fondo costante
        x = x * 0.05
        noise = pink * 0.0016
    else:                                                                        # "rumoroso": SNR ~8 dB
        noise = pink * np.sqrt(p_sig / (10 ** 0.8)) / (np.std(pink) + 1e-9)
    return (np.clip(x + noise, -1, 1) * 32767).astype(np.int16)


def engines(names):
    from aria import stt as S
    out = {}
    for n in names:
        if n == "small_vecchio":                                                 # com'era: greedy, nessuna normalizzazione
            e = S.FasterWhisperSTT({"model": "small", "compute_type": "int8", "beam_size": 1})
            e._run = lambda pcm, e=e: _old(e, pcm)
            out[n] = e
        elif n == "small_nuovo":
            out[n] = S.FasterWhisperSTT({"model": "small", "compute_type": "int8", "beam_size": 5})
        elif n == "turbo_q4":
            out[n] = S.MLXWhisperSTT({"model": "mlx-community/whisper-large-v3-turbo-q4"})
        elif n == "base_mlx":
            out[n] = S.MLXWhisperSTT({"model": "mlx-community/whisper-base-mlx", "prompt": False})
        elif n == "small_q4_mlx":                                # versione "Leggera" dell'app
            out[n] = S.MLXWhisperSTT({"model": "mlx-community/whisper-small-mlx-q4", "prompt": False})
        elif n == "large_v3":                                   # versione "Pesante" dell'app (3 GB da scaricare)
            out[n] = S.MLXWhisperSTT({"model": "mlx-community/whisper-large-v3-mlx", "prompt": False})
        elif n == "turbo_q4_senza_prompt":
            out[n] = S.MLXWhisperSTT({"model": "mlx-community/whisper-large-v3-turbo-q4", "prompt": False})
        elif n == "turbo_fp16":
            out[n] = S.MLXWhisperSTT({"model": "mlx-community/whisper-large-v3-turbo"})
    return out


def _old(e, pcm):
    m = e._load()
    segs, _ = m.transcribe(pcm.astype(np.float32) / 32768.0, language="it", beam_size=1, vad_filter=False,
                           condition_on_previous_text=False, temperature=0.0)
    return " ".join(s.text.strip() for s in segs).strip()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default="small_vecchio,small_nuovo,turbo_q4")
    ap.add_argument("--wavs")
    args = ap.parse_args()
    rng = np.random.default_rng(3)
    cases = []
    if args.wavs:
        for p in sorted(glob.glob(os.path.join(args.wavs, "*.wav"))):
            with wave.open(p) as w:
                cases.append(("reale", os.path.basename(p)[:-4].replace("_", " "), np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)))
    else:
        for i, ph in enumerate(PHRASES):
            base = say_pcm(ph, VOICES[i % len(VOICES)])
            for kind in ("pulito", "volume basso", "rumoroso"):
                cases.append((kind, ph, degrade(base, kind, rng)))
    E = engines(args.engines.split(","))
    for name, e in E.items():
        if hasattr(e, "warmup"):
            await e.warmup()
        else:
            e._load()
    print(f"{len(cases)} frasi\n")
    res = {n: {} for n in E}
    for name, e in E.items():
        for kind, ph, pcm in cases:
            t0 = time.time()
            hyp = await e.transcribe(pcm, 16000)
            dt = time.time() - t0
            errs, tot = wer(ph, hyp)
            r = res[name].setdefault(kind, [0, 0, 0.0, 0])
            r[0] += errs; r[1] += tot; r[2] += dt; r[3] += 1
            if args.wavs or errs > max(1, tot // 3):
                print(f"  [{name:13s}|{kind:12s}] atteso: {ph!r:60s} sentito: {hyp!r}")
    print("\nERRORE SULLE PAROLE (più basso = meglio)  e tempo medio per frase")
    kinds = sorted({k for r in res.values() for k in r})
    print(f"{'motore':16s}" + "".join(f"{k:>22s}" for k in kinds))
    for n in E:
        print(f"{n:16s}" + "".join(f"{100 * res[n][k][0] / res[n][k][1]:>14.0f}%  {res[n][k][2] / res[n][k][3]:4.2f}s " for k in kinds if k in res[n]))


if __name__ == "__main__":
    asyncio.run(main())
