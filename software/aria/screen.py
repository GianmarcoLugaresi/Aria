"""Guardare lo schermo: «cosa c'è scritto qui?», «non trovo il pulsante Esporta», «cosa ne pensi di questa pagina?».

Due modi di leggere lo schermo, scelti dall'utente nelle Impostazioni (e spenti di default: serve il permesso «Registrazione schermo»):
  - **OCR del Mac** (`screen_mac`): il riconoscimento testo di macOS (Vision), 0,3 s, nessuna RAM in piu'. Legge i testi e DICE DOVE sono (una scritta si trova al pixel);
    ragiona sul testo il chatbot normale, quindi non vede immagini e icone.
  - **Un modello che vede** (`screen_model`): un modello con la visione integrata (Gemma 4) guarda lo screenshot: capisce anche icone, layout e immagini e puo' dare un parere,
    ma ci mette qualche secondo e usa ~4 GB di RAM in piu' mentre risponde (gira in un processo a parte che poi finisce).

Si cattura lo schermo solo quando l'utente lo chiede a voce; l'immagine resta in un file temporaneo cancellato subito dopo e non lascia mai il Mac.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field

from . import profiles as P
from .textutil import normalize
from .voicecheck import _near

log = logging.getLogger("aria.screen")
STREAM_LIMIT = 64 * 1024 * 1024                                 # una riga di risposta dei programmi di supporto (tutto il testo o tutti i pulsanti dello schermo) supera facilmente i 64 KB di asyncio: «chunk is longer than limit»

# i programmi di supporto stanno in ARIA_BIN (nell'app scaricata: dentro Aria.app) oppure, dopo ./app/install.sh, in ~/Library/Application Support/Aria/bin
OCR_HELPER = os.path.join(os.environ.get("ARIA_BIN") or os.path.expanduser("~/Library/Application Support/Aria/bin"), "aria-apple-ocr")
POINTER_HELPER = os.path.join(os.environ.get("ARIA_BIN") or os.path.expanduser("~/Library/Application Support/Aria/bin"), "aria-pointer")
AX_HELPER = os.path.join(os.environ.get("ARIA_BIN") or os.path.expanduser("~/Library/Application Support/Aria/bin"), "aria-ax")
DEFAULT_VISION = "mlx-community/gemma-4-e4b-it-4bit"
SCREENCAPTURE = "/usr/sbin/screencapture"

SCREEN_OFF = ("Non guardo lo schermo: l'ho lasciato spento. Puoi attivarlo nelle Impostazioni di Aria, in «Cosa può fare Aria sul tuo Mac»: "
              "scegli se leggerlo con l'OCR del Mac o con un modello che vede.")
NO_PERMISSION = ("Per guardare lo schermo mi serve il permesso «Registrazione schermo». Ti ho aperto le Impostazioni di Sistema: attiva Aria nell'elenco, "
                 "o premi il più e aggiungila, e poi riprova.")
NO_PERMISSION_AGAIN = ("macOS mi dice ancora che non ho il permesso «Registrazione schermo». Se nell'elenco Aria risulta già attiva, quella è la voce di una versione "
                       "vecchia dell'app: dopo un aggiornamento macOS non la riconosce più, e spegnerla e riaccenderla non basta. Nelle Impostazioni selezionala, premi il meno "
                       "per toglierla, poi chiedimi di nuovo di guardare lo schermo e consenti. Se macOS te lo chiede, esci da Aria e riaprila.")
PRIVACY_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
NO_OCR_HELPER = "Manca il programma che legge lo schermo: rilancia l'installazione di Aria."

SCREEN_SYSTEM = (
    "Sei Aria, un'assistente vocale. Ti do il TESTO letto con l'OCR da quello che l'utente ha sullo schermo del Mac (dall'alto in basso; puo' avere errori e contenere menu e barre). "
    "Rispondi a voce, in italiano, con al massimo quattro frasi brevi, senza elenchi, senza markdown e senza simboli. "
    "Se ti chiede cosa dice o di riassumere: parti dal succo (cosa vuole davvero chi ha scritto, o la conclusione pratica), poi solo le cifre, le scadenze o l'unica cosa da fare, "
    "e di' cosa si puo' ignorare. Non cominciare con «questo documento parla di» ne' con «ecco». "
    "Usa SOLO quello che c'e' nel testo: se non basta per rispondere, dillo con onesta'. Ignora i testi di Aria stessa («Ti ascolto», «Ci penso»).")
VISION_PROMPT = (
    "Sei Aria, un'assistente vocale. Questa e' una schermata del Mac dell'utente (in basso al centro potrebbe esserci la finestrella di Aria, cioe' tu: ignorala). "
    "Rispondi a voce, in italiano, con al massimo quattro frasi brevi, senza elenchi, senza markdown e senza simboli. Descrivi solo quello che vedi davvero: "
    "se non sei sicura di una cosa, dillo. Se ti chiede dove si trova qualcosa, di' solo posizione (in alto a destra, sotto la barra…) e come si riconosce (colore, forma, scritta), senza preamboli. "
    "Se ti chiede di riassumere, parti dal succo e poi dai le cifre o le scadenze importanti. Richiesta dell'utente: ")

# parole che nella richiesta indicano il tipo di elemento («il pulsante Esporta»), non il suo testo
_NOISE = {"il", "lo", "la", "l", "i", "gli", "le", "un", "una", "uno", "pulsante", "tasto", "bottone", "voce", "menu", "scheda", "opzione", "link", "collegamento", "icona", "chiamato",
          "chiamata", "con", "scritto", "scritta", "di", "del", "della", "dello", "dei", "delle", "che", "dice", "si", "trova", "dove", "e", "qui", "schermo", "sullo", "sul",
          "per", "da", "a", "in", "su", "quello", "quella", "quel", "devo", "posso", "faccio", "fare", "clicco", "cliccare", "premere", "premo", "nella", "nel", "al", "alla", "allo", "ai", "sulla"}
# la zona dove sta la finestrella di Aria durante la cattura (centro in basso): quello che c'e' li' sotto non si legge e non e' dell'utente
_OVERLAY = (0.27, 0.73, 0.55)


# Le app hanno spesso l'interfaccia in inglese (o in un'altra lingua) e l'utente parla italiano: «dov'e' il pulsante per salvare?» deve trovare «Save». Gruppi di parole equivalenti (gia' normalizzate).
_SYN_GROUPS = [
    "salva salvare save", "apri aprire open", "chiudi chiudere close", "condividi condividere share", "esporta esportare export", "importa importare import", "stampa stampare print",
    "cerca cercare ricerca ricercare search find lente", "impostazioni preferenze settings preferences opzioni options rotella ingranaggio gear", "annulla annullare cancel undo",
    "ripeti redo", "invia inviare manda mandare send", "elimina eliminare cancella cancellare delete remove rimuovi rimuovere cestino trash", "copia copiare copy", "incolla incollare paste",
    "taglia tagliare cut", "modifica modificare edit", "nuovo nuova new", "visualizza vista view mostra", "aiuto help", "indietro back", "avanti forward next successivo continua continue",
    "aggiorna aggiornare refresh reload ricarica ricaricare", "scarica scaricare download", "carica caricare upload", "accedi accedere login signin entra entrare", "esci uscire logout signout",
    "registrati registrarsi signup register iscriviti", "home iniziale", "segnalibro segnalibri bookmark bookmarks preferiti favorites", "scheda tab", "finestra window", "cartella folder",
    "documento document", "informazioni info", "schermo intero fullscreen", "riduci minimize", "ingrandisci maximize zoom", "notifiche notifications", "profilo profile account",
    "piu plus aggiungi aggiungere add", "meno minus", "conferma confirm ok", "si yes", "precedente previous prev", "riproduci play avvia start", "pausa pause", "ferma stop",
    "muto mute silenzia", "rinomina rename", "duplica duplicate", "sposta move", "etichetta tag", "elenco lista list", "icone icons", "colonne columns", "galleria gallery", "cronologia history",
    "scarica download", "contatti contacts contatto contact", "nome name", "indirizzo address", "oggetto subject", "allegato allegati attachment attachments", "rispondi reply", "inoltra forward",
    "bozza bozze draft drafts", "posta mail inbox", "calendario calendar", "mappa mappe maps", "foto photos", "musica music", "messaggi messages", "note notes", "promemoria reminders",
    "attiva abilita enable", "disattiva disabilita disable", "tema theme", "lingua language", "password", "utente user", "rete network wifi", "suono sound audio", "schermo screen display",
    "chiave key", "tastiera keyboard", "mouse", "stampante printer", "batteria battery", "ora time", "data date", "fine end", "inizio start", "sopra up", "sotto down", "sinistra left", "destra right",
]
# espressioni di piu' parole che in inglese sono un'altra espressione: «salva con nome» = «Save As»
_PHRASES = {"salva con nome": ["save as"], "salva come": ["save as"], "schermo intero": ["full screen", "enter full screen"], "tutto schermo": ["full screen"], "nuova scheda": ["new tab"],
            "nuova finestra": ["new window"], "nuovo documento": ["new document"], "nuova cartella": ["new folder"], "chiudi finestra": ["close window"], "chiudi scheda": ["close tab"],
            "mostra tutto": ["show all"], "preferenze di sistema": ["system settings", "system preferences"], "impostazioni di sistema": ["system settings"], "pagina iniziale": ["home"],
            "modalita scura": ["dark mode"], "modalita aereo": ["airplane mode"], "non disturbare": ["do not disturb"], "cerca nel web": ["search the web"], "torna indietro": ["back"],
            "vai avanti": ["forward"], "cronologia di navigazione": ["history"], "scarica file": ["download"], "condividi schermo": ["share screen"], "invia messaggio": ["send message"],
            "rispondi a tutti": ["reply all"], "segna come letto": ["mark as read"], "svuota cestino": ["empty trash"], "sposta nel cestino": ["move to trash"], "ordina per": ["sort by"],
            "mostra barra laterale": ["show sidebar"], "nascondi barra laterale": ["hide sidebar"], "barra laterale": ["sidebar"], "barra degli strumenti": ["toolbar"], "tasto destro": ["right click", "context menu"]}
_SYN: dict[str, set[str]] = {}
for _g in _SYN_GROUPS:
    _ws = _g.split()
    for _w in _ws:
        _SYN.setdefault(_w, set()).update(x for x in _ws if x != _w)


def _syns(tok: str) -> set[str]:
    return _SYN.get(tok, set())


def _eq_syn(a: str, b: str) -> bool:
    """Due parole equivalenti: uguali, o con la stessa radice (condividi / condividere). Niente somiglianze «a occhio»: «rotella» non e' «cartella»."""
    return a == b or (len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5])


