"""In inglese Aria non deve dire (né dire al chatbot) parole italiane: ogni frase d'esempio passa dal flusso vero, con la rete e il Mac finti."""
import asyncio
import datetime as dt
import os
import re
from pathlib import Path

import httpx
import pytest

from aria.macos import Mac
from aria.tools import Tools
from test_human_flow import build_flow
from test_powers import Runner

DATA = Path(__file__).parent

# Parole che in italiano sono comuni e in inglese non esistono (niente «per», «come», «la»…: hanno un significato anche in inglese).
ITALIAN = re.compile(r"\b(non|che|sono|ecco|fatto|hai|vuoi|puoi|grazie|scusa|certo|domani|oggi|minuti|minuto|secondi|ricordo|promemoria|nessun|nessuna|nessuno|trovato|prego|ciao|"
                     r"invece|perch[eé]|cosa|anche|molto|quando|dove|ancora|adesso|sera|mattina|giorno|giorni|della|degli|nel|sul|gli|dei|ho|una|uno|il|ma|se|stai|sei|ora|"
                     r"nota|lista|spesa|scritto|salvato|salvata|aperto|aperta|chiuso|impostato|impostata|programmato|annullato|annullata|eccolo|eccola)\b", re.I)

EXTRA = ["hello", "hi Aria", "good morning", "good night", "how are you", "who are you", "what's your name", "thanks", "thank you so much", "sorry", "never mind", "stop",
         "goodbye", "see you later", "what can you do", "tell me a joke", "I'm tired", "I'm so sad today", "repeat that", "say that again", "speak slower", "be quiet",
         "what's the weather", "what's playing", "pause the music", "turn the volume up", "set the volume to thirty", "mute", "open Safari", "open YouTube",
         "play some jazz on YouTube", "search the web for pizza dough", "remind me to call Mark tomorrow at nine", "add milk to the shopping list", "read my shopping list",
         "what's on my calendar today", "add a meeting tomorrow at three to my calendar", "take a note that the code is 1234", "read my notes", "good morning briefing",
         "where is the export button", "what is on my screen", "summarize this page", "forget everything", "what do you know about me", "my name is Anna",
         "I live in Boston", "call my mom", "turn off the lights", "order a pizza", "send a message to Luca", "run my shortcut called focus"]


def handler(req):
    u = str(req.url)
    if "geocoding" in u:
        return httpx.Response(200, json={"results": [{"latitude": 41.9, "longitude": 12.5, "name": "Rome", "country": "Italy"}]})
    if "forecast" in u:
        return httpx.Response(200, json={"current": {"temperature_2m": 17.2, "weather_code": 3, "wind_speed_10m": 6, "apparent_temperature": 16},
                                         "daily": {"weather_code": [3, 61, 0, 95, 71, 45, 2], "temperature_2m_max": [19, 15, 22, 18, -1, 8, 25], "temperature_2m_min": [9, 8, 11, 10, -6, 2, 14],
                                                   "precipitation_probability_max": [10, 70, 0, 80, 60, 5, 0], "sunrise": ["2026-10-21T07:12"] * 7, "sunset": ["2026-10-21T18:03"] * 7,
                                                   "time": [f"2026-10-{21 + i}" for i in range(7)]}})
    if "opensearch" in u:
        return httpx.Response(200, json=["x", ["Napoleon"], [], []])
    if "page/summary" in u:
        return httpx.Response(200, json={"extract": "Napoleon Bonaparte was a French emperor."})
    if "translate" in u or "mymemory" in u or "lingva" in u:
        return httpx.Response(200, json={"responseData": {"translatedText": "Buongiorno"}})
    if "/search" in u or "duckduckgo" in u:
        return httpx.Response(200, json={"results": [{"title": "Trains", "content": "Trains run every 30 minutes"}]})
    return httpx.Response(404)


def phrases():
    out = []
    for line in (DATA / "positives_en.txt").read_text(encoding="utf-8").splitlines():
        if "|" in line:
            out.append(line.split("|", 1)[1].strip())
    return (out if os.environ.get("ARIA_FULL_SWEEP") else out[::3]) + EXTRA                 # di norma un campione (ogni frase costa ~0,35 s); con ARIA_FULL_SWEEP=1 tutte


def _clean(text):
    return re.sub(r"\[\[.*?\]\]", " ", text)                           # i nomi degli strumenti sono italiani per scelta: non contano


@pytest.mark.parametrize("phrase", phrases())
async def test_english_flow_has_no_italian_in_speech_or_prompts(english, phrase):
    a, hub, script, tts, spk = build_flow([phrase], ["Sure thing."], turns=2)
    cfg = a.cfg
    cfg["turn"].update(follow_up_timeout_s=0.3, first_turn_timeout_s=0.3)                    # (una sola frase per sessione: non serve aspettare il seguito)
    cfg.setdefault("tools", {}).setdefault("web_search", {})["searxng_url"] = "http://searx.local"
    a.tools = Tools(cfg, a.memory, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    a.tools.generate = a._generate_text
    a.tools.now_fn = lambda: dt.datetime(2026, 10, 21, 14, 30)
    a.tools.mac = Mac(runner=Runner({"Calendar": (0, "", "")}), platform="darwin")
    a.persona = (Path(__file__).parent.parent / "aria" / "data" / "persona_en.md").read_text(encoding="utf-8").split("---FINE---")[0].strip()      # il carattere vero, non quello finto del banco di prova
    await asyncio.wait_for(a.session(), 40)
    spoken = " ".join(tts.said)
    sent = " ".join(_clean(m["content"]) for call in script.calls for m in call
                    if isinstance(m.get("content"), str) and not m["content"].startswith("You are the command decoder"))      # (il decodificatore usa i nomi italiani degli strumenti come protocollo)
    assert not ITALIAN.findall(spoken) and not re.search("[àèìòù]", spoken), (phrase, spoken)
    assert not ITALIAN.findall(sent), (phrase, ITALIAN.findall(sent))
