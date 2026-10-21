"""Le piccole cose di tutti i giorni in INGLESE: date relative, conversioni, memoria detta bene, cosa Aria impara."""
import datetime as dt
import os
import tempfile

import pytest

from aria import everyday_en as E
from aria import intent, learn, memory

NOW = dt.datetime(2026, 10, 21, 14, 30)               # mercoledi' 21 ottobre 2026


@pytest.fixture(autouse=True)
def _en(english):
    pass


@pytest.mark.parametrize("text,expected", [
    ("what day is it tomorrow", "Tomorrow is Thursday, October twenty-second."),
    ("what's the date tomorrow", "Tomorrow is Thursday, October twenty-second."),
    ("what day was it yesterday", "Yesterday was Tuesday, October twentieth."),
    ("what's the date next Friday", "Next Friday is October twenty-third."),
    ("what day was last Monday", "Last Monday was October nineteenth."),
    ("what day is the day after tomorrow", "The day after tomorrow is Friday, October twenty-third."),
    ("what day will it be in 10 days", "It will be Saturday, October thirty-first."),
    ("how many days until Christmas", "There are 65 days to go: it will be Friday, December twenty-fifth."),
])
def test_date_questions(text, expected):
    assert E.date_kind(text), text
    assert E.date_answer(text, NOW) == expected
    assert intent.detect(text).name == "DATA"


def test_today_is_the_clock_not_a_date_calculation():
    for t in ("what day is it today", "what's today's date", "what's the date"):
        assert not E.date_kind(t) and intent.detect(t).name == "ORA", t


def test_pounds_of_weight_are_not_sterling():
    assert E.conversion_kind("how many pounds is 5 kilograms") == "unita"
    assert E.convert("how many pounds is 5 kilograms") == "5 kilograms is 11.02 pounds."
    assert E.conversion_kind("how much is 20 pounds sterling in euros") == "valuta"
    assert E.conversion_kind("how many euros is 50 dollars") == "valuta"


def test_timer_names():
    for text, arg in (("set a timer for ten minutes for the pasta", "ten minutes | pasta"), ("set a timer called pizza for 5 minutes", "5 minutes | pizza"),
                      ("timer for 20 minutes for my tea", "20 minutes | tea"), ("set a timer for 10 minutes", "10 minutes")):
        assert intent.detect(text).arg == arg, text


def test_memory_speaks_to_the_user_in_the_second_person():
    from aria.memory import Memory, person
    assert person("my dog is called Max") == "your dog is called Max" and person("I'm vegetarian") == "you're vegetarian"
    assert person("I was born in Turin") == "you were born in Turin" and person("I don't drink alcohol", "they") == "they don't drink alcohol"
    assert person("Is vegetarian") == "you're vegetarian" and person("Works as a nurse") == "you work as a nurse" and person("Their sister is called Laura") == "your sister is called Laura"
    assert person("Broke up with their girlfriend (said on October 21)") == "you broke up with your girlfriend" and person("Has two kids") == "you have two kids"
    m = Memory(os.path.join(tempfile.mkdtemp(), "m.db"))
    m.set_profile("name", "Anna")
    for f in ("my dog is called Max", "I'm vegetarian", "Is vegetarian"):
        m.add_fact(f)
    said = m.describe()
    assert said.startswith("I know that your name is Anna.") and "your dog is called Max" in said and "i'm" not in said and said.count("you're vegetarian") == 1


def test_what_aria_learns_without_leaving_half_sentences():
    got = lambda t: [f.text for f in learn.extract(t, NOW)]
    assert got("I have a dentist appointment on Friday at 3") == ["Friday, October 23: Has a dentist appointment"]
    assert got("I don't drink alcohol") == ["Doesn't drink alcohol"]
    assert got("I'm vegetarian") == ["Is vegetarian"] and got("my dog is called Max") == ["Their dog is called Max"]
    assert got("I'm tired") == [] and got("my name is not important") == []
