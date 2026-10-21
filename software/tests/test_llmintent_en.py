"""Decodificare una richiesta con il chatbot, in INGLESE: formato, strumenti ammessi e, soprattutto, niente dati inventati."""
import pytest

from aria import llmintent as L
from aria.textutil import ToolCall


@pytest.fixture(autouse=True)
def _en(english):
    pass


def test_the_prompt_is_in_english():
    system, user = L.prompt("  set a reminder for tomorrow ")
    assert system.startswith("You are the command decoder") and "Sentence: try to create a reminder" in system and user == "Sentence: set a reminder for tomorrow"


def test_parse_accepts_one_line_and_rejects_everything_else():
    assert L.parse("PROMEMORIA | tomorrow at nine call Mark") == ToolCall("PROMEMORIA", "tomorrow at nine call Mark")
    assert L.parse("MUSICA | track:relaxing\nuseless explanation") == ToolCall("MUSICA", "track:relaxing")
    assert L.parse("LISTA | shopping|eggs") == ToolCall("LISTA", "shopping|eggs")
    assert L.parse("`VOLUME | up`") == ToolCall("VOLUME", "up") and L.parse("Answer: AGENDA | tomorrow") == ToolCall("AGENDA", "tomorrow")
    assert L.parse("NONE") is None and L.parse("") is None and L.parse("Sure! Here is the reminder") is None
    assert L.parse("SCORCIATOIA | Goodnight") is None and L.parse("DELETE | everything") is None


def test_arguments_must_be_made_of_what_the_user_said():
    say = L.grounded
    assert say(ToolCall("PROMEMORIA", "tomorrow at nine call Mark"), "remind me tomorrow at 9 to call Mark")                    # «9» = «nine»
    assert say(ToolCall("PROMEMORIA", "tomorrow"), "try to create a reminder for tomorrow")
    assert say(ToolCall("TIMER", "ten minutes | pasta"), "set a timer of 10 minutes for the pasta")
    assert say(ToolCall("VOLUME", "set:40"), "put the volume at forty") and say(ToolCall("VOLUME", "up"), "louder")
    assert say(ToolCall("MUSICA", "track:relaxing"), "put on some relaxing music")
    assert not say(ToolCall("PROMEMORIA", "tomorrow at 10 grab a coffee"), "try to create a reminder for tomorrow")               # orario e motivo inventati
    assert not say(ToolCall("EVENTO", "October 6 2026 dentist"), "put the dentist in my calendar tomorrow")
    assert not say(ToolCall("NOTA", "remember to call Luke"), "make a note")


def test_the_decoder_can_route_to_the_everyday_tools_but_not_for_stories():
    assert L.plausible(ToolCall("DATA", "How many days until Valentine's Day"), "How many days until Valentine's Day")
    assert L.plausible(ToolCall("CASO", "x"), "Pick one of three colors at random")
    assert not L.plausible(ToolCall("CASO", "x"), "I rolled a die yesterday and I won")
    assert not L.plausible(ToolCall("CONVERTI", "x"), "I converted everything to miles")
    assert not L.plausible(ToolCall("PROMEMORIA", "x"), "yesterday I forgot to call Mark")
    assert L.plausible(ToolCall("VOLUME", "up"), "crank it up a bit")
    assert not L.plausible(ToolCall("VOLUME", "up"), "my sister plays the guitar")                                                # niente a che fare col volume: meglio non fare niente
    assert L.plausible(ToolCall("VOLUME", "up"), "turn the sound up")
    assert L.plausible(ToolCall("MUSICA", "pause"), "stop the tunes")
