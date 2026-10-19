"""La «voce naturale» (Qwen3-TTS in un processo a parte): si accende dalle Impostazioni, parla quando e' pronta, altrimenti (o se sbaglia) parla Pocket TTS."""
import asyncio
import sys

import numpy as np

from aria import profiles as P
from aria.tts import AutoTTS, QwenTTS

FAKE_SERVER = r'''
import json, os, sys, tempfile, wave
import numpy as np
mode = json.loads(sys.argv[1]).get("ref_text", "")
sys.stdout.write("rumore di una libreria\n"); sys.stdout.flush()
sys.stdout.write("READY\n"); sys.stdout.flush()
for line in sys.stdin:
    req = json.loads(line)
    if "rompi" in req["text"]:
        sys.stdout.write(json.dumps({"id": req["id"], "error": "RuntimeError: prova"}) + "\n"); sys.stdout.flush(); continue
    fd, path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes((np.ones(2400) * 1000).astype(np.int16).tobytes())
    sys.stdout.write(json.dumps({"id": req["id"], "path": path, "sec": 0.1}) + "\n"); sys.stdout.flush()
'''


class StubPocket:
    voice = "lola"

    def __init__(self):
        self.said = []

    def set_voice(self, n):
        self.voice = n

    async def synthesize(self, text):
        self.said.append(text)
        return np.zeros(100, dtype=np.int16), 24000

    async def warmup(self):
        pass


def make(tmp_path, on: bool, downloaded: bool = True):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("brains: []\n")
    P.set_power(str(cfg_path), "voice_natural", on)
    srv = tmp_path / "fake_server.py"
    srv.write_text(FAKE_SERVER)
    t = AutoTTS({"kind": "natural", "voice": "lola", "_config_path": str(cfg_path), "server_cmd": [sys.executable, str(srv)]})
    t.pocket = StubPocket()
    t.qwen.downloaded = lambda: downloaded
    return t


async def wait_ready(t, secs=10):
    for _ in range(int(secs * 10)):
        if t.qwen.usable():
            return True
        await asyncio.sleep(0.1)
    return False


async def test_off_means_pocket_and_short_chunks(tmp_path):
    t = make(tmp_path, on=False)
    pcm, sr = await t.synthesize("Ciao")
    assert t.pocket.said == ["Ciao"] and t.chunk_chars == 30 and t.qwen.proc is None


async def test_on_speaks_with_the_natural_voice_once_ready_and_pocket_meanwhile(tmp_path):
    t = make(tmp_path, on=True)
    await t.synthesize("Primo")                                          # il processo sta partendo: questa la dice ancora Pocket
    assert t.pocket.said == ["Primo"]
    assert await wait_ready(t)
    pcm, sr = await t.synthesize("Secondo")
    assert t.pocket.said == ["Primo"] and len(pcm) == 2400 and sr == 24000 and t.chunk_chars == 120
    t.qwen.close()


async def test_a_failure_of_the_natural_voice_is_covered_by_pocket(tmp_path):
    t = make(tmp_path, on=True)
    assert await wait_ready(t)
    pcm, sr = await t.synthesize("rompi tutto")
    assert t.pocket.said == ["rompi tutto"]
    pcm, sr = await t.synthesize("di nuovo")                              # un errore su UNA frase non spegne la voce naturale: la frase dopo e' sua
    assert t.pocket.said == ["rompi tutto"] and len(pcm) == 2400
    t.qwen.proc.kill()                                                    # se invece il processo muore: Pocket, e la naturale riprova dopo una pausa
    await asyncio.sleep(0.2)
    pcm, sr = await t.synthesize("dopo la morte")
    assert t.pocket.said[-1] == "dopo la morte"
    t.qwen._bad_until = 0.0
    assert await wait_ready(t)                                            # e riparte da sola
    t.qwen.close()


async def test_not_downloaded_means_pocket_and_a_background_download(tmp_path):
    t = make(tmp_path, on=True, downloaded=False)
    started = []
    t.qwen._download_bg = lambda: started.append(1)
    await t.synthesize("Ciao")
    assert t.pocket.said == ["Ciao"] and started


async def test_switching_off_frees_the_process(tmp_path):
    t = make(tmp_path, on=True)
    assert await wait_ready(t)
    P.set_power(t.qwen.cfg["_config_path"], "voice_natural", False)
    t.qwen._on_cache = (0.0, False)
    assert not t.qwen.usable() and t.qwen.proc is None


def test_voices_are_set_apart_from_pocket_voices(tmp_path):
    t = make(tmp_path, on=False)
    t.set_voice("anna")                                                  # un nome del selettore: vale per tutte e due le voci
    assert t.qwen.voice == "anna" and t.pocket.voice == "anna"
    t.set_voice("marco")                                                 # una che esiste solo naturale: Pocket resta com'era
    assert t.qwen.voice == "marco" and t.pocket.voice == "anna"
    import os
    d = os.path.join(os.path.dirname(__import__("aria").__file__), "voices")
    for v in QwenTTS.VOICES:
        assert os.path.exists(os.path.join(d, v + ".wav")) and open(os.path.join(d, v + ".txt"), encoding="utf-8").read().strip()


