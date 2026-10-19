"""Gli strumenti sui file di Aria: riconoscimento delle frasi, scrittura nella cartella, sicurezza, e il giro completo in conversazione."""
import asyncio
import os

import pytest

from aria import filetools as F
from aria.config import load
from aria.intent import detect
from aria.memory import Memory
from aria.textutil import ToolCall
from aria.tools import SPEAK_VERBATIM, Tools


@pytest.fixture(autouse=True)
def _home_is_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))                  # la cartella di Aria sta nella "Home" del test (le cartelle di sistema sono rifiutate)


def test_phrases_are_recognised_keeping_what_the_user_said():
    d = detect
    assert d("Scrivimi un testo sulla fotosintesi.") == ToolCall("SCRIVI", "testo|fotosintesi")
    assert d("Puoi scrivermi una poesia per mia madre?") == ToolCall("SCRIVI", "poesia|mia madre")
    assert d("Scrivi un articolo sulla storia di Roma e mettilo nella cartella") == ToolCall("SCRIVI", "articolo|storia di Roma")
    assert d("Preparami una scaletta sul caffè, per favore") == ToolCall("SCRIVI", "scaletta|caffè")
    assert d("fai una ricerca veloce sui polpi") == ToolCall("RICERCA", "polpi")
    assert d("Fammi una ricerca su come funziona un motore elettrico e salvala") == ToolCall("RICERCA", "come funziona un motore elettrico")
    assert d("Cerca i migliori ristoranti di Roma e salvali") == ToolCall("RICERCA", "i migliori ristoranti di Roma")
    assert d("Aggiungi latte, pane e uova alla lista della spesa") == ToolCall("LISTA", "della spesa|latte, pane e uova")
    assert d("Segna una nota: domani devo chiamare Marco Rossi.") == ToolCall("NOTA", "domani devo chiamare Marco Rossi")
    assert d("Prendi nota che ho finito il caffè") == ToolCall("NOTA", "ho finito il caffè")
    assert d("Che file ci sono nella cartella?") == ToolCall("ELENCO", "") and d("Apri la cartella") == ToolCall("APRI", "")
    assert d("Leggimi il file sui polpi") == ToolCall("LEGGI", "sui polpi")
    assert d("Riassumi il documento della ricerca sui polpi") == ToolCall("RIASSUMI", "della ricerca sui polpi")


def test_everyday_requests_are_not_hijacked():
    assert d_none("scrivi a Marco che arrivo tardi") and d_none("leggi le notizie") is False   # "leggi le notizie" resta una ricerca web
    assert detect("leggi le notizie") == ToolCall("CERCA", "leggi le notizie")
    assert detect("cerca notizie di oggi") == ToolCall("CERCA", "notizie di oggi")
    assert d_none("come stai?") and d_none("scrivi forte")
    assert detect("metti la sveglia") == ToolCall("TIMER", "")                                         # senza orario: chiede «a che ora?»
    assert detect("che tempo fa domani") == ToolCall("METEO", "domani") and detect("ricordati che mi piace il caffè") .name == "RICORDA"


def d_none(t):
    return detect(t) is None


class FakeTools(Tools):
    pass


def make_tools(tmp_path, with_ws=True, text="# Fotosintesi\n\nLe piante trasformano la luce in energia. " * 4):
    cfg = load()
    cfg.setdefault("human", {})["doc_web"] = False
    if with_ws:
        root = tmp_path / "Aria"
        root.mkdir(exist_ok=True)
        cfg["workspace"] = str(root)
    t = FakeTools(cfg, Memory())
    calls = []

    async def gen(system, user, max_tokens):
        calls.append((system, user, max_tokens))
        return text
    t.generate = gen
    t.gen_calls = calls
    return t


async def test_write_a_text_into_the_folder(tmp_path):
    t = make_tools(tmp_path)
    out = await t.run(ToolCall("SCRIVI", "testo|la fotosintesi"))
    assert out == "Fatto: ho scritto «Testo - la fotosintesi» e l'ho messo nella tua cartella."
    saved = (tmp_path / "Aria" / "Testo - la fotosintesi.md").read_text(encoding="utf-8")
    assert saved.startswith("# Fotosintesi") and "luce in energia" in saved
    system, user, max_tokens = t.gen_calls[0]
    assert "testo" in user and "la fotosintesi" in user and max_tokens >= 600 and "Markdown" in system
    again = await t.run(ToolCall("SCRIVI", "testo|la fotosintesi"))                                   # stesso argomento: un file nuovo, nessuna sovrascrittura
    assert (tmp_path / "Aria" / "Testo - la fotosintesi (2).md").exists() and "(2)" in again
    assert sorted(os.listdir(tmp_path / "Aria")) == ["Testo - la fotosintesi (2).md", "Testo - la fotosintesi.md"]


