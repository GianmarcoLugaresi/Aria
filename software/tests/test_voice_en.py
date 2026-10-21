"""Le piccole regole sulla voce, in INGLESE: interrompere Aria mentre parla, comando di stop, parole di riempimento, pezzi di frase per la voce."""
import pytest

from aria import bargein, textutil, voicecheck


@pytest.fixture(autouse=True)
def _en(english):
    pass


def test_the_user_can_interrupt_aria_in_english():
    spoken = "The weather in Rome tomorrow will be clear, with a high of nineteen degrees"
    assert bargein.interruption("wait a second", spoken) == "stop"
    assert bargein.interruption("stop", spoken) == "stop"
    assert bargein.interruption("hold on", spoken) == "stop"
    assert bargein.interruption("uh um hmm", spoken) is None                                  # solo esitazioni: nessuna interruzione
    assert bargein.interruption("the weather in Rome tomorrow", spoken) is None              # l'eco di Aria stessa
    assert bargein.interruption("can you also tell me about the weekend", spoken) == "talk"


def test_stop_command_in_english():
    for ok in ("stop", "Enough!", "be quiet", "That's enough", "OK stop", "stop talking", "quiet please"):
        assert textutil.is_stop_command(ok), ok
    for no in ("what is a stop sign", "the enough question", "turn the volume down", "set a timer"):
        assert not textutil.is_stop_command(no), no


def test_wake_phrase_works_the_same():
    assert textutil.matches_phrase("hey aria what time is it", "hey aria")
    assert textutil.matches_phrase("Hey, Aria!", "hey aria")
    assert not textutil.matches_phrase("hey maria how are you", "hey aria")


def test_fillers_are_not_words_for_the_voice_check():
    ok, _score, missing = voicecheck.score("Tomorrow at nine you have a meeting with Anna", "um tomorrow at nine you have a meeting with Anna")
    assert ok and missing == []
    ok, _score, missing = voicecheck.score("Tomorrow at nine you have a meeting with Anna", "tomorrow at nine you have a")
    assert not ok and missing


def test_long_sentences_break_at_english_conjunctions():
    text = "You have a meeting with Anna tomorrow morning and then lunch with your sister at one before the dentist at four"
    parts = voicecheck.split_long(text)
    assert len(parts) >= 2 and " ".join(p.rstrip(",") for p in parts) == text
    assert all(len(p) <= 75 for p in parts)


def test_wake_phrase_with_whisper_spellings_and_no_false_alarms():
    from aria.conversation import strip_wake
    for heard in ("Hey Aria", "Hey, Aria!", "Hay Aria", "Hey Area", "Hey Arya", "Hey Ariah", "Heyaria", "hey, aria, play some music"):
        assert textutil.matches_phrase(heard, "hey aria"), heard
    for heard in ("hey maria how are you", "the area is nice", "they are here", "hey there", "hey Mario", "hey Clara how are you", "Hey Daria", "hey Ilaria", "I said hey, Maria"):
        assert not textutil.matches_phrase(heard, "hey aria"), heard
    assert strip_wake("Hey Aria, what's the weather?", "hey aria") == "what's the weather?"
    assert strip_wake("Hey Aria,what is up", "hey aria") == "what is up"                       # (la virgola attaccata non mangia «what»)
    assert strip_wake("Hey Aria. Set a timer for ten minutes.", "hey aria") == "Set a timer for ten minutes."
    assert strip_wake("hello there", "hey aria") == "hello there"
