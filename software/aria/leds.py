"""Anello LED d'ambiente (strip WS2812 dentro l'anello diffusore): colori per stato, animati in base al livello voce."""
from __future__ import annotations

import asyncio
import logging
import math
import time

from .state import Hub

log = logging.getLogger("aria.leds")

PALETTE = {
    "idle": (40, 110, 200),
    "listening": (20, 200, 230),
    "thinking": (150, 80, 255),
    "speaking": (255, 70, 150),
    "error": (255, 40, 20),
}


def frame_colors(state: str, level: float, t: float, n: int) -> list[tuple[int, int, int]]:
    """Colori dei n LED al tempo t. Funzione pura: facile da provare."""
    r, g, b = PALETTE.get(state, PALETTE["idle"])
    out = []
    for i in range(n):
        if state == "idle":
            k = 0.10 + 0.07 * (0.5 + 0.5 * math.sin(t * 1.2))
        elif state == "thinking":
            k = 0.06 + 0.55 * max(0.0, math.cos((i / n - (t * 0.6) % 1.0) * 2 * math.pi)) ** 6
        else:
            k = 0.12 + 0.70 * level * (0.6 + 0.4 * math.sin(i / n * 6.283 * 3 + t * 5))
        k = max(0.0, min(1.0, k)) * 0.5                                   # tetto di luminosita': alimentazione e occhi
        out.append((int(r * k), int(g * k), int(b * k)))
    return out


class NullLeds:
    async def run(self, hub: Hub) -> None:
        return


class Pi5NeoLeds:
    """pip install pi5neo; strip su SPI (MOSI = GPIO10) con convertitore di livello 3.3V -> 5V."""

    def __init__(self, count: int = 38, dev: str = "/dev/spidev0.0"):
        from pi5neo import Pi5Neo  # type: ignore
        self.neo, self.n = Pi5Neo(dev, count, 800), count

    async def run(self, hub: Hub) -> None:
        t0 = time.monotonic()
        while True:
            for i, (r, g, b) in enumerate(frame_colors(hub.state.value, hub.level, time.monotonic() - t0, self.n)):
                self.neo.set_led_color(i, r, g, b)
            self.neo.update_strip()
            await asyncio.sleep(1 / 30)


def make_leds(cfg: dict):
    if cfg.get("kind") == "pi5neo":
        return Pi5NeoLeds(cfg.get("count", 38))
    return NullLeds()
