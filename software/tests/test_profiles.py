"""Versioni di Aria (Leggera/Media/Pesante), scelta del chatbot e gestione dei download: nessuna rete, nessun modello vero."""
import copy
import json

import httpx
import pytest
import yaml

from aria import config as cfgmod
from aria import models as M
from aria import profiles as P


def _cfg(tmp_path, extra=None):
    d = {"brains": [{"name": "mac",
                     "llm": {"base_url": "http://127.0.0.1:11434/v1", "model": "gemma3:4b", "extra_body": {}},
                     "stt": {"kind": "mlx-whisper", "model": "mlx-community/whisper-large-v3-turbo-q4", "prompt": False},
                     "tts": {"kind": "say"}}], "data_dir": str(tmp_path / "data")}
    d.update(extra or {})
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(d), encoding="utf-8")
    return str(p)


def test_media_leaves_config_untouched(tmp_path):
    path = _cfg(tmp_path)
    base = cfgmod.load(path, settings=False)
    loaded = cfgmod.load(path)                                                # nessun settings.json
    assert loaded["brains"] == base["brains"] and loaded["profile"] == "media"
    P.save_settings(path, {"profile": "media", "llm_model": None})
    assert cfgmod.load(path)["brains"][0] == base["brains"][0]


def test_profiles_override_stt_and_llm(tmp_path):
    path = _cfg(tmp_path)
    P.save_settings(path, {"profile": "leggera"})
    b = cfgmod.load(path)["brains"][0]
    assert b["stt"]["model"] == "mlx-community/whisper-small-mlx-q4"
    assert b["llm"] == {"kind": "mlx-lm", "model": "mlx-community/gemma-3-text-4b-it-4bit"}       # chatbot DENTRO Aria: niente Ollama
    P.save_settings(path, {"profile": "pesante"})
    b = cfgmod.load(path)["brains"][0]
    assert b["stt"]["model"] == "mlx-community/whisper-large-v3-mlx"
    assert b["llm"] == {"kind": "mlx-lm", "model": "mlx-community/gemma-2-9b-it-4bit"}
    assert {k: v for k, v in b["tts"].items() if k != "_config_path"} == {"kind": "say"}                                        # la voce non si tocca
    assert cfgmod.load(path, settings=False)["brains"][0]["llm"]["model"] == "gemma3:4b"    # config.yaml non e' stato riscritto


def test_chosen_chatbot_wins_and_reasoning_models_are_silenced(tmp_path):
    path = _cfg(tmp_path)
    P.save_settings(path, {"profile": "media", "llm_model": "Gemma4-12B:latest"})
    b = cfgmod.load(path)["brains"][0]
    assert b["llm"]["model"] == "Gemma4-12B:latest" and b["llm"]["extra_body"] == {"reasoning_effort": "none"}
    P.save_settings(path, {"profile": "media", "llm_model": "llama3.2:3b"})
    assert cfgmod.load(path)["brains"][0]["llm"]["extra_body"] == {}


def test_unknown_or_corrupt_settings_are_ignored(tmp_path):
    path = _cfg(tmp_path)
    base = cfgmod.load(path, settings=False)
    P.save_settings(path, {"profile": "ultra"})
    assert cfgmod.load(path)["brains"] == base["brains"]
    open(P.settings_path(path), "w").write("{non json")
    assert cfgmod.load(path)["brains"] == base["brains"]


def test_reasoning_and_embedding_detection():
    for n in ("Gemma4-12B:latest", "Qwen_3.8_27B:latest", "qwen3:8b", "deepseek-r1:7b", "gpt-oss:20b"):
        assert P.needs_no_think(n), n
    for n in ("gemma3:4b", "gemma2:9b", "llama3.1:8b", "qwen2.5:7b", "mistral-nemo:12b"):
        assert not P.needs_no_think(n), n
    assert P.is_embedding_model("nomic-embed-text:latest") and P.is_embedding_model("x", "bert")
    assert not P.is_embedding_model("gemma3:4b", "gemma3")


def _ollama_client(models):
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"models": models})))


def test_installed_llms_lists_chatbots_only(monkeypatch):
    tags = [{"name": "Qwen_3.8_27B:latest", "size": 12e9, "details": {"parameter_size": "27B", "family": "qwen"}},
            {"name": "gemma3:4b", "size": 3.3e9, "details": {"parameter_size": "4.3B", "family": "gemma3"}},
            {"name": "nomic-embed-text:latest", "size": 0.27e9, "details": {"family": "nomic-bert"}}]
    out = M.installed_llms(_ollama_client(tags))
    assert [m["name"] for m in out] == ["gemma3:4b", "Qwen_3.8_27B:latest"]
    assert out[0]["heavy"] is False and out[1]["heavy"] is True and out[1]["reasoning"] is True


