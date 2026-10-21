"""La lingua si sceglie nelle Impostazioni: salvataggio, comando del backend, e cosa cambia (scritte delle Impostazioni, riconoscimento vocale, voce, carattere)."""
import json

import pytest
import yaml

from aria import config as cfgmod
from aria import i18n
from aria import models as M
from aria import profiles as P
from test_profiles import _cfg


@pytest.fixture
def path(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "stt_installed", lambda c: True)
    monkeypatch.setattr(M, "disk_free_gb", lambda p=None: 19.0)
    monkeypatch.setattr(M, "mlx_lm_installed", lambda repo: True)
    return _cfg(tmp_path)


def test_the_language_is_saved_and_survives_model_choices(path):
    assert P.get_language(path) is None
    r = M.language_set(path, "en")
    assert r["ok"] and r["current"] == "en" and r["chosen"] == "en" and r["supported"] == ["it", "en"]
    P.save_settings(path, {"profile": "leggera", "llm_model": None})                       # salvare i modelli non perde la lingua
    P.set_power(path, "music", False)                                                      # ...e nemmeno accendere/spegnere una funzione
    assert P.get_language(path) == "en"
    assert M.language_set(path, "auto")["chosen"] is None and P.get_language(path) is None
    assert M.language_set(path, "klingon")["ok"] is False


def test_system_language_is_the_fallback_and_settings_win_over_config(tmp_path, monkeypatch):
    plain = _cfg(tmp_path)
    monkeypatch.setattr(i18n, "system_language", lambda: "en")
    assert M.current_language(plain) == "en"                                               # senza altro: la lingua del sistema
    monkeypatch.setattr(i18n, "system_language", lambda: "it")
    assert M.current_language(plain) == "it"
    forced = _cfg(tmp_path, {"language": "en"})
    assert M.current_language(forced) == "en"                                              # config.yaml vale piu' del sistema
    M.language_set(forced, "it")
    assert M.current_language(forced) == "it"                                              # le Impostazioni valgono piu' di config.yaml
    M.language_set(forced, "auto")
    assert M.current_language(forced) == "en"                                              # «auto» toglie la scelta: si torna a config.yaml


def test_status_speaks_the_chosen_language(path):
    it = M.status(path, [])
    assert it["language"]["current"] == "it"
    assert {p["id"]: p["label"] for p in it["profiles"]}["leggera"] == "Leggera"
    M.language_set(path, "en")
    en = M.status(path, [])
    assert en["language"] == {"current": "en", "chosen": "en", "system": i18n.system_language(), "supported": ["it", "en"]}
    labels = {p["id"]: p for p in en["profiles"]}
    assert labels["leggera"]["label"] == "Light" and labels["pesante"]["label"] == "Heavy" and "Aria's current setup" in labels["media"]["summary"]
    stt = {m["repo"]: m for m in en["stt_models"]}
    assert stt["apple:speech"]["label"] == "Apple (built into the Mac)" and stt["apple:speech"]["note"].startswith("The Mac's own")
    llm = {m["ref"]: m for m in en["llm_models"]}
    assert llm["mlx:mlx-community/gemma-4-e4b-it-4bit"]["note"].startswith("Tested at length") and llm["mlx:mlx-community/gemma-4-e4b-it-4bit"]["label"].endswith("· sees images")
    powers = {p["id"]: p for p in en["powers"]}
    assert powers["reminders"]["label"] == "Reminders" and powers["music"]["hint"].startswith("Controls Music")
    assert "Italian only" in powers["voice_natural"]["hint"] or "Italian" in powers["voice_natural"]["hint"]
    assert "Gemma 4" in powers["screen_model"]["hint"] and "Models that see images" in powers["screen_model"]["hint"]


def test_every_setting_text_has_an_english_version():
    from aria import ui_en
    assert set(ui_en.PROFILES) == set(P.PROFILES)
    assert set(ui_en.POWERS) == set(P.POWERS), set(P.POWERS) ^ set(ui_en.POWERS)
    assert set(ui_en.STT_NOTES) == {c["repo"] for c in P.STT_CATALOG}
    assert set(ui_en.LLM_NOTES) == {c["ref"] for c in P.LLM_CATALOG}
    for table in (ui_en.STT_NOTES, ui_en.LLM_NOTES):
        for text in table.values():
            assert text and not any(w in text.lower().split() for w in ("il", "della", "con", "quello", "sbaglia", "non")), text


def test_errors_come_out_in_english(path, monkeypatch):
    M.language_set(path, "en")
    monkeypatch.setattr(M, "stt_installed", lambda c: False)
    assert M.remove(path, "stt", "mlx-community/whisper-tiny-mlx") == {"ok": False, "error": "This model isn't installed."}
    r = M.apply(path, "inesistente")
    assert r == {"ok": False, "error": "unknown version: inesistente"}
    assert M.wake_set(path, "Aria")["error"].startswith("Type two or three words")
    assert M.power_set(path, "nope", True)["error"] == "unknown feature: nope"
    assert M._check_names("senza-barra", None).startswith("The speech recognition model name isn't valid")
    assert M._check_names(None, "bad name!").startswith("The chatbot name isn't valid")
    assert M.mlx_whisper_problem("org/inesistente") == "isn't downloaded"


def test_the_backend_command_line(path, capsys):
    assert M.main(["language", "--config", path]) == 0
    assert json.loads(capsys.readouterr().out)["current"] in ("it", "en")
    assert M.main(["language", "set", "--config", path, "en"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["chosen"] == "en"
    assert M.main(["status", "--config", path]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["language"]["current"] == "en" and {p["id"]: p["label"] for p in st["profiles"]}["media"] == "Medium"
    assert M.main(["language", "set", "--config", path, "xx"]) == 1


def test_config_follows_the_language(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump({"brains": [{"name": "m", "stt": {"kind": "mlx-whisper", "model": "mlx-community/whisper-large-v3-turbo-q4", "language": "it"},
                                             "tts": {"kind": "pocket", "voice": "lola", "language": "italian"}}], "persona_file": "persona.md"}))
    monkeypatch.setattr(i18n, "system_language", lambda: "it")
    it = cfgmod.load(str(p))
    assert it["language"] == "it" and it["brains"][0]["stt"]["language"] == "it" and it["brains"][0]["tts"]["language"] == "italian"
    P.set_language(str(p), "en")
    en = cfgmod.load(str(p))
    assert en["language"] == "en" and i18n.language() == "en"
    assert en["brains"][0]["stt"]["language"] == "en" and en["brains"][0]["tts"]["language"] == "english" and en["brains"][0]["tts"]["voice"] == "alba"
    assert en["persona_file"] == "persona.en.md"
    # una voce scelta a mano resta quella scelta
    p.write_text(yaml.safe_dump({"brains": [{"name": "m", "tts": {"kind": "pocket", "voice": "george", "language": "italian"}}]}))
    assert cfgmod.load(str(p))["brains"][0]["tts"]["voice"] == "george"
    i18n.set_language("it")
