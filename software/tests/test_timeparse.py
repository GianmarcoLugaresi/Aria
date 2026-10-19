"""Date e orari detti a voce: «domani alle nove e mezza», «lunedì alle 15», «tra due giorni»..."""
import datetime as dt

import pytest

from aria.timeparse import parse_when, say_when, to_int

NOW = dt.datetime(2026, 10, 6, 12, 0)                 # martedì 6 ottobre 2026, mezzogiorno


def w(text, now=NOW):
    r = parse_when(text, now)
    return None if r is None else (r.dt.strftime("%Y-%m-%d %H:%M"), r.has_time, r.has_date, r.rest)


def test_number_words():
    assert [to_int(x) for x in ("nove", "dodici", "ventitre", "trentacinque", "quarantuno", "15", "venti")] == [9, 12, 23, 35, 41, 15, 20]
    assert to_int("pizza") is None


def test_tomorrow_and_the_time():
    assert w("ricordami domani alle 9 di chiamare Marco") == ("2026-10-07 09:00", True, True, "ricordami di chiamare Marco")
    assert w("domani alle nove e mezza") == ("2026-10-07 09:30", True, True, "")
    assert w("domani alle 15:45") == ("2026-10-07 15:45", True, True, "")
    assert w("dopodomani alle dieci meno un quarto")[0] == "2026-10-08 09:45"
    assert w("domani") == ("2026-10-07 09:00", False, True, "")                   # senza ora: 9 (predefinita), segnalato


def test_hours_without_am_pm_follow_the_everyday_rule():
    assert w("oggi alle 5")[0] == "2026-10-06 17:00"           # le 5 = pomeriggio
    assert w("domani alle 8")[0] == "2026-10-07 08:00" and w("domani alle 11")[0] == "2026-10-07 11:00"
    assert w("domani alle 5 di mattina")[0] == "2026-10-07 05:00"
    assert w("domani alle 9 di sera")[0] == "2026-10-07 21:00" and w("domani alle 11 di notte")[0] == "2026-10-07 23:00"
    assert w("domani alle 3 del pomeriggio")[0] == "2026-10-07 15:00" and w("domani alle 12")[0] == "2026-10-07 12:00"


def test_dayparts_and_special_words():
    assert w("stasera")[:3] == ("2026-10-06 20:00", False, True)
    assert w("domani mattina")[:3] == ("2026-10-07 09:00", False, True) and w("domani pomeriggio")[0] == "2026-10-07 15:00"
    assert w("domani a mezzogiorno") == ("2026-10-07 12:00", True, True, "")      # (prima nel testo del promemoria restava una «a»)
    assert w("domani a mezzanotte")[0] == "2026-10-07 00:00"
    assert w("stamattina", dt.datetime(2026, 10, 6, 7, 0))[0] == "2026-10-06 09:00"


def test_weekdays_dates_and_relative():
    assert w("lunedì alle 15") == ("2026-10-12 15:00", True, True, "")             # martedì -> il prossimo lunedì
    assert w("martedì alle 10")[0] == "2026-10-13 10:00"                           # oggi e' martedì: quello dopo
    assert w("il 15 ottobre alle 18")[0] == "2026-10-15 18:00" and w("il 3 settembre")[0] == "2027-09-03 09:00"
    assert w("il 20/10 alle 9")[0] == "2026-10-20 09:00"
    assert w("il 15 alle 9")[0] == "2026-10-15 09:00" and w("il 2 alle 9")[0] == "2026-11-02 09:00"       # il 2 e' passato: il mese dopo
    assert w("tra due giorni")[:3] == ("2026-10-08 09:00", False, True)
    assert w("tra 3 giorni alle 18")[:2] == ("2026-10-09 18:00", True)
    assert w("tra venti minuti")[:2] == ("2026-10-06 12:20", True) and w("tra due ore")[0] == "2026-10-06 14:00"
    assert w("tra una settimana")[0] == "2026-10-13 09:00" and w("tra mezz'ora")[0] == "2026-10-06 12:30" and w("tra un quarto d'ora")[0] == "2026-10-06 12:15"