def _tok_in(tok: str, words: list[str]) -> bool:
    """La parola cercata (anche approssimata: l'OCR sbaglia qualche lettera) o un suo equivalente in un'altra lingua e' tra le parole date."""
    return any(_near(tok, w) for w in words) or any(_eq_syn(c, w) for c in _syns(tok) for w in words)


@dataclass
class Line:
    t: str
    x: float
    y: float
    w: float = 0.0
    h: float = 0.0
    words: list = field(default_factory=list)          # le parole della riga, ognuna con il suo riquadro (Line senza parole)


def where(x: float, y: float) -> str:
    """Un punto dello schermo (0-1, origine in alto a sinistra) detto a parole."""
    col = 0 if x < 0.34 else 1 if x < 0.66 else 2
    row = 0 if y < 0.34 else 1 if y < 0.66 else 2
    return [["in alto a sinistra", "in alto, al centro", "in alto a destra"],
            ["a sinistra, a metà altezza", "al centro dello schermo", "a destra, a metà altezza"],
            ["in basso a sinistra", "in basso, al centro", "in basso a destra"]][row][col]


def _in_overlay(ln: Line) -> bool:
    return _OVERLAY[0] <= ln.x <= _OVERLAY[1] and ln.y >= _OVERLAY[2]


def reading_order(lines: list[Line], limit: int = 5000) -> str:
    """Il testo letto, dall'alto in basso e da sinistra a destra (righe a quote simili stanno insieme)."""
    rows: list[list[Line]] = []
    for ln in sorted(lines, key=lambda l: (l.y, l.x)):
        if rows and abs(rows[-1][0].y - ln.y) < 0.012:
            rows[-1].append(ln)
        else:
            rows.append([ln])
    text = "\n".join("  ".join(l.t for l in sorted(r, key=lambda l: l.x)) for r in rows)
    return text[:limit]


