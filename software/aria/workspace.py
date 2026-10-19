"""La cartella di Aria: l'UNICO posto dove puo' creare e leggere file, scelto dall'utente.

Regole di sicurezza (valgono per tutto cio' che Aria fa con i file):
  - solo dentro la cartella scelta: niente ".." e niente collegamenti simbolici che escano (si controlla il percorso reale);
  - solo file di testo (.md .txt per scrivere; in lettura anche .csv, .pdf e .docx), mai file nascosti;
  - non cancella e non sovrascrive: se un nome esiste gia' ne crea uno nuovo ("Testo (2).md"); l'unica modifica a un file esistente e' aggiungere
    righe in fondo (liste e note);
  - limiti di grandezza, cosi' un errore del modello non riempie il disco.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys

from .textutil import normalize

WRITE_EXT = (".md", ".txt")
READ_EXT = (".md", ".txt", ".csv", ".pdf", ".docx")        # PDF e Word solo in lettura
MAX_WRITE = 120_000                   # byte per un file nuovo
MAX_FILE = 400_000                    # un file a cui si aggiungono righe non supera questa grandezza
MAX_READ = 200_000


class WorkspaceError(Exception):
    """Un problema spiegabile all'utente, gia' in italiano."""


def _home() -> str:
    return os.path.realpath(os.path.expanduser("~"))


_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def win_forbidden(p: str, home: str, env: dict) -> bool:
    """Windows: il disco intero, le cartelle di sistema e dei programmi, AppData. Funziona su stringhe (ntpath), cosi' si prova anche su un altro sistema."""
    import ntpath
    n, h = ntpath.normcase(ntpath.normpath(p)), ntpath.normcase(ntpath.normpath(home))
    if ntpath.splitdrive(n)[1] in ("", "\\"):
        return True
    for key in ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData"):
        r = env.get(key)
        if r:
            r = ntpath.normcase(ntpath.normpath(r))
            if n == r or n.startswith(r + "\\"):
                return True
    appdata = ntpath.join(h, "appdata")
    return n == appdata or n.startswith(appdata + "\\")


def check_root(path: str | None) -> str:
    """Convalida una cartella scelta come cartella di Aria e restituisce il percorso reale. Rifiuta le cartelle di sistema, la Home intera, la Libreria."""
    if not path or not str(path).strip():
        raise WorkspaceError("Non è stata indicata nessuna cartella.")
    p = os.path.realpath(os.path.expanduser(str(path).strip()))
    home = _home()
    if not os.path.isdir(p):
        raise WorkspaceError("La cartella non esiste (più).")
    if sys.platform == "win32" and win_forbidden(p, home, os.environ):
        raise WorkspaceError("Questa è una cartella di sistema o dei programmi: scegline un'altra (meglio una cartella dedicata, ad esempio «Aria» nei Documenti).")
    system = ("/System", "/usr", "/bin", "/sbin", "/etc", "/var", "/private", "/Library", "/Applications", "/opt", "/dev", "/cores")
    if p == "/" or p == home or home.startswith(p + os.sep):
        raise WorkspaceError("Scegli una cartella dedicata, non la Home o il disco intero: crea una cartella apposta, ad esempio «Aria».")
    in_home = p.startswith(home + os.sep)
    if (not in_home and any(p == s or p.startswith(s + os.sep) for s in system)) or p == os.path.join(home, "Library") or p.startswith(os.path.join(home, "Library") + os.sep):
        raise WorkspaceError("Questa è una cartella di sistema: scegline un'altra.")
    rel = os.path.relpath(p, home) if p.startswith(home + os.sep) else ""
    if rel.split(os.sep)[0].startswith("."):
        raise WorkspaceError("Le cartelle nascoste (come .ssh o .config) non vanno bene: scegline un'altra.")
    if not os.access(p, os.W_OK | os.X_OK):
        raise WorkspaceError("Non ho il permesso di scrivere in questa cartella.")
    return p


_BAD = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


def safe_stem(title: str, max_len: int = 60) -> str:
    """Un nome di file sicuro e leggibile a partire da un titolo (senza estensione)."""
    t = _BAD.sub(" ", title or "")
    t = re.sub(r"\s+", " ", t).strip(" .-_'")
    t = t[:max_len].strip(" .-_'")
    if t.split(".")[0].upper() in _WIN_RESERVED:                       # «Con», «Aux», «Nul»…: su Windows non si possono usare come nome di file (nemmeno con l'estensione)
        t += " (testo)"
    return (t[:1].upper() + t[1:]) if t else "Senza titolo"


