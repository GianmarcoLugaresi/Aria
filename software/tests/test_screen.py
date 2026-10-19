"""Guardare lo schermo: le frasi, la ricerca di una scritta, i due modi di leggere (OCR del Mac / modello che vede) e i permessi."""
import asyncio
import os
import stat
import sys

import pytest

from aria import intent, screen as S
from aria.config import load
from aria.memory import Memory
from aria.textutil import ToolCall
from aria.tools import Tools


def L(t, x, y, w=0.05, h=0.01):
    return S.Line(t, x, y, w, h)


SCREEN = [L("File", 0.03, 0.02), L("Modifica", 0.07, 0.02), L("Condividi", 0.86, 0.06), L("Esporta", 0.93, 0.06), L("Esporta come PDF", 0.5, 0.4),
          L("Il fatturato del trimestre è salito del dodici per cento.", 0.4, 0.5), L("Ti ascolto", 0.5, 0.9), L("Salva con nome", 0.2, 0.8)]


def test_screen_requests_need_an_explicit_reference_to_the_screen():
    assert intent.detect("Non trovo il pulsante Esporta") == ToolCall("SCHERMO", "dove|Esporta")
    assert intent.detect("dov'è il pulsante per salvare con nome") == ToolCall("SCHERMO", "dove|salvare con nome")
    assert intent.detect("Dove devo cliccare per esportare?") == ToolCall("SCHERMO", "dove|esportare")
    assert intent.detect("non trovo l'icona delle impostazioni sullo schermo") == ToolCall("SCHERMO", "dove|impostazioni")
    for t in ("guarda lo schermo", "cosa vedi sullo schermo?", "cosa c'è sullo schermo", "che cosa vedi", "cosa sto guardando?", "leggimi lo schermo", "Puoi riassumermi questa pagina?"):
        assert intent.detect(t) == ToolCall("SCHERMO", "leggi|"), t
    for t in ("cosa ne pensi di quello che vedo?", "secondo te cambierebbe qualcosa in questa pagina?", "aiutami con quello che vedi sullo schermo", "riassumi quello che sto leggendo",
              "Guardami lo schermo e dimmi cosa ne pensi"):
        c = intent.detect(t)
        assert c and c.name == "SCHERMO" and c.arg.startswith("parere|"), t
    for t in ("dov'è Roma?", "cosa ne pensi di mio cugino?", "guarda che bel tramonto", "ho guardato lo schermo tutto il giorno", "non trovo le chiavi", "dove si trova il bagno",
              "cosa vedi di strano in questa storia", "spegni lo schermo", "dov'è il mio telefono", "non trovo il telecomando"):
        c = intent.detect(t)
        assert not (c and c.name == "SCHERMO"), t
    # le frasi vere dell'utente (8 ott 01:16: il chatbot rispondeva da solo «non vedo nulla sullo schermo» perche' «fai un riassunto…» non era riconosciuta)
    assert intent.detect("Fai un riassunto di quello che vedi nello schermo?") == ToolCall("SCHERMO", "parere|Fai un riassunto di quello che vedi nello schermo")
    for t in ("Fammi un riassunto di quello che c'è sullo schermo", "mi fai un riassunto di questa pagina", "dammi un parere su quello che vedi sullo schermo"):
        c = intent.detect(t)
        assert c and c.name == "SCHERMO" and c.arg.startswith("parere|"), t
    assert intent.detect("puoi vedere lo schermo?") == ToolCall("SCHERMO", "leggi|") and intent.detect("riesci a vedere quello che ho davanti") == ToolCall("SCHERMO", "leggi|")
    for t in ("spegni lo schermo", "registra lo schermo", "fai uno screenshot dello schermo", "lo schermo del telefono è rotto", "come faccio a condividere lo schermo", "abbassa la luminosità dello schermo"):
        assert not (intent.detect(t) and intent.detect(t).name == "SCHERMO"), t
    on = lambda t: intent.detect(t, None, screen_on=True)
    assert on("dove c'è scritto Esporta?") == ToolCall("SCHERMO", "dove|Esporta") and on("mi dici dove c'è scritto Salva con nome sullo schermo") == ToolCall("SCHERMO", "dove|Salva con nome")
    assert intent.detect("trova Esporta sullo schermo") == ToolCall("SCHERMO", "dove|Esporta")
    c = intent.detect("Ok, leggendo il il il testo che leggi nello schermo, mi dici dove c'è scritto dov'è Roma?")        # la frase vera dell'01:20: prima leggeva il file della ricetta
    assert c and c.name == "SCHERMO" and c.arg.startswith("parere|")
    assert intent.detect("leggi il file della spesa").name == "LEGGI" and intent.detect("riassumi il documento polpi").name == "RIASSUMI"      # i file restano i file


