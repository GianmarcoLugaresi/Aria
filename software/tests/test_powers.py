"""I poteri di Aria sul Mac, provati con un esecutore finto: nessun test tocca davvero il Mac, i promemoria o la musica."""
import asyncio
import datetime as dt
import io
import json
import os
import zipfile

import httpx
import pytest

from aria import powers as PW
from aria.config import load
from aria.intent import detect
from aria.macos import Mac, MacError, search_url, site_url
from aria.memory import Memory
from aria.textutil import ToolCall
from aria.tools import MODEL_TOOLS, SPEAK_VERBATIM, Tools

NOW = dt.datetime(2026, 10, 6, 12, 0)                          # martedì 6 ottobre 2026, mezzogiorno


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))


class Runner:
    """Esecutore finto: registra ogni comando e risponde in base a cosa e' stato chiesto."""

    def __init__(self, replies=None, default=(0, "", "")):
        self.calls, self.replies, self.default = [], replies or {}, default

    def __call__(self, argv, timeout, stdin=None):
        self.calls.append(argv)
        for key, rep in self.replies.items():
            if any(key in part for part in argv):
                return rep(argv) if callable(rep) else rep
        return self.default


def make(tmp_path, replies=None, powers=None, text="Risposta."):
    cfg = load()
    cfg["workspace"] = str(tmp_path / "Aria")
    os.makedirs(cfg["workspace"], exist_ok=True)
    cfg["powers"] = powers or {}
    t = Tools(cfg, Memory())
    t.now_fn = lambda: NOW
    r = Runner(replies)
    apps_dir = tmp_path / "Apps"
    for n in ("Safari", "Mail", "Calendar", "Music", "Notes", "Spotify"):
        (apps_dir / f"{n}.app").mkdir(parents=True, exist_ok=True)
    t.mac = Mac(runner=r, platform="darwin", app_dirs=(str(apps_dir),))
    gen_calls = []

    async def gen(system, user, max_tokens):
        gen_calls.append((system, user, max_tokens))
        return text
    t.generate = gen
    t.gen_calls = gen_calls
    return t, r


def script_of(argv):
    return "\n".join(argv[i + 1] for i, a in enumerate(argv) if a == "-e")


def args_of(argv):
    i = max(k for k, a in enumerate(argv) if a == "-e")
    rest = argv[i + 2:]
    return rest[1:] if rest[:1] == ["--"] else rest


# ---------------------------------------------------------------- il ponte macOS
def test_user_text_never_goes_inside_a_script():
    evil = 'x" & (do shell script "rm -rf ~") & "'
    r = Runner()
    Mac(runner=r, platform="darwin").osa(PW.REMINDER_SCRIPT, evil)
    argv = r.calls[0]
    assert argv[0] == "osascript" and argv[-1] == evil                       # il testo e' un argomento separato...
    assert "rm -rf" not in script_of(argv) and "do shell script" not in script_of(argv)   # ...e non finisce mai nello script
    r2 = Runner()
    Mac(runner=r2, platform="darwin").osa(PW.REMINDER_SCRIPT, "-e", 'do shell script "rm -rf ~"')      # un titolo che comincia con «-e»: senza «--» osascript lo eseguiva come codice
    argv2 = r2.calls[0]
    assert argv2[argv2.index("--") + 1:] == ["-e", 'do shell script "rm -rf ~"'] and "do shell script" not in script_of(argv2[:argv2.index("--")])


def test_osascript_errors_are_explained():
    for err, expect in (("execution error: Not authorized to send Apple events to Calendar. (-1743)", "Automazione"),
                        ("Application isn't running. (-600)", "non è aperta"), ("boh (-1728)", "Non ho trovato")):
        with pytest.raises(MacError, match=expect):
            Mac(runner=Runner(default=(1, "", err)), platform="darwin").osa("return 1", app="Calendario")
    with pytest.raises(MacError, match="solo sul Mac"):
        Mac(runner=Runner(), platform="linux").osa("return 1")


def test_apps_are_resolved_by_real_name_only(tmp_path):
    t, r = make(tmp_path)
    m = t.mac
    assert m.resolve_app("Safari") == "Safari" and m.resolve_app("l'app Safari") == "Safari" and m.resolve_app("posta") == "Mail"
    assert m.resolve_app("calendario") == "Calendar" and m.resolve_app("la musica") == "Music" and m.resolve_app("sa") is None
    assert m.resolve_app("photoshop") is None and m.resolve_app("") is None
    m.open_app("Safari")
    assert r.calls[-1] == ["open", "-a", "Safari"]


