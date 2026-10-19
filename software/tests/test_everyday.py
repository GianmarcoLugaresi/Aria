"""Conversioni, date, dado e moneta, «cosa sai fare?»: risposte locali e certe (un chatbot piccolo qui inventa), e le frasi che le fanno partire."""
import datetime as dt
import random

import pytest

from aria import everyday, intent
from aria.textutil import ToolCall
from aria.tools import safe_eval

NOW = dt.datetime(2026, 10, 8, 5, 50)


@pytest.mark.parametrize("text,out", [
    ("Quanti chilometri sono 10 miglia?", "10 miglia sono 16 virgola zero 9 chilometri."),
    ("Quanti gradi Fahrenheit sono 20 gradi Celsius?", "20 gradi Celsius sono 68 gradi Fahrenheit."),
    ("Converti 5 chili in libbre", "5 chili sono 11 virgola zero 2 libbre."),
    ("Quanti centimetri sono 3 pollici?", "3 pollici sono 7 virgola 62 centimetri."),
    ("Quanti grammi sono due etti?", "2 etti sono 200 grammi."),
    ("Quante ore sono 3 giorni?", "3 giorni sono 72 ore."),
    ("Quanti litri sono mezzo gallone", "0 virgola 5 galloni sono 1 virgola 89 litri."),
    ("Converti 2,5 chili in grammi", "2 virgola 5 chili sono 2500 grammi."),
])
def test_unit_conversions(text, out):
    c = intent.detect(text, [])
    assert c is not None and c.name == "CONVERTI", (text, c)
    assert everyday.convert(c.arg) == out


def test_currency_is_searched_not_invented_and_other_talk_is_not_a_conversion():
    assert intent.detect("Quanti euro sono 50 dollari?").name == "CERCA"
    for t in ("Ho aspettato 10 minuti in più", "Mi piacciono i gatti", "Vorrei 3 mele e 2 pere"):
        c = intent.detect(t, [])
        assert c is None or c.name != "CONVERTI", t


def test_decimals_are_not_eaten():
    for text, expr, val in (("Quanto fa 2,5 per 4?", "2.5*4", 10), ("quanto fa due virgola cinque per quattro", "2.5*4", 10), ("Quanto fa 1.000 più 2,5?", "1000+2.5", 1002.5),
                            ("quanto fa 7,5 diviso 2", "7.5/2", 3.75)):
        c = intent.detect(text, [])
        assert c == ToolCall("CALCOLA", expr) and safe_eval(c.arg) == val, (text, c)


@pytest.mark.parametrize("text,out", [
    ("Quanti giorni mancano a Natale?", "Mancano 78 giorni: sarà venerdì venticinque dicembre."),
    ("Quanti giorni mancano al 25 aprile?", "Mancano 199 giorni: sarà domenica venticinque aprile duemilaventisette."),
    ("Quanti giorni mancano alla fine dell'anno?", "Mancano 84 giorni: sarà giovedì trentuno dicembre."),
    ("Che giorno sarà tra dieci giorni?", "Sarà domenica diciotto ottobre."),
    ("Che data sarà tra due settimane?", "Sarà giovedì ventidue ottobre."),
    ("Che giorno era 40 giorni fa?", "Era sabato ventinove agosto."),
    ("Quando è Pasqua nel 2027?", "Pasqua cade domenica ventotto marzo duemilaventisette."),
    ("Quando è Pasqua quest'anno?", "Pasqua è caduta domenica cinque aprile."),
    ("Che giorno della settimana è il 25 dicembre 2026?", "Venerdì venticinque dicembre."),
    ("Quanti giorni ci sono tra il primo gennaio e il 14 febbraio?", "Ci sono quarantaquattro giorni."),
    ("Quanti giorni sono passati dal 1 settembre?", "Sono passati trentasette giorni."),
    ("Che settimana dell'anno è?", "Siamo nella settimana numero quarantuno dell'anno."),
    ("Quanti anni ho se sono nato nel 1990?", "Hai trentasei anni, oppure trentacinque se il compleanno quest'anno deve ancora arrivare."),
])
def test_date_questions(text, out):
    c = intent.detect(text, [])
    assert c is not None and c.name == "DATA", (text, c)
    assert everyday.date_answer(c.arg, NOW) == out


