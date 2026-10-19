"""Prova carattere, strumenti e velocita' del cervello SENZA audio.

    python scripts/try_persona.py --config config.mac.yaml            # frasi di esempio
    python scripts/try_persona.py --config config.mac.yaml "Che ore sono?" "Chi ha scritto Il Gattopardo?"
"""
import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aria import config as cfgmod                       # noqa: E402
from aria.conversation import Aria                      # noqa: E402
from aria.main import build                             # noqa: E402
from aria.persona import build_system                   # noqa: E402
from aria.tools import Tools                            # noqa: E402

SAMPLE = [
    "Ciao! Come va?",
    "Sono stanchissimo, oggi riunioni tutto il giorno.",
    "Qual è la capitale dell'Australia?",
    "Pizza o pasta?",
    "Che tempo fa domani?",
    "Mettimi un timer di dieci minuti per la pasta.",
    "Quanto fa centoventi diviso otto?",
    "Sei una persona vera?",
    "Mi chiamo Mario e domani ho un esame di analisi.",
]


class Dummy:
    pass


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--model", help="sovrascrive il modello LLM della config")
    ap.add_argument("lines", nargs="*")
    args = ap.parse_args()
    cfg = cfgmod.load(args.config)
    if args.model:
        cfg['brains'][0]['llm']['model'] = args.model
    hub, memory, persona, router = build(cfg, args.config)
    tools = Tools(cfg, memory)
    aria = Aria(cfg, hub, Dummy(), Dummy(), Dummy(), Dummy(), router, tools, memory, persona)
    aria.sys_prompt = build_system(persona, cfg, "")
    for user in args.lines or SAMPLE:
        print(f"\ntu   > {user}")
        aria.history.append({"role": "user", "content": user})
        msgs = [{"role": "system", "content": aria.sys_prompt}] + aria.history[-12:]
        t0, first = time.monotonic(), None
        try:
            async for kind, val in aria.reply_events(msgs):
                now = time.monotonic() - t0
                if kind == "sentence":
                    first = first if first is not None else now
                    print(f"aria > {val}   [{now:.1f}s]")
                else:
                    print(f"       (strumento: {val.name} {val.arg!r})")
        except Exception as e:                           # noqa: BLE001
            print(f"ERRORE: {e}")
            break
        print(f"       primo testo dopo {first:.1f}s, totale {time.monotonic() - t0:.1f}s" if first else "       (nessuna risposta)")


asyncio.run(main())