def test_where_is_said_in_words_and_the_best_match_is_the_short_label():
    assert S.where(0.9, 0.05) == "in alto a destra" and S.where(0.5, 0.5) == "al centro dello schermo" and S.where(0.1, 0.9) == "in basso a sinistra"
    found = S.locate(SCREEN, "Esporta")
    assert found[0][1].t == "Esporta" and found[1][1].t == "Esporta come PDF"                     # il pulsante prima della frase lunga che lo contiene
    assert S.locate(SCREEN, "il pulsante Salva con nome")[0][1].t == "Salva con nome"            # «il pulsante» non fa parte della scritta
    assert S.locate(SCREEN, "esportare")[0][1].t == "Esporta"                                    # «per esportare» trova «Esporta»
    assert S.locate(SCREEN, "Stampa") == []
    said = S.describe_matches(S.locate(SCREEN, "Esporta"), SCREEN, "Esporta")
    assert said.startswith("Vedo «Esporta» in alto a destra") and "vicino a «Condividi»" in said and "Esporta come PDF" in said
    assert S.reading_order(SCREEN).splitlines()[0] == "File  Modifica"                           # dall'alto in basso, sinistra a destra


class FakeOCR:
    def __init__(self, lines, allowed=True):
        self.lines, self.allowed, self.asked = lines, allowed, False

    def available(self):
        return True

    async def permission(self, ask=False):
        self.asked = self.asked or ask
        return self.allowed

    async def read(self, path):
        return list(self.lines)


class FakeAX:
    """L'Accessibilita' finta: di default non c'e' il permesso (i test non devono leggere lo schermo vero)."""

    def __init__(self, elements=None, allowed=False):
        self.elements, self.allowed, self.asked = elements or [], allowed, False

    def available(self):
        return True

    async def permission(self, ask=False):
        self.asked = self.asked or ask
        return self.allowed

    async def dump(self):
        return {"ax": True, "app": "Finder", "win": "build", "n": len(self.elements), "elements": self.elements}


def make(tmp_path, monkeypatch, powers, ocr=None, generate=None, ax=None):
    cfg = load()
    cfg["powers"] = powers
    t = Tools(cfg, Memory())
    t.ax = ax or FakeAX()
    t.ocr = ocr or FakeOCR(SCREEN)
    t.generate = generate
    img = tmp_path / "shot.png"
    img.write_bytes(b"x" * 2000)

    async def cap(timeout=10.0):
        return str(img)
    monkeypatch.setattr(S, "capture", cap)
    return t, img


async def test_with_both_switches_off_the_screen_is_not_looked_at(tmp_path, monkeypatch):
    t, img = make(tmp_path, monkeypatch, {})
    assert await t.run(ToolCall("SCHERMO", "leggi|")) == S.SCREEN_OFF and img.exists()          # niente cattura


async def test_the_mac_ocr_finds_a_label_and_says_where_it_is(tmp_path, monkeypatch):
    t, img = make(tmp_path, monkeypatch, {"screen_mac": True})
    out = await t.run(ToolCall("SCHERMO", "dove|Esporta"))
    assert out.startswith("Vedo «Esporta» in alto a destra") and not img.exists()               # la foto dello schermo e' cancellata subito
    assert "Non vedo nessuna scritta «Stampa»" in await t.run(ToolCall("SCHERMO", "dove|Stampa"))
    t2, _ = make(tmp_path, monkeypatch, {"screen_mac": True}, ocr=FakeOCR([L("Ti ascolto", 0.5, 0.9), L("Pronta", 0.5, 0.95)]))
    assert (await t2.run(ToolCall("SCHERMO", "leggi|"))).startswith("Non vedo nessun testo sullo schermo.")      # la finestrella di Aria non conta...
    assert "Registrazione schermo" in await t2.run(ToolCall("SCHERMO", "leggi|"))                                  # ...e se non legge niente ricorda il permesso


async def test_the_mac_ocr_text_is_summarized_by_the_chatbot_without_aria_own_window(tmp_path, monkeypatch):
    seen = {}

    async def gen(system, user, max_tokens, temperature=None):
        seen["user"] = user
        return "Si parla del fatturato, salito del dodici per cento."
    t, _ = make(tmp_path, monkeypatch, {"screen_mac": True}, generate=gen)
    assert "fatturato" in await t.run(ToolCall("SCHERMO", "leggi|"))
    assert "Il fatturato del trimestre" in seen["user"] and "Ti ascolto" not in seen["user"] and "Riassumi" in seen["user"]
    await t.run(ToolCall("SCHERMO", "parere|cosa ne pensi di quello che vedo"))
    assert "cosa ne pensi di quello che vedo" in seen["user"]


