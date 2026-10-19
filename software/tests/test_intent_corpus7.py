"""Terza raccolta (tests/intent_corpus7.py, scritta di notte pensando a come si parla davvero): ogni richiesta va allo strumento giusto, la chiacchiera non fa partire niente."""
import pytest

from intent_corpus7 import FILES, NEG7, POS7
from aria import intent


@pytest.mark.parametrize("text,tools,parts", POS7)
def test_the_request_goes_to_the_right_tool(text, tools, parts):
    c = intent.detect(text, FILES, screen_on=True)
    assert c is not None and c.name in tools, (text, c)
    assert all(p in c.arg.lower() for p in parts), (text, c.arg, parts)


@pytest.mark.parametrize("text", NEG7)
def test_chitchat_starts_nothing(text):
    assert intent.detect(text, FILES, screen_on=True) is None, text
