"""Wake word "Hey Aria". Due strade: modello openWakeWord addestrato (produzione) o tasto Invio (sviluppo sul Mac)."""
from __future__ import annotations

import asyncio
import logging
import threading
import time

import numpy as np

log = logging.getLogger("aria.wake")


class OpenWakeWord:
    def __init__(self, model_path: str, threshold: float = 0.6, cooldown_s: float = 2.0):
        from openwakeword.model import Model  # type: ignore
        self.model = Model(wakeword_models=[model_path], inference_framework="onnx")
        self.threshold, self.cooldown = threshold, cooldown_s
        self.buf = np.zeros(0, dtype=np.int16)
        self.last = 0.0
        self.last_score = 0.0

    def feed(self, frame: np.ndarray) -> bool:
        self.buf = np.concatenate([self.buf, frame])
        hit = False
        while len(self.buf) >= 1280:                              # openWakeWord vuole blocchi da 80 ms
            chunk, self.buf = self.buf[:1280], self.buf[1280:]
            scores = self.model.predict(chunk)
            self.last_score = max(scores.values()) if scores else 0.0
            if self.last_score >= self.threshold and time.monotonic() - self.last > self.cooldown:
                self.last = time.monotonic()
                hit = True
        return hit


class KeyboardWake:
    """Sviluppo: premi Invio nel terminale al posto di dire 'Hey Aria'."""

    def __init__(self):
        self.event = threading.Event()
        threading.Thread(target=self._read, daemon=True).start()
        print("[dev] premi INVIO per svegliare Aria")

    def _read(self):
        while True:
            try:
                input()
            except EOFError:
                return
            self.event.set()

    def feed(self, frame: np.ndarray) -> bool:
        if self.event.is_set():
            self.event.clear()
            return True
        return False


def make_wake(cfg: dict):
    if cfg.get("model_path"):
        return OpenWakeWord(cfg["model_path"], cfg.get("threshold", 0.6), cfg.get("cooldown_s", 2.0))
    log.warning("nessun modello wake word in config: modalita' sviluppo (tasto Invio)")
    return KeyboardWake()
