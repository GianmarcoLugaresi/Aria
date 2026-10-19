import numpy as np
import pytest

from aria.memory import Memory
from aria.router import Router


def test_memory_roundtrip():
    m = Memory()
    assert m.add_fact("Mario ha un esame di analisi martedì")
    assert m.add_fact("Gli piace il caffè lungo")
    assert m.add_fact("gli piace il caffe lungo") is None              # duplicato (accenti/maiuscole)
    assert "esame" in " ".join(m.relevant("quando è l'esame?", 3))
    assert m.relevant("zzz qqq", 5)                                    # nessun match: ritorna comunque i piu' recenti
    m.add_session("avete parlato di musica e del progetto")
    ctx = m.context("caffè")
    assert "caff" in ctx and "Ultima volta" not in ctx                 # i riassunti automatici non si usano piu' (il modello piccolo li inventava)
    assert m.forget("caffe") == 1 and all("caff" not in f for f in m.all_facts())


class FakeLLM:
    def __init__(self, name, fail=False, tokens=("ciao", " mondo")):
        self.name, self.fail, self.tokens = name, fail, tokens

    async def stream(self, messages):
        if self.fail:
            raise ConnectionError("giu'")
        for t in self.tokens:
            yield t


class FakeHTTP:
    def __init__(self, up):
        self.up = up

    async def get(self, url):
        class R:
            status_code = 200
        if not self.up.get(url.split("/v1")[0], True):
            raise ConnectionError
        return R()


def make_router(up, fail_first=False):
    brains = [{"name": "mac", "llm": {"base_url": "http://mac/v1"}, "tts": {"kind": "piper"}},
              {"name": "pi", "llm": {"base_url": "http://pi/v1"}, "tts": {"kind": "piper"}}]

    def factory(stage, cfg):
        if stage == "llm":
            return FakeLLM(cfg["base_url"], fail=fail_first and "mac" in cfg["base_url"])

        class T:
            async def synthesize(self, text):
                return np.zeros(10, dtype=np.int16), 16000
        return T()
    return Router(brains, factory, http=FakeHTTP(up))


async def test_router_prefers_first_healthy():
    r = make_router({"http://mac": True, "http://pi": True})
    assert "".join([t async for t in r.llm_stream([])]) == "ciao mondo"
    assert ("mac", "llm") in r._objs and ("pi", "llm") not in r._objs


async def test_router_skips_unreachable_brain():
    r = make_router({"http://mac": False, "http://pi": True})
    assert "".join([t async for t in r.llm_stream([])]) == "ciao mondo"
    assert ("mac", "llm") not in r._objs


async def test_router_fails_over_and_bans():
    r = make_router({"http://mac": True, "http://pi": True}, fail_first=True)
    assert "".join([t async for t in r.llm_stream([])]) == "ciao mondo"
    assert r._ban[("mac", "llm")] > 0
    pcm, sr = await r.synthesize("x")
    assert sr == 16000


async def test_router_raises_when_all_down():
    r = make_router({"http://mac": False, "http://pi": False})
    with pytest.raises(RuntimeError):
        [t async for t in r.llm_stream([])]


async def test_in_process_engines_are_always_available():
    """Pocket TTS, say, Piper, Kokoro e faster-whisper girano nel processo: nessun controllo di rete."""
    brains = [{"name": "mac", "tts": {"kind": "pocket", "voice": "lola"}, "stt": {"kind": "faster-whisper"}},
              {"name": "sys", "tts": {"kind": "say"}}]
    r = Router(brains, lambda stage, cfg: object(), http=FakeHTTP({}))
    assert [b["name"] async for b, _ in r.candidates("tts")] == ["mac", "sys"]
    assert [b["name"] async for b, _ in r.candidates("stt")] == ["mac"]


