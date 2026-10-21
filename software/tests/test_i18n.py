"""La lingua: scelta (Impostazioni > config.yaml > sistema), adattamento della configurazione, salvataggio nelle Impostazioni."""
import json

import yaml

from aria import config as cfgmod
from aria import i18n, profiles as P


def _cfg(tmp_path, extra=None):
    d = {"brains": [{"name": "mac", "stt": {"kind": "mlx-whisper", "model": "mlx-community/whisper-large-v3-turbo-q4", "prompt": False},
                     "tts": {"kind": "pocket", "language": "italian", "voice": "lola"}, "llm": {"kind": "mlx-lm", "model": "x"}}],
         "wake": {"phrase": "hey aria", "mode": "stt", "stt": None}, "persona_file": "persona.md"}
    d.update(extra or {})
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(d), encoding="utf-8")
    return str(path)


def test_codes_are_cleaned():
    assert i18n.clean("en") == "en" and i18n.clean("EN-us") == "en" and i18n.clean("English") == "en" and i18n.clean("inglese") == "en"
    assert i18n.clean("it_IT") == "it" and i18n.clean("Italiano") == "it"
    assert i18n.clean("fr") is None and i18n.clean(None) is None and i18n.clean("") is None
    assert i18n.clean("fr", "it") == "it"


def test_the_choice_order_is_settings_then_config_then_system(monkeypatch):
    monkeypatch.setattr(i18n, "system_language", lambda: "en")
    assert i18n.resolve(None, None) == "en"
    assert i18n.resolve(None, "it") == "it"
    assert i18n.resolve("it", "en") == "it"
    assert i18n.resolve("xx", "yy") == "en"                                     # valori che non conosce: si passa alla lingua del sistema


class _Out:
    def __init__(self, stdout):
        self.stdout = stdout


def test_the_first_preferred_language_of_the_mac_decides(monkeypatch):
    monkeypatch.setattr(i18n.sys, "platform", "darwin")
    monkeypatch.setattr(i18n.subprocess, "run", lambda *a, **k: _Out('(\n    "it-IT",\n    "en-US"\n)'))
    assert i18n._read_system_language() == "it"
    monkeypatch.setattr(i18n.subprocess, "run", lambda *a, **k: _Out('(\n    "en-IT",\n    "it-IT"\n)'))
    assert i18n._read_system_language() == "en"
    monkeypatch.setattr(i18n.subprocess, "run", lambda *a, **k: _Out('(\n    "de-DE"\n)'))
    assert i18n._read_system_language() == "en"                                 # le altre lingue: inglese


def test_without_the_mac_command_the_locale_decides(monkeypatch):
    monkeypatch.setattr(i18n.sys, "platform", "linux")
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("it_IT", "UTF-8"))
    assert i18n._read_system_language() == "it"
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("fr_FR", "UTF-8"))
    assert i18n._read_system_language() == "en"


def test_on_windows_the_display_language_decides(monkeypatch):
    import ctypes
    import types
    monkeypatch.setattr(i18n.sys, "platform", "win32")
    for langid, want in ((0x0410, "it"), (0x0810, "it"), (0x0409, "en"), (0x0809, "en"), (0x040C, "en")):          # italiano (Italia, Svizzera), inglese (USA, Regno Unito), francese
        fake = types.SimpleNamespace(kernel32=types.SimpleNamespace(GetUserDefaultUILanguage=lambda langid=langid: langid))
        monkeypatch.setattr(ctypes, "windll", fake, raising=False)
        assert i18n._read_system_language() == want, hex(langid)
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(kernel32=types.SimpleNamespace(GetUserDefaultUILanguage=lambda: 1 / 0)), raising=False)
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: (None, None))
    monkeypatch.delenv("LANG", raising=False)
    assert i18n._read_system_language() == "en"                                 # se Windows non risponde: inglese


def test_on_windows_the_region_decides_the_units(monkeypatch):
    import ctypes
    import types
    monkeypatch.setattr(i18n.sys, "platform", "win32")
    monkeypatch.setattr(i18n, "_current", "en")
    for name, want in (("en-US", "imperial"), ("en-GB", "metric"), ("en-AU", "metric"), ("it-IT", "metric"), ("en-LR", "imperial")):
        def locale_name(buf, size, name=name):
            buf.value = name
            return len(name) + 1
        fake = types.SimpleNamespace(kernel32=types.SimpleNamespace(GetUserDefaultLocaleName=locale_name))
        monkeypatch.setattr(ctypes, "windll", fake, raising=False)
        assert i18n.units({}) == want, name
    assert i18n.units({"units": "imperial"}) == "imperial" and i18n.units({"units": "metric"}) == "metric"      # la configurazione vince
    monkeypatch.setattr(i18n, "_current", "it")
    assert i18n.units({}) == "metric"                                           # l'italiano e' sempre metrico


def test_italian_changes_nothing_in_the_configuration(tmp_path):
    path = _cfg(tmp_path)
    base = cfgmod.load(path, settings=False)
    loaded = cfgmod.load(path)
    assert loaded["language"] == "it"
    assert loaded["brains"][0]["stt"] == base["brains"][0]["stt"] and loaded["brains"][0]["tts"]["language"] == "italian" and loaded["brains"][0]["tts"]["voice"] == "lola"
    assert loaded["persona_file"] == base["persona_file"]


def test_english_switches_recognition_voice_and_character(tmp_path):
    path = _cfg(tmp_path)
    P.set_language(path, "en")
    cfg = cfgmod.load(path)
    b = cfg["brains"][0]
    assert cfg["language"] == "en" and i18n.language() == "en"
    assert b["stt"]["language"] == "en"
    assert b["tts"]["language"] == "english" and b["tts"]["voice"] == "alba"        # la voce di fabbrica dell'italiano diventa quella di fabbrica dell'inglese
    assert cfg["persona_file"] == "persona.en.md"


def test_a_voice_chosen_by_the_user_is_kept_in_english(tmp_path):
    path = _cfg(tmp_path)
    d = yaml.safe_load(open(path)); d["brains"][0]["tts"]["voice"] = "jane"
    open(path, "w").write(yaml.safe_dump(d))
    P.set_language(path, "en")
    assert cfgmod.load(path)["brains"][0]["tts"]["voice"] == "jane"


def test_a_persona_file_chosen_by_the_user_is_kept_in_english(tmp_path):
    path = _cfg(tmp_path, {"persona_file": "mia_persona.md"})
    P.set_language(path, "en")
    assert cfgmod.load(path)["persona_file"] == "mia_persona.md"


def test_the_language_choice_survives_other_settings_and_can_be_removed(tmp_path):
    path = _cfg(tmp_path)
    P.set_language(path, "en")
    P.save_settings(path, {"profile": "leggera"})                                # salvare una versione non cancella la lingua
    assert P.get_language(path) == "en"
    P.set_language(path, None)
    assert P.get_language(path) is None and "language" not in json.load(open(P.settings_path(path)))


def test_the_language_from_config_yaml_is_used_without_settings(tmp_path):
    path = _cfg(tmp_path, {"language": "en"})
    assert cfgmod.load(path)["language"] == "en"
    P.set_language(path, "it")                                                   # le Impostazioni vincono
    assert cfgmod.load(path)["language"] == "it"


def test_pick_follows_the_current_language(english):
    assert i18n.pick("ciao", "hello") == "hello"


def test_pick_is_italian_by_default():
    assert i18n.pick("ciao", "hello") == "ciao"
