"""Pilota il backend (avviato dall'app o da solo) via WebSocket e registra cosa succede.

    python scripts/app_integration_test.py [--wake]      # --wake: manda il comando come il tasto ⌥Spazio
"""
import argparse
import asyncio
import json
import time

from websockets.asyncio.client import connect


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wake", action="store_true")
    ap.add_argument("--timeout", type=float, default=240)
    args = ap.parse_args()
    t0 = time.monotonic()
    log = []

    def stamp(msg):
        log.append((time.monotonic() - t0, msg))
        print(f"[{time.monotonic() - t0:6.1f}s] {msg}", flush=True)

    for _ in range(120):                                       # il backend puo' impiegare un po' ad accendersi
        try:
            ws = await connect("ws://127.0.0.1:8765")
            break
        except OSError:
            await asyncio.sleep(1)
    else:
        raise SystemExit("backend non raggiungibile")
    stamp("collegato al backend")
    ready, woke, spoke, last_state = False, False, False, None
    async for raw in ws:
        m = json.loads(raw)
        if m.get("type") == "level":
            continue
        if m.get("type") in ("snapshot", "info") and m.get("ready") and not ready:
            ready = True
            stamp("MODELLI PRONTI")
        t = m.get("type")
        if t == "state":
            last_state = m["state"]
            stamp(f"stato → {last_state}")
            if last_state == "speaking":
                spoke = True
            if last_state == "idle" and spoke:
                break
        elif t == "transcript":
            stamp(f"{m['role']:5s}: {m['text']}")
        if ready and args.wake and not woke:
            woke = True
            await asyncio.sleep(1.0)
            stamp("invio comando WAKE (come ⌥Spazio)")
            await ws.send(json.dumps({"cmd": "wake"}))
        if time.monotonic() - t0 > args.timeout:
            stamp("TIMEOUT")
            break
    await ws.close()
    print("\nRIEPILOGO:", "OK, ha parlato" if spoke else "NON ha risposto")


asyncio.run(main())