def test_sites_are_https_and_public_only():
    assert site_url("YouTube") == "https://www.youtube.com" and site_url("il sito repubblica punto it") == "https://repubblica.it"
    assert site_url("example.com") == "https://example.com" and site_url("www.esempio.it") == "https://www.esempio.it"
    for bad in ("127.0.0.1", "192.168.1.1", "localhost", "file:///etc/passwd", "javascript:alert(1)", "pippo", "a b c"):
        assert site_url(bad) is None, bad
    assert search_url("youtube", "gatti & cani") == "https://www.youtube.com/results?search_query=gatti%20%26%20cani"
    assert search_url("boh", "x") is None and search_url("google", "  ") is None
    with pytest.raises(MacError):
        Mac(runner=Runner(), platform="darwin").open_url("file:///etc/passwd")


# ---------------------------------------------------------------- promemoria e calendario
async def test_reminder_with_and_without_a_date(tmp_path):
    t, r = make(tmp_path)
    out = await t.run(ToolCall("PROMEMORIA", "domani alle 9 di chiamare Marco"))
    assert out == "Fatto: ti ricorderò «Chiamare Marco» domani alle nove."
    assert args_of(r.calls[-1]) == ["Chiamare Marco", "2026", "10", "7", "9", "0"] and "Reminders" in script_of(r.calls[-1])
    out = await t.run(ToolCall("PROMEMORIA", "comprare il pane"))
    assert out == "@CHIEDI|PROMEMORIA|comprare il pane|Per quando te lo ricordo?"                      # senza data chiede «per quando?»: la risposta completa il promemoria
    out = await t.run(ToolCall("PROMEMORIA", "!comprare il pane"))                                       # «senza orario»: lo crea senza data
    assert out == "Fatto: ho aggiunto «Comprare il pane» ai tuoi promemoria." and args_of(r.calls[-1]) == ["Comprare il pane"]
    assert await t.run(ToolCall("PROMEMORIA", "domani alle 9")) == "@CHIEDI|PROMEMORIA|domani alle 9|Cosa devo ricordarti?"


async def test_reminders_list(tmp_path):
    t, r = make(tmp_path, {"Reminders": (0, "Comprare il pane\nChiamare Marco\n", "")})
    assert await t.run(ToolCall("PROMEMORIA_LISTA", "")) == "Hai due promemoria: Comprare il pane, Chiamare Marco."
    t2, _ = make(tmp_path, {"Reminders": (0, "", "")})
    assert await t2.run(ToolCall("PROMEMORIA_LISTA", "")) == "Non hai promemoria da fare."


async def test_calendar_event_and_agenda(tmp_path):
    t, r = make(tmp_path, {"Calendar": (0, "Personale", "")})
    out = await t.run(ToolCall("EVENTO", "cena con Marco venerdì alle 20"))
    assert out == "Fatto: «Cena con Marco» è in calendario venerdì alle venti, nel calendario Personale."
    a = args_of(r.calls[-1])
    assert a[:8] == ["Cena con Marco", "0", "2026", "10", "9", "20", "0", "60"] and a[8] == ""
    await t.run(ToolCall("EVENTO", "dentista domani"))
    assert args_of(r.calls[-1])[1] == "1"                                        # senza ora: tutto il giorno
    assert "Per quando" in await t.run(ToolCall("EVENTO", "cena con Marco"))
    t2, _ = make(tmp_path, {"Calendar": (0, "NOCAL", "")})
    assert "Non trovo un calendario" in await t2.run(ToolCall("EVENTO", "cena domani alle 20"))
    t3, r3 = make(tmp_path, {"Calendar": (0, "Dentista|false|15|0\nRiunione|false|9|30\nCompleanno Anna|true|0|0\n", "")})
    assert await t3.run(ToolCall("AGENDA", "domani")) == "Domani hai tre impegni: tutto il giorno «Compleanno Anna», alle nove e mezza «Riunione», alle quindici «Dentista»."
    assert args_of(r3.calls[-1]) == ["2026", "10", "7"]
    t4, _ = make(tmp_path, {"Calendar": (0, "", "")})
    assert await t4.run(ToolCall("AGENDA", "oggi")) == "Oggi non hai impegni in calendario."