def test_installed_llms_none_when_ollama_is_off():
    def boom(req):
        raise httpx.ConnectError("rifiutata")
    assert M.installed_llms(httpx.Client(transport=httpx.MockTransport(boom))) is None


def test_status_reports_missing_parts(tmp_path, monkeypatch):
    path = _cfg(tmp_path)
    monkeypatch.setattr(M, "stt_installed", lambda c: c.get("model", "").endswith("turbo-q4"))
    monkeypatch.setattr(M, "disk_free_gb", lambda p=None: 19.0)
    monkeypatch.setattr(M, "mlx_lm_installed", lambda repo: repo.endswith("gemma-3-text-4b-it-4bit"))
    llms = [{"name": "gemma3:4b", "gb": 3.3, "params": "4B", "heavy": False, "reasoning": False}]
    s = M.status(path, llms)
    byid = {p["id"]: p for p in s["profiles"]}
    assert byid["media"]["need_mb"] == 0 and byid["media"]["stt"]["installed"] and byid["media"]["llm"]["installed"]       # Media = config.yaml: Ollama gemma3:4b
    assert byid["leggera"]["need_mb"] == 197                                  # solo il riconoscimento vocale: il chatbot MLX c'e' gia'
    assert byid["pesante"]["need_mb"] == 3084 + 5200
    assert byid["leggera"]["llm"]["name"] == "mlx:mlx-community/gemma-3-text-4b-it-4bit" and byid["leggera"]["llm"]["label"] == "Gemma 3 4B"
    assert s["active_profile"] == "media" and s["active_llm"] == "gemma3:4b" and s["ollama"] is True and s["disk_free_gb"] == 19.0
    P.save_settings(path, {"profile": "leggera", "llm_model": "gemma3:4b"})
    assert M.status(path, llms)["active_profile"] == "leggera"


def test_apply_requires_everything_installed(tmp_path, monkeypatch):
    path = _cfg(tmp_path)
    llms = [{"name": "gemma3:4b", "gb": 3.3}, {"name": "Gemma4-12B:latest", "gb": 9.8}]
    mlx_ok = set()
    monkeypatch.setattr(M, "mlx_lm_installed", lambda repo: repo in mlx_ok)
    monkeypatch.setattr(M, "stt_installed", lambda c: False)
    r = M.apply(path, "leggera", llms=llms)
    assert not r["ok"] and "riconoscimento vocale" in r["error"]
    assert P.load_settings(path) == {}                                        # non e' stato scritto nulla
    monkeypatch.setattr(M, "stt_installed", lambda c: True)
    assert not M.apply(path, "pesante", llms=llms)["ok"]                     # il chatbot MLX della Pesante non e' scaricato
    assert not M.apply(path, "leggera", llms=llms)["ok"]                     # nemmeno quello della Leggera
    assert not M.apply(path, "media", "mai-visto:1b", llms=llms)["ok"]
    assert not M.apply(path, "media", llms=None)["ok"]                       # Media = Ollama di config.yaml, e Ollama e' spento
    mlx_ok.add("mlx-community/gemma-3-text-4b-it-4bit")
    assert M.apply(path, "leggera", llms=None) == {"ok": True, "profile": "leggera", "stt": "mlx-community/whisper-small-mlx-q4",
                                                    "llm": "mlx:mlx-community/gemma-3-text-4b-it-4bit"}       # un chatbot MLX NON richiede Ollama
    assert P.load_settings(path) == {"profile": "leggera", "llm_model": None}
    assert M.apply(path, "media", "Gemma4-12B:latest", llms=llms)["ok"]
    assert P.load_settings(path) == {"profile": "media", "llm_model": "Gemma4-12B:latest"}
    assert M.apply(path, "media", "gemma3:4b", llms=llms)["ok"]
    assert P.load_settings(path)["llm_model"] is None                         # uguale a quello della versione: nessun override


def test_ollama_pull_reports_aggregate_progress():
    lines = [{"status": "pulling manifest"},
             {"status": "pulling aaa", "digest": "aaa", "total": 4000, "completed": 1000},
             {"status": "pulling aaa", "digest": "aaa", "total": 4000, "completed": 4000},
             {"status": "pulling bbb", "digest": "bbb", "total": 100, "completed": 50},
             {"status": "success"}]
    body = "\n".join(json.dumps(x) for x in lines).encode()
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, content=body)
    events = []
    M.ollama_pull("gemma2:9b", 5000, lambda **kw: events.append(kw), httpx.Client(transport=httpx.MockTransport(handler)))
    assert seen["body"]["model"] == "gemma2:9b"
    last = events[-1]
    assert last["item"] == "llm" and last["done"] == 4050 and last["total"] == 5000 and last["status"] == "success"


