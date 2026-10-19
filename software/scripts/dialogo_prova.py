r"""Una conversazione intera con i modelli VERI (chatbot e voce) ma senza microfono: le frasi dell'utente le dai tu come testo.

    python scripts/dialogo_prova.py --config ~/Library/Application\ Support/Aria/config.yaml "ciao" "sono stanchissimo" "grazie, a dopo"
    python scripts/dialogo_prova.py --config ... --greet --wav ~/dialogo.wav "come stai?"      # parte con «Ciao Aria» da solo, salva l'audio

Mostra cosa dice Aria (e come lo "legge" la voce), quanto ci mette, e opzionalmente salva tutto l'audio in un WAV da ascoltare.
La memoria e' temporanea (non tocca quella vera).
"""
import argparse
import asyncio
import os
import sys
import tempfile
import time
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aria import config as cfgmod                       # noqa: E402
from aria.conversation import Aria                      # noqa: E402
from aria.main import build, warmup                     # noqa: E402
from aria.tools import Tools                            # noqa: E402

LOUD = np.full(512, 6000, dtype=np.int16)
QUIET = np.zeros(512, dtype=np.int16)


class FakeMic:
    def __init__(self, n_utterances):
        self.script = ([LOUD] * 14 + [QUIET] * 40) * n_utterances

    async def start(self): pass
    async def stop(self): pass
    def flush(self): pass

    async def frames(self):
        while True:
            await asyncio.sleep(0)
            yield self.script.pop(0) if self.script else QUIET


class FakeVAD:
    def reset(self): pass
    def prob(self, frame): return 0.95 if int(np.abs(frame).max()) > 1000 else 0.0


class Spk:
    def __init__(self):
        self.chunks, self.level, self.t_first = [], 0.0, None

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
    ap.add_argument("--wav")
    ap.add_argument("--greet", action="store_true", help="comincia con «Ciao Aria» da solo (chiamata a voce)")
    ap.add_argument("--workspace", help="cartella di Aria per la prova (dentro la tua Home; i file veri non si toccano)")
    ap.add_argument("--fake-mac", action="store_true", help="promemoria, calendario, musica... vengono solo registrati, non eseguiti")
    ap.add_argument("--base", action="store_true", help="ignora settings.json: usa il chatbot e Whisper del config.yaml (il 4B)")
    ap.add_argument("--llm", help="repo MLX del chatbot da provare (es. mlx-community/Qwen3.5-9B-MLX-4bit)")
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--hour", type=int, help="fa finta che sia quest'ora (per salutare di notte, al mattino...)")
    ap.add_argument("lines", nargs="+")
    args = ap.parse_args()
    cfg = cfgmod.load(args.config, settings=not (args.base or args.llm))
    if args.llm:
        cfg["brains"][0]["llm"] = {**cfg["brains"][0]["llm"], "kind": "mlx-lm", "model": args.llm}
        cfg["brains"][0]["llm"].pop("base_url", None)
        if args.no_think:
            cfg["brains"][0]["llm"]["chat_template_kwargs"] = {"enable_thinking": False}
    cfg["data_dir"] = tempfile.mkdtemp(prefix="aria_dialogo_")
    cfg["audio"]["barge_in"] = False
    cfg["audio"]["save_utterances"] = False
    cfg["turn"].update(follow_up_timeout_s=1.0, first_turn_timeout_s=1.0)
    hub, memory, persona, router = build(cfg, args.config)
    await warmup(router, hub)
    lines = list(args.lines)
    stt_lines = list(lines)

    async def fake_transcribe(pcm, sr=16000):
        return stt_lines.pop(0) if stt_lines else ""
    router.transcribe = fake_transcribe
    spoken = []
    orig = router.synthesize

    async def synth(text):
        t0 = time.monotonic()
        r = await orig(text)
        spoken.append((text, time.monotonic() - t0, len(r[0]) / r[1]))
        return r
    router.synthesize = synth
    first_tokens = []
    orig_llm = router.llm_stream

    async def timed_llm(messages, **kw):
        t0, first = time.monotonic(), True
        async for tok in orig_llm(messages, **kw):
            if first:
                first_tokens.append(time.monotonic() - t0)
                first = False
            yield tok
    router.llm_stream = timed_llm
    spk = Spk()
    if args.workspace:
        cfg["workspace"] = os.path.expanduser(args.workspace)
    tools = Tools(cfg, memory)
    if args.fake_mac:
        from aria.macos import Mac
        calls = []

        def runner(argv, timeout, stdin=None):
            calls.append(argv[:3] if argv and argv[0] != "osascript" else ["osascript", "…", *argv[-6:]])
            return 0, "", ""
        tools.mac = Mac(runner=runner, platform="darwin")
        tools._calls = calls
    aria = Aria(cfg, hub, FakeMic(len(lines)), spk, None, FakeVAD(), router, tools, memory, persona)
    if args.hour is not None:
        import datetime as dt
        real = dt.datetime
        class Fake(real):
            @classmethod
            def now(cls, tz=None):
                return real(2026, 10, 6, args.hour, 30)
        dt.datetime = Fake
    aria._voice_wake = args.greet
    await aria._prime_llm()                                   # come l'app: il carattere di Aria e' gia' in cache
    sub = hub.subscribe()
    t0 = time.monotonic()
    await asyncio.wait_for(aria.session(), 600)
    print(f"\n(totale {time.monotonic() - t0:.1f}s)\n")
    users = iter(lines)
    while not sub.empty():
        m = sub.get_nowait()
        if m["type"] == "transcript":
            print(("  TU:   " if m["role"] == "user" else "  ARIA: ") + m["text"])
    if args.fake_mac:
        print("\nComandi che avrebbe mandato al Mac:", *[f"\n   {c}" for c in tools._calls[:12]])
    if first_tokens:
        print("\nChatbot, primo testo dopo la domanda:", ", ".join(f"{x:.2f}s" for x in first_tokens))
    print("\nCome la legge la voce (testo | tempo di sintesi | durata audio):")
    for text, dt_s, dur in spoken:
        print(f"  {text!r:90.90} | {dt_s:4.2f}s | {dur:4.1f}s")
    if args.wav and spk.chunks:
        from aria.audio import resample
        sr = spk.chunks[0][1]
        audio = np.concatenate([resample(c, s, sr) for c, s in spk.chunks])
        with wave.open(os.path.expanduser(args.wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(audio.astype(np.int16).tobytes())
        print(f"\naudio salvato: {args.wav} ({len(audio) / sr:.1f}s)")


asyncio.run(main())
