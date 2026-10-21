"""Date e orari detti a voce in INGLESE («tomorrow at nine», «in half an hour», «next Friday at noon»): ogni riga e' stata controllata a mano."""
import datetime as dt

import pytest

from aria import timeparse

NOW = dt.datetime(2026, 10, 21, 14, 30)                  # mercoledi' 21 ottobre 2026, 14:30


@pytest.fixture(autouse=True)
def _en(english):
    pass


CASES = [
    # (frase, quando atteso, ha l'ora detta, resto della frase)
    ("tomorrow at nine", "2026-10-22 09:00", True, ""),
    ("tomorrow at 9 am", "2026-10-22 09:00", True, ""),
    ("tomorrow at nine thirty", "2026-10-22 09:30", True, ""),
    ("next Monday at 3 pm", "2026-10-26 15:00", True, ""),
    ("this Friday at noon", "2026-10-23 12:00", True, ""),
    ("on Saturday", "2026-10-24 09:00", False, ""),
    ("in two hours", "2026-10-21 16:30", True, ""),
    ("in half an hour", "2026-10-21 15:00", True, ""),
    ("in 45 minutes", "2026-10-21 15:15", True, ""),
    ("in an hour and a half", "2026-10-21 16:00", True, ""),
    ("in 2 weeks", "2026-11-04 09:00", False, ""),
    ("in three days", "2026-10-24 09:00", False, ""),
    ("tonight at eight", "2026-10-21 20:00", True, ""),
    ("tonight at 11", "2026-10-21 23:00", True, ""),
    ("tomorrow morning", "2026-10-22 09:00", False, ""),
    ("tomorrow morning at 8", "2026-10-22 08:00", True, ""),
    ("tomorrow afternoon at 3", "2026-10-22 15:00", True, ""),
    ("tomorrow night at 10", "2026-10-22 22:00", True, ""),                      # «night» + 10 = le 22, non le 10 del mattino
    ("this evening at 6", "2026-10-21 18:00", True, ""),
    ("at 5", "2026-10-21 17:00", True, ""),
    ("at 7", "2026-10-21 19:00", True, ""),                                       # le 7 sono gia' passate: sono le 19 di oggi, non le 7 di domani
    ("at 2", "2026-10-22 14:00", True, ""),                                       # le 14 sono passate (14:30) e le 2 di notte no: domani alle 14
    ("at 9 am", "2026-10-22 09:00", True, ""),                                    # con «am» e' domani
    ("at 7 o'clock", "2026-10-21 19:00", True, ""),
    ("at five thirty pm", "2026-10-21 17:30", True, ""),
    ("at a quarter past six", "2026-10-21 18:15", True, ""),
    ("at half past three", "2026-10-21 15:30", True, ""),
    ("twenty to nine tomorrow", "2026-10-22 08:40", True, ""),
    ("at 11:45 pm", "2026-10-21 23:45", True, ""),
    ("at midnight", "2026-10-22 00:00", True, ""),
    ("tomorrow at noon", "2026-10-22 12:00", True, ""),
    ("on the 3rd of November at 10", "2026-11-03 10:00", True, ""),
    ("November 3rd at 10 am", "2026-11-03 10:00", True, ""),
    ("on December 25th", "2026-12-25 09:00", False, ""),
    ("the day after tomorrow at 7", "2026-10-23 07:00", True, ""),
    ("next week", "2026-10-28 09:00", False, ""),
    ("next month", "2026-11-21 09:00", False, ""),
    ("this weekend", "2026-10-24 09:00", False, ""),
    ("remind me at seven o'clock to call mom", "2026-10-21 19:00", True, "remind me to call mom"),
    ("call Mark next week at 10", "2026-10-28 10:00", True, "call Mark"),
]


@pytest.mark.parametrize("text,when,has_time,rest", CASES)
def test_when_is_understood(text, when, has_time, rest):
    w = timeparse.parse_when(text, NOW)
    assert w is not None, text
    assert w.dt.strftime("%Y-%m-%d %H:%M") == when and w.has_time is has_time and w.rest == rest, (text, w)


def test_phrases_without_a_time_are_not_invented():
    for t in ("remind me to call Mark", "what is the weather", "I like pizza", "buy milk", "set a timer"):
        assert timeparse.parse_when(t, NOW) is None, t


@pytest.mark.parametrize("text,seconds", [("ten minutes", 600), ("an hour and a half", 5400), ("half an hour", 1800), ("2 hours 30 minutes", 9000), ("45 seconds", 45),
                                           ("a quarter of an hour", 900), ("1.5 hours", 5400), ("one hour and ten minutes", 4200), ("ninety seconds", 90), ("a minute", 60),
                                           ("two and a half hours", 9000), ("three quarters of an hour", 2700)])
def test_durations(text, seconds):
    from aria.tools import parse_duration
    assert parse_duration(text) == seconds, text


def test_later_today_means_a_couple_of_hours_from_now_and_never_the_past():
    w = timeparse.parse_when("later today to email Anna", NOW)
    assert w.dt == dt.datetime(2026, 10, 21, 16, 30) and w.has_time and w.rest == "to email Anna"
    assert timeparse.parse_when("later to email Anna", NOW).dt == dt.datetime(2026, 10, 21, 16, 30)
    assert timeparse.parse_when("later today to email Anna", dt.datetime(2026, 10, 21, 8, 5)).dt == dt.datetime(2026, 10, 21, 10, 15)
    assert timeparse.parse_when("later today to email Anna", dt.datetime(2026, 10, 21, 21, 10)).dt == dt.datetime(2026, 10, 22, 9, 0)     # troppo tardi: domattina