async def test_the_model_that_sees_answers_about_the_picture_and_needs_to_be_installed(tmp_path, monkeypatch):
    calls = []

    async def fake_vision(image, prompt, model, cfg, max_tokens=260):
        calls.append((os.path.exists(image), prompt, model))
        return "**In alto** a destra c'è un pulsante con la rotellina."
    monkeypatch.setattr(S, "run_vision", fake_vision)
    monkeypatch.setattr(S, "_vision_ready", lambda m: True)
    t, img = make(tmp_path, monkeypatch, {"screen_model": True})
    assert await t.run(ToolCall("SCHERMO", "parere|cosa ne pensi di questa pagina")) == "In alto a destra c'è un pulsante con la rotellina."            # senza markdown
    assert calls[0][0] is True and "cosa ne pensi di questa pagina" in calls[0][1] and calls[0][2] == S.DEFAULT_VISION and not img.exists()
    monkeypatch.setattr(S, "_vision_ready", lambda m: False)
    assert "non è ancora sul Mac" in await t.run(ToolCall("SCHERMO", "leggi|"))


async def test_without_the_screen_recording_permission_it_asks_and_explains(tmp_path, monkeypatch):
    ocr = FakeOCR(SCREEN, allowed=False)
    opened = []

    async def fake_open():
        opened.append(1)
    monkeypatch.setattr(S, "_open_privacy_pane", fake_open)
    t, img = make(tmp_path, monkeypatch, {"screen_mac": True}, ocr=ocr)
    assert await t.run(ToolCall("SCHERMO", "leggi|")) == S.NO_PERMISSION and ocr.asked and img.exists() and opened      # non cattura niente, apre il pannello dei permessi


def test_the_vision_model_is_the_chatbot_when_it_sees_images_else_gemma_4_e4b():
    assert S.vision_model({"screen": {"vision_model": "mlx:org/mio-vlm"}}) == "org/mio-vlm"
    assert S.vision_model({"brains": [{"llm": {"model": "mlx-community/gemma-4-12B-it-4bit"}}]}) == "mlx-community/gemma-4-12B-it-4bit"
    assert S.vision_model({"brains": [{"llm": {"model": "mlx-community/gemma-2-9b-it-4bit"}}]}) == S.DEFAULT_VISION
    assert S.vision_model({}) == S.DEFAULT_VISION