async def test_router_revives_a_dead_brain_once_and_retries():
    import httpx
    state = {"up": False}

    def handler(req):
        if not state["up"]:
            raise httpx.ConnectError("rifiutata")
        return httpx.Response(200, json={"data": []})
    llm = FakeLLM("ollama")
    r = Router([{"name": "mac", "llm": {"kind": "openai", "base_url": "http://x/v1"}}], lambda stage, c: llm,
               http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    calls = []

    async def revive(stage):
        calls.append(stage)
        state["up"] = True                                            # "Ollama" si e' acceso
        return True
    r.revive = revive
    out = "".join([t async for t in r.llm_stream([{"role": "user", "content": "ciao"}])])
    assert out == "ciao mondo" and calls == ["llm"]
    # se il revive non riesce: errore chiaro, e un solo tentativo
    state["up"] = False
    r2 = Router([{"name": "mac", "llm": {"kind": "openai", "base_url": "http://x/v1"}}], lambda stage, c: llm,
                http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    n = {"c": 0}

    async def nope(stage):
        n["c"] += 1
        return False
    r2.revive = nope
    import pytest
    with pytest.raises(RuntimeError, match="nessun cervello"):
        async for _ in r2.llm_stream([{"role": "user", "content": "ciao"}]):
            pass
    assert n["c"] == 1


def test_ollama_helpers(monkeypatch):
    from aria import ollama
    assert ollama.is_local("http://127.0.0.1:11434/v1") and ollama.is_local("http://localhost:11434/v1")
    assert not ollama.is_local("http://192.168.1.10:11434/v1") and not ollama.is_local("http://127.0.0.1:8080/v1") and not ollama.is_local(None)
    seq = iter([False, False, True])
    monkeypatch.setattr(ollama, "is_up", lambda timeout=1.5: next(seq))
    monkeypatch.setattr(ollama, "start", lambda: True)
    monkeypatch.setattr(ollama.time, "sleep", lambda s: None)
    assert ollama.ensure_running(5.0) is True
    monkeypatch.setattr(ollama, "is_up", lambda timeout=1.5: False)
    monkeypatch.setattr(ollama, "start", lambda: False)              # ne' app ne' comando: non aspetta
    assert ollama.ensure_running(5.0) is False


def test_memory_intent_and_tool():
    import asyncio
    from aria.intent import detect
    from aria.textutil import ToolCall
    for t in ("cosa sai di me?", "Che cosa ricordi di me", "come mi chiamo", "dove abito", "ti ricordi di me?"):
        assert detect(t) == ToolCall("MEMORIA", ""), t
    assert detect("come stai?") is None
    from aria.config import load
    from aria.tools import SPEAK_VERBATIM, Tools
    assert "MEMORIA" in SPEAK_VERBATIM
    m = Memory()
    m.set_profile("name", "Mario")
    assert "ti chiami Mario" in asyncio.run(Tools(load(), m).run(ToolCall("MEMORIA", "")))


def test_weather_asks_for_the_city_when_it_is_unknown():
    import asyncio
    import httpx
    from aria.config import load
    from aria.tools import NEED_CITY, Tools
    cfg = load()
    cfg["location"] = {"city": None, "lat": None, "lon": None}
    seen = []

    def handler(req):
        seen.append(str(req.url))
        if "geocoding" in str(req.url):
            return httpx.Response(200, json={"results": [{"latitude": 45.46, "longitude": 9.19, "name": "Milano"}]})
        return httpx.Response(200, json={"daily": {"weather_code": [1, 1], "temperature_2m_max": [20, 21], "temperature_2m_min": [10, 11],
                                                   "precipitation_probability_max": [0, 10]},
                                         "current": {"temperature_2m": 15, "weather_code": 1, "wind_speed_10m": 3}})
    mem = Memory()
    t = Tools(cfg, mem, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    from aria.textutil import ToolCall
    assert asyncio.run(t.run(ToolCall("METEO", "domani"))) == NEED_CITY and seen == []
    mem.set_profile("city", "Milano")                                # la citta' che l'utente ha detto
    out = asyncio.run(t.run(ToolCall("METEO", "domani")))
    assert "Milano" in out and any("geocoding" in u and "Milano" in u for u in seen)


async def test_with_a_single_recognizer_one_error_does_not_make_aria_deaf_for_thirty_seconds():
    """Il 7 ottobre: un errore del riconoscimento metteva da parte l'UNICO riconoscitore per 30 s -> 1157 «nessun riconoscimento vocale disponibile» di fila."""
    import numpy as np
    from aria.router import Router
    calls = []

    class Flaky:
        async def transcribe(self, pcm, sr):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("il programma di supporto si e' riavviato")
            return "ciao"
    r = Router([{"name": "mac", "stt": {"kind": "apple"}}], lambda stage, cfg: Flaky())
    try:
        await r.transcribe(np.zeros(160, np.int16))
    except RuntimeError:
        pass
    assert await r.transcribe(np.zeros(160, np.int16)) == "ciao" and not r._ban
