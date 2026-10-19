"""Le stesse richieste con gli involucri di tutti i giorni («Ehi Aria, …», «… per favore», «Senti, …», «Ehm… …», «…, Aria») devono andare allo stesso strumento;
e la chiacchiera, con gli stessi involucri (e un punto interrogativo messo dal riconoscimento), non deve far partire niente."""
import json
import os
import re

import pytest

import intent_corpus2 as c2
import intent_corpus3 as c3
import intent_corpus4 as c4
import intent_corpus5 as c5
import intent_corpus6 as c6
import intent_corpus7 as c7
import intent_corpus8 as c8
from aria import intent

POS = [(t, tools) for c in (c2.POS2, c3.POS3, c4.POS4, c5.POS5, c6.POS6, c7.POS7, c8.POS8) for t, tools, _p in c]
NEG = list(c2.NEG2) + list(c3.NEG3) + list(c4.NEG4) + list(c5.NEG5) + list(c6.NEG6) + list(c7.NEG7) + list(c8.NEG8) + json.load(open(os.path.join(os.path.dirname(__file__), "chat_sentences.json"), encoding="utf-8"))
WRAP = {
    "ehi aria": lambda p: "Ehi Aria, " + p[0].lower() + p[1:],
    "per favore": lambda p: p.rstrip("?.!") + " per favore",
    "ehm": lambda p: "Ehm... " + p[0].lower() + p[1:],
    "senti": lambda p: "Senti, " + p[0].lower() + p[1:],
    "scusa grazie": lambda p: "Scusa, " + p[0].lower() + p[1:].rstrip("?.!") + ", grazie",
    "aria in coda": lambda p: p.rstrip("?.!") + ", Aria",
    "interrogativo": lambda p: p.rstrip("?.!") + "?",
}


@pytest.mark.parametrize("name", sorted(WRAP))
def test_requests_keep_their_tool_when_wrapped(name):
    bad = []
    for p, tools in POS:
        c = intent.detect(WRAP[name](p), c2.FILES, screen_on=True)
        if c is None or c.name not in tools:
            bad.append((WRAP[name](p), c.name if c else None))
    assert len(bad) <= 2, bad                                   # (un paio di frasi cortissime con una sola parola chiave possono perdersi: non di piu')


@pytest.mark.parametrize("name", ["ehi aria", "per favore", "interrogativo", "senti"])
def test_chitchat_stays_chitchat_when_wrapped(name):
    fired = []
    for p in NEG:
        for screen in (False, True):
            c = intent.detect(WRAP[name](p), c2.FILES, screen_on=screen)
            if c is not None:
                fired.append((WRAP[name](p), c.name))
    assert not fired, fired


def test_lowercase_without_punctuation_still_works_for_the_plain_requests():
    ok = bad = 0
    for p, tools in POS:
        c = intent.detect(re.sub(r"[^\w\s']", "", p.lower()), c2.FILES, screen_on=True)
        ok += bool(c and c.name in tools)
        bad += not (c and c.name in tools)
    assert ok / (ok + bad) > 0.97