async def test_the_ocr_helper_talks_in_lines_and_forgets_answers_to_cancelled_requests(tmp_path):
    p = tmp_path / "aria-apple-ocr"
    p.write_text(f"#!{sys.executable}\nimport sys, time, json\nprint('READY', flush=True)\nn = 0\nfor line in sys.stdin:\n    cmd = line.rstrip('\\n').split('\\t')[0]\n    if cmd == 'PERM':\n        print(json.dumps({{'screen': True}}), flush=True)\n"
                 "    else:\n        n += 1\n        time.sleep(0.4 if n == 1 else 0)\n        print(json.dumps({'w': 100, 'h': 50, 'lines': [{'t': 'riga %d' % n, 'x': 0.5, 'y': 0.2, 'w': 0.1, 'h': 0.02}]}), flush=True)\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    ocr = S.AppleOCR(str(p))
    assert ocr.available() and await ocr.permission() is True
    first = asyncio.create_task(ocr.read("/tmp/a.png"))
    await asyncio.sleep(0.15)
    first.cancel()
    await asyncio.gather(first, return_exceptions=True)
    lines = await ocr.read("/tmp/b.png")
    assert [l.t for l in lines] == ["riga 2"] and lines[0].y == 0.2                              # la risposta alla prima (annullata) non finisce alla seconda
    ocr.close()
    assert not S.AppleOCR(str(tmp_path / "manca")).available()


def test_vision_helper_without_mlx_vlm_says_so(capsys):
    from aria import vision
    code = vision.main(["--image", "/tmp/x.png", "--model", "org/m", "--prompt", "ciao"])
    out = capsys.readouterr().out
    assert code == 1 and "error" in out


async def test_where_a_label_is_it_gets_highlighted_on_the_screen_and_can_be_shown_again(tmp_path, monkeypatch):
    shown = []

    async def fake_point(lines, seconds=6.0, helper=None):
        shown.append([l.t for l in lines])
        return True
    monkeypatch.setattr(S, "point_at", fake_point)
    t, _ = make(tmp_path, monkeypatch, {"screen_mac": True, "screen_point": True})
    assert not t.recent_found() and "Non so cosa indicarti" in await t.run(ToolCall("SCHERMO", "indica|"))
    out = await t.run(ToolCall("SCHERMO", "dove|Esporta"))
    assert out.endswith("Te lo segno sullo schermo.") and shown == [["Esporta", "Esporta come PDF"]] and t.recent_found()        # il piu' probabile e l'altro, piu' tenue
    assert await t.run(ToolCall("SCHERMO", "indica|")) == "Eccolo." and len(shown) == 2                                           # «indicamelo»
    t2, _ = make(tmp_path, monkeypatch, {"screen_mac": True, "screen_point": False})                                               # interruttore spento: lo dice a parole e basta
    assert "Te lo segno" not in await t2.run(ToolCall("SCHERMO", "dove|Esporta")) and len(shown) == 2
    out = await t.run(ToolCall("SCHERMO", "dove|Stampa"))
    assert "Non vedo nessuna scritta" in out and len(shown) == 2                              # se non c'e' niente non indica niente


async def test_the_pointer_helper_is_started_with_the_boxes_and_not_waited_for(tmp_path):
    log = tmp_path / "args.txt"
    p = tmp_path / "aria-pointer"
    p.write_text(f"#!{sys.executable}\nimport sys\nopen({str(log)!r}, 'w').write(' '.join(sys.argv[1:]))\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    assert await S.point_at([L("Esporta", 0.93, 0.06, 0.04, 0.014), L("Condividi", 0.86, 0.06, 0.05, 0.014)], 4.0, helper=str(p)) is True
    for _ in range(50):
        if log.exists() and log.read_text():
            break
        await asyncio.sleep(0.1)
    assert log.read_text() == "--seconds 4.0 0.9300,0.0600,0.0400,0.0140 0.8600,0.0600,0.0500,0.0140"
    assert await S.point_at([], 4.0, helper=str(p)) is False and await S.point_at([L("x", 0.5, 0.5)], 4.0, helper=str(tmp_path / "manca")) is False


def test_mostramelo_only_means_the_screen_right_after_something_was_found():
    assert intent.detect("indicamelo") == ToolCall("SCHERMO", "indica|") and intent.detect("puoi indicarmelo?") == ToolCall("SCHERMO", "indica|")
    assert intent.detect("indicami il pulsante Esporta") == ToolCall("SCHERMO", "dove|Esporta")


def test_a_word_inside_a_long_line_is_pointed_at_not_the_whole_line():
    words = [L("Sì,", 0.30, 0.50, 0.02, 0.012), L("si", 0.33, 0.50, 0.015, 0.012), L("può", 0.36, 0.50, 0.025, 0.012), L("il", 0.40, 0.50, 0.01, 0.012),
             L("cerchio", 0.45, 0.50, 0.04, 0.012), L("riquadro", 0.52, 0.50, 0.05, 0.012), L("luminoso", 0.59, 0.50, 0.05, 0.012)]
    line = S.Line("Sì, si può il cerchio riquadro luminoso", 0.45, 0.50, 0.40, 0.012, words)
    found = S.locate([line, L("Condividi", 0.86, 0.06)], "riquadro")
    best = found[0][1]
    assert best.t == "riquadro" and abs(best.x - 0.52) < 1e-6 and best.w < 0.06                  # il riquadro e' sulla parola, largo come la parola
    said = S.describe_matches(found, [line], "riquadro")
    assert said == "Vedo la parola «riquadro», in una frase al centro dello schermo."          # non legge la frase intera a voce
    two = S.locate([S.Line("Esporta come PDF", 0.5, 0.4, 0.2, 0.012, [L("Esporta", 0.45, 0.4, 0.06, 0.012), L("come", 0.5, 0.4, 0.04, 0.012), L("PDF", 0.55, 0.4, 0.03, 0.012)])], "esporta pdf")
    assert abs(two[0][1].w - (0.58 - 0.42)) < 0.02 or two[0][1].t == "Esporta come PDF"          # due parole = il riquadro che le contiene


def test_pointing_requests_in_any_phrasing_and_the_chatbot_cannot_claim_to_point():
    from aria import style
    for t in ("Mi indichi dov'è la scritta Somnium?", "Indicami dov'è la scritta Somnium.", "indicami dove si trova la parola Somnium", "evidenziami il pulsante Somnium", "trova la scritta Somnium"):
        assert intent.detect(t) == ToolCall("SCHERMO", "dove|Somnium"), t                      # le frasi vere delle 01:34: prima il chatbot rispondeva «ti indico subito…» e non faceva niente
    assert intent.detect("puoi trovarmi la parola Somnium?") == ToolCall("SCHERMO", "dove|Somnium")
    assert intent.screen_attempt("segnami lo schermo di quella roba li") and intent.screen_attempt("dov'è Roma?") is None and intent.screen_attempt("spegni lo schermo") is None
    for lie in ("Ti indico subito dove compare «Somnium» sullo schermo.", "È proprio lì che appare il riquadro luminoso attorno alla parola."):
        assert style.has_false_claim(lie), lie
    assert not style.has_false_claim("Il riquadro del quadro è bello.") and not style.has_false_claim("Vedo la parola Somnium in alto a destra.")


def test_where_is_written_goes_to_the_screen_only_when_the_screen_is_on_and_never_for_documents():
    files = ["Ricetta - gnocchi alla romana.md"]                                       # c'e' un documento nella cartella: prima «dov'e' scritto Somnium?» finiva li' (01:32, 02:32)
    for t in ("Dov'è scritto Somnium?", "Indicami dove c'è scritto somnium.", "Mi di dov'è scritto somnium lo schermo?", "dove c'è scritto Esporta?"):
        c = intent.detect(t, files, screen_on=True)
        assert c and c.name == "SCHERMO" and c.arg.startswith("dove|"), t
    assert intent.detect("Dov'è scritto Somnium?", files, screen_on=True) == ToolCall("SCHERMO", "dove|Somnium")
    assert intent.detect("Dov'è scritto Somnium?", files).name == "DOCUMENTO"           # schermo spento: e' una domanda sul documento, come prima
    for t in ("c'è scritto che la garanzia dura due anni?", "dov'è scritto il prezzo nel contratto", "dove c'è scritto il nome nel documento"):
        c = intent.detect(t, files, screen_on=True)
        assert c and c.name == "DOCUMENTO", t
    assert intent.detect("Me lo indichi") == ToolCall("SCHERMO", "indica|") and intent.detect("me lo mostri") == ToolCall("SCHERMO", "indica|")
    from aria import style
    assert style.has_false_claim("Ti indico.") and not style.has_false_claim("Vedo la parola Somnium in alto.")


AX_ELEMENTS = [{"r": "AXButton", "t": ["Condividi"], "x": 0.86, "y": 0.06, "w": 0.02, "h": 0.03}, {"r": "AXButton", "t": ["Impostazioni", "Settings"], "x": 0.95, "y": 0.06, "w": 0.02, "h": 0.03},
               {"r": "AXMenuBarItem", "t": ["File"], "x": 0.075, "y": 0.015, "w": 0.02, "h": 0.02, "m": "File"}, {"r": "AXTextField", "t": ["Cerca"], "x": 0.7, "y": 0.06, "w": 0.1, "h": 0.03},
               {"r": "AXImage", "t": ["Condividi"], "x": 0.3, "y": 0.5, "w": 0.05, "h": 0.05}, {"r": "AXButton", "t": ["Elimina"], "x": 0.5, "y": 0.5, "w": 0.02, "h": 0.03, "off": True},
               {"r": "AXButton", "t": ["Remota"], "x": 1.4, "y": 0.5, "w": 0.02, "h": 0.03}]


def test_accessibility_matches_icons_by_description_in_any_language_and_prefers_buttons():
    found = S.locate_ax(AX_ELEMENTS, "il pulsante per condividere")
    assert found[0][1].t == "Condividi" and found[0][1].role == "AXButton" and found[1][1].role == "AXImage"        # il pulsante prima dell'immagine con lo stesso nome
    assert S.locate_ax(AX_ELEMENTS, "impostazioni")[0][1].t == "Impostazioni"
    assert S.locate_ax(AX_ELEMENTS, "elimina") == [] and S.locate_ax(AX_ELEMENTS, "remota") == []                   # spenti e su un altro schermo: no
    assert S.locate_ax(AX_ELEMENTS, "la lente di ricerca") != [] or S.locate_ax(AX_ELEMENTS, "cerca")[0][1].role == "AXTextField"
    assert S.describe_ax(S.locate_ax(AX_ELEMENTS, "condividi")).startswith("Vedo il pulsante «Condividi» in alto a destra")


async def test_where_is_the_button_uses_accessibility_first_without_capturing_the_screen(tmp_path, monkeypatch):
    shown = []

    async def fake_point(lines, seconds=6.0, helper=None):
        shown.append((lines[0].role, round(lines[0].x, 2), round(lines[0].y, 2)))
        return True
    monkeypatch.setattr(S, "point_at", fake_point)
    captured = []

    async def cap(timeout=10.0):
        captured.append(1)
        raise AssertionError("non deve catturare lo schermo")
    monkeypatch.setattr(S, "capture", cap)
    ax = FakeAX(AX_ELEMENTS, allowed=True)
    t, _ = make(tmp_path, monkeypatch, {"screen_mac": True, "screen_point": True}, ax=ax)
    monkeypatch.setattr(S, "capture", cap)
    out = await t.run(ToolCall("SCHERMO", "dove|condividere"))
    assert out.startswith("Vedo il pulsante «Condividi» in alto a destra") and out.endswith("Te lo segno sullo schermo.") and shown == [("AXButton", 0.86, 0.06)] and not captured
    assert t.recent_found()                                                                    # e «indicamelo» lo ripete


async def test_without_the_accessibility_permission_it_falls_back_to_the_ocr_and_asks_once_when_nothing_is_found(tmp_path, monkeypatch):
    ax = FakeAX(AX_ELEMENTS, allowed=False)
    t, _ = make(tmp_path, monkeypatch, {"screen_mac": True, "screen_point": False}, ax=ax)
    assert (await t.run(ToolCall("SCHERMO", "dove|Esporta"))).startswith("Vedo «Esporta» in alto a destra")           # l'OCR lo trova lo stesso
    out = await t.run(ToolCall("SCHERMO", "dove|Stampa"))
    assert "permesso «Accessibilità»" in out and ax.asked                                       # non trova niente: suggerisce il permesso per le icone
    assert "permesso «Accessibilità»" not in await t.run(ToolCall("SCHERMO", "dove|Stampa"))     # una volta sola
    t2, _ = make(tmp_path, monkeypatch, {"screen_mac": True, "screen_ax": False}, ax=FakeAX(AX_ELEMENTS, allowed=True))
    assert (await t2.run(ToolCall("SCHERMO", "dove|Condividi"))).startswith("Vedo «Condividi»")              # interruttore spento: solo OCR


def test_ui_words_are_translated_between_italian_and_english():
    L = lambda t: S.Line(t, 0.5, 0.5, 0.1, 0.02)
    lines = [L("Save As…"), L("Export as PDF…"), L("Settings"), L("Enter Full Screen")]
    for q, want in (("salva con nome", "Save As…"), ("esportare in PDF", "Export as PDF…"), ("le impostazioni", "Settings"), ("schermo intero", "Enter Full Screen")):
        assert S.locate(lines, q) and S.locate(lines, q)[0][1].t == want, q


def test_the_model_box_answer_is_parsed_and_nonsense_is_refused():
    b = S.parse_box('```json\n{"box_2d": [633, 837, 673, 883]}\n```')
    assert b and abs(b.x - 0.86) < 1e-9 and abs(b.y - 0.653) < 1e-9 and abs(b.w - 0.046) < 1e-9
    assert S.parse_box('{"box_2d": null}') is None and S.parse_box("non lo vedo") is None
    assert S.parse_box('{"box_2d": [0, 0, 1000, 1000]}') is None and S.parse_box('{"box_2d": [600, 800, 500, 700]}') is None          # tutto lo schermo / al contrario


async def test_the_model_engine_points_roughly_when_it_finds_a_box_and_says_so(tmp_path, monkeypatch):
    shown = []

    async def fake_point(lines, seconds=6.0, helper=None):
        shown.append((round(lines[0].x, 2), round(lines[0].w, 3)))
        return True
    monkeypatch.setattr(S, "point_at", fake_point)
    answers = iter(['{"box_2d": [60, 750, 90, 790]}', '{"box_2d": null}'])

    async def fake_vision(image, prompt, model, cfg, max_tokens=260):
        assert "box_2d" in prompt and "Find" in prompt
        return next(answers)
    monkeypatch.setattr(S, "run_vision", fake_vision)
    monkeypatch.setattr(S, "_vision_ready", lambda m: True)
    t, _ = make(tmp_path, monkeypatch, {"screen_model": True, "screen_point": True})
    out = await t.run(ToolCall("SCHERMO", "dove|la lente di ricerca"))
    assert out.startswith("Credo sia in alto a destra") and "non sono sicura" in out and out.endswith("Te lo segno sullo schermo.") and shown == [(0.77, 0.064)]
    assert await t.run(ToolCall("SCHERMO", "dove|la lente di ricerca")) == "Non vedo «la lente di ricerca» sullo schermo."


async def test_read_aloud_requests_use_the_reading_prompt_and_summaries_do_not(tmp_path, monkeypatch):
    seen = []

    async def gen(system, user, max_tokens, temperature=None):
        seen.append(system)
        return "ok"
    t, _ = make(tmp_path, monkeypatch, {"screen_mac": True}, generate=gen)
    await t.run(ToolCall("SCHERMO", "parere|Leggimi questa email"))
    await t.run(ToolCall("SCHERMO", "parere|Riassumi e leggi questa email"))
    await t.run(ToolCall("SCHERMO", "parere|Cosa ne pensi di questa pagina?"))
    assert seen == [S.SCREEN_READ_SYSTEM, S.SCREEN_SYSTEM, S.SCREEN_SYSTEM]


def test_mac_info_questions_go_to_the_system_tool_and_messages_to_others_are_refused():
    for text, kind in {"Quanta batteria ho?": "batteria", "Quanto spazio libero ho sul disco?": "spazio", "Che versione di macOS ho?": "versione", "Da quanto tempo è acceso il Mac?": "accensione",
                       "A che wifi sono collegato?": "wifi", "Qual è il mio indirizzo IP?": "ip", "Quanta RAM sto usando?": "memoria"}.items():
        assert intent.detect(text) == ToolCall("SISTEMA", kind), text
    for t in ("Digli che arrivo tardi", "Avvisalo che sono qui", "Rispondigli di sì"):
        assert intent.detect(t) == ToolCall("NON_SO", "message"), t
    assert intent.detect("Avvisami tra dieci minuti").name == "TIMER"                                   # «avvisami» e' un timer, «avvisalo» un messaggio
    assert intent.detect("Traduci questa frase in inglese: buongiorno a tutti", None, screen_on=True).name == "TRADUCI"    # il testo c'e' gia': non e' una domanda sullo schermo, e' una traduzione
    assert intent.request_like("Silenzi tutto")


async def test_system_info_reads_the_mac_and_speaks_in_italian(monkeypatch):
    from aria import sysinfo

    async def fake_run(*cmd, timeout=8.0):
        if cmd[0].endswith("pmset"):
            return "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t87%; discharging; 4:12 remaining present: true\n"
        if cmd[0].endswith("sw_vers"):
            return "27.0.1\n"
        return ""
    monkeypatch.setattr(sysinfo, "_run", fake_run)
    assert await sysinfo.answer("batteria") == "Hai il ottantasette per cento di batteria, non sei collegato alla corrente, resta circa quattro ore e dodici minuti."
    assert await sysinfo.answer("versione") == "Hai macOS 27 punto 0 punto 1." and "giga liberi" in await sysinfo.answer("spazio")
    assert await sysinfo.answer("boh") == "Questa informazione sul Mac non la so dire."


async def test_the_time_in_another_city_is_told_with_its_own_clock_and_part_of_the_day():
    from aria import worldclock
    from aria.tools import Tools as T
    assert intent.detect("Che ora è a Tokyo?").arg.startswith("citta:") and intent.detect("Che ore sono?") == ToolCall("ORA", "ora")
    assert worldclock.find_zone("che ora e a new york adesso")[0] == "America/New_York" and worldclock.find_zone("che ora e in giappone")[1] == "in Giappone" and worldclock.find_zone("che ore sono") is None
    out = await T(load(), Memory()).run(ToolCall("ORA", "citta:che ora e a tokyo"))
    assert out.startswith("A Tokyo ") and ("sono le" in out or "è " in out) and ("di mattina" in out or "del pomeriggio" in out or "di sera" in out or "di notte" in out or "mezzo" in out)


def test_stage_directions_are_not_spoken_but_normal_emphasis_is_kept():
    from aria import style
    out = style.strip_markdown("*La voce si abbassa, calda e morbida, come se stesse sussurrando.* Non posso farti un caffè. Va *proprio* bene (sorride) e **molto**")
    assert out == "Non posso farti un caffè. Va proprio bene e molto"
    assert intent.detect("Leggimi le mail non lette") == ToolCall("NON_SO", "inbox") and intent.detect("Leggimi il file della spesa").name == "LEGGI"


def test_things_that_exist_only_on_screen_go_to_the_screen_tool_even_when_it_is_off_so_aria_answers_honestly():
    off = lambda t: intent.detect(t, None, screen_on=False)
    for t in ("Cosa significa questo errore?", "Che vuol dire questo avviso?", "Spiegami questo pulsante", "mi spieghi questa notifica"):
        assert off(t) is not None and off(t).name == "SCHERMO", t
    assert off("Cosa significa questo errore: 404 not found") is None                      # il testo c'e' gia' nella frase
    assert off("cosa significa questa frase") is None and off("cos'è questo") is None      # mai una voce di enciclopedia per «questa frase»
    assert off("cosa significa serendipità") == ToolCall("WIKI", "serendipità")


async def test_a_very_long_answer_line_from_the_helpers_is_read_in_full(tmp_path):
    """Un monitor pieno di testo/pulsanti fa una riga di risposta da centinaia di KB: con il limite di 64 KB di asyncio Aria diceva «chunk is longer than limit» e non indicava niente."""
    p = tmp_path / "aria-apple-ocr"
    p.write_text(f"#!{sys.executable}\nimport sys, json\nprint('READY', flush=True)\nfor line in sys.stdin:\n"
                 "    print(json.dumps({'w': 100, 'h': 50, 'lines': [{'t': 'riga %d' % i, 'x': 0.5, 'y': 0.2, 'w': 0.1, 'h': 0.02} for i in range(6000)]}), flush=True)\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    ocr = S.AppleOCR(str(p))
    lines = await ocr.read("/tmp/a.png")
    assert len(lines) == 6000
    ocr.close()


async def test_when_the_permission_keeps_failing_aria_explains_the_stale_entry_and_checks_with_a_fresh_helper(tmp_path, monkeypatch):
    """Dopo un aggiornamento dell'app macOS mostra Aria «attiva» ma non la riconosce: spegnere e riaccendere non basta, bisogna togliere la voce e riaggiungerla."""
    p = tmp_path / "aria-apple-ocr"
    p.write_text(f"#!{sys.executable}\nimport sys, json\nprint('READY', flush=True)\nfor line in sys.stdin:\n    print(json.dumps({{'screen': False}}), flush=True)\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    opened = []

    async def fake_pane():
        opened.append(1)
    monkeypatch.setattr(S, "_open_privacy_pane", fake_pane)
    t = Tools(load(), Memory())
    t.cfg["powers"] = {"screen_mac": True}
    t.ocr = S.AppleOCR(str(p))
    first = await t._schermo("leggi|")
    assert first == S.NO_PERMISSION and t.ocr.proc is None                    # (il prossimo controllo lo fa un processo nuovo)
    second = await t._schermo("leggi|")
    assert second == S.NO_PERMISSION_AGAIN and "meno" in second and len(opened) == 2


def test_pointing_at_every_place_a_word_appears_looks_at_the_screen_not_at_the_documents():
    """Dal log dell'utente: «Indicami tutti i punti dove c'è scritto AVS» finiva nei documenti («Nel documento non c'è scritto AVS»)."""
    from aria import intent as I
    files = ["Ricetta - gnocchi alla romana.md"]
    for t in ("Indicami tutti i punti dove c'è scritto AVS.", "indicami tutti i posti in cui compare la parola AVS", "segnami tutti i punti con scritto AVS",
              "Mostrami ogni punto dove si legge AVS sullo schermo", "Indicami tutte le volte che compare la parola AVS"):
        for on in (True, False):
            assert I.detect(t, files, screen_on=on) == ToolCall("SCHERMO", "dove|AVS"), (t, on)
    assert I.detect("Indicami tutti i punti dove c'è scritto latte nel contratto", files, screen_on=True).name == "DOCUMENTO"      # parla di un documento


def test_pointing_requests_survive_a_comment_before_them_and_a_comma_after_on_the_screen():
    """Dal log: «Ok, figo. Indicami dove c'è scritto AVS» finiva nei documenti; «Indicami sullo schermo, dove c'è scritto AVS» faceva un riassunto invece di indicare."""
    from aria import intent as I
    files = ["Ricetta - gnocchi alla romana.md"]
    for t in ("Ok, figo. Indicami dove c'è scritto AVS.", "Indicami sullo schermo, dove c'è scritto AVS.", "Grande! Indicami tutti i punti dove c'è scritto AVS",
              "Ok, figo. Indicami la scritta AVS"):
        assert I.detect(t, files, screen_on=True) == ToolCall("SCHERMO", "dove|AVS"), t
    assert I.detect("Ok, figo. Dimmi dove c'è scritto latte nella ricetta", files, screen_on=True).name == "DOCUMENTO"
    assert I.detect("Ok. Che ore sono?", files, screen_on=True).name == "ORA"
    assert I.detect("Bene, mi dici cosa vedi sullo schermo?", files, screen_on=True) == ToolCall("SCHERMO", "parere|Bene, mi dici cosa vedi sullo schermo")
