"""Estrarre il testo dai documenti della cartella di Aria (testo, Markdown, CSV, PDF, Word .docx) e trovarne i passaggi che rispondono a una domanda.

Solo lettura. Nessuna esecuzione: un PDF o un .docx qui e' solo testo da leggere (niente macro, niente script).
"""
from __future__ import annotations

import os
import re
import zipfile
import xml.etree.ElementTree as ET

from .textutil import normalize
from .workspace import WorkspaceError

MAX_PDF_BYTES = 25_000_000
MAX_PDF_PAGES = 150
MAX_DOCX_XML = 20_000_000
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _pdf_text(path: str) -> str:
    if os.path.getsize(path) > MAX_PDF_BYTES:
        raise WorkspaceError("Questo PDF è troppo grande per me.")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise WorkspaceError("Per leggere i PDF serve la libreria pypdf: rilancia l'installer di Aria.")
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise WorkspaceError("Questo PDF è protetto da password: non posso leggerlo.")
        pages = reader.pages[:MAX_PDF_PAGES]
        text = "\n\n".join((p.extract_text() or "") for p in pages)
    except WorkspaceError:
        raise
    except Exception as e:                                       # noqa: BLE001
        raise WorkspaceError(f"Non riesco a leggere questo PDF ({type(e).__name__}).") from e
    if len(re.sub(r"\s+", "", text)) < 20:
        raise WorkspaceError("Questo PDF sembra una scansione (solo immagini): non ho testo da leggere.")
    return text


def _docx_text(path: str) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML:
                raise WorkspaceError("Questo documento è troppo grande per me.")
            root = ET.fromstring(z.read("word/document.xml"))
    except WorkspaceError:
        raise
    except Exception as e:                                       # noqa: BLE001
        raise WorkspaceError(f"Non riesco a leggere questo documento Word ({type(e).__name__}).") from e
    paras = []
    for p in root.iter(f"{_W}p"):
        txt = "".join((t.text or "") for t in p.iter(f"{_W}t"))
        if txt.strip():
            paras.append(txt.strip())
    return "\n\n".join(paras)


def extract_text(path: str, limit: int = 400_000) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _pdf_text(path)[:limit]
    if ext == ".docx":
        return _docx_text(path)[:limit]
    with open(path, "rb") as f:
        return f.read(limit).decode("utf-8", errors="replace")


_STOP = {"quanto", "quale", "quali", "quando", "dove", "come", "perche", "chi", "cosa", "che", "dice", "scritto", "nel", "nella", "sono", "della", "delle",
         "degli", "dello", "dei", "documento", "file", "testo", "ancora", "anche", "questo", "questa", "sono", "stato", "essere"}


def _chunks(text: str, size: int = 900) -> list[str]:
    out, cur = [], ""
    for para in re.split(r"\n\s*\n|\n", text):
        para = para.strip()
        if not para:
            continue
        while len(para) > size:
            cut = para.rfind(". ", 0, size)
            cut = cut + 1 if cut > size // 3 else size
            out.append(para[:cut].strip())
            para = para[cut:].strip()
        if len(cur) + len(para) + 1 > size and cur:
            out.append(cur)
            cur = para
        else:
            cur = (cur + "\n" + para).strip()
    if cur:
        out.append(cur)
    return out


def relevant_passages(text: str, question: str, max_chars: int = 4500) -> str:
    """I pezzi del documento che contengono le parole della domanda (nell'ordine originale); se nessuno, l'inizio."""
    chunks = _chunks(text)
    words = {w for w in normalize(question).split() if len(w) >= 4 and w not in _STOP}
    scored = []
    for i, c in enumerate(chunks):
        n = normalize(c)
        s = sum(1 for w in words if w in n) + 0.01 * sum(n.count(w) for w in words)
        if s >= 1:
            scored.append((s, i))
    picked: list[int] = []
    used = 0
    for _s, i in sorted(scored, reverse=True):
        if used + len(chunks[i]) > max_chars and picked:
            break
        picked.append(i)
        used += len(chunks[i])
    if not picked:
        for i, c in enumerate(chunks):
            if used + len(c) > max_chars and picked:
                break
            picked.append(i)
            used += len(c)
    return "\n…\n".join(chunks[i] for i in sorted(picked))
