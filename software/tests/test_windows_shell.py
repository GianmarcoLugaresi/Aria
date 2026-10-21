"""Aria per Windows: l'involucro (windows/aria_win) e i pezzi del backend che cambiano su Windows. Niente di tutto questo tocca Windows davvero: si prova la LOGICA
(scorciatoie, stato e menu, avvio e riavvio del backend, WebSocket, registro, comparsa della schermata, app e volume) con finti al posto delle chiamate al sistema."""
import asyncio
import json
import os
import sys
import threading
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "windows"))

from aria import powers as PW                    # noqa: E402
from aria.config import load                     # noqa: E402
from aria.macos import MacError              # noqa: E402
from aria.memory import Memory                   # noqa: E402
from aria.tools import Tools                     # noqa: E402
from aria_win import autostart, hotkey, l10n, paths    # noqa: E402
from aria_win.backend import BackendManager      # noqa: E402
from aria_win.client import BackendClient        # noqa: E402
from aria_win.model import AppModel              # noqa: E402
from aria_win.overlay import OverlayController, target_origin   # noqa: E402


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("ARIA_SUPPORT", str(tmp_path / "support"))
    monkeypatch.setenv("ARIA_LOCAL", str(tmp_path / "local"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ARIA_LANG", "it")                           # di fabbrica le prove dell'involucro girano in italiano (l'inglese e' in test_windows_en.py)
    monkeypatch.setattr(l10n, "_code", None)


# ---------------------------------------------------------------- scorciatoia
def test_hotkey_specs_are_parsed_and_wrong_ones_are_refused():
    assert hotkey.parse("Ctrl+Alt+Spazio") == (hotkey.MOD_CONTROL | hotkey.MOD_ALT, 0x20)
    assert hotkey.parse("ctrl + shift + A") == (hotkey.MOD_CONTROL | hotkey.MOD_SHIFT, ord("A"))
    assert hotkey.parse("Win+F9") == (hotkey.MOD_WIN, 0x6F + 9)
    for bad in ("Spazio", "Ctrl+", "Hyper+X", "Ctrl+Alt+Blah", ""):
        with pytest.raises(ValueError):
            hotkey.parse(bad)
    hk = hotkey.HotKey("Ctrl+Alt+Space", lambda: None)
    started = hk.start()
    hk.stop()
    assert started is False or sys.platform == "win32"                                      # fuori da Windows non registra niente


# ---------------------------------------------------------------- stato e menu
def test_the_model_follows_the_backend_messages_like_the_mac_app_does():
    m = AppModel()
    assert m.status_text() == "Stato: in avvio…" and m.wake_label() == "Parla con Aria"
    m.set_connected(True)
    assert m.status_text() == "Stato: sto caricando i modelli…"
    assert m.handle({"ready": True, "wake_phrase": "hey aria"}) == {"ready"} and m.wake_phrase == "Hey Aria"            # (e' gia' la frase di fabbrica)
    assert m.handle({"wake_phrase": "ok aria"}) == {"wake_phrase"} and m.status_text() == "Stato: pronta, di' «Ok Aria»"
    m.handle({"wake_phrase": "hey aria"})
    assert m.handle({"state": "listening"}) == {"state"} and m.status_text() == "Stato: ti ascolta" and m.wake_label() == "Ferma Aria"
    assert m.icon_color() == (26, 178, 235)
    assert m.handle({"state": "listening"}) == set()                                      # nessun cambiamento: niente da ridisegnare
    m.handle({"muted": True})
    assert m.status_text() == "Stato: microfono silenziato" and m.icon_color() is None
    m.handle({"muted": False, "state": "idle", "voice": "paul", "paused": True})
    assert m.voice == "paul" and m.status_text() == "Stato: in pausa (a batteria)"
    m.problem = "Python non trovato"
    assert m.status_text().startswith("⚠ ") and m.icon_color() == (255, 102, 77)
    m.set_connected(False)
    assert m.state == "idle"
    assert m.handle({"state": 3, "muted": "si", "voice": None}) == set()                  # messaggi strani non rompono niente


# ---------------------------------------------------------------- percorsi e log
def test_paths_follow_the_environment_and_the_installer_file(tmp_path):
    assert paths.local_dir() == tmp_path / "local" and paths.support_dir() == tmp_path / "support"
    assert paths.python_exe().endswith(os.path.join("venv", "Scripts", "python.exe"))                    # (nessuno dei due esiste ancora: python.exe)
    (tmp_path / "local" / "venv" / "Scripts").mkdir(parents=True)
    for n in ("python.exe", "pythonw.exe"):
        (tmp_path / "local" / "venv" / "Scripts" / n).write_text("")
    assert paths.python_exe().endswith("pythonw.exe") and paths.python_exe(windowless=False).endswith("python.exe")
    (tmp_path / "support").mkdir()
    (tmp_path / "support" / "paths.json").write_text(json.dumps({"python": "C:/x/python.exe", "software": "C:/x/sw", "config": "C:/x/c.yaml"}))
    assert paths.python_exe() == "C:/x/python.exe" and paths.software_dir() == "C:/x/sw" and paths.config_file() == "C:/x/c.yaml"
    assert paths.persona_file().replace("\\", "/").endswith("/x/persona.md")
    log = tmp_path / "big.log"
    log.write_bytes(b"x" * 100)
    paths.rotate(log, limit=50)
    assert not log.exists() and (tmp_path / "big.log.1").exists()
    paths.rotate(tmp_path / "missing.log")                                                # un file che non c'e' non e' un errore


# ---------------------------------------------------------------- avvio del backend
class FakeProc:
    def __init__(self, code=1):
        self.pid, self.code, self.terminated = 4242, code, False

    def poll(self):
        return None if not self.terminated and self.code is None else self.code

    def wait(self, timeout=None):
        return self.code

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


def make_backend(tmp_path, procs):
    (tmp_path / "support").mkdir(exist_ok=True)
    (tmp_path / "support" / "config.yaml").write_text("name: Aria\n")
    py = tmp_path / "local" / "venv" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_text("")
    calls, waits = [], []

    def popen(cmd, **kw):
        calls.append((cmd, kw))
        return procs.pop(0)
    b = BackendManager(popen=popen, sleep=lambda s: waits.append(s))
    return b, calls, waits


def test_the_backend_is_started_with_the_right_command_and_environment(tmp_path):
    p = FakeProc(code=None)
    b, calls, _ = make_backend(tmp_path, [p])
    b.start()
    cmd, kw = calls[0]
    assert cmd[1:4] == ["-m", "aria.main", "--config"] and cmd[4].endswith("config.yaml") and cmd[0].endswith("python.exe")
    assert kw["env"]["ARIA_PARENT_WATCH"] == "1" and kw["env"]["PYTHONUTF8"] == "1" and kw["env"]["PYTHONPATH"] == paths.software_dir()
    assert b.problem is None and (tmp_path / "local" / "Logs" / "backend.log").exists()
    b.start()
    assert len(calls) == 1                                                                 # gia' acceso: non ne parte un secondo
    b.stop()
    assert p.terminated


def test_a_missing_python_or_config_is_reported_not_crashed(tmp_path):
    problems = []
    b = BackendManager(popen=lambda *a, **k: FakeProc())
    b.on_problem = problems.append
    b.start()
    assert "Python non trovato" in problems[-1]
    py = tmp_path / "local" / "venv" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.write_text("")
    b.start()
    assert "Configurazione mancante" in problems[-1]


def test_a_backend_that_keeps_falling_is_restarted_with_longer_and_longer_waits(tmp_path):
    procs = [FakeProc(code=1) for _ in range(4)] + [FakeProc(code=None)]
    b, calls, waits = make_backend(tmp_path, procs)
    b.start()
    for _ in range(100):                                                                   # la sentinella riparte da sola in un altro thread
        if len(calls) >= 5:
            break
        threading.Event().wait(0.02)
    assert len(calls) == 5 and waits[:4] == [3.0, 6.0, 9.0, 12.0]
    b.stop()


# ---------------------------------------------------------------- WebSocket
class FakeWS:
    def __init__(self, incoming):
        self.incoming, self.sent = list(incoming), []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send(self, data):
        self.sent.append(data)

    def recv(self, timeout=None):
        if self.incoming:
            return self.incoming.pop(0)
        raise ConnectionError("chiuso")                                                    # finita la sceneggiatura: il collegamento cade


def test_the_client_delivers_messages_sends_commands_and_reconnects():
    got, conn = [], []
    ws = FakeWS([json.dumps({"state": "listening"}), "non json", json.dumps([1, 2]), json.dumps({"ready": True})])
    attempts = []

    def connect(url):
        attempts.append(url)
        if len(attempts) == 1:
            return ws
        raise OSError("backend non pronto")
    c = BackendClient(on_message=got.append, on_connection=conn.append, connect=connect, sleep=lambda s: c.close())
    c.send({"cmd": "wake"})
    c.start()
    for _ in range(100):
        if conn[-1:] == [False] and len(conn) >= 2:
            break
        threading.Event().wait(0.02)
    assert got == [{"state": "listening"}, {"ready": True}]                                # il testo non JSON e quello che non e' un oggetto si ignorano
    assert ws.sent == [json.dumps({"cmd": "wake"})] and conn == [True, False]
    assert attempts[0] == "ws://127.0.0.1:8765"


# ---------------------------------------------------------------- avvio con Windows
class FakeReg:
    HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE, REG_SZ = "HKCU", 1, 2, 1

    def __init__(self):
        self.values = {}

    class _K:
        def __init__(self, store):
            self.s = store

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, root, path, res, access):
        return self._K(self.values)

    CreateKeyEx = OpenKey

    def QueryValueEx(self, k, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], 1

    def SetValueEx(self, k, name, _r, _t, value):
        self.values[name] = value

    def DeleteValue(self, k, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_start_with_windows_writes_and_removes_the_run_entry():
    reg = FakeReg()
    assert not autostart.is_enabled(reg)
    assert autostart.set_enabled(True, reg) and autostart.is_enabled(reg)
    assert reg.values["Aria"].endswith("-m aria_win") and reg.values["Aria"].startswith('"')
    assert autostart.set_enabled(False, reg) and not autostart.is_enabled(reg)
    assert autostart.set_enabled(False, reg)                                               # spegnere quando e' gia' spento non e' un errore
    if sys.platform != "win32":
        assert autostart.is_enabled() is False and autostart.set_enabled(True) is False    # fuori da Windows: niente registro, nessun errore


# ---------------------------------------------------------------- la schermata
class FakeDriver:
    def __init__(self):
        self.calls = []

    def appear(self):
        self.calls.append("appare")

    def disappear(self):
        self.calls.append("sparisce")


class SyncPool:
    def submit(self, fn):
        fn()


class FakeTimer:
    instances = []

    def __init__(self, delay, fn):
        self.delay, self.fn, self.cancelled, self.daemon = delay, fn, False, False
        FakeTimer.instances.append(self)

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


def test_the_overlay_appears_at_once_and_hides_after_a_delay_unless_she_speaks_again():
    FakeTimer.instances = []
    d = FakeDriver()
    o = OverlayController(d, hide_delay=2.6, timer=FakeTimer, pool=SyncPool())
    o.show()
    o.show()
    assert d.calls == ["appare"]                                                            # due show di fila: compare una volta sola
    o.hide()
    t1 = FakeTimer.instances[-1]
    assert t1.delay == 2.6 and not t1.cancelled
    o.show()                                                                                # ricomincia a parlare prima che sparisca
    assert t1.cancelled and d.calls == ["appare"]
    o.hide(0.0)
    FakeTimer.instances[-1].fn()
    assert d.calls == ["appare", "sparisce"] and not o.visible
    FakeTimer.instances[-1].fn()                                                            # un secondo timer in ritardo non fa sparire due volte
    assert d.calls == ["appare", "sparisce"]


def test_the_overlay_sits_at_the_bottom_centre_of_the_work_area():
    assert target_origin((0, 0, 1920, 1040)) == (700, 1040 - 330 - 64)
    assert target_origin((100, 50, 1380, 770), (520, 330)) == (100 + (1280 - 520) // 2, 770 - 330 - 64)


# ---------------------------------------------------------------- poteri: app, siti, volume, musica
def make_win(tmp_path, **kw):
    from aria.winos import WinOS
    start = tmp_path / "Start"
    for n in ("Spotify", "Blocco note", "Microsoft Edge", "Calcolatrice", "Disinstalla Spotify"):
        (start / "Programmi").mkdir(parents=True, exist_ok=True)
        (start / "Programmi" / f"{n}.lnk").write_text("")
    opened, keys = [], []
    w = WinOS(app_dirs=(str(start),), opener=opened.append, keys=lambda vk, times=1: keys.append(vk), **kw)
    return w, opened, keys


def test_windows_finds_apps_in_the_start_menu_and_opens_only_web_addresses(tmp_path):
    w, opened, _ = make_win(tmp_path)
    assert w.resolve_app("spotify").endswith("Spotify.lnk")
    assert w.resolve_app("il blocco note").endswith("Blocco note.lnk")
    assert w.resolve_app("browser").endswith("Microsoft Edge.lnk")                           # «browser» -> Edge
    assert w.resolve_app("calcolatrice").endswith("Calcolatrice.lnk")
    assert w.resolve_app("photoshop") is None
    assert "Disinstalla Spotify" not in " ".join(w.apps())                                    # i disinstallatori non sono «app da aprire»
    w.open_app(w.resolve_app("spotify"))
    w.open_url("https://www.youtube.com")
    assert opened[0].endswith("Spotify.lnk") and opened[1] == "https://www.youtube.com"
    for bad in ("file:///C:/Windows/system32/cmd.exe", "javascript:alert(1)", "calc.exe"):
        with pytest.raises(MacError):
            w.open_url(bad)
    assert len(opened) == 2


def test_what_only_exists_on_the_mac_says_so_on_windows(tmp_path):
    w, _, _ = make_win(tmp_path)
    for fn in (lambda: w.osa("return 1"), w.shortcuts_list, lambda: w.shortcuts_run("x")):
        with pytest.raises(MacError, match="Su Windows"):
            fn()


def test_volume_uses_the_endpoint_and_media_keys_go_to_whoever_plays(tmp_path):
    w, _, keys = make_win(tmp_path)

    class EP:
        level, mute = 0.4, 0

        def GetMasterVolumeLevelScalar(self):
            return self.level

        def SetMasterVolumeLevelScalar(self, v, _ctx):
            self.level = v

        def SetMute(self, on, _ctx):
            self.mute = on
    w._vol = EP()
    assert w.volume_get() == 40 and w.volume_set(150) == 100 and w._vol.level == 1.0 and w.volume_set(-3) == 0
    w.muted(True)
    assert w._vol.mute == 1
    w2, _, keys2 = make_win(tmp_path)
    w2._vol = False                                                                           # senza pycaw
    with pytest.raises(MacError):
        w2.volume_get()
    w2.muted(True)
    assert keys2 == [0xAD]                                                                    # il tasto «muto»
    assert w2.media("play") and w2.media("pause") and w2.media("next") and w2.media("previous") and not w2.media("boh")
    assert keys2[1:] == [0xB3, 0xB3, 0xB0, 0xB1]


def test_with_the_windows_helper_music_goes_through_media_keys_and_apps_open_from_the_start_menu(tmp_path):
    cfg = load()
    cfg["workspace"] = str(tmp_path / "Aria")
    os.makedirs(cfg["workspace"], exist_ok=True)
    cfg["powers"] = {}
    t = Tools(cfg, Memory())
    w, opened, keys = make_win(tmp_path)
    t.mac = w
    from aria.textutil import ToolCall
    out = asyncio.run(t.run(ToolCall("MUSICA", "pause")))
    assert out in ("Messa in pausa.", "Fatto, silenzio.", "Ok, pausa.") and keys == [0xB3]
    out = asyncio.run(t.run(ToolCall("MUSICA", "track:Queen")))
    assert "Spotify" in out and opened[-1] == "spotify:search:Queen"
    assert "non so dire" in asyncio.run(t.run(ToolCall("MUSICA", "now")))
    out = asyncio.run(t.run(ToolCall("APRI_APP", "spotify")))
    assert "Spotify" in out and opened[-1].endswith("Spotify.lnk")


def test_the_windows_shell_modules_are_all_importable_without_windows_libraries():
    import importlib
    for mod in ("aria_win.app", "aria_win.tray", "aria_win.overlay", "aria_win.win32", "aria_win.pick_folder"):
        importlib.import_module(mod)                                                          # (pystray, pywebview e tkinter si importano solo quando servono)
    from aria_win import win32
    assert win32.find_window("niente") == 0
    if sys.platform != "win32":                                                               # (su Windows queste chiamate sono vere: si provano a mano, vedi windows/README.md)
        assert win32.single_instance() is True and win32.make_overlay_style(123) is False
        assert win32.work_area() == (0, 0, 1920, 1040) and win32.system_uses_light_theme() is False
    from aria import power
    assert power.display_asleep() in (True, False, None)


def test_the_backend_ignores_the_mac_only_parts_on_other_systems(monkeypatch):
    from aria import main as M
    me = os.getpid() if sys.platform == "win32" else os.getppid()                             # (su Windows si chiede se un processo vivo e' vivo: il nostro)
    assert M._parent_alive(me) is True
    if sys.platform == "win32":
        assert M._parent_alive(4000000) is False                                              # un numero che non esiste: «non c'e' piu'»


def test_the_nvidia_dll_folders_of_the_environment_go_into_the_backend_path(tmp_path):
    b = BackendManager(popen=lambda *a, **k: FakeProc())
    assert b.gpu_library_dirs() == [] and b.environment()["PATH"] == os.environ.get("PATH", b.environment()["PATH"])
    base = tmp_path / "local" / "venv"
    (base / "Scripts").mkdir(parents=True)
    for pkg in ("cublas", "cudnn"):
        (base / "Lib" / "site-packages" / "nvidia" / pkg / "bin").mkdir(parents=True)
    (base / "Lib" / "site-packages" / "nvidia" / "readme").mkdir()                               # senza «bin»: si salta
    dirs = b.gpu_library_dirs()
    assert [os.path.basename(os.path.dirname(d)) for d in dirs] == ["cublas", "cudnn"]
    assert b.environment()["PATH"].startswith(dirs[0] + os.pathsep + dirs[1])


def test_on_windows_the_powers_create_the_windows_helper(monkeypatch):
    from aria.winos import WinOS
    monkeypatch.setattr(PW.sys, "platform", "win32")
    t = Tools(load(), Memory())
    t.mac = None
    assert isinstance(t._mac(), WinOS)
    monkeypatch.setattr(PW.sys, "platform", "darwin")
    t.mac = None
    assert not isinstance(t._mac(), WinOS)
