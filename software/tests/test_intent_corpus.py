"""Frasi come le direbbe una persona (tests/intent_corpus.py): quasi tutte devono essere capite, e la chiacchiera non deve far partire niente."""
import pytest

from aria import intent
from intent_corpus import FILES, NEG, POS


def _ok(text, tool, parts):
    c = intent.detect(text, FILES)
    return c is not None and c.name == tool and all(p in c.arg.lower() for p in parts)


@pytest.mark.parametrize("text,tool,parts", POS)
def test_natural_requests_are_understood(text, tool, parts):
    c = intent.detect(text, FILES)
    assert c is not None and c.name == tool, f"{text!r} -> {c}"
    assert all(p in c.arg.lower() for p in parts), f"{text!r} -> {c.arg!r}, mancano {[p for p in parts if p not in c.arg.lower()]}"


@pytest.mark.parametrize("text", NEG)
def test_small_talk_does_not_trigger_tools(text):
    c = intent.detect(text, FILES)
    assert c is None, f"{text!r} ha fatto partire {c}"


def test_slot_filling_and_list_followup():
    from aria.textutil import ToolCall
    slot = ToolCall("PROMEMORIA", "chiamare Mario")
    assert intent.merge_slot(slot, "domani alle nove.") == ToolCall("PROMEMORIA", "chiamare Mario domani alle nove")
    assert intent.merge_slot(slot, "senza orario") == ToolCall("PROMEMORIA", "!chiamare Mario")
    assert intent.merge_slot(ToolCall("NOTA", ""), "comprare le pile") == ToolCall("NOTA", "comprare le pile")
    assert intent.merge_slot(ToolCall("LISTA", "della spesa"), "il latte") == ToolCall("LISTA", "della spesa|il latte")
    assert intent.slot_cancelled("no, lascia stare") and intent.slot_cancelled("niente") and not intent.slot_cancelled("domani")
    assert intent.list_followup("e aggiungi anche le uova", "della spesa") == ToolCall("LISTA", "della spesa|le uova")
    assert intent.list_followup("anche il pane", "della spesa") == ToolCall("LISTA", "della spesa|il pane")
    assert intent.list_followup("metti il latte nel calendario", "della spesa") is None


def test_generated_small_talk_never_triggers_a_tool():
    """288 frasi di chiacchiera (musica, volume, calendario, ricordi, mappe, app, cucina, lavoro…) scritte da un altro chatbot: nessuna e' una richiesta."""
    import json
    import os
    sentences = json.load(open(os.path.join(os.path.dirname(__file__), "chat_sentences.json"), encoding="utf-8"))
    assert len(sentences) > 200
    fired = [(t, intent.detect(t, FILES)) for t in sentences]
    fired = [(t, c.name) for t, c in fired if c is not None]
    assert not fired, fired


def test_chit_chat_never_gets_the_honest_not_understood_guard():
    """La guardia («non ho capito cosa vuoi che faccia») scatta solo per vere richieste d'azione: mai per la chiacchiera."""
    import json
    import os
    sentences = json.load(open(os.path.join(os.path.dirname(__file__), "chat_sentences.json"), encoding="utf-8")) + NEG
    hit = [(t, intent.unmatched_action(t, FILES)) for t in sentences]
    assert not [(t, g) for t, g in hit if g], [(t, g) for t, g in hit if g]


def test_unmatched_requests_get_an_honest_answer_with_an_example():
    assert "Cancellare" in intent.unmatched_action("Cancella il promemoria del caffè")
    assert "Cancellare" in intent.unmatched_action("Togli l'evento di domani")
    assert "musica" in intent.unmatched_action("Crea una playlist di canzoni tristi")
    assert intent.unmatched_action("Metti la pasta a bollire") is None and intent.unmatched_action("Che musica ti piace?") is None