def test_ordinary_date_and_time_questions_still_go_to_the_clock():
    assert intent.detect("Che giorno è oggi?") == ToolCall("ORA", "data") and intent.detect("Che ore sono?") == ToolCall("ORA", "ora")


def test_dice_coin_and_picks():
    rng = random.Random(3)
    assert intent.detect("Tira un dado").name == "CASO" and intent.detect("Lancia una moneta").name == "CASO" and intent.detect("Testa o croce?").name == "CASO"
    assert everyday.chance_answer("Tira un dado", rng).startswith("È uscito ")
    assert everyday.chance_answer("Tira due dadi", rng).startswith("Sono usciti ")
    assert everyday.chance_answer("Lancia una moneta", rng) in ("È uscita testa.", "È uscita croce.")
    for _ in range(30):
        n = int(everyday.chance_answer("Scegli un numero da uno a dieci", rng).split()[-1].strip("."))
        assert 1 <= n <= 10
    assert everyday.chance_answer("Scegli tra pizza e sushi", rng) in ("Scelgo pizza.", "Scelgo sushi.")


def test_what_can_you_do_lists_only_what_is_on_and_says_what_she_cannot_do():
    for t in ("Cosa sai fare?", "Aiuto", "Come funzioni?", "A cosa servi?", "Cosa puoi fare per me?"):
        assert intent.detect(t, []) == ToolCall("AIUTO", ""), t
    full = everyday.help_text({})
    assert "calendario" in full and "musica" in full and "Non so telefonare" in full
    off = everyday.help_text({"music": False, "reminders": False, "calendar": False, "apps": False})
    assert "musica" not in off and "calendario" not in off


def test_speaking_louder_or_softer_is_the_volume_and_speed_is_honestly_refused():
    for text, call in (("Parla più forte", ToolCall("VOLUME", "up")), ("Parla più piano", ToolCall("VOLUME", "down")), ("Non ti sento", ToolCall("VOLUME", "up")),
                       ("Puoi parlare più forte?", ToolCall("VOLUME", "up")), ("Parla più lentamente", ToolCall("NON_SO", "speed")), ("Parla più veloce", ToolCall("NON_SO", "speed"))):
        assert intent.detect(text, []) == call, text
    assert intent.detect("Ho parlato con mia madre più forte del solito", []) is None


def test_compound_quantities_and_the_sun():
    c = intent.detect("Quanti centimetri sono due metri e mezzo?", [])
    assert c.name == "CONVERTI" and everyday.convert(c.arg) == "2 virgola 5 metri sono 250 centimetri." or "250" in everyday.convert(c.arg)
    c = intent.detect("Quanti minuti ci sono in due ore e mezza?", [])
    assert c.name == "CONVERTI" and "150 minuti" in everyday.convert(c.arg)
    assert intent.detect("Quanto tempo manca alla sveglia?", []).name == "TIMER_STATO"                  # non e' una data
    assert intent.detect("Quanto manca a Ferragosto?", []).name == "DATA"
    assert intent.detect("Quanto fa 12 al quadrato?", []) == ToolCall("CALCOLA", "12*12")
    assert intent.detect("A che ora tramonta il sole?", []) == ToolCall("METEO", "@sole oggi")
    assert intent.detect("A che ora fa buio a Roma?", []) == ToolCall("METEO", "@sole Roma oggi")
    assert intent.detect("Che ore sono?", []) == ToolCall("ORA", "ora")


