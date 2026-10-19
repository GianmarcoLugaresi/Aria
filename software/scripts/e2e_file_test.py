"""Prova end-to-end con modelli VERI e audio da file (niente microfono, niente altoparlante).

Genera con `say` la frase "Ciao Aria, <domanda>", la fa "ascoltare" ad Aria (wake in modalità stt),
e misura i tempi: riconoscimento, primo testo dell'LLM, primo audio della voce, totale.

    python scripts/e2e_file_test.py --config ~/Library/Application\\ Support/Aria/config.yaml "che ore sono?"
"""
import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import time
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aria import config as cfgmod                       # noqa: E402
from aria.conversation import Aria                      # noqa: E402
from aria.main import build, factory, warmup            # noqa: E402
from aria.state import Hub                              # noqa: E402
from aria.tools import Tools                            # noqa: E402
from aria.vad import make_vad                           # noqa: E402


def say_wav(text: str) -> np.ndarray:
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "u.wav")
        subprocess.run(["say", "-v", "Alice", "-o", p, "--file-format=WAVE", "--data-format=LEI16@16000", text], check=True)
        with wave.open(p) as w:
            return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


class FileMic:
    def __init__(self, pcm: np.ndarray):
        pad = np.zeros(16000 // 2, dtype=np.int16)
        self.pcm = np.concatenate([pad, pcm, np.zeros(16000 * 3, dtype=np.int16)])
        self.i = 0

    async def start(self): pass
    async def stop(self): pass
    def flush(self): pass

    async def frames(self):
        while True:
            await asyncio.sleep(0)
            if self.i + 512 <= len(self.pcm):
                f = self.pcm[self.i:self.i + 512]
                self.i += 512
            else:
                f = np.zeros(512, dtype=np.int16)
            yield f


class FileSpeaker:
    def __init__(self):
        self.chunks, self.t_first, self.level = [], None, 0.0

    def start(self): pass
    def close(self): pass
    def stop(self): pass

    def play(self, pcm, sr):
        if self.t_first is None:
            self.t_first = time.monotonic()
        self.chunks.append((np.asarray(pcm), sr))

    async def wait_done(self): await asyncio.sleep(0)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default=os.path.expanduser("~/aria_e2e_risposta.wav"))
    ap.add_argument("question", nargs="*", default=["che ore sono?"])
    args = ap.parse_args()
    cfg = cfgmod.load(args.config)
    cfg["wake"]["mode"] = "stt"
    cfg["audio"]["barge_in"] = False
    cfg["turn"].update(follow_up_timeout_s=1.0, first_turn_timeout_s=1.0)
    hub, memory, persona, router = build(cfg, args.config)

    t_w = time.monotonic()
    await warmup(router, hub)                                       # come all'avvio dell'app: carica i modelli una volta
    print(f"modelli caricati in {time.monotonic() - t_w:.1f}s")
    # misura i tempi dei singoli stadi
    T = {}
    orig_t, orig_s, orig_l = router.transcribe, router.synthesize, router.llm_stream

    async def t_transcribe(pcm, sr=16000):
        t0 = time.monotonic(); r = await orig_t(pcm, sr); T.setdefault("stt", []).append(time.monotonic() - t0); T["stt_text"] = r; return r

    async def t_synth(text):
        t0 = time.monotonic(); r = await orig_s(text); T.setdefault("tts", []).append(time.monotonic() - t0); return r

    async def t_llm(messages, **kw):
        t0, first = time.monotonic(), True
        async for tok in orig_l(messages, **kw):
            if first:
                T.setdefault("llm_first_token", []).append(time.monotonic() - t0); first = False
            yield tok

    router.transcribe, router.synthesize, router.llm_stream = t_transcribe, t_synth, t_llm

    utter = "Ciao Aria, " + " ".join(args.question)
    print(f"Frase sintetizzata con 'say': {utter!r}")
    pcm = say_wav(utter)
    print(f"durata {len(pcm) / 16000:.1f}s")
    spk = FileSpeaker()
    aria = Aria(cfg, hub, FileMic(pcm), spk, None, make_vad(cfg["vad"]["kind"]), router, Tools(cfg, memory), memory, persona)
    sub = hub.subscribe()

    t_start = time.monotonic()
    await asyncio.wait_for(aria.wait_for_wake(), 120)
    t_wake = time.monotonic()
    print(f"\nWAKE riconosciuto in {t_wake - t_start:.2f}s  (Whisper ha sentito: {T.get('stt_text')!r}; comando: {aria.pending_text!r})")
    t_cmd = time.monotonic()
    spk_first_ref = {}
    await asyncio.wait_for(aria.session(), 180)
    while not sub.empty():
        m = sub.get_nowait()
        if m["type"] == "transcript":
            print(f"  [{m['role']}] {m['text']}")
    print("\nTEMPI (dopo la fine della tua frase; il silenzio finale di ~0,8 s si aggiunge nella realtà):")
    print(f"  riconoscimento vocale (Whisper): {', '.join(f'{x:.2f}s' for x in T.get('stt', []))}")
    print(f"  LLM, primo token:                {', '.join(f'{x:.2f}s' for x in T.get('llm_first_token', []))}")
    print(f"  sintesi vocale per frase:        {', '.join(f'{x:.2f}s' for x in T.get('tts', []))}")
    if spk.t_first:
        print(f"  => dal comando al PRIMO AUDIO:   {spk.t_first - t_cmd:.2f}s")
    if spk.chunks:
        sr = spk.chunks[0][1]
        from aria.audio import resample
        audio = np.concatenate([resample(c, s, sr) for c, s in spk.chunks])
        with wave.open(args.out, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(audio.tobytes())
        print(f"  risposta salvata: {args.out}  ({len(audio) / sr:.1f}s di audio)")


asyncio.run(main())