def test_ollama_pull_error_and_truncated_stream():
    def err(req):
        return httpx.Response(200, content=json.dumps({"error": "pull model manifest: file does not exist"}).encode())
    with pytest.raises(RuntimeError, match="does not exist"):
        M.ollama_pull("nome-sbagliato", 1, lambda **kw: None, httpx.Client(transport=httpx.MockTransport(err)))

    def cut(req):
        return httpx.Response(200, content=json.dumps({"status": "pulling x", "digest": "x", "total": 10, "completed": 1}).encode())
    with pytest.raises(RuntimeError, match="interrotto"):
        M.ollama_pull("x", 10, lambda **kw: None, httpx.Client(transport=httpx.MockTransport(cut)))


def test_download_refuses_without_disk_space(tmp_path, monkeypatch):
    path = _cfg(tmp_path)
    monkeypatch.setattr(M, "stt_installed", lambda c: False)
    monkeypatch.setattr(M, "mlx_lm_installed", lambda repo: False)           # indipendente da cosa c'e' davvero nella cache del Mac
    monkeypatch.setattr(M, "installed_llms", lambda client=None: [])
    monkeypatch.setattr(M, "disk_free_gb", lambda p=None: 5.0)
    events = []
    assert M.download(path, "pesante", out=lambda **kw: events.append(kw)) is False
    assert events[-1]["event"] == "error" and "Spazio insufficiente" in events[-1]["message"]


def test_download_pulls_only_what_is_missing(tmp_path, monkeypatch):
    path = _cfg(tmp_path)
    calls = []
    monkeypatch.setattr(M, "stt_installed", lambda c: False)
    monkeypatch.setattr(M, "installed_llms", lambda client=None: [{"name": "gemma3:4b", "gb": 3.3}])
    monkeypatch.setattr(M, "disk_free_gb", lambda p=None: 50.0)
    have = {"mlx-community/gemma-3-text-4b-it-4bit"}
    monkeypatch.setattr(M, "mlx_lm_installed", lambda repo: repo in have)
    monkeypatch.setattr(M, "mlx_lm_problem", lambda repo: None)
    monkeypatch.setattr(M, "hf_download", lambda repo, total, out=None, item="stt": calls.append((item, repo)))
    monkeypatch.setattr(M, "mlx_whisper_problem", lambda repo: None)
    monkeypatch.setattr(M, "ollama_pull", lambda model, total, out=None, client=None: calls.append(("ollama", model)))
    events = []
    assert M.download(path, "leggera", out=lambda **kw: events.append(kw)) is True
    assert calls == [("stt", "mlx-community/whisper-small-mlx-q4")]               # il chatbot c'e' gia': non si riscarica
    assert events[-1] == {"event": "finished", "ok": True}
    calls.clear()
    assert M.download(path, "pesante", out=lambda **kw: None) is True             # il chatbot MLX si scarica da Hugging Face: Ollama non c'entra
    assert calls == [("stt", "mlx-community/whisper-large-v3-mlx"), ("llm", "mlx-community/gemma-2-9b-it-4bit")]
    calls.clear()
    assert M.download(path, "pesante", "mlx:mlx-community/gemma-3-text-4b-it-4bit", out=lambda **kw: None) is True    # chatbot scelto a mano e gia' installato
    assert calls == [("stt", "mlx-community/whisper-large-v3-mlx")]
    calls.clear()
    monkeypatch.setattr(M, "_ensure_ollama", lambda wait_s=25.0: True)
    assert M.download(path, "media", "llama3.1:8b", out=lambda **kw: None) is True        # un chatbot di Ollama si prende con Ollama
    assert calls == [("stt", "mlx-community/whisper-large-v3-turbo-q4"), ("ollama", "llama3.1:8b")]     # (qui nessun riconoscimento e' installato)
    monkeypatch.setattr(M, "_ensure_ollama", lambda wait_s=25.0: False)
    events.clear()
    assert M.download(path, "media", "llama3.2:3b", out=lambda **kw: events.append(kw)) is False and "Ollama non e' acceso" in events[-1]["message"]