class Workspace:
    def __init__(self, root: str):
        self.root = os.path.realpath(root)

    # ---------------------------------------------------------------- percorsi
    def _inside(self, path: str) -> str:
        real = os.path.realpath(path)
        if real != self.root and not real.startswith(self.root + os.sep):
            raise WorkspaceError("Quel file è fuori dalla mia cartella: non lo tocco.")
        return real

    def _path(self, name: str, ext_ok: tuple[str, ...]) -> str:
        if not name or os.sep in name or name.startswith(".") or name != os.path.basename(name):
            raise WorkspaceError("Nome di file non valido.")
        if not name.lower().endswith(ext_ok):
            raise WorkspaceError("Posso usare solo file di testo.")
        return self._inside(os.path.join(self.root, name))

    @staticmethod
    def display(name: str) -> str:
        """Il nome come si dice a voce: senza estensione."""
        return os.path.splitext(name)[0]

    # ---------------------------------------------------------------- scrivere
    def new_file(self, title: str, text: str, ext: str = ".md") -> str:
        """Crea un file NUOVO (mai sovrascrive: se il nome esiste ne cerca uno libero). Restituisce il nome."""
        if ext not in WRITE_EXT:
            raise WorkspaceError("Posso scrivere solo file di testo.")
        data = (text or "").strip() + "\n"
        if len(data.encode("utf-8")) > MAX_WRITE:
            raise WorkspaceError("Il testo è troppo lungo per un file solo.")
        stem = safe_stem(title)
        for n in range(1, 100):
            name = f"{stem}{'' if n == 1 else f' ({n})'}{ext}"
            path = self._path(name, WRITE_EXT)
            try:
                with open(path, "x", encoding="utf-8") as f:              # "x": fallisce se esiste gia' (anche per una gara)
                    f.write(data)
                return name
            except FileExistsError:
                continue
        raise WorkspaceError("Ci sono già troppi file con questo nome.")

    def append(self, title: str, line: str, header: str | None = None) -> str:
        """Aggiunge una riga in fondo a un file (lo crea se manca). L'unica modifica che Aria fa a un file esistente."""
        line = re.sub(r"\s+", " ", line or "").strip()
        if not line:
            raise WorkspaceError("Non c'è niente da aggiungere.")
        name = safe_stem(title) + ".md"
        path = self._path(name, WRITE_EXT)
        if os.path.exists(path):
            if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > MAX_FILE:
                raise WorkspaceError("Quel file non si può aggiornare (è troppo grande o non è un file normale).")
            new = False
        else:
            new = True
        with open(path, "a", encoding="utf-8") as f:
            if new and header:
                f.write(f"# {header}\n\n")
            f.write(line[:400] + "\n")
        return name

    # ---------------------------------------------------------------- leggere
    def list(self) -> list[tuple[str, int]]:
        """[(nome, byte)] dei file di testo nella cartella (non nascosti, non nelle sottocartelle), dal piu' recente."""
        out = []
        try:
            entries = os.listdir(self.root)
        except OSError:
            return []
        for n in entries:
            p = os.path.join(self.root, n)
            if n.startswith(".") or not n.lower().endswith(READ_EXT) or os.path.islink(p) or not os.path.isfile(p):
                continue
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append((st.st_mtime, n, st.st_size))
        return [(n, sz) for _m, n, sz in sorted(out, reverse=True)]

    def find(self, query: str) -> str | None:
        """Il file che meglio corrisponde a quello che l'utente ha detto ("il file della spesa")."""
        words = [w for w in normalize(query).split() if len(w) >= 3 and w not in {"file", "documento", "nota", "della", "dello", "delle", "degli", "del", "dei", "nel", "nella"}]
        best, best_score = None, 0
        for name, _sz in self.list():
            stem = normalize(self.display(name))
            if normalize(query) == stem:
                return name
            score = sum(1 for w in words if w in stem)
            if score > best_score:
                best, best_score = name, score
        return best if best_score else None

    def read(self, name: str, limit: int = MAX_READ) -> str:
        path = self._path(name, READ_EXT)
        if os.path.islink(path) or not os.path.isfile(path):
            raise WorkspaceError("Non trovo quel file.")
        if path.lower().endswith((".pdf", ".docx")):
            from .docs import extract_text                                      # import qui: docs usa WorkspaceError di questo file
            return extract_text(path, limit)[:limit]
        with open(path, "rb") as f:
            raw = f.read(min(limit, MAX_READ))
        return raw.decode("utf-8", errors="replace")


_GENERIC = {"file", "documento", "documenti", "testo", "pdf", "word", "della", "dello", "delle", "degli", "nella", "nello", "nelle", "negli", "sulla", "sullo",
            "sulle", "sugli", "quanto", "quando", "quale", "quali", "dimmi", "dammi", "leggi", "guarda", "controlla", "cerca", "trova", "dice", "scritto", "cosa",
            "come", "dove", "perche", "questo", "questa", "quello", "quella", "dentro", "mio", "mia", "miei", "sono", "hanno", "fatto", "fare", "dire"}


def match_file(query: str, names: list[str]) -> str | None:
    """Quale file di `names` e' quello di cui si parla nella frase: parole intere (o quasi: singolare/plurale) in comune col nome del file.
    Rigoroso apposta: le parole corte e quelle generiche non contano, cosi' una frase qualsiasi non "trova" un file per caso."""
    words = [w for w in normalize(query).split() if len(w) >= 4 and w not in _GENERIC]
    best, best_score = None, 0
    for name in names:
        stem = [w for w in normalize(os.path.splitext(name)[0]).split() if len(w) >= 3]
        score = 0
        for w in words:
            if any(w == t or (len(w) >= 5 and len(t) >= 5 and (w.startswith(t[:5]) and t.startswith(w[:5]))) for t in stem):
                score += 1
        if score > best_score:
            best, best_score = name, score
    return best if best_score else None


def stamp(now: dt.datetime | None = None) -> str:
    n = now or dt.datetime.now()
    return n.strftime("%Y-%m-%d %H:%M")


def plain_for_speech(markdown: str, max_chars: int = 700) -> str:
    """Un testo Markdown ridotto a parole da leggere a voce: senza #, asterischi, elenchi, link."""
    t = re.sub(r"```.*?```", " ", markdown or "", flags=re.S)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^[#>\-\*\+\s\[\]xX]+(?=\S)", "", t, flags=re.M)
    t = re.sub(r"[*_`#]+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_chars:
        t = t[:max_chars].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return t