async def test_chatty_model_output_is_cleaned_and_titled(tmp_path):
    t = make_tools(tmp_path, text="Ecco il testo che hai chiesto:\n\n```markdown\nLe api impollinano i fiori e producono miele per tutta l'estate.\n```")
    await t.run(ToolCall("SCRIVI", "testo|le api"))
    saved = (tmp_path / "Aria" / "Testo - le api.md").read_text(encoding="utf-8")
    assert saved.startswith("# Testo: le api\n\nLe api impollinano") and "Ecco" not in saved and "```" not in saved
    t2 = make_tools(tmp_path, text="troppo corto")
    assert "riprova" in await t2.run(ToolCall("SCRIVI", "testo|niente"))


async def test_without_a_folder_nothing_is_written(tmp_path):
    t = make_tools(tmp_path, with_ws=False)
    for name, arg in (("SCRIVI", "testo|x"), ("LISTA", "della spesa|latte"), ("NOTA", "ciao"), ("ELENCO", ""), ("LEGGI", "x"), ("RIASSUMI", "x"), ("APRI", "")):
        assert await t.run(ToolCall(name, arg)) == F.NO_WORKSPACE, name
    assert t.gen_calls == []                                                                         # nemmeno una richiesta al chatbot sprecata


async def test_a_deleted_or_dangerous_folder_counts_as_no_folder(tmp_path):
    t = make_tools(tmp_path)
    (tmp_path / "Aria").rmdir()
    assert await t.run(ToolCall("NOTA", "ciao")) == F.NO_WORKSPACE
    t.cfg["workspace"] = "/System"
    assert await t.run(ToolCall("NOTA", "ciao")) == F.NO_WORKSPACE


async def test_lists_and_notes_append(tmp_path):
    t = make_tools(tmp_path)
    assert await t.run(ToolCall("LISTA", "della spesa|latte")) == "Aggiunto «latte» alla lista della spesa."
    await t.run(ToolCall("LISTA", "della spesa|pane e uova"))
    assert (tmp_path / "Aria" / "Lista della spesa.md").read_text(encoding="utf-8") == "# Lista della spesa\n\n- [ ] latte\n- [ ] pane\n- [ ] uova\n"          # «pane e uova» sono due cose
    assert await t.run(ToolCall("NOTA", "domani chiamare Marco")) == "Nota salvata."
    note = (tmp_path / "Aria" / "Note.md").read_text(encoding="utf-8")
    assert note.startswith("# Note\n\n- 20") and note.endswith("— domani chiamare Marco\n")


async def test_list_read_and_summarise(tmp_path):
    t = make_tools(tmp_path, text="Le piante usano la luce. Producono ossigeno. Sono la base della catena alimentare.")
    assert await t.run(ToolCall("ELENCO", "")) == "La tua cartella è vuota."
    await t.run(ToolCall("SCRIVI", "testo|la fotosintesi"))
    await t.run(ToolCall("LISTA", "della spesa|latte"))
    elenco = await t.run(ToolCall("ELENCO", ""))
    assert elenco.startswith("Nella cartella ci sono due file.") and "Lista della spesa" in elenco and "Testo - la fotosintesi" in elenco
    letto = await t.run(ToolCall("LEGGI", "della spesa"))
    assert letto == "Nella lista della spesa c'è latte."                                  # una lista si legge come la direbbe una persona
    riassunto = await t.run(ToolCall("RIASSUMI", "sulla fotosintesi"))
    assert riassunto.startswith("«Testo - la fotosintesi»: Le piante usano la luce.")
    assert "Non trovo nessun file" in await t.run(ToolCall("LEGGI", "i miei sogni"))