def test_profiles_table_is_consistent():
    assert set(P.PROFILES) == {"leggera", "media", "pesante"}
    for pid, p in P.PROFILES.items():
        if p["stt"]:
            assert p["stt"]["model"] in P.STT_MB and p["stt"]["model"] in P.STT_NAMES, pid
    assert P.STT_MB["mlx-community/whisper-small-mlx-q4"] < P.STT_MB["mlx-community/whisper-large-v3-turbo-q4"] < P.STT_MB["mlx-community/whisper-large-v3-mlx"]
    assert P.PROFILES["leggera"]["ram_gb"] < P.PROFILES["media"]["ram_gb"] < P.PROFILES["pesante"]["ram_gb"]


# ------------------------------------------------------------------ versione personalizzata e scelta del modello di riconoscimento
def test_custom_profile_applies_chosen_models(tmp_path):
    path = _cfg(tmp_path)
    P.save_settings(path, {"profile": "personalizzata", "stt_model": "mlx-community/whisper-small-mlx", "llm_model": "Gemma4-12B:latest"})
    b = cfgmod.load(path)["brains"][0]
    assert b["stt"] == {"kind": "mlx-whisper", "model": "mlx-community/whisper-small-mlx", "prompt": False}
    assert b["llm"]["model"] == "Gemma4-12B:latest" and b["llm"]["extra_body"] == {"reasoning_effort": "none"}
    assert cfgmod.load(path)["profile"] == "personalizzata"
    P.save_settings(path, {"profile": "personalizzata", "llm_model": "llama3.2:3b"})          # il riconoscimento non scelto resta quello di config.yaml
    b = cfgmod.load(path)["brains"][0]
    assert b["stt"]["model"] == "mlx-community/whisper-large-v3-turbo-q4" and b["llm"]["model"] == "llama3.2:3b"


def test_different_stt_turns_a_preset_into_custom(tmp_path):
    base = cfgmod.load(_cfg(tmp_path), settings=False)
    t = M._target(base, "leggera", "mlx-community/whisper-medium-mlx", None)
    assert t["profile"] == "personalizzata" and P.stt_repo(t["stt"]) == "mlx-community/whisper-medium-mlx" and t["llm"] == "mlx:mlx-community/gemma-3-text-4b-it-4bit"
    t = M._target(base, "leggera", "mlx-community/whisper-small-mlx-q4", None)           # uguale a quello della versione: resta Leggera
    assert t["profile"] == "leggera"
    assert M._target(base, "personalizzata")["llm"] == "gemma3:4b"                       # senza scelte: come la Media


def test_apply_custom_saves_both_choices(tmp_path, monkeypatch):
    path = _cfg(tmp_path)
    llms = [{"name": "gemma3:4b", "gb": 3.3}, {"name": "llama3.1:8b", "gb": 4.9}]
    monkeypatch.setattr(M, "stt_installed", lambda c: c["model"] == "mlx-community/whisper-medium-mlx")
    r = M.apply(path, "personalizzata", "llama3.1:8b", "mlx-community/whisper-medium-mlx", llms)
    assert r == {"ok": True, "profile": "personalizzata", "stt": "mlx-community/whisper-medium-mlx", "llm": "llama3.1:8b"}
    assert P.load_settings(path) == {"profile": "personalizzata", "stt_model": "mlx-community/whisper-medium-mlx", "llm_model": "llama3.1:8b"}
    # da una versione, con un riconoscimento diverso: si salva come personalizzata
    assert M.apply(path, "media", None, "mlx-community/whisper-medium-mlx", llms)["profile"] == "personalizzata"
    r = M.apply(path, "personalizzata", None, "mlx-community/whisper-tiny-mlx", llms)         # non scaricato
    assert not r["ok"] and "whisper-tiny-mlx" in r["error"]
    assert P.load_settings(path)["stt_model"] == "mlx-community/whisper-medium-mlx"           # il rifiuto non ha toccato il file


def test_invalid_names_are_rejected(tmp_path):
    path = _cfg(tmp_path)
    for stt in ("../etc/passwd", "whisper", "a b/c", "https://huggingface.co/x/y"):
        r = M.apply(path, "personalizzata", None, stt, [])
        assert not r["ok"] and "non e' valido" in r["error"], stt
    assert not M.apply(path, "personalizzata", "gemma3 4b", None, [])["ok"]
    events = []
    assert M.download(path, "personalizzata", None, "../x", out=lambda **kw: events.append(kw)) is False and events[-1]["event"] == "error"
    assert P.load_settings(path) == {}


