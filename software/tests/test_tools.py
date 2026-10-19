import asyncio
import datetime as dt

import httpx
import pytest

from aria.config import load
from aria.memory import Memory
from aria.textutil import ToolCall
from aria.tools import Tools, day_part, fmt_duration, it_number, now_it, parse_duration, safe_eval, speak_number


def test_numbers():
    assert [it_number(w) for w in ("tre", "dodici", "venti", "ventuno", "ventitré", "trentotto", "quarantacinque", "sessanta", "17")] \
        == [3, 12, 20, 21, 23, 38, 45, 60, 17]
    assert it_number("pizza") is None


@pytest.mark.parametrize("text,sec", [
    ("dieci minuti", 600), ("10 minuti", 600), ("un'ora e mezza", 5400), ("mezz'ora", 1800), ("un quarto d'ora", 900),
    ("2 ore e 30 minuti", 9000), ("trenta secondi", 30), ("venti minuti", 1200), ("un minuto", 60),
    ("un'ora e un quarto", 4500),
])
def test_parse_duration(text, sec):
    assert parse_duration(text) == sec


def test_parse_duration_none_and_format():
    assert parse_duration("tra poco") is None
    assert fmt_duration(5400) == "1 ora e 30 minuti" and fmt_duration(45) == "45 secondi"


def test_safe_eval():
    assert safe_eval("2+3*4") == 14 and safe_eval("(10-4)/3") == 2 and safe_eval("2^10") == 1024
    assert abs(safe_eval("sqrt(16)") - 4) < 1e-9 and safe_eval("15% * 200") == 30
    for bad in ("__import__('os').system('ls')", "2**9999", "a+b", "open('x')"):
        with pytest.raises(Exception):
            safe_eval(bad)
    assert speak_number(3.5) == "3 virgola 5" and speak_number(4.0) == "4"


def test_dates():
    n = dt.datetime(2026, 10, 6, 15, 7)
    assert now_it(n) == "martedì 6 ottobre 2026, ore 15:07"
    assert day_part(n) == "pomeriggio"


def mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_weather_and_wiki_and_search():
    def handler(req: httpx.Request):
        u = str(req.url)
        if "geocoding" in u:
            return httpx.Response(200, json={"results": [{"latitude": 41.9, "longitude": 12.5, "name": "Roma"}]})
        if "forecast" in u:
            return httpx.Response(200, json={"current": {"temperature_2m": 17.2, "weather_code": 3, "wind_speed_10m": 6},
                                             "daily": {"weather_code": [3, 61], "temperature_2m_max": [19, 15], "temperature_2m_min": [9, 8],
                                                       "precipitation_probability_max": [10, 70]}})
        if "opensearch" in u:
            return httpx.Response(200, json=["x", ["Canberra"], [], []])
        if "page/summary" in u:
            return httpx.Response(200, json={"extract": "Canberra è la capitale dell'Australia."})
        if "/search" in u:
            return httpx.Response(200, json={"results": [{"title": "Orari", "content": "Treni ogni 30 minuti"}]})
        return httpx.Response(404)

    cfg = load()
    cfg["tools"]["web_search"]["searxng_url"] = "http://searx.local"
    t = Tools(cfg, Memory(), client=mock_client(handler))
    w = await t.run(ToolCall("METEO", "Roma domani"))
    assert "Roma" in w and "domani" in w.lower() and "pioggia debole" in w and "70" in w and "tra 8 e 15 gradi" in w
    w2 = await t.run(ToolCall("METEO", ""))
    assert "oggi" in w2.lower() and "17" in w2
    assert "capitale dell'Australia" in await t.run(ToolCall("WIKI", "Canberra"))
    assert "Treni ogni 30 minuti" in await t.run(ToolCall("CERCA", "orari treni"))
    assert "14" in await t.run(ToolCall("CALCOLA", "2*7"))
    assert "sconosciuto" in await t.run(ToolCall("BOH", "x"))