async def test_research_saves_a_note_with_sources_and_only_what_was_found(tmp_path):
    t = make_tools(tmp_path, text="I polpi hanno tre cuori e otto braccia. Vivono nei mari di tutto il mondo.\n\n- Hanno tre cuori\n- Il sangue è blu\n- Sono molto intelligenti")

    async def web(arg, n=None):
        return [("Polpo - Wikipedia", "Il polpo è un mollusco cefalopode.", "https://it.wikipedia.org/wiki/Polpo"), ("Curiosità", "Ha tre cuori.", "https://esempio.it/polpi")]
    t._web_results = web
    out = await t.run(ToolCall("RICERCA", "polpi"))
    assert out.startswith("I polpi hanno tre cuori e otto braccia.") and out.endswith("Ho salvato la ricerca in «Ricerca - polpi».")
    note = (tmp_path / "Aria" / "Ricerca - polpi.md").read_text(encoding="utf-8")
    assert note.startswith("# Ricerca: polpi") and "## In breve\nI polpi hanno tre cuori" in note and "- Il sangue è blu" in note
    assert "- Polpo - Wikipedia — https://it.wikipedia.org/wiki/Polpo" in note and "- Curiosità — https://esempio.it/polpi" in note
    system, user, _ = t.gen_calls[0]
    assert "SOLO quello che è scritto" in system and "Il polpo è un mollusco cefalopode." in user       # il modello vede solo i risultati veri

    async def nothing(arg, n=None):
        return []
    t._web_results = nothing
    assert await t.run(ToolCall("RICERCA", "zzz")) == "Non ho trovato niente su zzz."
    t2 = make_tools(tmp_path, with_ws=False)
    t2._web_results = web
    assert "scegli una cartella nelle Impostazioni" in await t2.run(ToolCall("RICERCA", "polpi"))   # senza cartella risponde comunque, a voce


def test_split_summary_and_sentences():
    assert F._split_summary("Prima frase. Seconda frase.\n\n- uno\n- due") == ("Prima frase. Seconda frase.", "- uno\n- due")
    assert F._split_summary("Una. Due. Tre. Quattro.") == ("Una. Due.", "- Tre.\n- Quattro.")
    assert F._split_summary("") == ("", "")
    assert F.first_sentences("Una frase breve. Un'altra frase breve. " * 20, 60).endswith(".") and len(F.first_sentences("x " * 500, 50)) <= 50


def test_tool_names_are_spoken_verbatim_and_long_ones_flagged():
    assert F.FILE_TOOLS <= SPEAK_VERBATIM and F.LONG_TOOLS == {"SCRIVI", "SALVA", "RICERCA", "RIASSUMI"}


async def test_permission_error_is_explained(tmp_path):
    t = make_tools(tmp_path)

    async def boom(arg):
        raise PermissionError("negato")
    t._nota = boom
    assert "permessi di Aria" in await t.run(ToolCall("NOTA", "x"))


# ---------------------------------------------------------------- in conversazione
async def test_writing_a_text_by_voice_says_it_is_working_then_confirms(tmp_path):
    from tests.test_conversation import build, utterance
    a, hub, llm, tts, spk, tools = build(utterance(), ["scrivimi un testo sulla fotosintesi"])
    a.cfg["workspace"] = str(tmp_path / "Aria")
    os.makedirs(a.cfg["workspace"])
    real = Tools(a.cfg, a.memory)
    a.tools = real
    real.generate = None                                                       # prova anche il collegamento automatico al chatbot...
    a.router.llm_stream = _fake_stream("# Fotosintesi\n\nLe piante trasformano la luce in energia. " * 3)
    real.generate = a._generate_text
    await asyncio.wait_for(a.session(), 40)
    from aria.conversation import WORKING_DOC
    assert any(s in tts.said for s in WORKING_DOC)                                             # per un documento dice che lo scrive e lo rilegge
    assert any("Testo - fotosintesi" in s and "nella tua cartella" in s for s in tts.said)
    assert os.path.exists(os.path.join(a.cfg["workspace"], "Testo - fotosintesi.md"))


def _fake_stream(text):
    async def stream(messages, max_tokens=None):
        assert max_tokens and max_tokens >= 600                                 # un testo non puo' essere lungo come una frase parlata
        assert messages[0]["role"] == "system" and "Aria" not in messages[0]["content"]      # fuori dal carattere vocale di Aria
        for i in range(0, len(text), 25):
            yield text[i:i + 25]
    return stream