def test_mlx_whisper_problem_detects_wrong_format(tmp_path, monkeypatch):
    def snap(files):
        d = tmp_path / ("s" + str(len(list(tmp_path.iterdir()))))
        d.mkdir()
        for name, content in files.items():
            (d / name).write_text(content)
        monkeypatch.setattr(M, "_snapshot_dir", lambda repo: str(d))
    monkeypatch.setattr(M, "_snapshot_dir", lambda repo: None)
    assert "scaricato" in M.mlx_whisper_problem("a/b")
    snap({"config.json": json.dumps({"n_audio_state": 512}), "weights.npz": "x"})
    assert M.mlx_whisper_problem("a/b") is None
    snap({"config.json": json.dumps({"model_type": "whisper", "d_model": 512}), "model.safetensors": "x"})     # formato "transformers", non MLX
    assert "MLX" in M.mlx_whisper_problem("a/b")
    snap({"config.json": json.dumps({"n_audio_state": 512})})
    assert "pesi" in M.mlx_whisper_problem("a/b")
    snap({"config.json": "{rotto"})
    assert "config.json" in M.mlx_whisper_problem("a/b")


def test_ollama_registry_size_lookup():
    seen = []

    def handler(req):
        seen.append(str(req.url))
        if "missing" in str(req.url):
            return httpx.Response(404)
        return httpx.Response(200, json={"layers": [{"size": 5_000_000_000}, {"size": 400_000_000}]})
    c = httpx.Client(transport=httpx.MockTransport(handler))
    assert M.ollama_size_bytes("gemma2:9b", c) == 5_400_000_000
    assert M.ollama_size_bytes("miousername/mio-modello", c) == 5_400_000_000
    assert M.ollama_size_bytes("missing:1b", c) is None
    assert seen[0].endswith("/v2/library/gemma2/manifests/9b") and seen[1].endswith("/v2/miousername/mio-modello/manifests/latest")


def test_status_lists_catalog_and_chosen_repo(tmp_path, monkeypatch):
    path = _cfg(tmp_path)
    monkeypatch.setattr(M, "stt_installed", lambda c: P.stt_repo(c) in ("mlx-community/whisper-small-mlx-q4", "x/mio-modello"))
    monkeypatch.setattr(M, "disk_free_gb", lambda p=None: 19.0)
    monkeypatch.setattr(M, "ram_total_gb", lambda: 16.0)
    s = M.status(path, [], extra_stt="x/mio-modello")
    byrepo = {m["repo"]: m for m in s["stt_models"]}
    assert len(s["stt_models"]) == len(P.STT_CATALOG) + 1
    assert byrepo["mlx-community/whisper-small-mlx-q4"]["installed"] and byrepo["mlx-community/whisper-small-mlx-q4"]["wer"] == [10, 31, 27]
    assert byrepo["x/mio-modello"]["custom"] is True and byrepo["x/mio-modello"]["installed"] is True
    assert not byrepo["mlx-community/whisper-tiny-mlx"]["installed"]
    assert s["ram_total_gb"] == 16.0 and s["active_stt"] == "mlx-community/whisper-large-v3-turbo-q4"
    P.save_settings(path, {"profile": "personalizzata", "stt_model": "y/altro", "llm_model": "llama3.2:3b"})
    s = M.status(path, [])
    assert (s["active_profile"], s["active_stt"], s["active_llm"]) == ("personalizzata", "y/altro", "llama3.2:3b")
    assert any(m["repo"] == "y/altro" and m["custom"] for m in s["stt_models"])               # il modello attivo scelto a mano compare in elenco


def test_download_custom_stt_checks_size_and_name(tmp_path, monkeypatch):
    path = _cfg(tmp_path)
    monkeypatch.setattr(M, "stt_installed", lambda c: False)
    monkeypatch.setattr(M, "installed_llms", lambda client=None: [{"name": "gemma3:4b", "gb": 3.3}])
    monkeypatch.setattr(M, "disk_free_gb", lambda p=None: 50.0)
    monkeypatch.setattr(M, "mlx_whisper_problem", lambda repo: None)
    calls = []
    monkeypatch.setattr(M, "hf_download", lambda repo, total, out=None: calls.append((repo, total)))
    monkeypatch.setattr(M, "hf_total_bytes", lambda repo: 777_000_000)
    assert M.download(path, "personalizzata", None, "x/mio-modello", out=lambda **kw: None) is True
    assert calls == [("x/mio-modello", 777_000_000)]                                       # peso preso dalla rete: non e' nel catalogo
    def nf(repo):
        raise RuntimeError("404")
    monkeypatch.setattr(M, "hf_total_bytes", nf)
    events = []
    assert M.download(path, "personalizzata", None, "x/non-esiste", out=lambda **kw: events.append(kw)) is False
    assert "Non trovo il modello" in events[-1]["message"]
    monkeypatch.setattr(M, "hf_total_bytes", lambda repo: 1)
    monkeypatch.setattr(M, "mlx_whisper_problem", lambda repo: "non e' nel formato MLX Whisper")
    events.clear()
    assert M.download(path, "personalizzata", None, "x/trasformers", out=lambda **kw: events.append(kw)) is False
    assert "formato MLX" in events[-1]["message"]