def test_voice_requests_are_recognised_and_ordinary_talk_about_voices_is_not():
    from aria.dialog import voice_request
    for text, want in (("Cambia voce", ("cycle", "")), ("Puoi cambiare voce?", ("cycle", "")), ("Usa un'altra voce", ("cycle", "")), ("Attiva la voce naturale", ("natural_on", "")),
                       ("Vorrei una voce più naturale", ("natural_on", "")), ("Usa la voce di Marco", ("set", "marco")), ("Voglio una voce maschile", ("set", "marco")),
                       ("Torna alla voce di prima", ("natural_off", "")), ("voce di Chiara", ("set", "chiara"))):
        assert voice_request(text) == want, text
    for text in ("Che voce hai?", "Mi piace la tua voce", "Cambia argomento", "Hai una voce bellissima", "Non sento bene la tua voce, alza il volume"):
        assert voice_request(text) is None, text


async def test_asking_for_another_voice_by_speaking(tmp_path):
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from test_conversation import build, utterance
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("brains: []\n")
    # voce automatica spenta: dice onestamente che ne ha una sola e come averne altre
    a, hub, llm, tts, spk, tools = build(utterance(), ["Cambia voce"])
    auto = AutoTTS({"kind": "natural", "voice": "lola", "_config_path": str(cfg_path)})
    auto.pocket = tts                                                       # (la voce di prima e' quella finta dei test)
    a.router._objs[("t", "tts")] = auto
    a.cfg["_config_path"] = str(cfg_path)
    await asyncio.wait_for(a.session(), 20)
    assert any("attiva la voce naturale" in s.lower() for s in tts.said) and not llm.calls
    # «attiva la voce naturale»: la accende (e basta, senza far partire il chatbot)
    a2, hub2, llm2, tts2, spk2, tools2 = build(utterance(), ["Attiva la voce naturale"])
    auto2 = AutoTTS({"kind": "natural", "voice": "lola", "_config_path": str(cfg_path)})
    auto2.qwen.downloaded = lambda: False
    auto2.qwen._download_bg = lambda: None
    auto2.pocket = tts2
    a2.router._objs[("t", "tts")] = auto2
    a2.cfg["_config_path"] = str(cfg_path)
    await asyncio.wait_for(a2.session(), 20)
    assert P.get_powers(str(cfg_path))["voice_natural"] is True and any("scaricare il modello" in s for s in tts2.said) and not llm2.calls


def test_the_voice_server_gives_the_model_the_language_by_name_not_by_code():
    """Con «it» il modello non riconosceva la lingua e parlava con un accento a caso (giapponese): vuole «italian»."""
    from aria.qwentts_server import lang_name
    assert lang_name("it") == "italian" and lang_name(None) == "italian" and lang_name("IT") == "italian"
    assert lang_name("en") == "english" and lang_name("fr") == "french" and lang_name("de") == "german" and lang_name("es") == "spanish" and lang_name("pt") == "portuguese"
    assert lang_name("italian") == "italian" and lang_name("english") == "english" and lang_name("boh") == "italian"


def test_a_voice_picked_from_the_selector_changes_both_the_old_voice_and_the_natural_one_and_is_remembered(tmp_path):
    """Prima il selettore dell'app cambiava solo la voce di Pocket: la naturale restava sempre «Aria» (tutte uguali, nessuna maschile)."""
    from aria.main import _restore_voice
    from aria.state import Hub
    from aria.tts import AutoTTS, QwenTTS
    cfg = {"data_dir": str(tmp_path), "brains": [{"name": "x", "tts": {"kind": "natural", "voice": "lola"}}]}
    hub = Hub()
    _restore_voice(cfg, hub)
    hub.dispatch_command({"cmd": "voice", "name": "paul"})                     # dal selettore: un nome maschile
    assert (tmp_path / "voce.txt").read_text() == "paul" and (tmp_path / "voce_naturale.txt").read_text() == "paul"
    a = AutoTTS({"kind": "natural", "voice": "lola"})
    a.set_voice("paul")
    assert a.pocket.voice == "paul" and a.qwen.voice == "paul"
    hub.dispatch_command({"cmd": "voice", "name": "marco"})                    # a voce: una che esiste solo naturale
    assert (tmp_path / "voce_naturale.txt").read_text() == "marco" and (tmp_path / "voce.txt").read_text() == "paul"
    a.set_voice("marco")
    assert a.qwen.voice == "marco" and a.pocket.voice == "paul"
    cfg2 = {"data_dir": str(tmp_path), "brains": [{"name": "x", "tts": {"kind": "natural", "voice": "lola"}}]}
    _restore_voice(cfg2, Hub())                                                # al riavvio: la naturale e' Marco, quella di prima Paul
    t = cfg2["brains"][0]["tts"]
    assert t["voice"] == "paul" and t["voice_natural"] == "marco" and AutoTTS(t).qwen.voice == "marco"
    cfg3 = {"data_dir": str(tmp_path / "vuota"), "brains": [{"name": "x", "tts": {"kind": "natural", "voice": "javert"}}]}
    assert AutoTTS(cfg3["brains"][0]["tts"]).qwen.voice == "javert"            # senza scelte a voce: quella del selettore
    assert QwenTTS({"voice": "boh"}).voice == "aria"


def test_every_selector_voice_has_its_own_reference_recording_and_they_are_not_copies():
    import hashlib
    import os
    from aria.tts import QwenTTS
    d = os.path.join(os.path.dirname(__import__("aria").__file__), "voices")
    digests = {v: hashlib.md5(open(os.path.join(d, v + ".wav"), "rb").read()).hexdigest() for v in QwenTTS.VOICES}
    assert len(set(digests.values())) == len(QwenTTS.VOICES)