# ---------------------------------------------------------------- musica e volume
async def test_music_controls(tmp_path):
    t, r = make(tmp_path, {'is running': (0, "true", ""), "player state": (0, "ok", "")})
    r.replies = {'application "Spotify" is running': (0, "false", ""), 'application "Music" is running': (0, "true", ""), "tell application \"Music\"": (0, "ok", "")}
    assert await t.run(ToolCall("MUSICA", "play")) == "Ecco la musica." and args_of(r.calls[-1]) == ["play"]
    assert await t.run(ToolCall("MUSICA", "pause")) == "Messa in pausa." and await t.run(ToolCall("MUSICA", "next")) == "Passo alla prossima."
    r.replies["tell application \"Music\""] = (0, "Bohemian Rhapsody|Queen", "")
    assert await t.run(ToolCall("MUSICA", "now")) == "Sta suonando «Bohemian Rhapsody» di Queen."
    assert await t.run(ToolCall("MUSICA", "track:i Queen")) == "Metto «Bohemian Rhapsody» di Queen." and args_of(r.calls[-1]) == ["track", "Queen"]
    r.replies["tell application \"Music\""] = (0, "NONE", "")
    out = await t.run(ToolCall("MUSICA", "track:Boh"))                                                      # non e' nella libreria: apre la ricerca su Apple Music
    assert "Boh" in out and "Apple Music" in out and r.calls[-1][:2] == ["open", "music://music.apple.com/it/search?term=Boh"]
    r.replies["tell application \"Music\""] = (0, "ok", "")
    assert await t.run(ToolCall("MUSICA", "play|Music")) == "Ecco la musica."                                 # l'app scelta a voce
    r.replies["tell application \"Music\""] = (0, "STOP", "")
    assert await t.run(ToolCall("MUSICA", "now")) == "Adesso non sta suonando niente."


async def test_spotify_is_used_when_only_spotify_is_open(tmp_path):
    t, r = make(tmp_path)
    r.replies = {'application "Music" is running': (0, "false", ""), 'application "Spotify" is running': (0, "true", ""), 'tell application "Spotify"': (0, "ok", "")}
    assert await t.run(ToolCall("MUSICA", "pause")) == "Messa in pausa." and "Spotify" in script_of(r.calls[-1])
    out = await t.run(ToolCall("MUSICA", "track:Queen"))                                                    # Spotify non si comanda per titolo: si apre la ricerca
    assert "Spotify" in out and r.calls[-1][:2] == ["open", "spotify:search:Queen"]
    assert await t.run(ToolCall("MUSICA", "pause|Spotify")) == "Messa in pausa."


async def test_volume(tmp_path):
    vol = {"v": 40}

    def fake(argv):
        s = script_of(argv)
        if "output volume of" in s:
            return 0, str(vol["v"]), ""
        if "set volume output volume" in s:
            vol["v"] = int(args_of(argv)[0])
            return 0, "", ""
        return 0, "", ""
    t, r = make(tmp_path, {"volume": fake})
    assert await t.run(ToolCall("VOLUME", "up")) == "Volume al cinquantadue per cento." and vol["v"] == 52
    assert await t.run(ToolCall("VOLUME", "down")) == "Volume al quaranta per cento."
    assert await t.run(ToolCall("VOLUME", "set:30")) == "Volume al trenta per cento." and vol["v"] == 30
    await t.run(ToolCall("VOLUME", "set:250"))
    assert vol["v"] == 100                                                      # mai oltre il massimo
    await t.run(ToolCall("VOLUME", "down")), await t.run(ToolCall("VOLUME", "set:0"))
    assert vol["v"] == 0
    assert await t.run(ToolCall("VOLUME", "get")) == "Il volume è al zero per cento."
    assert "Ho tolto l'audio" in await t.run(ToolCall("VOLUME", "mute")) and "muted" in script_of(r.calls[-1]) and args_of(r.calls[-1]) == ["1"]
    assert "riacceso" in await t.run(ToolCall("VOLUME", "unmute")) and args_of(r.calls[-1]) == ["0"]


