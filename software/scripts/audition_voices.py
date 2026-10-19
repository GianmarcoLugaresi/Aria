"""Genera la stessa frase con piu' voci/motori e salva i WAV: ascoltali e scegli all'orecchio.

    python scripts/audition_voices.py --piper models/it_IT-paola-medium.onnx --kokoro-dir models --out ~/aria_voci
    python scripts/audition_voices.py --openai http://localhost:8082/v1 --openai-voice if_sara     # server TTS gia' avviato
"""
import argparse
import asyncio
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aria.tts import KokoroTTS, OpenAITTS, PiperTTS      # noqa: E402

FRASI = [
    "Ciao! Eccomi. Dimmi pure, ti ascolto.",
    "Domani a Roma coperto, tra i nove e i diciannove gradi. Una giacca leggera ti basta.",
    "Mh, questa non me la ricordo. Aspetta che guardo.",
    "Uff, riunioni dalle nove alle sei? Poverino. Stasera ti meriti una cena decente.",
]


def save(path, pcm, sr):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.asarray(pcm, dtype=np.int16).tobytes())


async def run(label, engine, out):
    for i, f in enumerate(FRASI, 1):
        try:
            pcm, sr = await engine.synthesize(f)
        except Exception as e:                        # noqa: BLE001
            print(f"  {label}: saltato ({e})")
            return
        p = os.path.join(out, f"{label}_{i}.wav")
        save(p, pcm, sr)
    print(f"  {label}: ok -> {out}/{label}_*.wav")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.expanduser("~/aria_voci"))
    ap.add_argument("--piper")
    ap.add_argument("--kokoro-dir")
    ap.add_argument("--kokoro-voices", default="if_sara,im_nicola")
    ap.add_argument("--openai")
    ap.add_argument("--openai-voice", default="alloy")
    ap.add_argument("--openai-model", default="tts-1")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    if args.piper:
        await run("piper_" + os.path.basename(args.piper).split(".")[0], PiperTTS({"model_path": args.piper}), args.out)
    if args.kokoro_dir:
        for v in args.kokoro_voices.split(","):
            await run(f"kokoro_{v}", KokoroTTS({"model_dir": args.kokoro_dir, "voice": v}), args.out)
    if args.openai:
        await run(f"server_{args.openai_voice}", OpenAITTS({"base_url": args.openai, "voice": args.openai_voice, "model": args.openai_model}), args.out)
    print("\nAscolta con:  open " + args.out)


asyncio.run(main())
