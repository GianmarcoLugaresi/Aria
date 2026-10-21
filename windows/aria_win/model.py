"""Lo stato dell'involucro e il testo del menu: la stessa logica di AppDelegate.swift, senza niente di grafico (cosi' si prova ovunque)."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import voices
from .l10n import tr

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
    hotkey: str = "Ctrl+Alt+Space"                    # come si scrive nella configurazione; in italiano nel menu «Space» diventa «Spazio»
    language_choice: str = "auto"                     # quello scelto nel menu Lingua: «auto», «it» o «en»
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
            return tr("Stato: in avvio…", "Status: starting…")
        if not self.ready:
            return tr("Stato: sto caricando i modelli…", "Status: loading the models…")
        if self.muted:
            return tr("Stato: microfono silenziato", "Status: microphone muted")
        if self.paused and self.state == "idle":
            return tr("Stato: in pausa (a batteria)", "Status: paused (on battery)")
        if self.state == "listening":
            return tr("Stato: ti ascolta", "Status: listening")
        if self.state == "thinking":
            return tr("Stato: ci pensa", "Status: thinking")
        if self.state == "speaking":
            return tr("Stato: sta parlando", "Status: speaking")
        return tr(f"Stato: pronta, di' «{self.wake_phrase}»", f"Status: ready, say “{self.wake_phrase}”")

    def icon_color(self) -> tuple[int, int, int] | None:
        """Il colore con cui tingere l'icona (None = icona normale, bianca o nera secondo il tema di Windows)."""
        if self.muted:
            return None
        if self.problem:
            return STATE_COLORS["error"]
        return STATE_COLORS.get(self.state)

    def wake_label(self) -> str:
        return tr("Ferma Aria", "Stop Aria") if self.state != "idle" else tr("Parla con Aria", "Talk to Aria")

    def hotkey_text(self) -> str:
        """La scorciatoia come la si legge nel menu: «Ctrl+Alt+Spazio» in italiano, «Ctrl+Alt+Space» in inglese."""
        return self.hotkey.replace("Spazio", "Space").replace("Space", tr("Spazio", "Space"))

    def voice_groups(self) -> list[tuple[str, list[str]]]:
        return voices.groups()

    def labels(self) -> dict[str, str]:
        """Le scritte del menu nella lingua in uso (le stesse del menu dell'app per Mac, dove c'e' l'equivalente)."""
        return {
            "voice": tr("Voce", "Voice"),
            "mute": tr(f"Silenzia il microfono (niente «{self.wake_phrase}»)", f"Mute the microphone (no “{self.wake_phrase}”)"),
            "autostart": tr("Avvia con Windows", "Start with Windows"),
            "language": tr("Lingua", "Language"),
            "lang_auto": tr("Automatica (come Windows)", "Automatic (like Windows)"),
            "folder": tr("Cartella di Aria…", "Aria's folder…"),
            "config": tr("Apri la configurazione", "Open the configuration"),
            "persona": tr("Apri il carattere (persona.md)", "Open the personality (persona.en.md)"),
            "logs": tr("Mostra i log", "Show logs"),
            "quit": tr("Esci da Aria", "Quit Aria"),
        }