def _union(parts: list[Line]) -> Line:
    """Il riquadro che contiene tutte le parole date (e il loro testo)."""
    x0, x1 = min(p.x - p.w / 2 for p in parts), max(p.x + p.w / 2 for p in parts)
    y0, y1 = min(p.y - p.h / 2 for p in parts), max(p.y + p.h / 2 for p in parts)
    return Line(" ".join(p.t for p in parts), (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)


def locate(lines: list[Line], target: str) -> list[tuple[float, Line]]:
    """Dove sta la scritta cercata («Esporta», «Salva con nome»), le piu' probabili prima. Il risultato e' il riquadro delle SOLE parole trovate (non dell'intera riga: «riquadro» dentro una frase
    lunga indica quella parola), con `.context` = la riga in cui sta. Una riga corta (un pulsante) vale piu' di una frase lunga che la contiene."""
    tnorm = normalize(target)
    alts = [[w for w in tnorm.split() if w not in _NOISE]]
    for it, ens in _PHRASES.items():                                                 # «salva con nome» -> anche «save as»
        if it in tnorm:
            alts += [e.split() for e in ens]
    alts = [a for a in alts if a]
    if not alts:
        return []
    out = []
    for ln in lines:
        words = normalize(ln.t).split()
        toks = next((a for a in alts if words and all(_tok_in(tok, words) for tok in a)), None)
        if toks is None:
            continue
        score = 1.0 - min(0.4, 0.04 * max(0, len(words) - len(toks)))
        hit = ln
        if ln.words and len(words) > len(toks):                          # riga lunga: stringe il riquadro sulle parole che combaciano
            picked = []
            for tok in toks:
                cand = [w for w in ln.words if _tok_in(tok, normalize(w.t).split())]
                if cand:
                    picked.append(cand[0])
            if picked:
                hit = _union(picked)
        m = Line(hit.t, hit.x, hit.y, hit.w, hit.h)
        m.context = ln.t                                                 # type: ignore[attr-defined]
        out.append((score, m))
    return sorted(out, key=lambda m: -m[0])


def _label(t: str, n: int = 40) -> str:
    t = " ".join(t.split())
    return t if len(t) <= n else t[:n].rstrip() + "…"


def _said_label(m: Line) -> str:
    ctx = getattr(m, "context", m.t)
    if len(ctx.split()) > len(m.t.split()) + 3:                          # una parola dentro una frase: non si legge la frase intera a voce
        return f"la parola «{_label(m.t, 30)}», in una frase"
    return f"«{_label(m.t)}»"


def describe_matches(matches: list[tuple[float, Line]], lines: list[Line], target: str) -> str:
    """«Esporta» e' in alto a destra, vicino a «Condividi»."""
    if not matches:
        return ""
    best = matches[0][1]
    near = [l for l in lines if abs(l.x - best.x) < 0.12 and abs(l.y - best.y) < 0.06 and normalize(l.t) != normalize(getattr(best, "context", best.t))]
    nearby = min(near, key=lambda l: (l.x - best.x) ** 2 + (l.y - best.y) ** 2) if near else None
    s = f"Vedo {_said_label(best)} {where(best.x, best.y)}"
    if nearby is not None and len(nearby.t.split()) <= 5 and len(getattr(best, "context", best.t).split()) <= len(best.t.split()) + 3:
        s += f", vicino a «{_label(nearby.t, 30)}»"
    others = [m[1] for m in matches[1:3] if m[0] >= matches[0][0] - 0.15]
    s += "."
    if others:
        s += " C'è anche " + (" e ".join(f"{_said_label(o)} {where(o.x, o.y)}" for o in others)) + "."
    return s


class AppleOCR:
    """Il programma di supporto (software/helpers/aria_apple_ocr.swift): una richiesta per riga; si tiene acceso (la prima lettura compila il modello di macOS, poi 0,3 s)."""

    def __init__(self, helper: str | None = None):
        self.helper = helper or os.environ.get("ARIA_APPLE_OCR") or OCR_HELPER
        self.proc: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()
        self.pending = 0

    def available(self) -> bool:
        return os.path.exists(self.helper)

    async def _start(self) -> None:
        if self.proc and self.proc.returncode is None:
            return
        if not self.available():
            raise RuntimeError(NO_OCR_HELPER)
        self.pending = 0
        self.proc = await asyncio.create_subprocess_exec(self.helper, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=STREAM_LIMIT)
        line = await asyncio.wait_for(self.proc.stdout.readline(), 30)
        if line.decode("utf-8", "ignore").strip() != "READY":
            self.proc.kill()
            self.proc = None
            raise RuntimeError("il programma che legge lo schermo non parte")

    async def _ask(self, command: str, timeout: float) -> dict:
        async with self.lock:
            await self._start()
            try:
                while self.pending > 0:                                   # risposta rimasta a una richiesta annullata: si butta
                    await asyncio.wait_for(self.proc.stdout.readline(), 10)
                    self.pending -= 1
                self.proc.stdin.write((command + "\n").encode())
                self.pending += 1
                await self.proc.stdin.drain()
                line = await asyncio.wait_for(self.proc.stdout.readline(), timeout)
                self.pending -= 1
            except Exception:                                             # noqa: BLE001
                if self.proc:
                    self.proc.kill()
                self.proc, self.pending = None, 0
                raise
        return json.loads(line.decode("utf-8", "ignore") or "{}")

    async def read(self, path: str) -> list[Line]:
        d = await self._ask(f"OCR\t{path}", 180)                        # la primissima volta macOS prepara il modello (anche un minuto)
        if d.get("error"):
            raise RuntimeError(d["error"])
        def box(r: dict, with_words: bool = True) -> Line:
            return Line(str(r.get("t", "")), float(r.get("x", 0)), float(r.get("y", 0)), float(r.get("w", 0)), float(r.get("h", 0)),
                        [box(w, False) for w in r.get("words", [])] if with_words else [])
        return [box(r) for r in d.get("lines", [])]

    async def permission(self, ask: bool = False) -> bool:
        return bool((await self._ask("ASK" if ask else "PERM", 60)).get("screen"))

    async def warmup(self) -> None:
        """Alla partenza (se l'OCR del Mac e' acceso): legge un'immagine piccola per far preparare il modello a macOS, cosi' la prima richiesta vera non aspetta."""
        try:
            fd, path = tempfile.mkstemp(suffix=".png", prefix="aria_ocr_")
            os.close(fd)
            import struct
            import zlib
            raw = b"".join(b"\x00" + b"\xff" * 3 * 64 for _ in range(64))
            png = b"\x89PNG\r\n\x1a\n"
            for tag, data in ((b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)), (b"IDAT", zlib.compress(raw)), (b"IEND", b"")):
                png += struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            with open(path, "wb") as f:
                f.write(png)
            await self.read(path)
            os.remove(path)
        except Exception as e:                                           # noqa: BLE001
            log.info("OCR del Mac: riscaldamento non riuscito (%s)", str(e)[:100])

    def close(self) -> None:
        if self.proc and self.proc.returncode is None:
            self.proc.kill()
        self.proc, self.pending = None, 0                                  # (il prossimo uso riparte con un processo nuovo)