# ---------------------------------------------------------------- app, siti, mappe
async def test_open_apps_and_sites(tmp_path):
    t, r = make(tmp_path)
    assert await t.run(ToolCall("APRI_APP", "Safari")) == "Ho aperto Safari." and r.calls[-1] == ["open", "-a", "Safari"]
    assert await t.run(ToolCall("APRI_APP", "posta")) == "Ho aperto Mail." and r.calls[-1] == ["open", "-a", "Mail"]
    assert await t.run(ToolCall("APRI_APP", "YouTube")) == "Ho aperto il sito YouTube." and r.calls[-1] == ["open", "https://www.youtube.com"]
    assert "Non trovo" in await t.run(ToolCall("APRI_APP", "Photoshop"))                 # un nome proprio che non c'e': lo dice
    from aria.powers import PASS
    assert await t.run(ToolCall("APRI_APP", "programma inesistente")) == PASS             # non sembra il nome di un'app: ne parla il chatbot
    assert await t.run(ToolCall("APRI_APP", "~Photoshop")) == PASS                        # «vai su…» agisce solo se trova davvero qualcosa
    assert await t.run(ToolCall("WEB", "youtube|gatti")) == "Ecco la ricerca su youtube: «gatti»." and r.calls[-1][1].endswith("search_query=gatti")
    assert await t.run(ToolCall("MAPPA", "Piazza Navona, Roma")) == "Ecco «Piazza Navona, Roma» sulla mappa." and "maps.apple.com/?q=Piazza%20Navona%2C%20Roma" in r.calls[-1][1]
    n = len(r.calls)
    assert "Non so cercare" in await t.run(ToolCall("WEB", "motoreignoto|x")) and len(r.calls) == n


# ---------------------------------------------------------------- scorciatoie
async def test_shortcuts_ask_for_confirmation_first(tmp_path):
    t, r = make(tmp_path, {"shortcuts": lambda a: (0, "Buonanotte\nLuci soggiorno\n", "") if a[1] == "list" else (0, "Fatto!", "")})
    assert await t.run(ToolCall("SCORCIATOIE", "")) == "Hai due scorciatoie: Buonanotte, Luci soggiorno."
    out = await t.run(ToolCall("SCORCIATOIA", "buonanotte"))
    assert out == f"{PW.CONFIRM}|SCORCIATOIA_OK|Buonanotte|Vuoi che esegua la scorciatoia «Buonanotte»?"
    assert not any(c[:2] == ["shortcuts", "run"] for c in r.calls)               # finora NON e' stato eseguito niente
    assert await t.run(ToolCall("SCORCIATOIA_OK", "Buonanotte")) == "Fatto: ho eseguito «Buonanotte». Fatto!" and r.calls[-1] == ["shortcuts", "run", "Buonanotte"]
    assert "Non trovo nessuna scorciatoia" in await t.run(ToolCall("SCORCIATOIA", "pippo"))


async def test_shortcuts_allowlist_and_no_confirm_option(tmp_path):
    t, r = make(tmp_path, {"shortcuts": lambda a: (0, "Buonanotte\nElimina tutto\n", "") if a[1] == "list" else (0, "", "")})
    t.cfg["tools"] = {**t.cfg["tools"], "shortcuts": {"allow": ["Buonanotte"]}}
    assert "non è nell'elenco" in await t.run(ToolCall("SCORCIATOIA", "elimina tutto"))
    t.cfg["tools"]["confirm_shortcuts"] = False
    assert await t.run(ToolCall("SCORCIATOIA", "buonanotte")) == "Fatto: ho eseguito «Buonanotte»." and r.calls[-1] == ["shortcuts", "run", "Buonanotte"]


# ---------------------------------------------------------------- documenti
def _docx(text):
    buf = io.BytesIO()
    paras = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in text.split("\n"))
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{paras}</w:body></w:document>')
    return buf.getvalue()


async def test_questions_about_a_word_document(tmp_path):
    t, r = make(tmp_path, text="La garanzia dura ventiquattro mesi dalla data di acquisto.")
    body = "\n".join(["Premessa generale del contratto."] * 40 + ["Art. 7 Garanzia: la garanzia dura 24 mesi dalla consegna."] + ["Altre clausole varie."] * 40)
    (tmp_path / "Aria" / "Contratto di vendita.docx").write_bytes(_docx(body))
    out = await t.run(ToolCall("DOCUMENTO", "contratto|quanto dura la garanzia"))
    assert out == "«Contratto di vendita»: La garanzia dura ventiquattro mesi dalla data di acquisto."
    system, user, _ = t.gen_calls[0]
    assert "SOLO il testo del documento" in system and "garanzia dura 24 mesi" in user and "Domanda: quanto dura la garanzia" in user
    assert user.count("Premessa generale") < 40                                  # al modello vanno i passaggi pertinenti, non tutto il documento
    assert "Non trovo nessun file" in await t.run(ToolCall("DOCUMENTO", "manuale|boh"))


