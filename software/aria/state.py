"""Stati e bus eventi: tutto cio' che deve reagire a "cosa sta facendo Aria" (display, LED, app Mac) si abbona qui.

Messaggi (dict JSON-izzabili):
  {"type": "state", "state": "listening"}                  cambio di stato
  {"type": "level", "level": 0.42}                         livello voce 0..1 (coalescente: se il client e' lento resta solo l'ultimo)
  {"type": "transcript", "role": "user"|"aria", "text": ..., "final": bool, "id": n?}   sottotitoli (con "id": la stessa frase che cresce parola per parola, a tempo con la voce)
  {"type": "info", ...}                                    altro (voce attuale, silenziato...)
Comandi in ingresso dal client (WebSocket): {"cmd": "wake"|"stop"|"mute"|"unmute"|"voice", ...}
"""
from __future__ import annotations

import asyncio
from collections import deque
from enum import Enum
from typing import Callable


class State(str, Enum):
    IDLE = "idle"              # in attesa del wake word
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


class Subscription:
    """Coda per un client: gli eventi importanti si conservano tutti, il livello si riduce all'ultimo valore."""

    def __init__(self, maxlen: int = 256):
        self._events: deque = deque(maxlen=maxlen)
        self._level: dict | None = None
        self._ev = asyncio.Event()

    def push(self, msg: dict) -> None:
        if msg.get("type") == "level":
            self._level = msg
        else:
            self._events.append(msg)
        self._ev.set()

    def empty(self) -> bool:
        return not self._events and self._level is None

    def get_nowait(self) -> dict:
        if self._events:
            return self._events.popleft()
        if self._level is not None:
            msg, self._level = self._level, None
            return msg
        raise asyncio.QueueEmpty

    async def get(self) -> dict:
        while True:
            try:
                return self.get_nowait()
            except asyncio.QueueEmpty:
                self._ev.clear()
                await self._ev.wait()


class Hub:
    def __init__(self):
        self.state = State.IDLE
        self.level = 0.0
        self.info: dict = {}
        self.prog: dict | None = None                       # barra di avanzamento in corso (per chi si collega a meta')
        self._subs: list[Subscription] = []
        self._cmd_handlers: list[Callable[[dict], None]] = []

    # --- abbonamenti
    def subscribe(self) -> Subscription:
        s = Subscription()
        self._subs.append(s)
        return s

    def unsubscribe(self, s: Subscription) -> None:
        if s in self._subs:
            self._subs.remove(s)

    def snapshot(self) -> dict:
        snap = {"type": "snapshot", "state": self.state.value, "level": round(self.level, 3), **self.info}
        if self.prog:
            snap["progress"] = self.prog
        return snap

    def _emit(self, msg: dict) -> None:
        for s in list(self._subs):
            s.push(msg)

    # --- uscite
    def set_state(self, state: State) -> None:
        if state != self.state:
            self.state = state
            self._emit({"type": "state", "state": state.value})

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, float(level)))
        self._emit({"type": "level", "level": round(self.level, 3)})

    def transcript(self, role: str, text: str, final: bool = True, sid: int | None = None) -> None:
        """`sid`: la stessa frase aggiornata man mano che la voce la dice (i sottotitoli «a tempo»): lo schermo sostituisce il testo di quella frase invece di aggiungerne un'altra."""
        msg = {"type": "transcript", "role": role, "text": text, "final": final}
        if sid is not None:
            msg["id"] = sid
        self._emit(msg)

    def progress(self, label: str, fraction: float | None = None, until: float | None = None, eta: float | None = None) -> None:
        """Una operazione lunga (un documento, una ricerca): l'overlay mostra una barra in basso. `fraction` = dove parte questa fase (None = non si sa quanto manca: barra che scorre),
        `until` = dove arriva circa a fine fase e `eta` = in quanti secondi (la barra si avvicina piano, senza mai finire prima del tempo)."""
        self.prog = {"label": label, "fraction": None if fraction is None else round(max(0.0, min(1.0, float(fraction))), 3),
                     "until": None if until is None else round(max(0.0, min(1.0, float(until))), 3), "eta": eta}
        self._emit({"type": "progress", "active": True, **self.prog})

    def progress_done(self) -> None:
        if self.prog is not None:
            self.prog = None
            self._emit({"type": "progress", "active": False})

    def set_info(self, **kw) -> None:
        self.info.update(kw)
        self._emit({"type": "info", **kw})

    # --- comandi in ingresso
    def on_command(self, handler: Callable[[dict], None]) -> None:
        self._cmd_handlers.append(handler)

    def dispatch_command(self, cmd: dict) -> None:
        for h in self._cmd_handlers:
            h(cmd)