_ROLE_IT = {"AXButton": "il pulsante", "AXMenuButton": "il pulsante", "AXPopUpButton": "il menu a tendina", "AXMenuBarItem": "il menu", "AXMenuItem": "la voce di menu", "AXCheckBox": "la casella",
            "AXRadioButton": "il pulsante", "AXTextField": "il campo", "AXTextArea": "il campo", "AXSearchField": "il campo di ricerca", "AXComboBox": "il campo", "AXLink": "il link",
            "AXTab": "la scheda", "AXTabGroup": "la scheda", "AXImage": "l'icona", "AXSlider": "il cursore", "AXDisclosureTriangle": "la freccia", "AXSegmentedControl": "il selettore",
            "AXHeading": "il titolo", "AXStaticText": "la scritta", "AXCell": "la riga", "AXRow": "la riga", "AXToolbar": "la barra degli strumenti", "AXGroup": "l'elemento"}
_INTERACTIVE = {"AXButton", "AXMenuButton", "AXPopUpButton", "AXMenuBarItem", "AXMenuItem", "AXCheckBox", "AXRadioButton", "AXTextField", "AXTextArea", "AXSearchField", "AXComboBox", "AXLink",
                "AXTab", "AXSlider", "AXDisclosureTriangle", "AXSegmentedControl"}


