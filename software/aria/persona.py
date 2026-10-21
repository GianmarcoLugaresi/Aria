"""Costruisce il system prompt: carattere (file .md) + data/ora + memoria. Un SOLO messaggio di sistema (alcuni template, es. Gemma, non ne vogliono due)."""
from __future__ import annotations

import datetime as dt
import os

from . import i18n
from .tools import now_it

PLACEHOLDER_NOTE = "<!--"


def resolve_path(path: str, bases: list[str]) -> str:
    p = os.path.expanduser(path)
    if os.path.isabs(p) and os.path.exists(p):
        return p
    for b in bases:
        cand = os.path.normpath(os.path.join(b, p))
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError(f"file non trovato: {path} (cercato in {bases})")


def load_persona(path: str, bases: list[str]) -> str:
    text = open(resolve_path(path, bases), encoding="utf-8").read()
    # tutto cio' che e' dopo la riga '---FINE---' (note per umani) non va al modello
    return text.split("---FINE---")[0].strip()


def load_persona_for(cfg: dict, bases: list[str], config_path: str | None = None) -> str:
    """Il carattere per la lingua in uso. In inglese, se l'utente non ha ancora `persona.en.md` accanto a config.yaml, parte quello incluso nel pacchetto (aria/data/persona_en.md),
    e ne lascia una copia modificabile accanto alla configurazione (come per persona.md in italiano)."""
    path = cfg["persona_file"]
    try:
        return load_persona(path, bases)
    except FileNotFoundError:
        if not (i18n.is_en() and os.path.basename(path) == "persona.en.md"):
            raise
    packaged = os.path.join(os.path.dirname(os.path.abspath(__file__)), i18n.PACKAGED_PERSONA_EN)
    text = open(packaged, encoding="utf-8").read()
    if config_path:
        try:
            dest = os.path.join(os.path.dirname(os.path.abspath(config_path)), "persona.en.md")
            if not os.path.exists(dest):
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(text)
        except OSError:
            pass
    return text.split("---FINE---")[0].strip()


def build_system(persona: str, cfg: dict, memory_ctx: str = "", now=None) -> str:
    name = cfg.get("name", "Aria")
    n = now or dt.datetime.now()
    if i18n.is_en():
        from .speech_en import now_en
        date = now_en(n).split(", at")[0]                                           # «Tuesday, October 6, 2026»: l'ora esatta no, o commenta l'orario a ogni frase
        late = " It is the middle of the night: speak softly and gently." if (n.hour < 5 or n.hour >= 23) else ""
        part = ("night" if n.hour < 5 else "morning" if n.hour < 12 else "lunchtime" if n.hour < 14 else "afternoon" if n.hour < 18 else "evening" if n.hour < 23 else "night")
        parts = [persona.replace("{{nome}}", name),
                 f"It is now: {date}, {part}.{late} Don't comment on the day or the time unless it matters to what they say. "
                 f"You don't know the user's name or where they live unless it is written below: don't make it up."]
        if memory_ctx:
            parts.append(memory_ctx)
        return "\n\n".join(parts)
    date = now_it(n).split(", ore")[0]                                              # «martedì 6 ottobre 2026»: l'ora esatta no, o commenta l'orario a ogni frase
    late = " È notte fonda: parla piano e con dolcezza." if (n.hour < 5 or n.hour >= 23) else ""
    part = ("notte" if n.hour < 5 else "mattina" if n.hour < 12 else "ora di pranzo" if n.hour < 14 else "pomeriggio" if n.hour < 18 else "sera" if n.hour < 23 else "notte")   # senza, il chatbot indovina («stamattina» alle 19:50)
    parts = [persona.replace("{{nome}}", name),
             f"Adesso è: {date}, {part}.{late} Non commentare il giorno o l'ora se non c'entrano con quello che dice. "
             f"Non sai come si chiama l'utente né dove abita, a meno che non sia scritto qui sotto: non inventarlo."]
    if memory_ctx:
        parts.append(memory_ctx)
    return "\n\n".join(parts)
