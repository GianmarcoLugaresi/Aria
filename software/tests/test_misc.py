import asyncio
import json

from aria.config import deep_merge, load
from aria.leds import frame_colors
from aria.llm import ThinkFilter
from aria.state import Hub, State


def test_config_merge(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("name: Luna\nturn:\n  end_silence_ms: 500\n")
    cfg = load(str(p))
    assert cfg["name"] == "Luna" and cfg["turn"]["end_silence_ms"] == 500 and cfg["turn"]["min_speech_ms"] == 250
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 9}}) == {"a": {"b": 9, "c": 2}}


def test_thinkfilter_across_chunks():
    f = ThinkFilter()
    out = ""
    for ch in ["ok<thi", "nk>segreto</thi", "nk> bene"]:
        out += f.push(ch)
    out += f.flush()
    assert out == "ok bene"


def test_led_frames_are_valid_and_state_dependent():
    for st in ("idle", "listening", "thinking", "speaking", "error"):
        cols = frame_colors(st, 0.8, 1.23, 20)
        assert len(cols) == 20 and all(0 <= c <= 255 for px in cols for c in px)
    assert max(sum(p) for p in frame_colors("speaking", 1.0, 0.0, 10)) > max(sum(p) for p in frame_colors("speaking", 0.0, 0.0, 10))


async def test_hub_coalesces_levels_but_keeps_events():
    hub = Hub()
    sub = hub.subscribe()
    for i in range(50):
        hub.set_level(i / 50)
    hub.set_state(State.SPEAKING)
    hub.transcript("aria", "Ciao!")
    msgs = []
    while not sub.empty():
        msgs.append(sub.get_nowait())
    assert [m["type"] for m in msgs] == ["state", "transcript", "level"]      # il livello arriva per ultimo, una volta sola
    assert msgs[-1]["level"] == 0.98 and msgs[1]["text"] == "Ciao!"


async def test_hub_commands():
    hub = Hub()
    got = []
    hub.on_command(got.append)
    hub.dispatch_command({"cmd": "wake"})
    assert got == [{"cmd": "wake"}]


async def test_display_websocket_roundtrip():
    from websockets.asyncio.client import connect
    from aria.display import serve_display
    hub = Hub()
    cmds = []
    hub.on_command(cmds.append)
    server = await serve_display(hub, "127.0.0.1", 0, fps=60)
    port = server.sockets[0].getsockname()[1]
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        first = json.loads(await asyncio.wait_for(ws.recv(), 2))
        assert first["state"] == "idle" and first["type"] == "snapshot"
        hub.set_state(State.LISTENING)
        hub.transcript("user", "ciao")
        hub.set_level(0.5)
        got = []
        for _ in range(5):
            got.append(json.loads(await asyncio.wait_for(ws.recv(), 2)))
            if got[-1].get("level") == 0.5:
                break
        assert [g["type"] for g in got][:2] == ["state", "transcript"] and got[-1]["level"] == 0.5
        await ws.send(json.dumps({"cmd": "wake"}))
        await asyncio.sleep(0.1)
        assert cmds == [{"cmd": "wake"}]
    server.close()
    await server.wait_closed()


def test_voice_choice_is_persisted_and_restored(tmp_path):
    import json as _json
    from aria.main import _restore_voice
    cfg = load()
    cfg["data_dir"] = str(tmp_path)
    cfg["brains"] = [{"name": "x", "tts": {"kind": "pocket", "voice": "lola"}}]
    hub = Hub()
    _restore_voice(cfg, hub)
    assert cfg["brains"][0]["tts"]["voice"] == "lola"            # nessun file: resta il default
    hub.dispatch_command({"cmd": "voice", "name": "vera"})       # scelta dal menu dell'app
    assert (tmp_path / "voce.txt").read_text() == "vera"
    cfg2 = load()
    cfg2["data_dir"] = str(tmp_path)
    cfg2["brains"] = [{"name": "x", "tts": {"kind": "pocket", "voice": "lola"}}]
    hub2 = Hub()
    _restore_voice(cfg2, hub2)
    assert cfg2["brains"][0]["tts"]["voice"] == "vera" and hub2.info["voice"] == "vera"


def test_make_tts_knows_the_new_engines():
    from aria.tts import MacSayTTS, make_tts
    assert isinstance(make_tts({"kind": "say", "voice": "Alice"}), MacSayTTS)
    assert make_tts({"kind": "pocket", "voice": "lola"}).voice == "lola"       # non carica il modello finche' non serve


async def test_transcript_messages_never_dropped_behind_levels():
    hub = Hub()
    sub = hub.subscribe()
    hub.transcript("user", "uno")
    for i in range(100):
        hub.set_level(i / 100)
    hub.transcript("aria", "due")
    got = []
    while not sub.empty():
        got.append(sub.get_nowait())
    assert [m["text"] for m in got if m["type"] == "transcript"] == ["uno", "due"]


async def test_llm_retries_without_extra_body_when_server_refuses_it():
    import httpx
    from aria.llm import OpenAILLM
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append("reasoning_effort" in body)
        if "reasoning_effort" in body:
            return httpx.Response(400, json={"error": "model does not support thinking"})
        sse = 'data: {"choices":[{"delta":{"content":"Ciao"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})

    llm = OpenAILLM({"base_url": "http://x/v1", "model": "m", "extra_body": {"reasoning_effort": "none"}})
    llm.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = "".join([t async for t in llm.stream([{"role": "user", "content": "ciao"}])])
    assert out == "Ciao" and seen == [True, False]
    out2 = "".join([t async for t in llm.stream([{"role": "user", "content": "ciao"}])])   # poi non riprova piu' con il parametro
    assert out2 == "Ciao" and seen == [True, False, False]


def test_audio_watchdog_decides_when_to_reopen_the_devices():
    from aria import audio
    assert audio.audio_problem((1, 2), (1, 2), 0.1, False) is None
    assert audio.audio_problem((1, 2), (3, 2), 0.1, False) == "cambiato"             # gli AirPods si sono collegati: si passa ai nuovi
    assert audio.audio_problem((1, 2), (3, 2), 0.1, True) is None                    # ma non mentre sta parlando
    assert audio.audio_problem((1, 2), (1, 2), 9.0, True) == "ferma"                 # il microfono non manda piu' niente: si riapre anche mentre parla
    assert audio.audio_problem((None, None), (3, 2), 0.1, False) is None             # senza sapere i dispositivi non si tocca niente
    assert audio.audio_problem((1, 2), (3, 2), 0.1, False, follow_default=False) is None      # dispositivi scelti a mano nella configurazione: non si segue il predefinito
    ids = audio.default_devices()
    assert isinstance(ids, tuple) and len(ids) == 2


def test_power_state_is_read_without_crashing():
    from aria import power
    assert power.on_battery() in (True, False, None) and power.display_asleep() in (True, False, None)
