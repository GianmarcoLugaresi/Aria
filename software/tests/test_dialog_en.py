"""Gli atti della conversazione in inglese: saluti, thanks, ok, repeat, complaints, voce."""
import datetime as dt

import pytest

from aria import dialog


@pytest.mark.parametrize("text", ["Hi", "hello Aria", "Good morning", "hey there", "Hi, Aria!", "hey"])
def test_greetings(english, text):
    assert dialog.is_greeting(text)


@pytest.mark.parametrize("text", ["Thanks", "thank you so much", "Thanks a lot, Aria", "cheers", "you're the best", "That's very kind of you", "Great, thanks!", "much appreciated"])
def test_thanks(english, text):
    assert dialog.is_thanks(text)


@pytest.mark.parametrize("text", ["ok", "okay", "got it", "I see", "alright", "makes sense", "sounds good", "uh huh", "ah okay", "perfect", "fair enough"])
def test_acks(english, text):
    assert dialog.is_ack(text)


@pytest.mark.parametrize("text", ["bye", "goodbye Aria", "see you tomorrow", "good night", "talk to you later", "I'm off", "that's all", "that's it, thanks", "I have to go", "take care",
                                   "have a good one", "nothing else", "I'm done"])
def test_farewells(english, text):
    assert dialog.is_farewell(text)


@pytest.mark.parametrize("text", ["what", "sorry?", "can you repeat that", "say that again", "I didn't catch that", "pardon", "come again?", "what did you say", "once more", "I didn't hear that"])
def test_repeat_requests(english, text):
    assert dialog.is_repeat_request(text)


@pytest.mark.parametrize("text", ["haha", "hahaha", "lol", "that's funny", "you made me laugh", "ha ha ha"])
def test_laughs(english, text):
    assert dialog.is_laugh(text)


@pytest.mark.parametrize("text", ["go to sleep", "shut down", "turn yourself off", "go into the background", "that will be all for now", "you can rest now", "stand by", "please go away now"])
def test_dismissals(english, text):
    assert dialog.is_dismissal(text)


@pytest.mark.parametrize("text", ["are you there", "can you hear me", "Aria", "you still there", "hello?"])
def test_presence_checks(english, text):
    assert dialog.is_presence_check(text)


@pytest.mark.parametrize("text", ["sorry", "my bad", "oops", "I'm sorry", "excuse me"])
def test_apologies(english, text):
    assert dialog.is_apology(text)


@pytest.mark.parametrize("text,kind", [("you're mumbling", "voice"), ("I can't understand you", "voice"), ("you talk too fast", "voice"), ("you froze again", "glitch"), ("you're so slow", "glitch"),
                                       ("you keep freezing", "glitch"), ("you didn't understand", "wrong"), ("that's not what I said", "wrong"), ("that makes no sense", "wrong")])
def test_complaints(english, text, kind):
    assert dialog.complaint_kind(text) == kind


@pytest.mark.parametrize("text", ["what's the weather like", "set a timer for ten minutes", "thanks for the weather, now tell me the time", "good point about the weather and also the news"])
def test_requests_are_not_dialog_acts(english, text):
    assert not (dialog.is_greeting(text) or dialog.is_thanks(text) or dialog.is_ack(text) or dialog.is_farewell(text) or dialog.is_repeat_request(text) or dialog.is_dismissal(text))


@pytest.mark.parametrize("text,expected", [("change your voice", ("cycle", "")), ("use the natural voice", ("natural_on", "")), ("go back to the old voice", ("natural_off", "")),
                                            ("use the voice jane", ("set", "jane")), ("switch to george", ("set", "george")), ("use a male voice", ("set", "george")), ("use a female voice", ("set", "alba"))])
def test_voice_requests(english, text, expected):
    assert dialog.voice_request(text) == expected


def test_unfinished_sentences(english):
    assert dialog.looks_unfinished("I wanted to ask you about the")
    assert dialog.looks_unfinished("so, um,")
    assert dialog.looks_unfinished("remind me to call and")
    assert not dialog.looks_unfinished("What's the weather like today?")
    assert not dialog.looks_unfinished("Set a timer for ten minutes.")
    assert not dialog.looks_unfinished("okay")
    for done in ("what time is it", "thank you", "how are you", "where are you from", "what is it for", "I love you", "so do I", "what should I do", "I think so", "hold on"):
        assert not dialog.looks_unfinished(done), done                          # finiscono con una parola che chiude la frase: non si aspetta altro
    for open_ in ("I want to", "my sister and", "I was wondering if", "tell her that the"):
        assert dialog.looks_unfinished(open_), open_


def test_replies_are_english_and_nonempty(english):
    now = dt.datetime(2026, 10, 21, 22, 30)
    assert dialog.farewell_reply(now, "Mark", "bye").startswith(("Have a good evening", "Talk to you later", "Bye", "Catch you later"))
    assert dialog.greeting(now, "Mark", None)
    assert dialog.thanks_reply() and dialog.unclear_reply() and dialog.presence_reply() and dialog.apology_reply() and dialog.laugh_reply()
    assert dialog.repeat_reply("It is sunny.").endswith("It is sunny.")
    assert dialog.complaint_reply("voice")
    assert "?" in dialog.greeting_and_name(now)
    assert dialog.dismiss_replies()[0].startswith("Okay")


def test_italian_is_untouched_by_the_english_rules():
    assert dialog.is_thanks("grazie mille") and dialog.is_farewell("ciao a presto") and not dialog.is_thanks("thank you")