async def test_without_a_folder_it_does_not_say_it_is_working(tmp_path):
    from tests.test_conversation import build, utterance
    a, hub, llm, tts, spk, tools = build(utterance(), ["scrivimi un testo sulla fotosintesi"])
    a.tools = Tools(a.cfg, a.memory)
    await asyncio.wait_for(a.session(), 40)
    said = " ".join(tts.said)
    assert F.NO_WORKSPACE.replace(":", "") .split("scegline")[0].strip() in said.replace(":", "") and "scegline una nelle Impostazioni" in said
    assert not any(w in said for w in ("ci lavoro", "mi metto al lavoro", "qualche secondo"))


# ---------------------------------------------------------------- Impostazioni: scegliere la cartella
def test_settings_choose_and_clear_the_folder_without_losing_model_choices(tmp_path):
    import yaml
    from aria import models as M
    from aria import profiles as P
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"brains": [{"name": "mac", "llm": {"base_url": "http://x/v1", "model": "gemma3:4b"},
                                               "stt": {"kind": "mlx-whisper", "model": "mlx-community/whisper-large-v3-turbo-q4"}, "tts": {"kind": "say"}}]}))
    folder = tmp_path / "Aria"
    folder.mkdir()
    assert M.workspace_status(str(cfg)) == {"path": None, "valid": False, "error": None, "files": 0}
    r = M.workspace_set(str(cfg), str(folder))
    assert r["ok"] and r["path"] == os.path.realpath(folder) and r["valid"] and r["files"] == 0
    (folder / "Nota.md").write_text("ciao")
    assert M.workspace_status(str(cfg))["files"] == 1
    P.save_settings(str(cfg), {"profile": "personalizzata", "stt_model": "x/y", "llm_model": "gemma3:4b"})       # salvare i modelli...
    assert P.get_workspace(str(cfg)) == os.path.realpath(folder)                                                  # ...non fa perdere la cartella
    bad = M.workspace_set(str(cfg), "/System")
    assert not bad["ok"] and "sistema" in bad["error"] and P.get_workspace(str(cfg)) == os.path.realpath(folder)    # un rifiuto non cambia nulla
    assert not M.workspace_set(str(cfg), str(tmp_path))["ok"]                                                    # la Home (qui = tmp_path) no
    folder.rmdir() if not os.listdir(folder) else (folder / "Nota.md").unlink() or folder.rmdir()
    st = M.workspace_status(str(cfg))
    assert st["path"] and not st["valid"] and "non esiste" in st["error"]                                         # cartella sparita: lo dice
    assert M.workspace_clear(str(cfg))["path"] is None and P.load_settings(str(cfg))["profile"] == "personalizzata"


def test_workspace_is_in_the_settings_status(tmp_path, monkeypatch):
    import yaml
    from aria import models as M
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"brains": [{"name": "mac", "llm": {"kind": "mlx-lm", "model": "mlx-community/gemma-3-text-4b-it-4bit"},
                                               "stt": {"kind": "mlx-whisper", "model": "mlx-community/whisper-large-v3-turbo-q4"}, "tts": {"kind": "say"}}]}))
    monkeypatch.setattr(M, "stt_installed", lambda c: True)
    monkeypatch.setattr(M, "mlx_lm_installed", lambda r: True)
    assert M.status(str(cfg), [])["workspace"]["path"] is None


RICETTA = ("Gli gnocchi alla romana si fanno con la semola. Porta il latte a bollore con il burro e il sale. Versa la semola a pioggia mescolando. "
           "Cuoci per dieci minuti, poi stendi l'impasto su un piano. Quando è freddo ritaglia dei dischi. Disponili in teglia con burro e parmigiano e inforna.")