async def test_offline_is_graceful():
    def boom(req):
        raise httpx.ConnectError("offline")
    t = Tools(load(), Memory(), client=mock_client(boom))
    assert "internet" in await t.run(ToolCall("METEO", ""))


async def test_timer_fires_callback():
    fired = []

    async def on_timer(label):
        fired.append(label)

    t = Tools(load(), Memory(), on_timer=on_timer, client=mock_client(lambda r: httpx.Response(200)))
    out = await t.run(ToolCall("TIMER", "30 secondi | pasta"))
    assert "30 secondi" in out and "pasta" in out and out.startswith("Timer impostato")
    for task in list(t.timers.values()):
        task.cancel()
    await asyncio.create_task(t._fire(99, 0, "pasta"))
    assert fired == ["pasta"]
    assert (await t.run(ToolCall("TIMER", "boh"))).startswith("@CHIEDI|TIMER|")                  # non capisce quanto: lo chiede


def test_intent_router_recognises_obvious_requests():
    from aria.intent import detect, number_it
    assert detect("Che tempo fa domani a Roma?") == ToolCall("METEO", "Roma domani")
    assert detect("che tempo fa domani?") == ToolCall("METEO", "domani")
    assert detect("Mettimi un timer di dieci minuti per la pasta") == ToolCall("TIMER", "dieci minuti | pasta")
    assert detect("Quanto fa centoventi diviso otto?") == ToolCall("CALCOLA", "120/8")
    assert detect("quanto fa 15 per 4") == ToolCall("CALCOLA", "15*4")
    assert detect("Chi è Leonardo da Vinci?") == ToolCall("WIKI", "Leonardo da Vinci")
    assert detect("cos'è la fotosintesi") == ToolCall("WIKI", "la fotosintesi")
    assert detect("Che ore sono?") == ToolCall("ORA", "ora")
    assert detect("che giorno è oggi") == ToolCall("ORA", "data")
    assert detect("Ricordati che mi piace il caffè lungo") == ToolCall("RICORDA", "mi piace il caffè lungo")
    for chat in ("Ciao come stai?", "mare o montagna?", "sono stanchissimo, riunioni tutto il giorno", "sei una persona vera?"):
        assert detect(chat) is None
    assert [number_it(x) for x in ("centoventi", "duecentotrentacinque", "mille", "tremilaquattrocento", "otto")] == [120, 235, 1000, 3400, 8]


def test_spoken_time_and_date():
    import datetime as dt
    from aria.tools import speak_date, speak_time, words_it
    d = lambda h, m: dt.datetime(2026, 10, 6, h, m)
    assert speak_time(d(0, 2)) == "È mezzanotte e due."
    assert speak_time(d(12, 0)) == "È mezzogiorno."
    assert speak_time(d(13, 5)) == "È l'una e cinque."
    assert speak_time(d(15, 15)) == "Sono le tre e un quarto."
    assert speak_time(d(15, 30)) == "Sono le tre e mezza."
    assert speak_time(d(15, 45)) == "Sono le quattro meno un quarto."
    assert speak_time(d(23, 59)) == "Sono le undici e cinquantanove."
    assert [words_it(x) for x in (21, 28, 33, 2026)] == ["ventuno", "ventotto", "trentatré", "duemilaventisei"]
    assert speak_date(d(9, 0)) == "Oggi è martedì sei ottobre duemilaventisei."
    assert speak_date(dt.datetime(2026, 11, 1)) == "Oggi è domenica primo novembre duemilaventisei."


def test_durations_written_the_short_way_and_calculations_with_several_operators():
    from aria.tools import parse_duration, safe_eval
    from aria import intent
    for text, sec in (("1h", 3600), ("2h", 7200), ("30 min", 1800), ("1h30", 5400), ("1,5 ore", 5400), ("45 sec", 45), ("tre quarti d'ora", 2700), ("1 ora e 30", 5400), ("un'ora e mezza", 5400)):
        assert parse_duration(text) == sec, text
    assert safe_eval(intent.detect("quanto fa due per tre piu quattro", []).arg) == 10
    assert safe_eval(intent.detect("Quanto fa 10 meno 2 per 3", []).arg) == 4
    assert intent.detect("Metti un timer di 1h", []).name == "TIMER"