def test_the_weather_day_is_understood_not_silently_replaced_by_today():
    import datetime as dt
    thu = dt.date(2026, 10, 8)
    assert everyday.forecast_when("Roma domani", thu)[:2] == ([1], "Domani")
    assert everyday.forecast_when("dopodomani", thu)[:2] == ([2], "Dopodomani")
    assert everyday.forecast_when("Roma sabato", thu) == ([2], "Sabato", "Roma")
    assert everyday.forecast_when("nel weekend", thu)[0] == [2, 3]
    assert everyday.forecast_when("Milano tra tre giorni", thu) == ([3], "Tra 3 giorni", "Milano")
    assert everyday.forecast_when("tra due settimane", thu)[0] == [14]
    assert everyday.forecast_when("il 3 novembre", thu)[0] is None                      # oltre i quindici giorni lo dice
    assert everyday.forecast_when("oggi", thu)[0] == [0]
    assert everyday.when_phrase("Che tempo farà sabato a Roma?") == "sabato" and everyday.when_phrase("A che ora tramonta il sole domani?") == "domani"
    assert intent.detect("Che tempo farà sabato a Roma?", []) == ToolCall("METEO", "Roma sabato")
    assert intent.detect("Che tempo farà tra tre giorni a Milano?", []) == ToolCall("METEO", "Milano tra tre giorni")
    assert intent.detect("A che ora tramonta il sole domani?", []) == ToolCall("METEO", "@sole domani")


def test_the_agenda_keeps_the_day_that_was_asked():
    for text, arg in (("Che impegni ho il 15 ottobre?", "il 15 ottobre"), ("Cosa ho tra tre giorni?", "tra tre giorni"), ("Cosa ho nel weekend?", "weekend"),
                      ("Cosa ho fra due settimane?", "fra due settimane"), ("Sono libero il primo novembre?", "il primo novembre"), ("Cosa ho dopodomani?", "dopodomani")):
        assert intent.detect(text, []) == ToolCall("AGENDA", arg), text
    from aria.timeparse import parse_when
    now = dt.datetime(2026, 10, 8, 6, 0)
    assert parse_when("15 ottobre", now).dt.date() == dt.date(2026, 10, 15) and parse_when("il primo novembre", now).dt.date() == dt.date(2026, 11, 1)
    assert intent.detect("Cosa ho da fare?", []).name == "BRIEFING"


def test_translation_requests_and_the_dedicated_translator():
    import asyncio
    from aria.tools import Tools
    from aria.config import load
    for text, call in (("Traduci buongiorno a tutti in inglese", ToolCall("TRADUCI", "inglese|buongiorno a tutti")), ("Come si dice ciao in francese?", ToolCall("TRADUCI", "francese|ciao")),
                       ("Traduci in spagnolo: dove si trova la stazione", ToolCall("TRADUCI", "spagnolo|dove si trova la stazione")), ("In inglese come si dice grazie mille?", ToolCall("TRADUCI", "inglese|grazie mille")),
                       ("Traduci questa frase in inglese: buongiorno a tutti", ToolCall("TRADUCI", "inglese|buongiorno a tutti")), ("Mi traduci 'mi piace il gelato' in tedesco?", ToolCall("TRADUCI", "tedesco|mi piace il gelato"))):
        assert intent.detect(text, []) == call, text
    for text in ("Mi piace l'inglese", "Parlo inglese e francese", "Come si dice questo?"):
        assert intent.detect(text, []) is None, text

    async def go():
        t = Tools(load())
        seen = []

        async def gen(system, user, max_tokens=300, temperature=None):
            seen.append((system, user, temperature))
            return '"Good morning everyone"\nNota: ...'
        t.generate = gen
        out = await t.run(ToolCall("TRADUCI", "inglese|buongiorno a tutti"))
        assert out == "In inglese: Good morning everyone." and seen[0][2] == 0.0 and "Lingua: inglese" in seen[0][1]
        assert "non so scrivere" in await t.run(ToolCall("TRADUCI", "giapponese|ciao"))
    asyncio.run(go())


def test_weather_for_the_week_and_the_next_days_keeps_the_city_name_clean():
    """«questa settimana a Torino» diventava le previsioni di oggi per la citta' «questa settimana Torino» (e «prossimi giorni» restava nel nome)."""
    import datetime as dt
    from aria import everyday as E
    today = dt.date(2026, 10, 9)
    assert E.forecast_when("questa settimana a Torino", today) == (list(range(7)), "Questa settimana", "a Torino")
    offs, label, rest = E.forecast_when("che tempo fa la prossima settimana a Roma", today)
    assert offs[0] == 3 and len(offs) == 7 and label == "La prossima settimana" and "settimana" not in rest
    assert E.forecast_when("prossimi giorni a Milano", today) == ([1, 2, 3], "Nei prossimi giorni", "a Milano")
