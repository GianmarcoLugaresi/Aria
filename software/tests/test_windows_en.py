"""Aria per Windows in due lingue: la scelta della lingua, i testi del menu e dei messaggi, le voci, il cambio di lingua dal menu dell'icona, la schermata e gli script di installazione.
Come per il resto di windows/aria_win, niente tocca Windows davvero: si prova la LOGICA con finti al posto delle chiamate al sistema."""
import datetime as dt
import json
import os
import re
import sys
import types
from pathlib import Path

import pytest

WINDOWS = Path(__file__).resolve().parent.parent.parent / "windows"
sys.path.insert(0, str(WINDOWS))

from aria import i18n                                    # noqa: E402
from aria_win import app as app_mod, hotkey, l10n, overlay, paths, voices   # noqa: E402
from aria_win.backend import BackendManager             # noqa: E402
from aria_win.model import AppModel                      # noqa: E402
from aria_win.tray import Tray                           # noqa: E402


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("ARIA_SUPPORT", str(tmp_path / "support"))
    monkeypatch.setenv("ARIA_LOCAL", str(tmp_path / "local"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ARIA_LANG", raising=False)
    monkeypatch.setattr(l10n, "_code", None)                     # la lingua si rilegge in ogni prova (e a fine prova torna com'era)
    monkeypatch.setattr(l10n, "system_language", lambda: "it")
    (tmp_path / "support").mkdir()


def english(monkeypatch):
    monkeypatch.setenv("ARIA_LANG", "en")
    monkeypatch.setattr(l10n, "_code", None)


# ---------------------------------------------------------------- la scelta della lingua
def test_the_choice_order_is_env_then_menu_then_config_then_windows(tmp_path, monkeypatch):
    support = tmp_path / "support"
    assert l10n.detect() == "it"                                                      # Windows in italiano
    monkeypatch.setattr(l10n, "system_language", lambda: "en")
    assert l10n.detect() == "en"
    (support / "config.yaml").write_text('name: Aria\nlanguage: "it"   # la lingua\n', encoding="utf-8")
    assert l10n.detect() == "it" and l10n.settings_choice() is None and l10n.chosen() == "auto"
    (support / "settings.json").write_text(json.dumps({"language": "en-US"}), encoding="utf-8")
    assert l10n.detect() == "en" and l10n.chosen() == "en"                            # il menu vince su config.yaml
    monkeypatch.setenv("ARIA_LANG", "it")
    assert l10n.detect() == "it"                                                      # la variabile (solo per le prove) vince su tutto
    (support / "settings.json").write_text("non e' json", encoding="utf-8")
    monkeypatch.delenv("ARIA_LANG")
    assert l10n.settings_choice() is None                                             # un file rovinato non rompe niente


def test_codes_are_cleaned():
    assert [l10n.clean(x) for x in ("en", "EN", "en-US", "English", "it", "it_IT", "italiano", "auto", "", None, "fr")] == ["en", "en", "en", "en", "it", "it", "it", None, None, None, None]


def test_the_language_of_windows_decides_when_nothing_is_chosen(monkeypatch):
    import ctypes
    monkeypatch.undo()                                                                 # (torna alla vera system_language)
    monkeypatch.setattr(sys, "platform", "win32")
    for langid, want in ((0x0410, "it"), (0x0810, "it"), (0x0409, "en"), (0x0809, "en"), (0x040C, "en")):
        fake = types.SimpleNamespace(kernel32=types.SimpleNamespace(GetUserDefaultUILanguage=lambda langid=langid: langid))
        monkeypatch.setattr(ctypes, "windll", fake, raising=False)
        assert l10n.system_language() == want, hex(langid)
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(kernel32=types.SimpleNamespace(GetUserDefaultUILanguage=lambda: 1 / 0)), raising=False)
    assert l10n.system_language() in ("it", "en")                                      # se Windows non risponde non si rompe niente


# ---------------------------------------------------------------- stato, menu e voci
def test_the_status_text_and_labels_follow_the_language(monkeypatch):
    m = AppModel()
    assert m.status_text() == "Stato: in avvio…" and m.wake_label() == "Parla con Aria" and m.hotkey_text() == "Ctrl+Alt+Spazio"
    english(monkeypatch)
    assert m.status_text() == "Status: starting…" and m.wake_label() == "Talk to Aria" and m.hotkey_text() == "Ctrl+Alt+Space"
    m.set_connected(True)
    assert m.status_text() == "Status: loading the models…"
    m.handle({"ready": True})
    assert m.status_text() == "Status: ready, say “Hey Aria”"
    m.handle({"wake_phrase": "ok aria"})
    assert m.status_text() == "Status: ready, say “Ok Aria”"
    m.handle({"state": "listening"})
    assert m.status_text() == "Status: listening" and m.wake_label() == "Stop Aria"
    m.handle({"state": "thinking"})
    assert m.status_text() == "Status: thinking"
    m.handle({"state": "speaking"})
    assert m.status_text() == "Status: speaking"
    m.handle({"state": "idle", "muted": True})
    assert m.status_text() == "Status: microphone muted"
    m.handle({"muted": False, "paused": True})
    assert m.status_text() == "Status: paused (on battery)"
    lab = m.labels()
    assert lab["voice"] == "Voice" and lab["language"] == "Language" and lab["autostart"] == "Start with Windows" and lab["quit"] == "Quit Aria" and lab["logs"] == "Show logs"
    assert lab["mute"] == "Mute the microphone (no “Ok Aria”)" and lab["lang_auto"] == "Automatic (like Windows)"
    m.hotkey = "Ctrl+Shift+A"
    assert m.hotkey_text() == "Ctrl+Shift+A"                                           # una scorciatoia personale resta com'e'
    m.hotkey = "Ctrl+Alt+Spazio"
    assert m.hotkey_text() == "Ctrl+Alt+Space"


def test_every_italian_label_has_an_english_one(monkeypatch):
    m = AppModel()
    it = m.labels()
    english(monkeypatch)
    en = m.labels()
    assert it.keys() == en.keys() and all(it[k] != en[k] for k in ("voice", "mute", "autostart", "language", "lang_auto", "folder", "config", "persona", "logs", "quit"))


def test_the_english_voices_are_the_same_as_the_backend_and_the_mac_menu(monkeypatch):
    assert voices.groups("it") == voices.GROUPS and voices.groups("en") == voices.GROUPS_EN
    assert sorted(voices.FEMALE_EN + voices.MALE_EN) == sorted(i18n.EN_VOICES)          # lo stesso elenco del cervello (e, per prova a parte, del menu del Mac)
    assert "lola" in voices.FEMALE and "lola" not in voices.FEMALE_EN and "giovanni" not in voices.MALE_EN
    m = AppModel()
    assert m.voice_groups()[0][0] == "Voci femminili"
    english(monkeypatch)
    assert [t for t, _ in m.voice_groups()] == ["Female voices", "Male voices"]


# ---------------------------------------------------------------- il menu dell'icona
class _Item:
    def __init__(self, text, action, **kw):
        self.text, self.action, self.kw = text, action, kw


class _Menu:
    SEPARATOR = object()

    def __init__(self, *items):
        self._items = items

    @property
    def items(self):                                            # come pystray: un'unica funzione = voci generate al momento
        return self._items[0]() if len(self._items) == 1 and callable(self._items[0]) else self._items


def _fake_pystray(monkeypatch):
    mod = types.ModuleType("pystray")
    mod.Menu, mod.MenuItem = _Menu, _Item
    monkeypatch.setitem(sys.modules, "pystray", mod)


def _texts(items):
    out = []
    for i in items:
        out.append("-" if i is _Menu.SEPARATOR else (i.text(i) if callable(i.text) else i.text))
    return out


def test_the_tray_menu_is_translated_and_has_a_language_submenu(monkeypatch):
    _fake_pystray(monkeypatch)
    calls = []
    actions = {k: (lambda *a, k=k: calls.append((k, a))) for k in ("wake", "stop", "set_voice", "set_language", "toggle_mute", "toggle_autostart", "pick_folder", "open_config", "open_persona", "open_logs", "quit")}
    model = AppModel()
    menu = Tray(model, actions)._menu()
    top = _texts(menu.items)
    assert top[0] == "Parla con Aria   (Ctrl+Alt+Spazio)" and "Voce" in top and "Lingua" in top and "Esci da Aria" in top and "Avvia con Windows" in top
    english(monkeypatch)
    top = _texts(menu.items)
    assert top[0] == "Talk to Aria   (Ctrl+Alt+Space)" and top[2] == "Status: starting…"
    assert top[4:8] == ["Voice", "Language", "Mute the microphone (no “Hey Aria”)", "Start with Windows"]
    assert top[-1] == "Quit Aria" and "Show logs" in top and "Open the configuration" in top
    voice = next(i for i in menu.items if i is not _Menu.SEPARATOR and callable(i.text) and i.text(i) == "Voice")
    names = [i.text for i in voice.action.items if i is not _Menu.SEPARATOR]
    assert names[0] == "Female voices" and "Alba" in names and "Lola" not in names and "Male voices" in names and "George" in names
    lang = next(i for i in menu.items if i is not _Menu.SEPARATOR and callable(i.text) and i.text(i) == "Language")
    labels = [i.text(i) if callable(i.text) else i.text for i in lang.action.items]
    assert labels == ["Automatic (like Windows)", "Italiano", "English"]
    model.language_choice = "en"
    assert [i.kw["checked"](i) for i in lang.action.items] == [False, False, True] and all(i.kw["radio"] for i in lang.action.items)
    lang.action.items[2].action()
    lang.action.items[0].action()
    assert calls == [("set_language", ("en",)), ("set_language", ("auto",))]
    alba = next(i for i in voice.action.items if i is not _Menu.SEPARATOR and i.text == "Alba")
    alba.action()
    assert calls[-1] == ("set_voice", ("alba",))


def test_the_real_pystray_menu_works_too(monkeypatch):
    """Con pystray vero (se c'e'): le funzioni del menu hanno il numero di parametri che pystray si aspetta, le voci cambiano con la lingua e i clic arrivano alle azioni."""
    pystray = pytest.importorskip("pystray")
    calls = []
    actions = {k: (lambda *a, k=k: calls.append((k, a))) for k in ("wake", "stop", "set_voice", "set_language", "toggle_mute", "toggle_autostart", "pick_folder", "open_config", "open_persona", "open_logs", "quit")}
    model = AppModel()
    menu = Tray(model, actions)._menu()

    def by_text(items, text):
        return next(i for i in items if i.text == text)
    top = list(menu)
    assert [i.text for i in top if i is not pystray.Menu.SEPARATOR][:2] == ["Parla con Aria   (Ctrl+Alt+Spazio)", "Stato: in avvio…"]
    lang = by_text(top, "Lingua")
    assert [i.text for i in lang.submenu] == ["Automatica (come Windows)", "Italiano", "English"]
    voice_it = [i.text for i in by_text(top, "Voce").submenu]
    assert voice_it[0] == "Voci femminili" and "Lola" in voice_it
    english(monkeypatch)
    model.language_choice = "en"
    top = list(menu)
    lang = by_text(top, "Language")
    assert [i.checked for i in lang.submenu] == [False, False, True]
    voice_en = [i.text for i in by_text(top, "Voice").submenu]
    assert voice_en[0] == "Female voices" and "Alba" in voice_en and "Lola" not in voice_en
    list(lang.submenu)[1](None)
    by_text(by_text(top, "Voice").submenu, "George")(None)
    by_text(top, "Quit Aria")(None)
    assert calls == [("set_language", ("it",)), ("set_voice", ("george",)), ("quit", ())]


# ---------------------------------------------------------------- il cambio di lingua dal menu
def _app(monkeypatch, tmp_path):
    a = app_mod.AriaApp()
    seen = []
    monkeypatch.setattr(a.backend, "restart", lambda: seen.append("restart"))
    monkeypatch.setattr(a.driver, "set_language", lambda c: seen.append(("overlay", c)))
    monkeypatch.setattr(a.tray, "refresh", lambda: seen.append("refresh"))
    return a, seen


def test_changing_language_from_the_menu_saves_it_redraws_everything_and_restarts_the_brain(monkeypatch, tmp_path):
    a, seen = _app(monkeypatch, tmp_path)
    a.model.voice, a.model.ready = "lola", True
    cli = []

    def fake_cli(*args):
        cli.append(args)
        (tmp_path / "support" / "settings.json").write_text(json.dumps({"language": args[2]}), encoding="utf-8")        # come fa `aria.models language set`
        return 0, {"ok": True, "current": args[2]}
    monkeypatch.setattr(a, "_models_cli", fake_cli)
    a._set_language("en")
    assert cli == [("language", "set", "en")] and l10n.code() == "en" and a.model.language_choice == "en"
    assert a.model.voice == "" and a.model.ready is False and a.model.problem is None
    assert seen == [("overlay", "en"), "refresh", "restart"]
    assert a.model.status_text() == "Status: starting…"
    a._set_language("en")                                                              # la stessa lingua: niente da fare
    assert len(cli) == 1


def test_a_failed_language_change_says_so_and_changes_nothing(monkeypatch, tmp_path):
    a, seen = _app(monkeypatch, tmp_path)
    monkeypatch.setattr(a, "_models_cli", lambda *args: (1, {"ok": False, "error": "unknown language: fr (use it, en or auto)"}))
    a._set_language("fr")
    assert a.model.problem == "unknown language: fr (use it, en or auto)" and l10n.code() == "it" and seen == ["refresh"]
    assert a.model.status_text().startswith("⚠ ")
    monkeypatch.setattr(a, "_models_cli", lambda *args: (3, {}))
    a._set_language("en")
    assert a.model.problem == "Non sono riuscita a cambiare la lingua."


def test_a_second_language_change_while_the_first_is_running_is_ignored(monkeypatch, tmp_path):
    a, seen = _app(monkeypatch, tmp_path)
    calls = []
    a._language_lock.acquire()
    monkeypatch.setattr(a, "_models_cli", lambda *args: calls.append(args) or (0, {"ok": True}))
    a._set_language("en")
    assert calls == [] and seen == []
    a._language_lock.release()


def test_the_real_models_program_is_driven_with_the_same_command_line_as_the_mac_app(monkeypatch, tmp_path):
    """`python -m aria.models language set en --config …` (davvero, in un processo a parte): scrive la scelta e risponde con un JSON che l'involucro sa leggere."""
    software = Path(__file__).resolve().parent.parent
    (tmp_path / "software").symlink_to(software)
    (tmp_path / "support" / "paths.json").write_text(json.dumps({"python": sys.executable, "software": str(software), "config": str(tmp_path / "support" / "config.yaml")}), encoding="utf-8")
    (tmp_path / "support" / "config.yaml").write_text("name: Aria\n", encoding="utf-8")
    a, seen = _app(monkeypatch, tmp_path)
    a._set_language("en")
    assert l10n.code() == "en" and l10n.chosen() == "en" and a.model.language_choice == "en" and seen == [("overlay", "en"), "refresh", "restart"]
    a._set_language("it")
    assert l10n.code() == "it" and a.model.language_choice == "it"
    a._set_language("auto")
    assert l10n.chosen() == "auto" and a.model.language_choice == "auto"


def test_the_english_personality_file_is_prepared_before_it_is_opened(monkeypatch, tmp_path):
    software = Path(__file__).resolve().parent.parent
    (tmp_path / "support" / "paths.json").write_text(json.dumps({"python": sys.executable, "software": str(software), "config": str(tmp_path / "support" / "config.yaml")}), encoding="utf-8")
    assert app_mod.AriaApp.persona_path() == str(tmp_path / "support" / "persona.md")          # in italiano: quello di sempre
    english(monkeypatch)
    target = tmp_path / "support" / "persona.en.md"
    assert app_mod.AriaApp.persona_path() == str(target) and "friendly voice" in target.read_text(encoding="utf-8")
    target.write_text("il mio carattere", encoding="utf-8")
    assert app_mod.AriaApp.persona_path() == str(target) and target.read_text(encoding="utf-8") == "il mio carattere"          # quello modificato dall'utente non si tocca


# ---------------------------------------------------------------- schermata, messaggi, scorciatoia
def test_the_overlay_page_and_its_language(monkeypatch):
    assert overlay.page_url().endswith("overlay.html?lang=it") and overlay.page_url("en").endswith("overlay.html?lang=en")
    english(monkeypatch)
    assert overlay.page_url().endswith("overlay.html?lang=en")
    js = []
    d = overlay.WebviewDriver()
    d.set_language("en")                                                                  # senza finestra non fa niente
    d.window = types.SimpleNamespace(evaluate_js=lambda code: js.append(code))
    d.set_language("en")
    d.set_language("it")
    d.set_language("fr")
    assert js == ["window.ARIA_LANG = 'en'; window.ariaLang && window.ariaLang('en')", "window.ARIA_LANG = 'it'; window.ariaLang && window.ariaLang('it')",
                  "window.ARIA_LANG = 'it'; window.ariaLang && window.ariaLang('it')"]
    d.window = types.SimpleNamespace(evaluate_js=lambda code: 1 / 0)
    d.set_language("en")                                                                  # un errore della pagina non rompe il cambio di lingua


def test_the_overlay_page_reads_the_language_from_the_address():
    page = (WINDOWS.parent / "app" / "Resources" / "overlay.html").read_text(encoding="utf-8")
    assert "Q.get('lang')" in page and "function ariaLang" in page


def test_backend_problems_are_reported_in_english(monkeypatch, tmp_path):
    english(monkeypatch)
    seen = []
    b = BackendManager(popen=lambda *a, **k: None)
    b.on_problem = seen.append
    b.start()
    assert seen[-1].startswith("Python not found (") and seen[-1].endswith("Run the installer.")
    py = tmp_path / "local" / "venv" / "Scripts"
    py.mkdir(parents=True)
    (py / "python.exe").write_text("")
    b.start()
    assert seen[-1].startswith("Configuration missing: ")


def test_shortcut_errors_are_in_english(monkeypatch):
    english(monkeypatch)
    for bad, text in (("Spazio", "Invalid shortcut"), ("Hyper+X", "Unknown modifier"), ("Ctrl+Alt+Blah", "Unknown key")):
        with pytest.raises(ValueError, match=text):
            hotkey.parse(bad)


def test_the_folder_picker_asks_in_the_right_language(monkeypatch):
    tk = types.ModuleType("tkinter")
    seen = []

    class Root:
        def withdraw(self): pass
        def attributes(self, *a): pass
        def destroy(self): pass
    tk.Tk, tk.filedialog = Root, types.SimpleNamespace(askdirectory=lambda title, mustexist: seen.append(title) or "")
    monkeypatch.setitem(sys.modules, "tkinter", tk)
    monkeypatch.setitem(sys.modules, "tkinter.filedialog", tk.filedialog)
    from aria_win import pick_folder
    pick_folder.main()
    english(monkeypatch)
    pick_folder.main()
    assert seen == ["Scegli la cartella dove Aria legge e scrive i file", "Choose the folder where Aria reads and writes files"]


# ---------------------------------------------------------------- gli script PowerShell (non si possono eseguire qui: controlli statici)
def _scripts():
    return [WINDOWS / "install.ps1", WINDOWS / "uninstall.ps1"]


def _strip_ps(text: str) -> str:
    """Toglie da uno script PowerShell stringhe, here-string e commenti, lasciando la struttura (parentesi, graffe)."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith('@"', i) or text.startswith("@'", i):                              # here-string: fino a «"@» a inizio riga
            q = text[i + 1]
            j = text.find("\n" + q + "@", i)
            assert j != -1, "here-string non chiusa"
            i = j + 3
            out.append(" STR ")
        elif c in "\"'":
            j = i + 1
            while j < n:
                if text[j] == "`" and c == '"':
                    j += 2
                    continue
                if text[j] == c:
                    if j + 1 < n and text[j + 1] == c:                                         # '' dentro '…' = apice
                        j += 2
                        continue
                    break
                j += 1
            assert j < n, "stringa non chiusa vicino a: " + text[i:i + 60]
            i = j + 1
            out.append(" STR ")
        elif c == "#":
            j = text.find("\n", i)
            i = n if j == -1 else j
        else:
            out.append(c)
            i += 1
    return "".join(out)


@pytest.mark.parametrize("script", _scripts(), ids=lambda p: p.name)
def test_the_powershell_scripts_have_balanced_quotes_and_brackets_and_a_bom(script):
    raw = script.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "senza BOM Windows PowerShell 5 legge male gli accenti"
    assert b"\r" not in raw
    code = _strip_ps(raw.decode("utf-8-sig"))
    for a, b in ("()", "{}", "[]"):
        assert code.count(a) == code.count(b), (script.name, a, code.count(a), code.count(b))
    depth = 0
    for ch in code:
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
            assert depth >= 0
    assert depth == 0


@pytest.mark.parametrize("script", _scripts(), ids=lambda p: p.name)
def test_the_powershell_scripts_are_bilingual_and_do_not_trip_on_case_insensitive_names(script):
    text = script.read_text(encoding="utf-8-sig")
    code = _strip_ps(text)
    assert "function T(" in text and "(T " in text and ("$Lingua" in text)
    # in PowerShell $IT e $it sono la stessa variabile: nessun parametro di funzione puo' avere il nome (senza badare alle maiuscole) di una variabile dello script
    script_vars = {m.group(1).lower() for m in re.finditer(r"^\$(\w+)\s*=", code, flags=re.M)}
    for fn in re.finditer(r"function\s+[\w-]+\s*\(([^)]*)\)", code):
        params = {p.lower() for p in re.findall(r"\$(\w+)", fn.group(1))}
        assert not (params & script_vars), (script.name, params & script_vars)
    # ogni (T "italiano" "inglese") ha due testi, e quello inglese e' solo ASCII (niente accenti ne' virgolette «curve»: Windows PowerShell 5 le legge male)
    calls = re.findall(r'\(T\s+"((?:[^"`]|`.)*)"\s+"((?:[^"`]|`.)*)"\)', text)
    assert len(calls) >= 3
    for ita, eng in calls:
        assert not re.search(r"[^\x00-\x7F]", eng), eng


def test_the_installer_has_the_language_option_and_tells_aria_which_language_to_use():
    text = (WINDOWS / "install.ps1").read_text(encoding="utf-8-sig")
    assert '[Alias("Language")][ValidateSet("auto", "it", "en")][string]$Lingua = "auto"' in text
    assert '[Alias("Model")]' in text and '[Alias("Yes")]' in text
    assert "aria.models language set $Lingua" in text and "TwoLetterISOLanguageName" in text
    assert text.count("if ($IsIt) {") == 1 and "persona.en.md" in text
    assert "Ctrl + Alt + Space" in text and "Ctrl + Alt + Spazio" in text
    un = (WINDOWS / "uninstall.ps1").read_text(encoding="utf-8-sig")
    assert "settings.json" in un and "$IsIt" in un


def test_the_windows_configuration_mentions_the_language():
    cfg = (WINDOWS / "config.windows.yaml").read_text(encoding="utf-8")
    assert "language: en" in cfg and "tts: {kind: pocket, language: italian, voice: lola}" in cfg          # Pocket: la lingua e la voce di partenza le cambia il cervello da solo


# ---------------------------------------------------------------- il cervello su Windows: promemoria, schermo e informazioni di sistema (stesse risposte del Mac dove si puo', onesto dove no)
def _windows_tools(tmp_path, monkeypatch, lang="it"):
    """Gli strumenti del cervello come se girassero su Windows (la lingua del cervello e' quella di aria.i18n, un'altra cosa da quella dell'involucro; conftest la rimette in italiano a fine prova)."""
    from aria import i18n
    from aria import powers as PW
    from aria import screen as SC
    from aria import sysinfo
    from test_powers import NOW, make
    t, _ = make(tmp_path)
    t.cfg["data_dir"] = str(tmp_path / "data")
    (tmp_path / "data").mkdir()
    for mod in (PW, SC, sysinfo):
        monkeypatch.setattr(mod.sys, "platform", "win32")
    i18n.set_language(lang)
    return t, NOW


async def test_on_windows_a_reminder_is_a_timer_at_the_right_time_and_survives_a_restart(tmp_path, monkeypatch):
    import time as _time
    from aria.textutil import ToolCall
    t, now = _windows_tools(tmp_path, monkeypatch, "en")
    out = await t.run(ToolCall("PROMEMORIA", "call Mark tomorrow at nine"))
    assert out == "Okay, tomorrow at nine a m I'll remind you to call Mark.", out
    (tid, (due, label)), = t.timer_meta.items()
    assert label == "to call Mark" and abs((due - _time.time()) - (dt.datetime(2026, 10, 7, 9, 0) - now).total_seconds()) < 5
    saved = json.loads((tmp_path / "data" / "timers.json").read_text())
    assert saved[0]["label"] == "to call Mark"                                          # sta su disco: alla prossima apertura si riarma
    assert (await t.run(ToolCall("PROMEMORIA_LISTA", ""))).startswith("You have one reminder: call Mark (tomorrow at nine a m)")
    from aria.main import _timer_message
    assert _timer_message(label) == "Reminder: to call Mark."                           # e a ora arrivata lo dice
    asks = await t.run(ToolCall("PROMEMORIA", "call Mark"))                             # senza un'ora non c'e' niente da armare: la chiede
    assert asks.endswith("|When should I remind you?") and asks.startswith("@CHIEDI|PROMEMORIA|")
    assert (await t.run(ToolCall("PROMEMORIA", "tomorrow at nine"))).endswith("|What should I remind you about?")
    t.timers[tid].cancel()


async def test_on_windows_a_reminder_in_italian_says_it_the_italian_way(tmp_path, monkeypatch):
    from aria.textutil import ToolCall
    t, now = _windows_tools(tmp_path, monkeypatch)
    out = await t.run(ToolCall("PROMEMORIA", "chiamare Mario domani alle nove"))
    assert out == "Va bene, domani alle nove ti ricordo di chiamare Mario.", out
    assert (await t.run(ToolCall("PROMEMORIA_LISTA", ""))).startswith("Hai un promemoria: chiamare Mario (domani alle nove)")
    from aria.main import _timer_message
    assert _timer_message("di chiamare Mario") == "Ti ricordo di chiamare Mario."
    assert (await t.run(ToolCall("PROMEMORIA", "chiamare Mario"))).endswith("|Per quando te lo ricordo?")
    for task in list(t.timers.values()):
        task.cancel()


async def test_on_windows_with_nothing_to_remind_the_list_says_so(tmp_path, monkeypatch):
    from aria.textutil import ToolCall
    t, _ = _windows_tools(tmp_path, monkeypatch, "en")
    assert await t.run(ToolCall("PROMEMORIA_LISTA", "")) == "You have no reminders to do."
    await t.run(ToolCall("TIMER", "ten minutes | pasta"))                               # un timer normale non e' un promemoria
    assert await t.run(ToolCall("PROMEMORIA_LISTA", "")) == "You have no reminders to do."
    for task in list(t.timers.values()):
        task.cancel()


async def test_on_windows_the_screen_questions_say_the_feature_is_not_there_instead_of_pointing_at_mac_settings(tmp_path, monkeypatch):
    from aria.textutil import ToolCall
    t, _ = _windows_tools(tmp_path, monkeypatch)
    for arg in ("leggi|", "dove|Esporta", "parere|riassumi la pagina", "indica|"):
        assert await t.run(ToolCall("SCHERMO", arg)) == "Su Windows questa funzione non c'è ancora."
    from aria import i18n
    i18n.set_language("en")
    try:
        out = await t.run(ToolCall("SCHERMO", "leggi|"))
    finally:
        i18n.set_language("it")
    assert out == "This feature isn't available on Windows yet." and "Mac" not in out


@pytest.mark.parametrize("lang", ["it", "en"])
async def test_on_windows_the_system_questions_are_answered_about_the_pc(tmp_path, monkeypatch, lang):
    from aria import i18n, sysinfo
    i18n.set_language(lang)
    try:
        monkeypatch.setattr(sysinfo.sys, "platform", "win32")
        monkeypatch.setattr(sysinfo, "_win_power", lambda: (80, False, 2 * 3600 + 15 * 60))
        monkeypatch.setattr(sysinfo, "_win_memory", lambda: (42, 16 * 2 ** 30))
        monkeypatch.setattr(sysinfo, "_win_uptime_seconds", lambda: 3 * 86400 + 5 * 3600)
        monkeypatch.setattr(sysinfo, "_win_build", lambda: 22631)
        monkeypatch.setattr(sysinfo, "_local_ip", lambda: "192.168.1.20")

        async def netsh(*cmd, timeout=8.0):
            return "    Name                   : Wi-Fi\n    BSSID                  : aa:bb:cc:dd:ee:ff\n    SSID                   : Casa Mia\n    Signal                 : 91%\n"
        monkeypatch.setattr(sysinfo, "_run", netsh)
        monkeypatch.setattr(sysinfo.shutil, "disk_usage", lambda path: (500 * 10 ** 9, 300 * 10 ** 9, 200 * 10 ** 9))
        said = {k: await sysinfo.answer(k) for k in ("batteria", "memoria", "accensione", "versione", "ip", "wifi", "spazio", "boh")}
    finally:
        i18n.set_language("it")
    if lang == "en":
        assert said["batteria"] == "You have eighty percent battery and you're not plugged in, about two hours and fifteen minutes left."
        assert said["memoria"] == "About forty-two percent of the memory is free of sixteen gigabytes."
        assert said["accensione"] == "The PC has been on for three days and five hours."
        assert said["versione"] == "You have Windows 11." and said["ip"] == "Your IP address on the local network is 192 dot 168 dot 1 dot 20."
        assert said["wifi"] == "You're connected to the wifi network Casa Mia." and said["spazio"].startswith("You have about ") and said["boh"] == "I can't tell you that about the PC."
    else:
        assert said["batteria"] == "Hai il ottanta per cento di batteria, non sei collegato alla corrente, resta circa due ore e quindici minuti."
        assert said["accensione"] == "Il PC è acceso da tre giorni e cinque ore." and said["versione"] == "Hai Windows 11." and said["wifi"] == "Sei collegato alla rete wifi Casa Mia."
        assert said["boh"] == "Questa informazione sul PC non la so dire."
    assert not any("Mac" in v or "macOS" in v for v in said.values()), said


async def test_on_windows_the_battery_and_errors_are_handled(tmp_path, monkeypatch):
    from aria import i18n, sysinfo
    monkeypatch.setattr(sysinfo.sys, "platform", "win32")
    i18n.set_language("en")
    try:
        monkeypatch.setattr(sysinfo, "_win_power", lambda: None)
        assert await sysinfo.answer("batteria") == "This PC has no battery."                  # un PC fisso
        monkeypatch.setattr(sysinfo, "_win_power", lambda: (100, True, None))
        assert await sysinfo.answer("batteria") == "The battery is fully charged and you're plugged in."
        monkeypatch.setattr(sysinfo, "_win_power", lambda: (55, True, None))
        assert await sysinfo.answer("batteria") == "The battery is at fifty-five percent and you're plugged in."
        monkeypatch.setattr(sysinfo, "_win_power", lambda: 1 / 0)
        monkeypatch.setattr(sysinfo, "_win_memory", lambda: 1 / 0)
        monkeypatch.setattr(sysinfo, "_win_build", lambda: 1 / 0)
        monkeypatch.setattr(sysinfo, "_win_uptime_seconds", lambda: 1 / 0)
        monkeypatch.setattr(sysinfo, "_local_ip", lambda: (_ for _ in ()).throw(OSError("rete")))
        assert [await sysinfo.answer(k) for k in ("batteria", "memoria", "versione", "accensione", "ip")] == [
            "I can't read the battery.", "I can't read the memory.", "I can't read the Windows version.", "I can't read how long the PC has been on.", "You don't seem to be connected to a network."]

        async def no_wifi(*cmd, timeout=8.0):
            return ""
        monkeypatch.setattr(sysinfo, "_run", no_wifi)
        assert await sysinfo.answer("wifi") == "You don't seem to be connected to wifi."
    finally:
        i18n.set_language("it")


def test_asking_for_the_windows_version_is_understood_in_both_languages():
    from aria import intent
    from aria.textutil import ToolCall
    for text in ("che versione di Windows ho", "quale Windows ho"):
        assert intent.detect(text, [], False) == ToolCall("SISTEMA", "versione"), text
    from aria import i18n
    i18n.set_language("en")
    try:
        for text in ("what version of Windows am I running", "which windows do I have"):
            assert intent.detect(text, [], False) == ToolCall("SISTEMA", "versione"), text
    finally:
        i18n.set_language("it")


async def test_on_windows_the_morning_briefing_includes_the_reminders(tmp_path, monkeypatch):
    from aria.textutil import ToolCall
    t, _ = _windows_tools(tmp_path, monkeypatch, "en")

    async def no_weather(arg):
        return ""

    async def no_news(n):
        return []
    monkeypatch.setattr(t, "_weather", no_weather)
    monkeypatch.setattr(t, "_headlines", no_news)
    await t.run(ToolCall("PROMEMORIA", "call Mark tomorrow at nine"))
    out = await t.run(ToolCall("BRIEFING", ""))
    assert "Among your reminders: call Mark." in out and "Mac" not in out
    for task in list(t.timers.values()):
        task.cancel()


def test_what_aria_says_she_can_do_on_windows_does_not_promise_the_mac_things(monkeypatch):
    from aria import everyday, everyday_en
    mac_it, mac_en = everyday.help_text({}), everyday_en.help_text({})
    assert "Sul Mac so" in mac_it and "calendario" in mac_it and "On the Mac I can" in mac_en and "calendar events" in mac_en and "look at the screen" in mac_en
    monkeypatch.setattr(everyday.sys, "platform", "win32")
    monkeypatch.setattr(everyday_en.sys, "platform", "win32")
    win_it, win_en = everyday.help_text({}), everyday_en.help_text({})
    assert "Su questo PC so metterti dei promemoria e dirti quali hai" in win_it and "calendario" not in win_it and "schermo" not in win_it and "Mac" not in win_it
    assert "On this PC I can set reminders and tell you which ones are coming up" in win_en and "calendar" not in win_en and "screen" not in win_en and "Mac" not in win_en
    assert "volume" in win_en and "controllare la musica e il volume" in win_it


async def test_what_aria_cannot_do_talks_about_the_pc_on_windows(tmp_path, monkeypatch):
    from aria.textutil import ToolCall
    t, _ = _windows_tools(tmp_path, monkeypatch, "en")
    assert "PC's settings" in await t.run(ToolCall("NON_SO", "system")) and "Mac" not in await t.run(ToolCall("NON_SO", "system"))
    from aria import i18n
    i18n.set_language("it")
    assert "impostazioni del PC" in await t.run(ToolCall("NON_SO", "system"))