async def test_asked_for_a_file_aria_writes_a_separate_reviewed_document_not_the_conversation(tmp_path):
    t = make_tools(tmp_path)
    calls = []
    BOZZA = "# Gnocchi alla romana\n\n## Ingredienti\n- 500 ml di latte\n- 150 g di semola\n\n## Preparazione\n1. Porta il latte a bollore.\n2. Versa la semola a pioggia.\n\n## Consigli\nServili caldi."

    async def gen(system, user, max_tokens):
        calls.append((system, user, max_tokens))
        if system == F.TOPIC_SYSTEM:
            return "Gnocchi alla romana"
        if system == F.DOC_PRO_SYSTEM:
            return "Ecco il documento:\n\n" + BOZZA
        return BOZZA.replace("Servili caldi.", "Servili caldi, con burro fuso e parmigiano. (rivisto)")
    t.generate = gen
    import json
    arg = json.dumps({"kind": "ricetta", "request": "scrivimi tutta la ricetta in un file", "source": RICETTA,
                      "history": [{"role": "user", "content": "dimmi la ricetta degli gnocchi alla romana"}, {"role": "assistant", "content": RICETTA}]}, ensure_ascii=False)
    out = await t.run(ToolCall("SALVA", arg))
    assert out == "Fatto: ho scritto «Gnocchi alla romana» nella tua cartella, dentro trovi ingredienti, preparazione e consigli."
    saved = (tmp_path / "Aria" / "Gnocchi alla romana.md").read_text(encoding="utf-8")
    assert saved.startswith("# Gnocchi alla romana") and "## Ingredienti" in saved and "1. Porta il latte" in saved and "(rivisto)" in saved      # un documento vero, rivisto
    assert "Ecco il documento" not in saved and "Aria:" not in saved                                                                     # non la chat
    systems = [c[0] for c in calls]
    assert systems == [F.TOPIC_SYSTEM, F.DOC_PRO_SYSTEM, F.REVIEW_SYSTEM]                                                                # argomento -> bozza -> revisione
    draft_prompt = calls[1][1]
    assert "scrivimi tutta la ricetta" in draft_prompt and "semola a pioggia" in draft_prompt and "dimmi la ricetta degli gnocchi" in draft_prompt     # richiesta, quello che ha detto e la conversazione
    assert "Gnocchi" in calls[2][1] and calls[1][2] >= 900


async def test_the_document_is_checked_against_the_web_and_lists_its_sources(tmp_path):
    t = make_tools(tmp_path)
    t.cfg.setdefault("human", {})["doc_web"] = True
    t.cfg["human"]["doc_pages"] = False                                                              # niente rete nei test: qui si finge solo la ricerca
    seen = []

    async def web(topic, n=None):
        seen.append(topic)
        return [("Gnocchi alla romana - GialloZafferano", "Si fanno con la semola, non con le patate.", "https://example.org/gnocchi")]

    async def gen(system, user, max_tokens):
        if system == F.TOPIC_SYSTEM:
            return "gnocchi alla romana"
        return "# Gnocchi alla romana\n\nSi fanno con la semola di grano duro.\n\n## Preparazione\n1. Cuoci la semola nel latte."
    t._web_results, t.generate = web, gen
    t.cfg["tools"]["web_search"] = {"kind": "ddgs"}
    out = await t.run(ToolCall("SALVA", "ricetta|" + RICETTA))
    assert seen == ["gnocchi alla romana"] and out.startswith("Fatto: ho scritto")
    saved = (tmp_path / "Aria" / "Gnocchi alla romana.md").read_text(encoding="utf-8")
    assert "## Fonti" in saved and "https://example.org/gnocchi" in saved


async def test_a_broken_review_falls_back_to_the_draft_and_nothing_is_saved_without_material(tmp_path):
    t = make_tools(tmp_path)
    outs = iter(["Gnocchi alla romana", "# Gnocchi alla romana\n\n" + "Si fanno con la semola e il latte. " * 6, "ok"])

    async def gen(system, user, max_tokens):
        return next(outs)
    t.generate = gen
    await t.run(ToolCall("SALVA", "ricetta|" + RICETTA))
    assert "semola e il latte" in (tmp_path / "Aria" / "Gnocchi alla romana.md").read_text(encoding="utf-8")       # la «revisione» era un «ok»: tiene la bozza
    assert "abbastanza lungo" in await make_tools(tmp_path).run(ToolCall("SALVA", "testo|ciao"))
    assert await make_tools(tmp_path, with_ws=False).run(ToolCall("SALVA", "testo|" + RICETTA)) == F.NO_WORKSPACE


def test_asking_to_write_the_last_answer_into_a_file_is_understood():
    from aria import intent as I, style
    assert I.is_save_reply("mi lo scriveresti tutta quanta la ricetta all'interno di un file?") == "ricetta"
    assert I.is_save_reply("Sì, scrivimi tutto quanto all'interno della cartella, scrivimi tutta la ricetta.") == "ricetta"
    assert I.is_save_reply("salvamelo nella cartella") == "testo" and I.is_save_reply("copia tutto in un file") == "testo"
    for t in ("che ore sono", "ho aperto un file ieri", "metti la musica", "scrivimi una poesia sul mare", "com'è andata la riunione"):
        assert I.is_save_reply(t) is None, t
    assert style.has_false_claim("Va bene. Metto tutta la ricetta completa nella tua cartella, così puoi consultarla.")        # e' una bugia se non parte lo strumento
    assert style.has_false_claim("Ti faccio presente che è pronta per essere consultata appena avrai tempo.")
    assert not style.has_false_claim("Prima scalda la padella, poi metto il sale.")