def test_ram_estimate_matches_measurements():
    assert abs(P.estimate_ram_gb(464, 2.6) - 4.4) < 0.8                                     # Media (Whisper turbo + Gemma 3 4B MLX): misurata 4,3-4,4 GB
    assert P.estimate_ram_gb(3084, 5.2) > 10 and P.estimate_ram_gb(None, 2.6) > P.estimate_ram_gb(197, 2.6)
    assert [c["mb"] for c in P.STT_CATALOG] == sorted(c["mb"] for c in P.STT_CATALOG)       # elenco dal piu' piccolo al piu' grande
    assert P.PROFILES["media"]["measured"] and P.PROFILES["media"]["ram_gb"] == 4.4


# ------------------------------------------------------------------ rimozione dei modelli
def _status_with(monkeypatch, path, stt_have, mlx_have, ollama=None, active=None):
    monkeypatch.setattr(M, "stt_installed", lambda c: P.stt_repo(c) in stt_have)
    monkeypatch.setattr(M, "mlx_lm_installed", lambda repo: repo in mlx_have)
    monkeypatch.setattr(M, "disk_free_gb", lambda p=None: 19.0)
    monkeypatch.setattr(M, "ram_total_gb", lambda: 16.0)
    if active:
        P.save_settings(path, active)
    return M.status(path, ollama or [])


def test_status_lists_chatbots_from_mlx_and_ollama_and_flags_removable(tmp_path, monkeypatch):
    path = _cfg(tmp_path, {"brains": [{"name": "mac", "llm": {"kind": "mlx-lm", "model": "mlx-community/gemma-3-text-4b-it-4bit"},
                                       "stt": {"kind": "mlx-whisper", "model": "mlx-community/whisper-large-v3-turbo-q4"}, "tts": {"kind": "say"}}]})
    llms = [{"name": "Gemma4-12B:latest", "gb": 9.8, "params": "12B", "heavy": True, "reasoning": True}]
    s = _status_with(monkeypatch, path, {"mlx-community/whisper-large-v3-turbo-q4", "mlx-community/whisper-small-mlx-q4"},
                     {"mlx-community/gemma-3-text-4b-it-4bit", "mlx-community/gemma-2-9b-it-4bit"}, llms)
    assert s["active_llm"] == "mlx:mlx-community/gemma-3-text-4b-it-4bit"
    by = {m["ref"]: m for m in s["llm_models"]}
    assert by["mlx:mlx-community/gemma-3-text-4b-it-4bit"]["block"] == "in uso" and not by["mlx:mlx-community/gemma-3-text-4b-it-4bit"]["removable"]
    assert by["mlx:mlx-community/gemma-2-9b-it-4bit"]["removable"] and by["Gemma4-12B:latest"]["source"] == "ollama" and by["Gemma4-12B:latest"]["removable"]
    assert not by["mlx:mlx-community/gemma-3-1b-it-4bit"]["installed"] and "removable" not in by["mlx:mlx-community/gemma-3-1b-it-4bit"]
    st = {m["repo"]: m for m in s["stt_models"]}
    assert st["mlx-community/whisper-large-v3-turbo-q4"]["block"] == "in uso" and st["mlx-community/whisper-small-mlx-q4"]["removable"]
    assert s["ollama"] is True and s["profiles"][0]["llm"]["label"] == "Gemma 3 4B"


def test_the_last_installed_model_cannot_be_removed(tmp_path, monkeypatch):
    path = _cfg(tmp_path)
    s = _status_with(monkeypatch, path, {"mlx-community/whisper-large-v3-turbo-q4"}, set(), [{"name": "gemma3:4b", "gb": 3.3, "heavy": False, "reasoning": False}])
    assert {m["repo"]: m["block"] for m in s["stt_models"] if m["installed"]} == {"mlx-community/whisper-large-v3-turbo-q4": "in uso"}
    # senza Whisper in uso: l'unico rimasto resta comunque protetto
    P.save_settings(path, {"profile": "personalizzata", "stt_model": "mlx-community/whisper-small-mlx-q4", "llm_model": "gemma3:4b"})
    s = _status_with(monkeypatch, path, {"mlx-community/whisper-large-v3-turbo-q4"}, set(), [{"name": "gemma3:4b", "gb": 3.3, "heavy": False, "reasoning": False}])
    only = [m for m in s["stt_models"] if m["installed"]]
    assert len(only) == 1 and only[0]["block"] == "ultimo installato"


