"""Fa girare il server del display con stati finti, per provare hardware/display/index.html senza microfono ne' modelli.

    python scripts/demo_display.py        # poi apri hardware/display/index.html (es. con: python -m http.server -d ../hardware 8000)
"""
import asyncio
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aria.display import serve_display      # noqa: E402
from aria.state import Hub, State           # noqa: E402

CYCLE = [(State.IDLE, 3), (State.LISTENING, 5), (State.THINKING, 2.5), (State.SPEAKING, 6)]


async def main():
    hub = Hub()
    await serve_display(hub, "127.0.0.1", 8765, 30)
    t = 0.0
    while True:
        for st, dur in CYCLE:
            hub.set_state(st)
            end = t + dur
            while t < end:
                lvl = {State.IDLE: 0.04, State.THINKING: 0.3}.get(st, abs(math.sin(t * 6)) * abs(math.sin(t * 1.3 + 1)))
                hub.set_level(lvl)
                await asyncio.sleep(1 / 30)
                t += 1 / 30


asyncio.run(main())
