"""Audio finto per collaudare l'intera app senza microfono né altoparlanti.

Attivazione:  ARIA_FAKE_AUDIO=/percorso/frase.wav   (WAV mono 16 kHz; la frase parte quando Aria passa a "ti ascolto")
La risposta di Aria viene salvata in ~/aria_app_risposta.wav.
"""
from __future__ import annotations

import asyncio
import os
import time
import wave

import numpy as np

from .audio import resample
from .state import Hub, State


class FileMic:
    def __init__(self, path: str, hub: Hub):
        with wave.open(path) as w:
            self.pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        self.hub = hub
        self.i = -1
        self.at = os.environ.get("ARIA_FAKE_AUDIO_AT", "listening")     # "listening" (dopo il tasto) | "ready" (da solo, per il "Ciao Aria" a voce)

    async def start(self) -> None: pass
    async def stop(self) -> None: pass
    def flush(self) -> None: pass

    async def frames(self):
        while True:
            await asyncio.sleep(0.032)                                  # tempo reale
            if self.i < 0 and ((self.at == "listening" and self.hub.state == State.LISTENING)
                               or (self.at == "ready" and self.hub.info.get("ready"))):
                self.i = 0
            if 0 <= self.i < len(self.pcm):
                f = self.pcm[self.i:self.i + 512]
                self.i += 512
                yield np.pad(f, (0, 512 - len(f)))
            else:
                yield np.zeros(512, dtype=np.int16)


class NullSpeaker:
    """Non suona: accumula l'audio, simula la durata (cosi' gli stati dell'app sono realistici) e lo salva in un WAV."""

    def __init__(self, out_rate: int = 24000):
        self.rate, self.level = out_rate, 0.0
        self.chunks: list[np.ndarray] = []
        self.busy_until = 0.0

    def start(self) -> None: pass
    def close(self) -> None: pass

    def play(self, pcm: np.ndarray, sr: int) -> None:
        x = resample(np.asarray(pcm), sr, self.rate)
        self.chunks.append(x)
        now = time.monotonic()
        self.busy_until = max(self.busy_until, now) + len(x) / self.rate
        self.level = 0.5

    def stop(self) -> None:
        self.busy_until = 0.0
        self.level = 0.0

    @property
    def playing(self) -> bool:
        return time.monotonic() < self.busy_until

    async def wait_done(self) -> None:
        while self.playing:
            await asyncio.sleep(0.05)
        self.level = 0.0
        if self.chunks:
            out = os.path.expanduser("~/aria_app_risposta.wav")
            with wave.open(out, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(self.rate)
                w.writeframes(np.concatenate(self.chunks).astype(np.int16).tobytes())
