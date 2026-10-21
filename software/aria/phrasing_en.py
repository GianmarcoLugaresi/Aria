"""Dal parlato alla forma «da comando», in inglese. Gemello inglese di phrasing.py.

Una persona non dice «remind me to call Mark»: dice «Hey, could you remind me to call Mark?», «I'd like you to remind me to…», «Can you please set a timer for me?».
`canonical()` toglie i giri di parole (saluti, «could you», «I'd like to», «please»…) cosi' le regole di intent_en.py devono conoscere UNA forma sola.
Il testo resta quello dell'utente (maiuscole, apostrofi, virgole): si cambia solo l'involucro.
"""
from __future__ import annotations

import re

_APOS = r"['’]?"
_LEAD_WORDS = (r"hey", r"yo", r"hi", r"hello", r"ok", r"okay", r"alright", r"all right", r"so", r"well", r"um+", r"uh+", r"erm", r"hmm+", r"now", r"then", r"and", r"but", r"also", r"oh", r"ah",
               r"right", r"yeah", r"yes", r"yep", r"listen", r"aria", r"please", r"kindly", r"just", r"actually", r"sorry", r"excuse me", r"quick question",
               r"one more thing", r"by the way", r"anyway", r"tell you what", r"hey aria", r"okay so", r"so then", r"oops", r"quickly", r"real quick")
_LEAD = re.compile(r"^(?:(?:" + "|".join(sorted(_LEAD_WORDS, key=len, reverse=True)) + r"|(?:look|say|no|wait)(?=\s*[,!:;]))\b[\s,.!:;\-]*)+", re.I)      # «look,» / «no,» sono intercalari; «look up…», «no more music» no
_TRAIL = re.compile(r"(?:[\s,.!?]*\b(?:please|thanks|thank you(?: very much| so much)?|for me|if you can|if you could|if you don" + _APOS + r"t mind|aria|okay|ok|right now|real quick|when you can|for now|would you|will you|can you|could you)\b)+[\s.!?]*$", re.I)

_MODAL = re.compile(
    r"^(?:(?:could|can|would|will|might|may)\s+you\s+(?:please\s+|kindly\s+|possibly\s+)?(?:go ahead and\s+)?|do you think you could\s+|do you think you can\s+|would you mind\s+|do you mind\s+|"
    r"is it possible to\s+|is it possible for you to\s+|is there a way to\s+|i" + _APOS + r"?d (?:like|love|appreciate)\s+(?:it\s+)?(?:if you could\s+|if you would\s+|you to\s+|for you to\s+|to\s+)?|"
    r"i would (?:like|love|appreciate)\s+(?:it\s+)?(?:if you could\s+|you to\s+|for you to\s+|to\s+)?|i want you to\s+|i need you to\s+|i wanted you to\s+|i" + _APOS + r"d want you to\s+|"
    r"i want to\s+|i wanna\s+|i need to\s+|i gotta\s+|i have to\s+|i" + _APOS + r"d like to\s+|i" + _APOS + r"m going to need you to\s+|let me\s+|let" + _APOS + r"s\s+|go ahead and\s+|you can\s+|you could\s+|you should\s+|you may\s+|"
    r"how about\s+|why don" + _APOS + r"t you\s+|why not\s+|maybe\s+|perhaps\s+|if you can\s+|when you can\s+|as soon as you can\s+|first\s+|try to\s+|try\s+)", re.I)


def fold(raw: str) -> str:
    return raw.lower().replace("’", "'")


def canonical(raw: str) -> str:
    """«Hey Aria, could you please set a timer for ten minutes?» -> «set a timer for ten minutes»."""
    s = (raw or "").strip()
    for _ in range(4):
        n = _LEAD.sub("", s, count=1)
        if n == s:
            break
        s = n
    for _ in range(3):
        n = _MODAL.sub("", s, count=1)
        if n == s:
            break
        s = n
        n = _LEAD.sub("", s, count=1)
        s = n or s
    for _ in range(3):
        n = _TRAIL.sub("", s)
        if n == s or not n.strip():
            break
        s = n
    s = s.strip()
    return s if s else (raw or "").strip()