def _pdf(text: str) -> bytes:
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
            f"<</Length {len(stream)}>>\nstream\n".encode() + stream + b"\nendstream", b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n" + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    return out + f"trailer\n<</Root 1 0 R/Size {len(objs) + 1}>>\nstartxref\n{xref}\n%%EOF".encode()


async def test_pdf_documents_are_read_when_pypdf_is_there(tmp_path):
    pytest.importorskip("pypdf")
    t, _ = make(tmp_path)
    (tmp_path / "Aria" / "Garanzia.pdf").write_bytes(_pdf("La garanzia dura ventiquattro mesi."))
    assert "garanzia dura ventiquattro mesi" in await t.run(ToolCall("LEGGI", "garanzia"))
    (tmp_path / "Aria" / "Rotto.pdf").write_bytes(b"non e' un pdf")
    assert "Non riesco a leggere questo PDF" in await t.run(ToolCall("LEGGI", "rotto"))


# ---------------------------------------------------------------- briefing
async def test_morning_briefing_collects_what_is_available(tmp_path):
    rss = '<?xml version="1.0"?><rss><channel><item><title>Primo titolo</title></item><item><title>Secondo titolo</title></item><item><title>Terzo</title></item><item><title>Quarto</title></item></channel></rss>'
    t, r = make(tmp_path, {"Calendar": (0, "Riunione|false|10|0\n", ""), "Reminders": (0, "Comprare il pane\n", "")})
    t.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=rss.encode())))
    t.memory.set_profile("name", "Mario")

    async def weather(arg):
        return "Oggi a Roma: sereno, tra 8 e 19 gradi."
    t._weather = weather
    out = await t.run(ToolCall("BRIEFING", ""))
    assert out.startswith("Buon pomeriggio, Mario! Oggi è martedì sei ottobre duemilaventisei.")
    assert "Oggi a Roma: sereno" in out and "In agenda: alle dieci «Riunione»." in out and "Tra i promemoria: Comprare il pane." in out
    assert "Dalle notizie: Primo titolo; Secondo titolo; Terzo." in out and "Quarto" not in out


async def test_briefing_survives_missing_pieces(tmp_path):
    t, r = make(tmp_path, {"Calendar": (1, "", "Not authorized to send Apple events (-1743)"), "Reminders": (1, "", "Not authorized (-1743)")})
    t.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(500)))

    async def no_city(arg):
        return "@CITTA"
    t._weather = no_city
    out = await t.run(ToolCall("BRIEFING", ""))
    assert out.startswith("Buon pomeriggio! Oggi è martedì") and "agenda" not in out and "notizie" not in out and "@CITTA" not in out


# ---------------------------------------------------------------- interruttori e sicurezza
async def test_switched_off_powers_do_nothing(tmp_path):
    t, r = make(tmp_path, powers={"reminders": False, "music": False, "apps": False, "shortcuts": False, "calendar": False, "documents": False, "briefing": False})
    for name, arg in (("PROMEMORIA", "x"), ("PROMEMORIA_LISTA", ""), ("EVENTO", "x domani"), ("AGENDA", "oggi"), ("MUSICA", "play"), ("VOLUME", "up"), ("APRI_APP", "Safari"),
                      ("WEB", "google|x"), ("MAPPA", "x"), ("SCORCIATOIA", "x"), ("SCORCIATOIE", ""), ("DOCUMENTO", "a|b"), ("BRIEFING", "")):
        assert await t.run(ToolCall(name, arg)) == PW.POWER_OFF, name
    assert r.calls == []                                                          # nemmeno un comando e' partito