class AXProbe:
    """Il programma di supporto che legge l'interfaccia dell'app in primo piano con l'API Accessibilita' di macOS (software/helpers/aria_ax.swift): posizioni ESATTE di pulsanti, icone con
    descrizione e menu. Stesso protocollo a righe dell'OCR; serve il permesso «Accessibilita» per Aria."""

    def __init__(self, helper: str | None = None):
        self.helper = helper or os.environ.get("ARIA_AX") or AX_HELPER
        self.proc: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()
        self.pending = 0

    def available(self) -> bool:
        return os.path.exists(self.helper)

    async def _start(self) -> None:
        if self.proc and self.proc.returncode is None:
            return
        self.pending = 0
        self.proc = await asyncio.create_subprocess_exec(self.helper, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=STREAM_LIMIT)
        line = await asyncio.wait_for(self.proc.stdout.readline(), 15)
        if line.decode("utf-8", "ignore").strip() != "READY":
            self.proc.kill()
            self.proc = None
            raise RuntimeError("il programma che legge l'interfaccia non parte")

    async def _ask(self, command: str, timeout: float) -> dict:
        async with self.lock:
            await self._start()
            try:
                while self.pending > 0:
                    await asyncio.wait_for(self.proc.stdout.readline(), 5)
                    self.pending -= 1
                self.proc.stdin.write((command + "\n").encode())
                self.pending += 1
                await self.proc.stdin.drain()
                line = await asyncio.wait_for(self.proc.stdout.readline(), timeout)
                self.pending -= 1
            except Exception:                                             # noqa: BLE001
                if self.proc:
                    self.proc.kill()
                self.proc, self.pending = None, 0
                raise
        return json.loads(line.decode("utf-8", "ignore") or "{}")

    async def permission(self, ask: bool = False) -> bool:
        return bool((await self._ask("ASK" if ask else "PERM", 30)).get("ax"))

    async def dump(self) -> dict:
        return await self._ask("DUMP", 15)

    def close(self) -> None:
        if self.proc and self.proc.returncode is None:
            self.proc.kill()
        self.proc, self.pending = None, 0                                  # (il prossimo uso riparte con un processo nuovo)


def locate_ax(elements: list[dict], target: str) -> list[tuple[float, Line]]:
    """Gli elementi dell'interfaccia (da AXProbe.dump) la cui etichetta e' quella cercata, anche in un'altra lingua; i piu' probabili prima (i pulsanti prima delle scritte).
    Il risultato e' il riquadro esatto dell'elemento, con `.role` e `.menu`."""
    tnorm = normalize(target)
    alts = [[w for w in tnorm.split() if w not in _NOISE]]
    for it, ens in _PHRASES.items():
        if it in tnorm:
            alts += [e.split() for e in ens]
    alts = [a for a in alts if a]
    if not alts:
        return []
    out = []
    for e in elements:
        if e.get("off") or not (0.0 <= e.get("x", -1) <= 1.0 and 0.0 <= e.get("y", -1) <= 1.0):
            continue                                                       # spento, o su un altro schermo
        best = None
        for label in e.get("t", []):
            words = normalize(label).split()
            toks = next((a for a in alts if words and all(_tok_in(tok, words) for tok in a)), None)
            if toks is not None:
                sc = 1.0 - min(0.4, 0.04 * max(0, len(words) - len(toks)))
                if best is None or sc > best[0]:
                    best = (sc, label)
        if best is None:
            continue
        sc = best[0] + (0.06 if e.get("r") in _INTERACTIVE else -0.06 if e.get("r") in ("AXStaticText", "AXGroup", "AXCell", "AXRow", "AXImage") else 0.0)
        m = Line(best[1], float(e["x"]), float(e["y"]), float(e.get("w", 0)), float(e.get("h", 0)))
        m.role, m.menu = e.get("r", ""), e.get("m", "")                      # type: ignore[attr-defined]
        out.append((sc, m))
    return sorted(out, key=lambda m: -m[0])


def describe_ax(matches: list[tuple[float, Line]]) -> str:
    """«Vedo il pulsante «Condividi» in alto a destra.»"""
    best = matches[0][1]
    kind = _ROLE_IT.get(getattr(best, "role", ""), "")
    s = f"Vedo {kind + ' ' if kind else ''}«{_label(best.t)}» {where(best.x, best.y)}."
    others = [m[1] for m in matches[1:3] if m[0] >= matches[0][0] - 0.1]
    if others:
        s += " C'è anche " + " e ".join(f"{_ROLE_IT.get(getattr(o, 'role', ''), 'un elemento')} «{_label(o.t, 30)}» {where(o.x, o.y)}" for o in others) + "."
    return s