def test_remove_refuses_in_use_and_last_and_unknown(tmp_path, monkeypatch):
    path = _cfg(tmp_path)
    llms = [{"name": "gemma3:4b", "gb": 3.3, "heavy": False, "reasoning": False}, {"name": "llama3.2:3b", "gb": 2.0, "heavy": False, "reasoning": False}]
    s = _status_with(monkeypatch, path, {"mlx-community/whisper-large-v3-turbo-q4", "mlx-community/whisper-tiny-mlx"}, set(), llms)
    r = M.remove(path, "stt", "mlx-community/whisper-large-v3-turbo-q4", s)
    assert not r["ok"] and "sta usando" in r["error"]
    r = M.remove(path, "llm", "gemma3:4b", s)
    assert not r["ok"] and "sta usando" in r["error"]
    r = M.remove(path, "stt", "mlx-community/whisper-base-mlx", s)
    assert not r["ok"] and "non e' installato" in r["error"]
    assert not M.remove(path, "stt", "../../etc", s)["ok"] and not M.remove(path, "boh", "x/y", s)["ok"]
    assert M.remove(path, "llm", "mlx:mlx-community/gemma-2-9b-it-4bit", s)["error"] == "Questo modello non e' installato."


def test_remove_deletes_only_inside_the_hf_cache(tmp_path, monkeypatch):
    cache = tmp_path / "hub"
    repo_dir = cache / "models--mlx-community--whisper-tiny-mlx"
    (repo_dir / "blobs").mkdir(parents=True)
    (repo_dir / "blobs" / "abc").write_bytes(b"x" * 3_000_000)
    (repo_dir / "snapshots" / "rev").mkdir(parents=True)
    (repo_dir / "snapshots" / "rev" / "weights.npz").symlink_to(repo_dir / "blobs" / "abc")       # come nella cache vera: un collegamento al blob
    monkeypatch.setattr("huggingface_hub.constants.HF_HUB_CACHE", str(cache))
    path = _cfg(tmp_path)
    s = _status_with(monkeypatch, path, {"mlx-community/whisper-large-v3-turbo-q4", "mlx-community/whisper-tiny-mlx"}, set(),
                     [{"name": "gemma3:4b", "gb": 3.3, "heavy": False, "reasoning": False}])
    r = M.remove(path, "stt", "mlx-community/whisper-tiny-mlx", s)
    assert r == {"ok": True, "freed_mb": 3} and not repo_dir.exists()                              # 3 MB, non 6: il collegamento non si conta due volte
    assert cache.exists()                                                    # la cache stessa e le altre cartelle restano


