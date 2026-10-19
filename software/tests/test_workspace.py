"""La cartella di Aria: dove puo' scrivere e leggere, e soprattutto dove NON puo'."""
import os

import pytest

from aria import workspace as W
from aria.workspace import Workspace, WorkspaceError


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "Aria"
    root.mkdir()
    return Workspace(str(root))


def test_new_files_never_overwrite(ws):
    a = ws.new_file("Testo sulla fotosintesi", "# Fotosintesi\nLe piante...")
    b = ws.new_file("Testo sulla fotosintesi", "un'altra versione")
    c = ws.new_file("Testo sulla fotosintesi", "ancora")
    assert (a, b, c) == ("Testo sulla fotosintesi.md", "Testo sulla fotosintesi (2).md", "Testo sulla fotosintesi (3).md")
    assert open(os.path.join(ws.root, a), encoding="utf-8").read().startswith("# Fotosintesi")        # il primo e' intatto


def test_names_are_sanitised_and_confined(ws, tmp_path):
    for title in ("../../etc/passwd", "a/b\\c:d*e?", "  ...  ", ".nascosto"):
        name = ws.new_file(title, "x")
        assert os.sep not in name and not name.startswith(".") and name.endswith(".md")
        assert os.path.dirname(os.path.realpath(os.path.join(ws.root, name))) == ws.root
    assert not (tmp_path / "etc").exists() and not os.path.exists(os.path.join(os.path.dirname(ws.root), "passwd.md"))
    assert W.safe_stem("") == "Senza titolo" and W.safe_stem("ciao: mondo?") == "Ciao mondo" and len(W.safe_stem("x" * 300)) <= 60


def test_only_text_files_and_size_limits(ws):
    with pytest.raises(WorkspaceError):
        ws.new_file("script", "echo", ext=".sh")
    with pytest.raises(WorkspaceError, match="troppo lungo"):
        ws.new_file("enorme", "x" * (W.MAX_WRITE + 10))
    for bad in ("../x.md", "/etc/hosts", ".segreto.md", "foto.png", "a/b.md"):
        with pytest.raises(WorkspaceError):
            ws.read(bad)


def test_symlinks_cannot_escape(ws, tmp_path):
    outside = tmp_path / "fuori.txt"
    outside.write_text("segreto")
    os.symlink(outside, os.path.join(ws.root, "collegamento.txt"))
    os.symlink(tmp_path, os.path.join(ws.root, "cartella.md"))
    assert ws.list() == []                                                   # i collegamenti non compaiono nemmeno
    with pytest.raises(WorkspaceError):
        ws.read("collegamento.txt")
    ws.append("collegamento", "riga")                                        # "Collegamento.md" non esiste: lo crea, dentro la cartella
    assert os.path.isfile(os.path.join(ws.root, "Collegamento.md")) and outside.read_text() == "segreto"
    os.symlink(outside, os.path.join(ws.root, "Lista.md"))
    with pytest.raises(WorkspaceError):
        ws.append("Lista", "latte")                                          # un collegamento a un file esterno non si aggiorna
    assert outside.read_text() == "segreto"


def test_append_creates_then_adds_lines(ws):
    n = ws.append("Lista della spesa", "- [ ] latte", header="Lista della spesa")
    ws.append("Lista della spesa", "- [ ]   pane  ")
    assert n == "Lista della spesa.md"
    assert open(os.path.join(ws.root, n), encoding="utf-8").read() == "# Lista della spesa\n\n- [ ] latte\n- [ ] pane\n"
    with pytest.raises(WorkspaceError):
        ws.append("Lista della spesa", "   ")
    big = os.path.join(ws.root, "Grande.md")
    open(big, "w").write("x" * (W.MAX_FILE + 1))
    with pytest.raises(WorkspaceError, match="troppo grande"):
        ws.append("Grande", "altra riga")


def test_list_find_and_read(ws):
    ws.new_file("Ricerca - polpi", "# Polpi\nHanno tre cuori.")
    ws.new_file("Lista della spesa", "- latte")
    open(os.path.join(ws.root, ".nascosto.md"), "w").write("x")
    open(os.path.join(ws.root, "foto.png"), "w").write("x")
    names = [n for n, _ in ws.list()]
    assert sorted(names) == ["Lista della spesa.md", "Ricerca - polpi.md"]
    assert ws.find("la lista della spesa") == "Lista della spesa.md"
    assert ws.find("il file sui polpi") == "Ricerca - polpi.md" and ws.find("ricerca polpi") == "Ricerca - polpi.md"
    assert ws.find("cuori di polpo") is None and ws.find("zzz") is None
    assert "tre cuori" in ws.read("Ricerca - polpi.md")
    assert W.Workspace.display("Ricerca - polpi.md") == "Ricerca - polpi"


def test_speech_text_drops_markdown():
    md = "# Titolo\n\n**Ciao** [mondo](http://x.it)\n- uno\n- [ ] due\n```code```\n\n> citazione"
    assert W.plain_for_speech(md) == "Titolo Ciao mondo uno due citazione"
    assert W.plain_for_speech("parola " * 300, 50).endswith("…") and len(W.plain_for_speech("parola " * 300, 50)) <= 52


def test_check_root_refuses_dangerous_folders(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "Documents" / "Aria").mkdir(parents=True)
    (home / "Library" / "Preferences").mkdir(parents=True)
    (home / ".ssh").mkdir()
    monkeypatch.setenv("HOME", str(home))
    ok = W.check_root(str(home / "Documents" / "Aria"))
    assert ok == os.path.realpath(str(home / "Documents" / "Aria"))
    for bad in (str(home), "/", "/System", "/usr/bin", "/Applications", str(home / "Library"), str(home / "Library" / "Preferences"), str(home / ".ssh"),
                str(tmp_path), str(home / "non-esiste"), ""):
        with pytest.raises(WorkspaceError):
            W.check_root(bad)
    (home / "sola-lettura").mkdir()
    os.chmod(home / "sola-lettura", 0o500)
    try:
        with pytest.raises(WorkspaceError, match="permesso"):
            W.check_root(str(home / "sola-lettura"))
    finally:
        os.chmod(home / "sola-lettura", 0o700)


def test_windows_system_folders_are_refused_and_reserved_file_names_are_not_used():
    env = {"SystemRoot": r"C:\Windows", "ProgramFiles": r"C:\Program Files", "ProgramFiles(x86)": r"C:\Program Files (x86)", "ProgramData": r"C:\ProgramData"}
    home = r"C:\Users\Marta"
    for bad in (r"C:\\", "C:\\", r"D:\Windows\System32".replace("D:", "C:"), r"C:\Program Files\Aria", r"c:\program files (x86)", r"C:\ProgramData\x", r"C:\Users\Marta\AppData\Roaming"):
        assert W.win_forbidden(bad, home, env), bad
    for ok in (r"C:\Users\Marta\Documents\Aria", r"D:\Aria", r"C:\Users\Marta\Desktop\Aria"):
        assert not W.win_forbidden(ok, home, env), ok
    for name in ("Con", "aux", "COM3", "Nul.txt"):
        assert W.safe_stem(name) != name and "(testo)" in W.safe_stem(name)
    assert W.safe_stem("Console") == "Console"
