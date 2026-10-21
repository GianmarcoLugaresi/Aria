"""Il riconoscimento vocale in INGLESE: suggerimento a Whisper, allucinazioni, esitazioni e lingua passata al riconoscimento di Apple."""
import stat
import sys

import numpy as np
import pytest

from aria import stt
from aria.stt import AppleSTT


@pytest.fixture(autouse=True)
def _en(english):
    pass


def test_whisper_is_told_the_conversation_is_in_english():
    assert stt.prompt() == stt.PROMPT_EN and "English" in stt.prompt()


def test_english_hallucinations_on_silence_are_dropped():
    for junk in ("Thanks for watching!", "Please subscribe to the channel", "Subtitles by the Amara.org community", "Thank you for watching"):
        assert stt.clean_transcript(junk) == "", junk
    assert stt.clean_transcript("Thank you so much, Aria") == "Thank you so much, Aria"                       # un grazie vero resta
    assert stt.clean_transcript("yes yes yes yes yes yes") == ""


def test_english_hesitations_are_removed():
    assert stt.dedupe_repeats("Set a timer for the the pasta") == "Set a timer for the pasta"
    assert stt.dedupe_repeats("I I want to to go") == "I want to go"
    assert stt.dedupe_repeats("it is very very good") == "it is very very good"                                 # l'enfasi resta
    assert stt.dedupe_repeats("set a timer set a timer for ten minutes") == "set a timer for ten minutes"


async def test_apple_stt_is_started_with_the_language(tmp_path):
    p = tmp_path / "aria-apple-stt"
    p.write_text(f"#!{sys.executable}\nimport sys\nprint('READY', flush=True)\nfor line in sys.stdin:\n    print('R\\t' + ' '.join(sys.argv[1:]), flush=True)\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    s = AppleSTT({"helper": str(p)})
    assert s.locale == "en-US"
    assert await s.transcribe((np.sin(np.linspace(0, 600, 16000)) * 3000).astype(np.int16), 16000) == "--locale en-US"
    s.close()
    assert AppleSTT({"helper": str(p), "locale": "en-GB"}).locale == "en-GB"