def test_power_switches_are_saved_in_settings_and_survive_model_choices(tmp_path):
    from aria import profiles as P
    cfg = tmp_path / "config.yaml"
    cfg.write_text("brains: []\n")
    assert P.get_powers(str(cfg)) == {k: k not in P.POWERS_OFF_BY_DEFAULT for k in P.POWERS}                  # tutti accesi di default, tranne guardare lo schermo (chiede un permesso)
    P.set_power(str(cfg), "music", False)
    P.save_settings(str(cfg), {"profile": "media", "llm_model": None})            # salvare i modelli non spegne/accende nulla
    assert P.get_powers(str(cfg))["music"] is False and P.get_powers(str(cfg))["apps"] is True
    P.set_workspace(str(cfg), None)
    assert P.get_powers(str(cfg))["music"] is False
    with pytest.raises(KeyError):
        P.set_power(str(cfg), "inesistente", True)
    t = Tools({**load(), "_config_path": str(cfg)}, Memory())                      # lo strumento legge gli interruttori dal file, a caldo
    assert t._on("music") is False and t._on("apps") is True
    P.set_power(str(cfg), "music", True)
    assert t._on("music") is True


def test_only_harmless_tools_can_be_started_by_the_chatbot():
    assert MODEL_TOOLS == {"CERCA", "WIKI", "METEO", "TIMER", "CALCOLA", "RICORDA", "ORA", "MEMORIA"}
    assert PW.POWER_TOOLS <= SPEAK_VERBATIM


def test_things_aria_cannot_do_are_said_plainly():
    for text, kind in (("Chiama la mamma", "call"), ("Manda un messaggio a Marco", "message"), ("Spegni la luce in cucina", "home"), ("Ordina una pizza", "buy"),
                       ("Puoi accendere la tv?", "home")):
        assert detect(text) == ToolCall("NON_SO", kind), text


def test_trap_phrases_do_not_trigger_powers():
    for t in ("Avvia un timer di dieci minuti", "Apri la porta", "Metti la sveglia alle sette", "Silenzia il microfono",
              "Scrivi a Marco che arrivo tardi", "Come stai?", "Suona il campanello", "Ricordati che mi piace il caffè"):
        c = detect(t)
        assert c is None or c.name in {"TIMER", "RICORDA", "NON_SO"}, (t, c)               # (aprire una porta di casa = «non so farlo», non un'app)
    assert detect("ricordami tra dieci minuti di spegnere il forno").name == "TIMER"       # relativo breve: resta il timer dentro Aria
    assert detect("Ricordami domani alle 9 di chiamare Marco") == ToolCall("PROMEMORIA", "domani alle 9 di chiamare Marco")


# ---------------------------------------------------------------- in conversazione
async def test_shortcut_runs_only_after_a_spoken_yes(tmp_path):
    from tests.test_conversation import build, utterance
    for answer, runs in (("sì, esegui", True), ("no grazie", False), ("che ore sono", False)):
        a, hub, llm, tts, spk, tools = build(utterance() + utterance(), ["esegui la scorciatoia Buonanotte", answer])
        real, r = make(tmp_path, {"shortcuts": lambda argv: (0, "Buonanotte\n", "") if argv[1] == "list" else (0, "", "")})
        real.cfg = a.cfg
        a.tools = real
        await asyncio.wait_for(a.session(), 40)
        said = " ".join(tts.said)
        assert "Vuoi che esegua la scorciatoia Buonanotte?" in said                       # le virgolette «» non si leggono: la voce riceve il testo senza
        assert any(c[:2] == ["shortcuts", "run"] for c in r.calls) is runs, answer
        if runs:
            assert "Fatto: ho eseguito Buonanotte" in said
        assert a.pending_confirm is None


async def test_the_chatbot_cannot_start_a_shortcut_by_itself(tmp_path):
    from tests.test_conversation import build, utterance
    a, hub, llm, tts, spk, tools = build(utterance(), ["racconta qualcosa"])

    async def stream(messages, max_tokens=None):
        for t in ["Va bene. ", "[[SCORCIATOIA: ", "Elimina tutto", "]]"]:
            yield t
    a.router.llm_stream = stream
    real, r = make(tmp_path, {"shortcuts": (0, "Elimina tutto\n", "")})
    real.cfg = a.cfg
    a.tools = real
    await asyncio.wait_for(a.session(), 30)
    assert not any(c[:2] == ["shortcuts", "run"] for c in r.calls) and not any(c and c[0] == "shortcuts" for c in r.calls)    # nessun comando e' partito


