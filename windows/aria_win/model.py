"""Lo stato dell'involucro e il testo del menu: la stessa logica di AppDelegate.swift, senza niente di grafico (cosi' si prova ovunque)."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import voices

# colori dell'icona nei vari stati (come sul Mac): ascolta, pensa, parla, errore
STATE_COLORS = {"listening": (26, 178, 235), "thinking": (158, 92, 242), "speaking": (242, 87, 158), "error": (255, 102, 77)}


@dataclass
class AppModel:
    state: str = "idle"
    muted: bool = False
    ready: bool = False
    paused: bool = False
    connected: bool = False
    voice: str = ""
    wake_phrase: str = "Hey Aria"
    problem: str | None = None
    hotkey: str = "Ctrl+Alt+Spazio"
    autostart: bool = False
    changes: list = field(default_factory=list)

    def handle(self, m: dict) -> set[str]:
        """Aggiorna lo stato da un messaggio del backend. Restituisce cosa e' cambiato: {'state', 'voice', 'muted', 'ready', 'paused', 'wake_phrase'}."""
        changed: set[str] = set()
        if isinstance(m.get("state"), str) and m["state"] != self.state:
            self.state = m["state"]
            changed.add("state")
        if isinstance(m.get("voice"), str) and m["voice"] != self.voice:
            self.voice = m["voice"]
            changed.add("voice")
        for key in ("muted", "ready", "paused"):
            if isinstance(m.get(key), bool) and m[key] != getattr(self, key):
                setattr(self, key, m[key])
                changed.add(key)
        w = m.get("wake_phrase")
        if isinstance(w, str) and w:
            pretty = " ".join(p[:1].upper() + p[1:] for p in w.split(" "))
            if pretty != self.wake_phrase:
                self.wake_phrase = pretty
                changed.add("wake_phrase")
        return changed

    def set_connected(self, ok: bool) -> None:
        self.connected = ok
        if not ok:
            self.state = "idle"

    def status_text(self) -> str:
        if self.problem:
            return "⚠ " + self.problem
        if not self.connected:
            return "Stato: in avvio…"
        if not self.ready:
            return "Stato: sto caricando i modelli…"
        if self.muted:
            return "Stato: microfono silenziato"
        if self.paused and self.state == "idle":
            return "Stato: in pausa (a batteria)"
        return {"listening": "Stato: ti ascolta", "thinking": "Stato: ci pensa", "speaking": "Stato: sta parlando"}.get(self.state, f"Stato: pronta, di' «{self.wake_phrase}»")

    def icon_color(self) -> tuple[int, int, int] | None:
        """Il colore con cui tingere l'icona (None = icona normale, bianca o nera secondo il tema di Windows)."""
        if self.muted:
            return None
        if self.problem:
            return STATE_COLORS["error"]
        return STATE_COLORS.get(self.state)

    def wake_label(self) -> str:
        return "Ferma Aria" if self.state != "idle" else "Parla con Aria"

    def voice_groups(self) -> list[tuple[str, list[str]]]:
        return voices.GROUPS