def test_source_titles_glued_by_a_search_engine_are_cut_at_the_join():
    out = F._sources_md([("Gnocchi alla Romana Recipe - Great Italian ChefsRicetta Gnocchi alla romana - Cucchiaio d'", "", "https://x.it/a"), ("Da McDonald's alla pizza", "", "")])
    assert out.splitlines() == ["- Gnocchi alla Romana Recipe - Great Italian Chefs — https://x.it/a", "- Da McDonald's alla pizza"]


def test_a_leaked_thinking_block_never_ends_up_in_the_document():
    assert F._clean_doc("<|channel>thought\nragiono qui\n<channel|># Gnocchi\n\nTesto del documento.") == "# Gnocchi\n\nTesto del documento."
    assert F._clean_doc("<|channel>thought\nragionamento mai chiuso") == ""


async def test_writing_a_document_reports_its_stages_in_order(tmp_path):
    t = make_tools(tmp_path)
    seen = []
    t.progress = lambda label, start, until, eta: seen.append((label, start, until))

    async def gen(system, user, max_tokens, temperature=None):
        return "# Gnocchi\n\n" + RICETTA
    t.generate = gen
    await t.run(ToolCall("SCRIVI", "ricetta|gnocchi alla romana"))
    labels = [x[0] for x in seen]
    assert labels[0] == "Capisco di cosa scrivere" and labels[-1] == "Salvo il file nella cartella"
    assert "Scrivo la bozza" in labels and labels.index("Scrivo la bozza") < labels.index("Rileggo e correggo")
    starts = [x[1] for x in seen]
    assert starts == sorted(starts) and all(0 <= x[1] <= x[2] <= 1 for x in seen)         # la barra va solo in avanti


def test_a_document_request_is_understood_whatever_the_order_of_the_words():
    from aria import intent as I, style
    gnocchi = ToolCall("SCRIVI", "ricetta|gnocchi alla romana")
    for t in ("Mi scriveresti all'interno del file all'interno di una cartella, la ricetta delle degli gnocchi alla romana.",       # la frase vera, detta con la destinazione prima
              "scrivimi in un file la ricetta degli gnocchi alla romana", "nella cartella scrivimi la ricetta degli gnocchi alla romana",
              "Mi iscrivili all'interno di una cartella e un file con scritto la ricetta degli gnocchi alla romana.",                 # «scrivili» sentito male
              "mi creeresti un file con la ricetta degli gnocchi alla romana", "scrivi un file con la ricetta degli gnocchi alla romana",
              "metti la ricetta degli gnocchi alla romana in un file nella cartella", "puoi mettere in un documento la ricetta degli gnocchi alla romana?"):
        assert I.detect(t) == gnocchi, t
    for t in ("E mi diresti la ricetta di degli gnocchi alla romana e me li metteresti all'interno di una della cartella?",         # la frase vera delle 23:56 (destinazione sentita male)
              "Dimmi la ricetta degli gnocchi alla romana in un file.", "la ricetta degli gnocchi me la scriveresti in un file?"):
        assert I.detect(t) == ToolCall("SCRIVI", "ricetta|gnocchi alla romana" if "romana" in t else "ricetta|gnocchi"), t
    assert I.detect("mi racconteresti la storia di Roma e la metteresti in un documento?") == ToolCall("SCRIVI", "storia|Roma")
    assert I.detect("dimmi la ricetta della carbonara") is None and I.file_attempt("dimmi la ricetta della carbonara") is None        # senza file e' una domanda normale
    assert I.file_attempt("scrivi un file") and I.file_attempt("come si mette un file in una cartella?") is None and I.file_attempt("ho messo la ricetta nel file ieri") is None
    assert I.detect("puoi scrivere in un file la spiegazione della relatività?") == ToolCall("SCRIVI", "spiegazione|relatività")
    assert I.detect("scrivi nella cartella una lettera per mia nonna") == ToolCall("SCRIVI", "lettera|mia nonna")
    assert I.detect("scrivimi la ricetta della torta di mele e mettila nella cartella per favore") == ToolCall("SCRIVI", "ricetta|torta di mele")
    assert I.detect("fammi un documento sulla storia di Roma").name == "SCRIVI"
    # senza argomento («tutta la ricetta», «mettilo nella cartella») non e' un documento nuovo: si salva quello di cui si parla
    for t in ("scrivimi tutta la ricetta in un file", "Vai, mettilo nella cartella.", "Dai, butta il file all'interno della cartella.",
              "Sì, prendi e scrivi tutta quanta la ricetta all'interno del di un file e mettila all'interno della cartella.",
              "Fai una cosa, scrivimi tutto questo quanto in un file e mettilo nella cartella."):
        assert I.detect(t) is None and I.is_save_reply(t), t
        assert I.file_request(t)[1] is None
    for t in ("ho messo la ricetta nel file ieri", "crea un file chiamato spesa", "leggimi il file della spesa", "apri la cartella", "metti un po' di musica"):
        assert I.file_request(t) is None, t
    for lie in ("Certo. Ti scrivo subito la ricetta degli gnocchi alla romana nel tuo file.", "Ho messo tutto nella cartella, puoi controllare quando vuoi.",
                "Il file è in fase di caricamento.", "La sto scrivendo adesso."):
        assert style.has_false_claim(lie), lie
    assert not style.has_false_claim("Se vuoi posso scrivere la ricetta in un file, basta che me lo chiedi.")


