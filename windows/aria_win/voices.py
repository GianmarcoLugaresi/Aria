"""Le voci tra cui scegliere nel menu (le stesse di Pocket TTS dell'app per Mac; le «naturali» di Qwen3-TTS richiedono un chip Apple).

In inglese l'elenco e' ridotto alle voci registrate da persone che parlano inglese (lola, estelle, giovanni… hanno l'accento spagnolo, francese, italiano): come in AppDelegate.swift.
"""
from . import l10n

FEMALE = ["lola", "vera", "eve", "jane", "mary", "cosette", "anna", "estelle", "fantine"]
MALE = ["giovanni", "paul", "george", "michael", "javert"]
GROUPS = [("Voci femminili", FEMALE), ("Voci maschili", MALE)]

FEMALE_EN = ["alba", "anna", "azelma", "cosette", "eponine", "eve", "fantine", "jane", "mary", "vera"]
MALE_EN = ["charles", "george", "jean", "javert", "marius", "michael", "paul"]
GROUPS_EN = [("Female voices", FEMALE_EN), ("Male voices", MALE_EN)]


def groups(lang: str | None = None) -> list[tuple[str, list[str]]]:
    """I gruppi di voci per la lingua (di default quella in uso)."""
    return GROUPS_EN if (lang or l10n.code()) == "en" else GROUPS
