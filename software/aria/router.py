"""Catena di cervelli con failover.

Ogni stadio (LLM, STT, TTS) sceglie il primo "cervello" raggiungibile tra quelli in config. Esempio tipico:
  1) il Mac / un mini PC di casa: veloce e intelligente (se acceso)
  2) il Raspberry stesso: lento ma sempre disponibile
Se uno stadio fallisce a meta', si passa al successivo e il guasto viene ricordato per 30 secondi.
"""
from __future__ import annotations

import logging
import time
from typing import AsyncIterator

import httpx
import numpy as np

log = logging.getLogger("aria.router")
LOCAL_KINDS = {"faster-whisper", "mlx-whisper", "mlx-lm", "piper", "kokoro", "pocket", "say", "apple", "natural"}          # girano nel processo: sempre "raggiungibili"


class Router:
    def __init__(self, brains: list[dict], factory, health_ttl: float = 15.0, ban_s: float = 30.0, http: httpx.AsyncClient | None = None):
        self.brains, self.factory = brains, factory
        self.ttl, self.ban_s = health_ttl, ban_s
        self._health: dict[tuple[str, str], tuple[float, bool]] = {}
        self._ban: dict[tuple[str, str], float] = {}
        self._objs: dict[tuple[str, str], object] = {}
        self.http = http or httpx.AsyncClient(timeout=0.8)
        self.revive = None                                      # async (stage) -> bool: prova a rimettere in piedi uno stadio (es. riaprire Ollama)

    async def _healthy(self, brain: dict, stage: str) -> bool:
        key = (brain["name"], stage)
        if self._ban.get(key, 0) > time.monotonic():
            return False
        cfg = brain.get(stage)
        if not cfg:
            return False
        if cfg.get("kind") in LOCAL_KINDS:
            return True
        ts, ok = self._health.get(key, (0.0, False))
        if time.monotonic() - ts < self.ttl:
            return ok
        base = cfg.get("base_url", "").rstrip("/")
        try:
            r = await self.http.get(base + "/models")
            ok = r.status_code < 500
        except Exception:                                      # noqa: BLE001
            ok = False
        self._health[key] = (time.monotonic(), ok)
        return ok

    def _obj(self, brain: dict, stage: str):
        key = (brain["name"], stage)
        if key not in self._objs:
            self._objs[key] = self.factory(stage, brain[stage])
        return self._objs[key]

    async def candidates(self, stage: str):
        for b in self.brains:
            if await self._healthy(b, stage):
                yield b, self._obj(b, stage)

    def objects(self, stage: str) -> list:
        """Gli adattatori gia' creati per quello stadio (serve per cambiare voce a caldo)."""
        return [o for (n, st), o in self._objs.items() if st == stage]

    def tts_chunk(self, default: int) -> int:
        """A pezzi di quanti caratteri conviene far dire le frasi alla voce in uso (Pocket TTS le taglia se lunghe; la voce naturale no)."""
        for o in self.objects("tts"):
            c = getattr(o, "chunk_chars", None)
            if c:
                return int(c)
        return default

    def fail(self, brain: dict, stage: str) -> None:
        if sum(1 for b in self.brains if b.get(stage)) <= 1:
            log.warning("cervello '%s' (%s): errore (e' l'unico: si riprova alla prossima)", brain["name"], stage)
            return                                             # senza alternative, «metterlo da parte» per 30 s voleva dire 30 s senza capire niente (osservato: 1157 errori di fila)
        log.warning("cervello '%s' (%s) non risponde: passo al prossimo per %ds", brain["name"], stage, int(self.ban_s))
        self._ban[(brain["name"], stage)] = time.monotonic() + self.ban_s

    # -- operazioni con failover
    async def llm_stream(self, messages: list[dict], max_tokens: int | None = None, temperature: float | None = None) -> AsyncIterator[str]:
        """Streaming dal primo chatbot raggiungibile. Se nessuno risponde, `revive` (es. riaprire Ollama) ha una possibilita' e si riprova."""
        last: Exception | None = None
        for attempt in (0, 1):
            async for b, llm in self.candidates("llm"):
                started = False
                try:
                    kw = {k: v for k, v in (("max_tokens", max_tokens), ("temperature", temperature)) if v is not None}      # solo se richiesti: i chatbot finti dei test non li conoscono
                    async for tok in llm.stream(messages, **kw):
                        started = True
                        yield tok
                    return
                except Exception as e:                         # noqa: BLE001
                    last = e
                    self.fail(b, "llm")
                    if started:                                # e' gia' uscito del testo: non ricominciare da capo
                        return
            if attempt == 0 and self.revive is not None and await self.revive("llm"):
                self._health.clear()                           # il guasto era appena stato ricordato: ora e' risolto
                self._ban.clear()
                continue
            break
        raise RuntimeError(f"nessun cervello LLM disponibile ({last})")

    async def transcribe(self, pcm: np.ndarray, sr: int = 16000) -> str:
        last: Exception | None = None
        async for b, stt in self.candidates("stt"):
            try:
                return await stt.transcribe(pcm, sr)
            except Exception as e:                             # noqa: BLE001
                last = e
                self.fail(b, "stt")
        raise RuntimeError(f"nessun riconoscimento vocale disponibile ({last})")

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        last: Exception | None = None
        async for b, tts in self.candidates("tts"):
            try:
                return await tts.synthesize(text)
            except Exception as e:                             # noqa: BLE001
                last = e
                self.fail(b, "tts")
        raise RuntimeError(f"nessuna sintesi vocale disponibile ({last})")