async def test_timer_status_and_cancel():
    t = Tools(load(), Memory(), client=mock_client(lambda r: httpx.Response(200)))
    assert await t.run(ToolCall("TIMER_STATO", "")) == "Non hai nessun timer attivo."
    assert await t.run(ToolCall("TIMER_ANNULLA", "")) == "Non c'è nessun timer attivo."
    await t.run(ToolCall("TIMER", "10 minuti | pasta"))
    out = await t.run(ToolCall("TIMER_STATO", ""))
    assert out.startswith("Mancano") and "pasta" in out and ("10 minuti" in out or "9 minuti" in out)
    await t.run(ToolCall("TIMER", "5 minuti | torta"))
    assert (await t.run(ToolCall("TIMER_STATO", ""))).startswith("Hai due timer")
    q = await t.run(ToolCall("TIMER_ANNULLA", ""))
    assert q.startswith("@CHIEDI|TIMER_ANNULLA|") and "pasta" in q and "torta" in q                    # due timer e nessun nome: chiede quale
    assert "annullato il timer per pasta" in await t.run(ToolCall("TIMER_ANNULLA", "quello della pasta"))
    await asyncio.sleep(0)
    assert len(t._live_timers()) == 1
    assert "annullato" in await t.run(ToolCall("TIMER_ANNULLA", "tutti"))
    await asyncio.sleep(0)
    assert t._live_timers() == []


def test_timer_status_and_cancel_phrases():
    from aria.intent import detect
    for text, call in (("Quanto manca al timer?", ToolCall("TIMER_STATO", "")), ("che timer ho attivi?", ToolCall("TIMER_STATO", "")), ("Quanto manca al timer della pasta", ToolCall("TIMER_STATO", "pasta")),
                       ("annulla il timer", ToolCall("TIMER_ANNULLA", "")), ("Ferma il timer della pasta", ToolCall("TIMER_ANNULLA", "pasta")), ("cancella tutti i timer", ToolCall("TIMER_ANNULLA", "tutti")),
                       ("spegni la sveglia", ToolCall("TIMER_ANNULLA", "")), ("non mi serve più il timer", ToolCall("TIMER_ANNULLA", ""))):
        assert detect(text) == call, text
    for text in ("Quanto manca per arrivare a Roma?", "Il timer della lavatrice è rotto", "Ho un timer sul forno nuovo", "ferma"):
        assert detect(text) is None, text


async def test_a_relative_reminder_keeps_what_to_remember():
    from aria.intent import detect
    c = detect("ricordami tra dieci minuti di spegnere il forno")
    assert c == ToolCall("TIMER", "dieci minuti | di spegnere il forno")
    t = Tools(load(), Memory(), client=mock_client(lambda r: httpx.Response(200)))
    out = await t.run(c)
    assert out.startswith(("Va bene, tra", "Ok, tra")) and "di spegnere il forno" in out
    for task in list(t.timers.values()):
        task.cancel()



def test_timer_durations_said_with_minutes_after_the_hour():
    """«timer di un'ora e venti» diventava un timer di UN'ora (e «un minuto e 30 secondi» di un minuto)."""
    from aria import intent
    from aria.tools import parse_duration
    for said, secs in (("timer di 1 ora e 20", 4800), ("timer di un'ora e venti", 4800), ("timer di un'ora e venti minuti", 4800), ("timer di un'ora e mezza", 5400),
                       ("timer di 1 ora e un quarto", 4500), ("timer di un minuto e 30 secondi", 90), ("timer di 2 ore e 15 minuti", 8100), ("timer di 10 minuti per la pasta", 600)):
        c = intent.detect(said)
        assert c and c.name == "TIMER" and parse_duration(c.arg.split("|")[0]) == secs, (said, c)