def test_remove_ollama_model_uses_the_delete_api(tmp_path, monkeypatch):
    path = _cfg(tmp_path)
    llms = [{"name": "gemma3:4b", "gb": 3.3, "heavy": False, "reasoning": False}, {"name": "llama3.2:3b", "gb": 2.0, "heavy": False, "reasoning": False}]
    s = _status_with(monkeypatch, path, {"mlx-community/whisper-large-v3-turbo-q4"}, set(), llms)
    seen = {}

    def handler(req):
        seen["m"], seen["url"], seen["body"] = req.method, str(req.url), json.loads(req.content)
        return httpx.Response(200)
    r = M.remove(path, "llm", "llama3.2:3b", s, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert r["ok"] and seen["m"] == "DELETE" and seen["url"].endswith("/api/delete") and seen["body"] == {"model": "llama3.2:3b"}


def test_chatbot_reference_helpers():
    assert P.llm_ref_from_text("llama3.1:8b") == "llama3.1:8b" and P.llm_ref_from_text("llama3.1") == "llama3.1"
    assert P.llm_ref_from_text("mlx-community/gemma-3-1b-it-4bit") == "mlx:mlx-community/gemma-3-1b-it-4bit"
    assert P.llm_ref_from_text("mlx:org/x") == "mlx:org/x"
    assert P.llm_label("mlx:mlx-community/gemma-2-9b-it-4bit") == "Gemma 2 9B" and P.llm_label("mlx:org/boh") == "org/boh" and P.llm_label("gemma3:4b") == "gemma3:4b"
    assert M._check_names(None, "mlx:../x") and M._check_names(None, "mlx:org/ok") is None and M._check_names(None, "gemma3:4b") is None


def test_mlx_chatbot_download_checks_the_format(tmp_path, monkeypatch):
    path = _cfg(tmp_path)
    monkeypatch.setattr(M, "stt_installed", lambda c: True)
    monkeypatch.setattr(M, "installed_llms", lambda client=None: None)         # Ollama non c'e': non serve
    monkeypatch.setattr(M, "mlx_lm_installed", lambda repo: False)
    monkeypatch.setattr(M, "disk_free_gb", lambda p=None: 50.0)
    monkeypatch.setattr(M, "hf_total_bytes", lambda repo: 1_000_000)
    monkeypatch.setattr(M, "hf_download", lambda repo, total, out=None, item="stt": "/x")
    monkeypatch.setattr(M, "mlx_lm_problem", lambda repo: "il tipo di modello 'boh' non e' supportato da Aria")
    events = []
    assert M.download(path, "personalizzata", "mlx:org/strano", None, out=lambda **kw: events.append(kw)) is False
    assert "non e' supportato" in events[-1]["message"]


def test_mlx_chatbot_install_detection(tmp_path, monkeypatch):
    d = tmp_path / "snap"
    d.mkdir()
    monkeypatch.setattr(M, "_snapshot_dir", lambda repo: str(d))
    assert not M.mlx_lm_installed("a/b")                                       # manca tutto
    (d / "config.json").write_text(json.dumps({"model_type": "gemma3_text"}))
    assert not M.mlx_lm_installed("a/b")                                       # manca il peso
    (d / "model.safetensors").write_bytes(b"x" * 2_000_000)
    assert M.mlx_lm_installed("a/b")
    (d / "model.safetensors").unlink()
    (d / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {"a": "model-1.safetensors", "b": "model-2.safetensors"}}))
    (d / "model-1.safetensors").write_bytes(b"x")
    assert not M.mlx_lm_installed("a/b")                                       # un pezzo manca: download incompleto
    (d / "model-2.safetensors").write_bytes(b"x")
    assert M.mlx_lm_installed("a/b")


def test_pocket_voice_becomes_the_automatic_voice_so_the_natural_one_can_be_switched_on_live(tmp_path):
    import yaml
    from aria import config as cfgmod
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"brains": [{"name": "m", "tts": {"kind": "pocket", "language": "italian", "voice": "lola"}}]}))
    t = cfgmod.load(str(path))["brains"][0]["tts"]
    assert t["kind"] == "natural" and t["voice"] == "lola" and t["_config_path"].endswith("config.yaml")
    from aria.tts import AutoTTS, QwenTTS
    a = AutoTTS(t)
    assert a.voice == "lola" and a.chunk_chars == 30                   # spenta: la voce di prima, a pezzi corti
    a.set_voice("marco")
    assert a.qwen.voice == "marco" and a.pocket.voice == "lola"        # le voci della naturale non toccano quella di Pocket
    assert QwenTTS.NATURAL_ONLY == ("aria", "chiara", "elena", "marco") and set(QwenTTS.FOLLOW) >= {"lola", "mary", "anna", "paul", "george", "javert"}      # (i nomi del selettore dell'app hanno tutti la loro voce naturale)
    assert QwenTTS.VOICES == QwenTTS.NATURAL_ONLY + QwenTTS.FOLLOW


def test_the_wake_phrase_can_be_chosen_in_the_settings_and_wins_over_config(tmp_path):
    from aria import models as M
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"wake": {"phrase": "ciao aria"}, "brains": [{"name": "m", "tts": {"kind": "pocket", "voice": "lola"}}]}))
    assert cfgmod.load(str(path))["wake"]["phrase"] == "ciao aria"
    assert M.wake_set(str(path), "Aria")["ok"] is False                                      # una parola sola: scatterebbe in ogni frase
    assert M.wake_set(str(path), "Hey, Aria!") == {"ok": True, "wake_phrase": "hey aria"}
    assert cfgmod.load(str(path))["wake"]["phrase"] == "hey aria" and M._wake_status(str(path)) == "hey aria"
    P.set_power(str(path), "screen_mac", True)                                               # (salvare altro non la perde)
    P.save_settings(str(path), {"profile": "media"})
    assert P.get_wake_phrase(str(path)) == "hey aria"
    P.set_wake_phrase(str(path), None)
    assert cfgmod.load(str(path))["wake"]["phrase"] == "ciao aria"


def test_battery_rest_is_a_switch_in_the_settings_and_on_by_default(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"brains": [{"name": "m"}]}))
    assert P.get_powers(str(path))["battery_rest"] is True
    P.set_power(str(path), "battery_rest", False)
    assert P.get_powers(str(path))["battery_rest"] is False