async def test_a_web_page_is_read_as_plain_text_and_only_public_https_pages_are(tmp_path, monkeypatch):
    import socket
    import httpx
    real_gai = socket.getaddrinfo
    fake_dns = {"ricette.example.org": "93.184.216.34", "rinvio.example.org": "93.184.216.35", "trappola.example.org": "127.0.0.1"}     # (niente rete nei test)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (fake_dns[host], port))] if host in fake_dns else real_gai(host, port, *a, **k))
    HTML = ("<html><head><title>x</title><script>var a=1;</script></head><body><nav>Menu Home Contatti Accedi</nav>"
            "<h1>Gnocchi alla romana</h1><p>Una introduzione lunga abbastanza per essere tenuta nel testo della pagina.</p>"
            "<h2>Ingredienti</h2><ul><li>500 ml di latte intero fresco</li><li>150 g di semolino di grano duro</li></ul>"
            "<h2>Preparazione</h2><p>Porta il latte a bollore con il burro e il sale, poi versa il semolino a pioggia.</p><footer>Copyright tutti i diritti riservati</footer></body></html>")
    asked = []

    def handler(req):
        asked.append(str(req.url))
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})
    cfg = load()
    t = Tools(cfg, Memory(), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    body = await t._page_text("https://ricette.example.org/gnocchi")
    assert body.startswith("Ingredienti") and "150 g di semolino" in body and "versa il semolino a pioggia" in body
    assert "Menu Home" not in body and "var a=1" not in body and "Copyright" not in body                      # via menu, script e piè di pagina
    for bad in ("http://example.org/x", "https://127.0.0.1/x", "https://localhost/x", "https://nas.local/x", "file:///etc/passwd", "https://192.168.1.5/x"):
        assert await t._page_text(bad) == "", bad
    assert asked == ["https://ricette.example.org/gnocchi"]                                                    # le altre non sono nemmeno state richieste

    def redirecting(req):                                                                                      # un sito pubblico che rinvia al Mac stesso / a un nome che porta a 127.0.0.1
        asked.append(str(req.url))
        if req.url.host == "rinvio.example.org":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8765/" if "a" in req.url.path else "https://trappola.example.org/x"})
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
    asked.clear()
    t2 = Tools(cfg, Memory(), client=httpx.AsyncClient(transport=httpx.MockTransport(redirecting)))
    assert await t2._page_text("https://rinvio.example.org/a") == "" and await t2._page_text("https://rinvio.example.org/b") == ""
    assert asked == ["https://rinvio.example.org/a", "https://rinvio.example.org/b"]                          # il rinvio non viene seguito


# ---- dal log dell'utente (14 ottobre, 01:19): «prendi questo testo e scrivi le altre strofe e mettile in un file» faceva una RICERCA sul web su «come scrivere strofe»
# e salvava un articolo; e se il testo era nella stessa frase rispondeva «non ho ancora niente da mettere in un file»
LYRICS = ("E questo aspetterei duecento anni per poterti guardare, per tenerti le mani, e non mi accontenterò, no, io non ci casco in questa stupida buca, "
          "io guarderò un po' più in alto, voglio un sorriso grande che arrivi un po' sopra l'occhio, il cuore spostato che batta dentro il mio collo.")


def test_creative_requests_are_recognised_without_taking_the_history_of_rome_for_one():
    for kind, req in (("testo", "Prendi questo testo e scrivi le altre strofe e mettile in un file"), ("poesia", "il mare"), ("testo", "una canzone sull'amore"),
                      ("lettera", "per mia nonna"), ("testo", "un rap sul caffè"), ("testo", "scrivi il ritornello")):
        assert F.is_creative(kind, req), (kind, req)
    for kind, req in (("testo", "la storia di Roma"), ("testo", "la fotosintesi"), ("ricetta", "scrivimi la ricetta"), ("testo", "come funziona il frigorifero")):
        assert not F.is_creative(kind, req), (kind, req)


async def test_writing_more_verses_is_creative_no_web_no_article_and_the_lyrics_are_read_whole(tmp_path):
    t = make_tools(tmp_path)
    t.cfg.setdefault("human", {})["doc_web"] = True
    web = []

    async def search(topic, n=None):
        web.append(topic)
        return [("Come scrivere strofe", "x", "https://example.org")]
    t._web_results = search
    calls = []

    async def gen(system, user, max_tokens):
        calls.append((system, user))
        if system == F.TOPIC_SYSTEM:
            return "Strofe per la canzone"
        return "# Duecento anni\n\nAspetterei ancora un giorno\nper vederti tornare\n\nE poi non mi importa niente\nse devo ricominciare"
    t.generate = gen
    import json
    arg = json.dumps({"kind": "testo", "request": "Prendi questo testo e scrivi le altre strofe e mettimile all'interno di un file nella cartella", "source": "",
                      "history": [{"role": "user", "content": "Ti leggo questo testo di questa canzone."}, {"role": "user", "content": LYRICS}]}, ensure_ascii=False)
    out = await t.run(ToolCall("SALVA", arg))
    assert out.startswith("Fatto: ho scritto")
    assert web == []                                                                                    # niente ricerca: non e' un testo di fatti
    systems = [c[0] for c in calls]
    assert systems == [F.TOPIC_SYSTEM, F.DOC_CREATIVE_SYSTEM, F.REVIEW_CREATIVE_SYSTEM]               # scrive di fantasia, non da redattore
    assert "cuore spostato che batta dentro il mio collo" in calls[1][1]                               # il testo dettato arriva intero (prima era tagliato a 500 caratteri)
    saved = next((tmp_path / "Aria").glob("*.md")).read_text(encoding="utf-8")
    assert "Aspetterei ancora un giorno" in saved and "## Fonti" not in saved


async def test_a_long_request_that_carries_its_own_text_is_not_refused(tmp_path):
    from tests.test_conversation import build, utterance
    a, hub, llm, tts, spk, tools = build(utterance(), [f"Ti leggo questo testo di questa canzone: {LYRICS} Tu prendilo e scrivi le altre strofe e mettile all'interno di un file."])
    a.cfg["workspace"] = str(tmp_path / "Aria")
    os.makedirs(a.cfg["workspace"])
    real = Tools(a.cfg, a.memory)
    a.tools = real
    systems = []

    async def stream(messages, max_tokens=None, temperature=None):
        systems.append(messages[0]["content"])
        text = "# Duecento anni\n\nAspetterei ancora un giorno\nper vederti tornare\n\nE poi non mi importa niente\nse devo ricominciare" if "Duecento" not in messages[-1]["content"] else "# Duecento anni\n\nAspetterei ancora un giorno"
        for i in range(0, len(text), 25):
            yield text[i:i + 25]
    a.router.llm_stream = stream
    real.generate = a._generate_text
    await asyncio.wait_for(a.session(), 40)
    said = " ".join(tts.said)
    assert "Non ho ancora niente da mettere in un file" not in said                                     # il testo era nella frase stessa
    assert any(s == F.DOC_CREATIVE_SYSTEM for s in systems)
    assert list((tmp_path / "Aria").glob("*.md"))