def test_settings_cli_can_switch_powers(tmp_path, monkeypatch):
    import yaml
    from aria import models as M
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"brains": [{"name": "mac", "llm": {"kind": "mlx-lm", "model": "mlx-community/gemma-3-text-4b-it-4bit"},
                                               "stt": {"kind": "mlx-whisper", "model": "mlx-community/whisper-large-v3-turbo-q4"}, "tts": {"kind": "say"}}]}))
    monkeypatch.setattr(M, "stt_installed", lambda c: True)
    monkeypatch.setattr(M, "mlx_lm_installed", lambda r: True)
    st = M.status(str(cfg), [])["powers"]
    assert [p["id"] for p in st] == ["shortcuts", "reminders", "calendar", "music", "apps", "documents", "briefing", "screen_mac", "screen_model", "screen_point", "screen_ax", "voice_natural", "battery_rest"]
    assert all(p["enabled"] for p in st if not p["id"].startswith("screen") and p["id"] != "voice_natural") and not any(p["enabled"] for p in st if p["id"] in ("screen_mac", "screen_model", "voice_natural"))      # lo schermo e' spento finche' non lo scegli
    assert M.power_set(str(cfg), "music", False)["ok"]
    assert {p["id"]: p["enabled"] for p in M.status(str(cfg), [])["powers"]}["music"] is False
    assert M.main(["power", "music", "on", "--config", str(cfg)]) == 0
    assert {p["id"]: p["enabled"] for p in M.powers_status(str(cfg))}["music"] is True
    assert not M.power_set(str(cfg), "boh", True)["ok"] and M.main(["power", "boh", "on", "--config", str(cfg)]) == 1


def test_the_two_ways_of_reading_the_screen_exclude_each_other_and_models_say_if_they_see_images(tmp_path, monkeypatch):
    import yaml
    from aria import models as M, profiles as P
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"brains": [{"name": "mac", "llm": {"kind": "mlx-lm", "model": "mlx-community/gemma-4-e4b-it-4bit"},
                                               "stt": {"kind": "mlx-whisper", "model": "mlx-community/whisper-large-v3-turbo-q4"}, "tts": {"kind": "say"}}]}))
    monkeypatch.setattr(M, "stt_installed", lambda c: True)
    monkeypatch.setattr(M, "mlx_lm_installed", lambda r: True)
    on = lambda: {p["id"]: p["enabled"] for p in M.powers_status(str(cfg)) if p["id"] in ("screen_mac", "screen_model")}
    assert on() == {"screen_mac": False, "screen_model": False}
    M.power_set(str(cfg), "screen_mac", True)
    assert on() == {"screen_mac": True, "screen_model": False}
    M.power_set(str(cfg), "screen_model", True)                                 # scegliere l'altra spegne la prima
    assert on() == {"screen_mac": False, "screen_model": True}
    M.power_set(str(cfg), "screen_model", False)
    assert on() == {"screen_mac": False, "screen_model": False}                 # e si possono spegnere tutte e due
    models = {m["ref"]: m["label"] for m in M.status(str(cfg), [])["llm_models"]}
    assert "vede le immagini" in models["mlx:mlx-community/gemma-4-e4b-it-4bit"]
    for ref in ("mlx:mlx-community/gemma-2-9b-it-4bit", "mlx:mlx-community/gemma-3-text-4b-it-4bit", "mlx:mlx-community/gemma-3-text-12b-it-4bit"):
        assert "vede le immagini" not in models[ref], ref
    hint = [p for p in M.powers_status(str(cfg)) if p["id"] == "screen_model"][0]["hint"]
    assert "Gemma 4" in hint and "Non vedono" in hint and "già sul Mac" in hint            # dice quali vedono, quale userebbe e se c'e'
    assert P.has_vision("mlx:mlx-community/gemma-4-12B-it-4bit") and not P.has_vision("mlx:mlx-community/gemma-2-9b-it-4bit")


async def test_a_reminder_for_a_time_already_passed_today_goes_to_tomorrow(tmp_path):
    t, r = make(tmp_path)
    t.now_fn = lambda: dt.datetime(2026, 10, 6, 15, 0)
    out = await t.run(ToolCall("PROMEMORIA", "oggi alle 9 di chiamare Marco"))
    assert "domani" in out and args_of(r.calls[-1])[1:6] == ["2026", "10", "7", "9", "0"]