async def capture(timeout: float = 10.0) -> str:
    """Una foto dello schermo principale in un file temporaneo (chi la chiama lo cancella)."""
    fd, path = tempfile.mkstemp(suffix=".png", prefix="aria_screen_")
    os.close(fd)
    try:
        proc = await asyncio.create_subprocess_exec(SCREENCAPTURE, "-x", "-t", "png", "-m", path, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(proc.wait(), timeout)
        if proc.returncode != 0 or os.path.getsize(path) < 1000:
            raise RuntimeError("non sono riuscita a catturare lo schermo")
        return path
    except BaseException:
        try:
            os.remove(path)
        except OSError:
            pass
        raise


async def _open_privacy_pane() -> None:
    """Apre in Impostazioni di Sistema il pannello «Registrazione schermo»: macOS non sempre mostra da solo la finestra del permesso. Succede solo quando il permesso manca."""
    try:
        await asyncio.create_subprocess_exec("/usr/bin/open", PRIVACY_PANE, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    except Exception as e:                                                # noqa: BLE001
        log.info("non riesco ad aprire le Impostazioni di Sistema: %s", e)


async def point_at(lines: list[Line], seconds: float = 6.0, helper: str | None = None) -> bool:
    """Evidenzia sullo schermo le righe trovate (la prima luminosa, le altre tenui) con un riquadro che pulsa, per qualche secondo: un programma a parte (aria_pointer.swift),
    con la finestra trasparente che lascia passare i clic. Parte e basta: non si aspetta che finisca. True se e' partito."""
    path = helper or os.environ.get("ARIA_POINTER") or POINTER_HELPER
    if not lines or not os.path.exists(path):
        return False
    boxes = [f"{l.x:.4f},{l.y:.4f},{l.w:.4f},{l.h:.4f}" for l in lines[:3]]
    try:
        proc = await asyncio.create_subprocess_exec(path, "--seconds", str(seconds), *boxes, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        asyncio.ensure_future(proc.wait())                                 # niente processi zombie
        return True
    except Exception as e:                                                # noqa: BLE001
        log.info("non riesco a indicare sullo schermo: %s", e)
        return False


def vision_model(cfg: dict) -> str:
    """Quale modello guarda lo schermo: quello scelto in config (`screen.vision_model`), altrimenti il chatbot di Aria se vede le immagini, altrimenti Gemma 4 E4B."""
    chosen = (cfg.get("screen") or {}).get("vision_model")
    if chosen:
        return chosen.removeprefix("mlx:")
    chat = (cfg.get("brains") or [{}])[0].get("llm", {}).get("model") if isinstance(cfg.get("brains"), list) else None
    if chat and P.has_vision("mlx:" + chat):
        return chat
    return DEFAULT_VISION


async def run_vision(image: str, prompt: str, model: str, cfg: dict, max_tokens: int = 260) -> str:
    """Il modello che vede risponde sull'immagine, in un processo a parte (la sua memoria torna libera appena ha finito)."""
    budget = int((cfg.get("screen") or {}).get("max_soft_tokens", 1120))
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false", "PYTHONWARNINGS": "ignore", "PYTHONPATH": pkg_parent + os.pathsep + os.environ.get("PYTHONPATH", "")}
    proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "aria.vision", "--image", image, "--model", model, "--budget", str(budget), "--max-tokens", str(max_tokens), "--prompt", prompt,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env, cwd=pkg_parent)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), 180)
    except BaseException:
        proc.kill()
        raise
    for line in reversed(out.decode("utf-8", "ignore").splitlines()):
        if line.startswith("{"):
            d = json.loads(line)
            if d.get("error"):
                raise RuntimeError(d["error"])
            return str(d.get("text", "")).strip()
    log.warning("modello che vede: nessuna risposta (%s)", err.decode("utf-8", "ignore")[-300:])
    raise RuntimeError("il modello che vede non ha risposto")


_BOX = re.compile(r"\[\s*(\d{1,4})\s*,\s*(\d{1,4})\s*,\s*(\d{1,4})\s*,\s*(\d{1,4})\s*\]")


