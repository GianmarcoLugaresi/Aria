"""Confronta i motori di dettatura sulle registrazioni VERE dell'utente (le ultime 40 frasi salvate in ~/.aria/utterances).

    python scripts/stt_real.py [--engines turbo_q4,turbo_fp16,large_v3] [--dir ~/.aria/utterances]

Non c'e' la frase giusta (il nome del file e' quello che aveva capito Aria allora): si guardano i testi uno accanto all'altro e dove i motori
sono d'accordo, quasi sempre e' giusto. Stampa anche tempo e quante frasi sono state «scartate» (vuote).
"""
import argparse
import asyncio
import glob
import os
import sys
import time
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aria import stt as S                                      # noqa: E402

MODELS = {"turbo_q4": "mlx-community/whisper-large-v3-turbo-q4", "turbo_fp16": "mlx-community/whisper-large-v3-turbo", "large_v3": "mlx-community/whisper-large-v3-mlx",
          "small": "mlx-community/whisper-small-mlx-q4"}


def load(path):
    with wave.open(path) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return pcm, w.getframerate()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default="turbo_q4,turbo_fp16,large_v3")
    ap.add_argument("--dir", default=os.path.expanduser("~/.aria/utterances"))
    ap.add_argument("--gain", type=float, default=1.0, help="moltiplica il volume prima di dettare (prova di un volume piu' alto)")
    args = ap.parse_args()
    files = sorted(glob.glob(os.path.join(args.dir, "*.wav")))
    names = args.engines.split(",")
    out = {n: [] for n in names}
    times = {n: 0.0 for n in names}
    for n in names:
        stt = S.MLXWhisperSTT({"model": MODELS[n], "prompt": False})
        await stt.warmup()
        for f in files:
            pcm, sr = load(f)
            if args.gain != 1.0:
                pcm = np.clip(pcm.astype(np.float32) * args.gain, -32768, 32767).astype(np.int16)
            t = time.time()
            out[n].append((await stt.transcribe(pcm, sr)).strip())
            times[n] += time.time() - t
        del stt
    for i, f in enumerate(files):
        pcm, sr = load(f)
        rms = 20 * np.log10(max(1e-6, float(np.sqrt(np.mean((pcm.astype(np.float32) / 32768) ** 2)))))
        print(f"\n[{os.path.basename(f)[:40]}]  {len(pcm) / sr:.1f}s  rms {rms:.0f} dB")
        for n in names:
            print(f"   {n:11} {out[n][i]}")
    print("\nTEMPO TOTALE per", len(files), "frasi:", {n: round(t, 1) for n, t in times.items()}, "| frasi vuote:", {n: sum(1 for x in out[n] if not x) for n in names})


asyncio.run(main())