def test_time_only_already_passed_means_tomorrow():
    assert w("alle 9", dt.datetime(2026, 10, 6, 10, 0))[0] == "2026-10-07 09:00"         # le 9 sono passate
    assert w("alle 17", dt.datetime(2026, 10, 6, 10, 0))[0] == "2026-10-06 17:00"


def test_nothing_to_find_and_the_rest_is_kept():
    assert w("comprare il pane") is None and w("chiama Marco") is None
    assert w("metti in calendario cena con Marco venerdì alle 20") == ("2026-10-09 20:00", True, True, "metti in calendario cena con Marco")
    assert w("che ore sono") is None
    assert w("appuntamento con il dentista il 15 ottobre alle 10 e mezza")[:2] == ("2026-10-15 10:30", True)
    assert w("Domani alle 9: Chiamare Marco Rossi")[3] == "Chiamare Marco Rossi"


@pytest.mark.parametrize("when,has_time,expected", [
    (dt.datetime(2026, 10, 6, 15, 0), True, "oggi alle quindici"),
    (dt.datetime(2026, 10, 7, 9, 30), True, "domani alle nove e mezza"),
    (dt.datetime(2026, 10, 8, 18, 15), True, "dopodomani alle diciotto e un quarto"),
    (dt.datetime(2026, 10, 12, 1, 0), True, "lunedì all'una"),
    (dt.datetime(2026, 10, 20, 12, 0), True, "martedì venti ottobre a mezzogiorno"),
    (dt.datetime(2026, 10, 7, 9, 0), False, "domani"),
    (dt.datetime(2026, 10, 7, 0, 0), True, "domani a mezzanotte"),
    (dt.datetime(2026, 10, 7, 9, 7), True, "domani alle nove e sette"),
])
def test_say_when(when, has_time, expected):
    assert say_when(when, has_time, NOW) == expected


def test_vague_moments_of_the_day_and_three_quarters_of_an_hour():
    import datetime as dt
    from aria.timeparse import parse_when
    now = dt.datetime(2026, 10, 8, 6, 30)
    for text, when in (("dopo pranzo", dt.datetime(2026, 10, 8, 14, 0)), ("domani dopo cena", dt.datetime(2026, 10, 9, 21, 30)), ("fra tre quarti d'ora", dt.datetime(2026, 10, 8, 7, 15)),
                       ("tra un quarto d'ora", dt.datetime(2026, 10, 8, 6, 45)), ("domani prima di pranzo", dt.datetime(2026, 10, 9, 12, 0))):
        w = parse_when(text, now)
        assert w is not None and w.dt == when and w.has_time, text


def test_half_hours_and_minutes_after_a_relative_hour_are_not_lost():
    """«ricordami tra un'ora e mezza» metteva il promemoria tra UN'ora (e nel testo restava «e mezza»)."""
    assert w("ricordami tra un'ora e mezza di uscire") == ("2026-10-06 13:30", True, True, "ricordami di uscire")
    assert w("tra 2 ore e mezza")[0] == "2026-10-06 14:30" and w("tra un'ora e un quarto")[0] == "2026-10-06 13:15"
    assert w("tra 1 ora e 20 minuti")[0] == "2026-10-06 13:20" and w("tra 2 ore e tre quarti")[0] == "2026-10-06 14:45"
    assert w("tra due ore")[0] == "2026-10-06 14:00"


def test_tonight_at_two_said_in_the_evening_is_the_coming_night_and_feb_29_finds_a_leap_year():
    sera = dt.datetime(2026, 10, 9, 22, 30)
    assert w("stanotte alle 2 di svegliarmi", sera)[:2] == ("2026-10-10 02:00", True)
    assert w("stanotte a mezzanotte", sera)[0] == "2026-10-10 00:00"
    assert w("stanotte alle 23", sera)[0] == "2026-10-09 23:00"
    assert w("il 29 febbraio", sera)[0] == "2028-02-29 09:00"
