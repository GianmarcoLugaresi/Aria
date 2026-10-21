"""Come si ripulisce, in INGLESE, quello che scrive il chatbot prima che venga detto."""
import pytest

from aria import style


@pytest.fixture(autouse=True)
def _en(english):
    pass


@pytest.mark.parametrize("written,cleaned", [
    ("As an AI language model, I don't have personal experiences, but I can help you with that.", "I don't have personal experiences, but I can help you with that."),
    ("As a virtual assistant, I can look that up for you.", "I can look that up for you."),
    ("Certainly! Here is the answer.", "Here is the answer."),
    ("Great question! Honestly, I'd say yes.", "Honestly, I'd say yes."),
    ("Absolutely! The weather will be nice tomorrow.", "The weather will be nice tomorrow."),
    ("Here you go. Let me know if you need anything else!", "Here you go."),
    ("Aria: Hello there.", "Hello there."),
    ("Ciao! How are you?", "Hi! How are you?"),
])
def test_assistant_boilerplate_goes_away(written, cleaned):
    assert style.clean_reply(written) == cleaned


def test_stage_directions_and_markdown_are_not_said():
    assert style.strip_markdown("*smiles* Hello there! *laughs* That's a great question.") == "Hello there! That's a great question."
    assert style.strip_markdown("**Bold** text and *emphasis* here.") == "Bold text and emphasis here."
    assert style.strip_markdown("# Title\nSome text.") == "Title. Some text."
    assert style.strip_markdown("- one\n- two") == "one. two"
    assert style.strip_markdown("(smiles) Fine.") == "Fine."


def test_italian_stage_directions_still_go_away_in_italian():
    from aria import i18n
    i18n.set_language("it")
    assert style.strip_markdown("*sorride* Ciao a tutti!") == "Ciao a tutti!"


@pytest.mark.parametrize("claim", [
    "Done, I've set a timer for ten minutes.", "I've added milk to your list.", "Okay, I saved it to your folder.", "I'll write the recipe in a file right away.",
    "I've created a reminder for tomorrow.", "Sure, I put it on your calendar.", "I just opened Safari for you.", "I turned the volume down.",
    "Here it is, I'm pointing at the button now.", "I've texted Luca.", "I called your mom.", "I've set an alarm for seven.", "All done, it's in your notes.",
    "I'm opening YouTube now.", "Done!", "Okay, I'm on it.", "All set.", "Sure, I'll remind you tomorrow.", "I ordered a pizza for you.", "Got it, done."])
def test_the_chatbot_claiming_an_action_that_never_ran_is_caught(claim):
    assert style.has_false_claim(claim), claim


@pytest.mark.parametrize("fine", [
    "I think a timer is a good idea.", "I can't set timers on my own, but you can ask me.", "You added milk to the list yesterday, right?", "That sounds like a lovely plan.",
    "I opened with a joke earlier.", "Want me to set a reminder?", "Done is better than perfect.", "The meeting is on your calendar tomorrow.", "I'm playing along.",
    "I'm starting to like this.", "Sure, a nap sounds good.", "Of course you can.", "Okay, that makes sense.", "All right, let's think about it.", "It's all set in stone, as they say.",
    "If you're done with the exam, you deserve a break.", "When I'm done thinking, I'll tell you.", "You've called me twice today.", "Sounds like you turned a corner.", "You did it, well done!"])
def test_ordinary_sentences_are_not_taken_for_false_claims(fine):
    assert not style.has_false_claim(fine), fine