def parse_box(text: str) -> Line | None:
    """La risposta del modello che vede a «dammi il riquadro di X» ({"box_2d": [y_min, x_min, y_max, x_max]}, da 0 a 1000) -> un Line (0-1, origine in alto a sinistra), o None."""
    m = _BOX.search(text or "")
    if not m:
        return None
    y0, x0, y1, x1 = (int(g) / 1000.0 for g in m.groups())
    if not (0 <= x0 < x1 <= 1.0 and 0 <= y0 < y1 <= 1.0) or (x1 - x0) > 0.7 or (y1 - y0) > 0.7:
        return None
    return Line("", (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)


SCREEN_READ_SYSTEM = (
    "Sei Aria, un'assistente vocale. Ti do il TESTO letto con l'OCR dallo schermo del Mac (dall'alto in basso; ha errori e contiene menu e barre). L'utente vuole che tu LEGGA AD ALTA VOCE il contenuto principale. "
    "Leggi il testo principale nell'ordine giusto, correggendo gli errori ovvi dell'OCR, saltando menu, barre e pulsanti. Al massimo 800 caratteri: se e' piu' lungo leggi l'inizio e di' che continua. "
    "Solo italiano parlato, senza elenchi, senza markdown e senza simboli. Se non c'e' un testo da leggere, dillo.")


class ScreenTools:
    """Lo strumento SCHERMO (modo|testo): «leggi» (cosa c'e'), «dove» (dov'e' un pulsante/una scritta), «parere» (domanda libera su quello che si vede)."""
    ocr = None                                                            # AppleOCR (si crea alla prima richiesta)

    def _screen_engine(self) -> str | None:
        if self._on("screen_mac"):
            return "mac"
        if self._on("screen_model"):
            return "model"
        return None

    def _ocr_helper(self) -> AppleOCR:
        if self.ocr is None:
            self.ocr = AppleOCR((self.cfg.get("screen") or {}).get("ocr_helper"))
        return self.ocr

    ax = None                                                             # AXProbe (si crea alla prima richiesta)
    _ax_hint_given = False

    def _ax_probe(self) -> AXProbe:
        if self.ax is None:
            self.ax = AXProbe((self.cfg.get("screen") or {}).get("ax_helper"))
        return self.ax

    async def _find_with_ax(self, text: str) -> str | None:
        """«Dov'e' il pulsante X?» con l'API Accessibilita': posizione esatta (anche delle icone senza scritta). None se non c'e' il permesso, il programma o l'elemento."""
        if not self._on("screen_ax"):
            return None
        probe = self._ax_probe()
        if not probe.available():
            return None
        try:
            if not await probe.permission():
                return None
            d = await probe.dump()
        except Exception as e:                                                # noqa: BLE001
            log.info("accessibilita': non riesco a leggere l'interfaccia (%s)", str(e)[:100])
            return None
        found = locate_ax(d.get("elements", []), text)
        log.info("accessibilita': %s elementi in %s, %d corrispondenze per %r", d.get("n"), d.get("app"), len(found), text)
        if not found or found[0][0] < 0.75:
            return None
        import time
        said = describe_ax(found)
        self._last_found = [found[0][1]] + [m[1] for m in found[1:3] if m[0] >= found[0][0] - 0.1]
        self._last_found_at = time.monotonic()
        menu = getattr(found[0][1], "menu", "")
        if menu and getattr(found[0][1], "role", "") == "AXMenuItem":
            said = f"È la voce «{_label(found[0][1].t)}» del menu {menu}, in alto."
        if await self._point(self._last_found):
            said += " Te lo segno sullo schermo."
        return said

    _last_found: list | None = None                                        # le righe che ha appena indicato (per «indicamelo» / «fammelo vedere»)
    _last_found_at = 0.0

    def recent_found(self) -> bool:
        """Ha trovato qualcosa sullo schermo da poco? «mostramelo» ha senso solo allora: altrimenti parlava d'altro."""
        import time
        return bool(self._last_found) and time.monotonic() - self._last_found_at < 600

    async def _point(self, lines: list) -> bool:
        if not self._on("screen_point"):
            return False
        return await point_at(lines, float((self.cfg.get("screen") or {}).get("point_seconds", 6)))

    async def _schermo(self, arg: str) -> str:
        mode, _, text = arg.partition("|")
        mode, text = (mode.strip() or "leggi"), text.strip()
        if mode == "indica":                                              # «indicamelo»: di nuovo il riquadro su quello che ha appena trovato (la posizione e' quella di prima: se hai spostato la finestra, rifai la domanda)
            if not self._last_found:
                return "Non so cosa indicarti: dimmi cosa cerchi, ad esempio «non trovo il pulsante Esporta»."
            return "Eccolo." if await self._point(self._last_found) else "Non riesco a indicarlo sullo schermo, ma ti ho detto dove si trova."
        engine = self._screen_engine()
        if engine is None:
            return SCREEN_OFF
        if mode == "dove":
            self._prog("Guardo i pulsanti", 0.05, 0.3, 2)
            via_ax = await self._find_with_ax(text)                          # la via migliore: posizione esatta, senza nemmeno catturare lo schermo
            if via_ax:
                return via_ax
        helper = self._ocr_helper()
        if engine == "mac" and not helper.available():
            return NO_OCR_HELPER
        self._prog("Guardo lo schermo", 0.05, 0.2, 3)
        ok = await helper.permission() if helper.available() else True
        log.info("schermo: modo=%s motore=%s permesso=%s", mode, engine, ok)
        if not ok:
            import time as _time
            again = _time.monotonic() - getattr(self, "_perm_asked_at", -1e9) < 3600           # gia' chiesto da poco: l'utente dice che e' attivo, ma macOS non lo riconosce
            try:
                await helper.permission(ask=True)                          # macOS dovrebbe mostrare la finestra del permesso (dal vivo non l'ha fatto: per questo apre anche il pannello)
            except Exception:                                             # noqa: BLE001
                pass
            getattr(helper, "close", lambda: None)()                      # il prossimo controllo lo fa un processo nuovo: il permesso dato nel frattempo si vede subito
            self._perm_asked_at = _time.monotonic()
            await _open_privacy_pane()
            return NO_PERMISSION_AGAIN if again else NO_PERMISSION
        path = await capture()
        try:
            return await (self._schermo_mac if engine == "mac" else self._schermo_model)(mode, text, path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    async def _ax_permission_hint(self) -> str:
        """Se non trova un pulsante e l'Accessibilita' non e' concessa, lo dice (e la chiede a macOS): con quella le icone senza scritta si trovano con precisione."""
        if not self._on("screen_ax") or self._ax_hint_given:
            return ""
        probe = self._ax_probe()
        try:
            if not probe.available() or await probe.permission():
                return ""
            self._ax_hint_given = True
            await probe.permission(ask=True)
            return "Per trovare anche le icone senza scritta mi serve il permesso «Accessibilità»: ti ho aperto le Impostazioni, attiva Aria e riprova."
        except Exception:                                                     # noqa: BLE001
            return ""

    async def _schermo_mac(self, mode: str, text: str, path: str) -> str:
        self._prog("Leggo il testo", 0.2, 0.6, 4)
        lines = [l for l in await self._ocr_helper().read(path) if l.t.strip() and not _in_overlay(l)]
        log.info("schermo: letto %d righe di testo", len(lines))
        if not lines:
            return ("Non vedo nessun testo sullo schermo. Se dovrei vederne, controlla che Aria abbia il permesso «Registrazione schermo» "
                    "in Impostazioni di Sistema, sotto Privacy e sicurezza.")
        if mode == "dove":
            found = locate(lines, text)
            if found:
                said = describe_matches(found, lines, text)
                import time
                self._last_found = [found[0][1]] + [m[1] for m in found[1:3] if m[0] >= found[0][0] - 0.15]
                self._last_found_at = time.monotonic()
                if await self._point(self._last_found):
                    said += " Te lo segno sullo schermo."
                return said
            hint = await self._ax_permission_hint()
            return (f"Non vedo nessuna scritta «{_label(text)}» sullo schermo. " + (hint or "Se è un'icona senza testo, con l'OCR del Mac non posso trovarla: "
                    "con «un modello che vede», nelle Impostazioni, ci riesco ma solo a grandi linee."))
        question = text or "Riassumi cosa c'è sullo schermo e di cosa parla."
        if self.generate is None:
            return "Leggo: " + " ".join(l.t for l in lines[:12])[:500]
        self._prog("Ci penso", 0.6, 0.95, 8)
        aloud = bool(re.search(r"\b(?:legg\w+|leggere|ad alta voce)\b", normalize(question))) and not re.search(r"\b(?:riassum\w+|sintetizz\w+|spieg\w+|traduc\w+)\b", normalize(question))
        out = await self.generate(SCREEN_READ_SYSTEM if aloud else SCREEN_SYSTEM,
                                  f"Richiesta dell'utente: {question}\n\nTesto letto dallo schermo (dall'alto in basso):\n{reading_order(lines)}", 520 if aloud else 320)
        return (out or "").strip() or "Non sono riuscita a capire cosa c'è sullo schermo."

    async def _schermo_model(self, mode: str, text: str, path: str) -> str:
        model = vision_model(self.cfg)
        if not _vision_ready(model):
            return f"Il modello che vede ({P.llm_label('mlx:' + model)}) non è ancora sul Mac: scegli Gemma 4 E4B tra i chatbot nelle Impostazioni e premi «Scarica»."
        if mode == "dove":                                                    # il modello da' un riquadro (approssimato): si indica con prudenza
            self._prog("Cerco con il modello", 0.2, 0.9, 12)
            raw = await run_vision(path, f"Find \"{text}\" in this screenshot (a button, icon, menu or text). Answer ONLY with JSON: {{\"box_2d\": [y_min, x_min, y_max, x_max]}} with coordinates "
                                          f"normalized to 0-1000, or {{\"box_2d\": null}} if it is not visible.", model, self.cfg, max_tokens=70)
            box = parse_box(raw)
            if box is None:
                return f"Non vedo «{_label(text)}» sullo schermo."
            import time
            box.w, box.h = max(box.w * 1.6, 0.06), max(box.h * 1.6, 0.05)               # il riquadro del modello e' approssimato: lo si allarga
            box.t = text
            self._last_found, self._last_found_at = [box], time.monotonic()
            said = f"Credo sia {where(box.x, box.y)}, ma non sono sicura della posizione esatta."
            if await self._point(self._last_found):
                said += " Te lo segno sullo schermo."
            return said
        ask = {"leggi": text or "Riassumi cosa c'è sullo schermo e leggi i testi principali."}.get(mode) or text or "Descrivi cosa c'è sullo schermo."
        self._prog("Guardo con il modello", 0.2, 0.95, 12)
        out = await run_vision(path, VISION_PROMPT + ask, model, self.cfg)
        from .style import strip_markdown
        return strip_markdown(out).strip() or "Non sono riuscita a capire cosa c'è sullo schermo."


def _vision_ready(model: str) -> bool:
    try:
        from .models import mlx_lm_installed
        return bool(mlx_lm_installed(model))
    except Exception:                                                     # noqa: BLE001
        return True
