"""Gli strumenti sui file di Aria, in INGLESE: riconoscimento delle frasi, scrittura nella cartella, liste, note, ricerche."""
import os

import pytest

from aria import filetools as F
from aria.intent import detect
from aria.textutil import ToolCall
from test_filetools import make_tools


@pytest.fixture(autouse=True)
def _en(english, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))


def test_phrases_are_recognised_keeping_what_the_user_said():
    d = detect
    assert d("Write me a text about photosynthesis.") == ToolCall("SCRIVI", "text|photosynthesis")
    assert d("Can you write me a poem for my mother?") == ToolCall("SCRIVI", "poem|my mother")
    assert d("Write an article about the history of Rome and put it in the folder") == ToolCall("SCRIVI", "article|the history of Rome")
    assert d("Prepare an outline about coffee, please") == ToolCall("SCRIVI", "outline|coffee")
    assert d("do a quick research on octopuses") == ToolCall("RICERCA", "octopuses")
    assert d("Do some research on how an electric motor works and save it") == ToolCall("RICERCA", "how an electric motor works")
    assert d("Add milk, bread and eggs to the shopping list") == ToolCall("LISTA", "shopping|milk, bread and eggs")
    assert d("Make a note: tomorrow I have to call Mark Smith.") == ToolCall("NOTA", "tomorrow I have to call Mark Smith")
    assert d("What files are in the folder?") == ToolCall("ELENCO", "")
    assert d("Open the folder") == ToolCall("APRI", "")


def test_everyday_requests_are_not_hijacked():
    assert detect("write to Mark that I'll be late") is None or detect("write to Mark that I'll be late").name != "SCRIVI"
    assert detect("how are you?") is None and detect("write loudly") is None
    assert detect("set an alarm") == ToolCall("TIMER", "")
    assert detect("what's the weather tomorrow").name == "METEO"


async def test_write_a_text_into_the_folder(tmp_path):
    t = make_tools(tmp_path, text="# Photosynthesis\n\nPlants turn light into energy. " * 4)
    out = await t.run(ToolCall("SCRIVI", "text|photosynthesis"))
    assert out == "Done: I wrote \"Text - photosynthesis\" and put it in your folder."
    saved = (tmp_path / "Aria" / "Text - photosynthesis.md").read_text(encoding="utf-8")
    assert saved.startswith("# Photosynthesis") and "light into energy" in saved
    system, user, max_tokens = t.gen_calls[0]
    assert system == F.TOPIC_SYSTEM_EN or system == F.DOC_PRO_SYSTEM_EN
    assert "text" in user and "photosynthesis" in user and "Write a text about" in user and max_tokens >= 600
    systems = [c[0] for c in t.gen_calls]
    assert systems == [F.DOC_PRO_SYSTEM_EN, F.REVIEW_SYSTEM_EN]
    again = await t.run(ToolCall("SCRIVI", "text|photosynthesis"))
    assert (tmp_path / "Aria" / "Text - photosynthesis (2).md").exists() and "(2)" in again


async def test_chatty_model_output_is_cleaned_and_titled(tmp_path):
    t = make_tools(tmp_path, text="Sure, here is the text you asked for:\n\n```markdown\nBees pollinate flowers and make honey all summer long.\n```")
    await t.run(ToolCall("SCRIVI", "text|bees"))
    saved = (tmp_path / "Aria" / "Text - bees.md").read_text(encoding="utf-8")
    assert saved.startswith("# Text: bees\n\nBees pollinate") and "Sure" not in saved and "```" not in saved
    t2 = make_tools(tmp_path, text="too short")
    assert "try again" in await t2.run(ToolCall("SCRIVI", "text|nothing"))


async def test_without_a_folder_nothing_is_written(tmp_path):
    t = make_tools(tmp_path, with_ws=False)
    for name, arg in (("SCRIVI", "text|x"), ("LISTA", "shopping|milk"), ("NOTA", "hello"), ("ELENCO", ""), ("LEGGI", "x"), ("RIASSUMI", "x"), ("APRI", "")):
        assert await t.run(ToolCall(name, arg)) == F.NO_WORKSPACE_EN, name
    assert t.gen_calls == []


async def test_lists_and_notes_append(tmp_path):
    t = make_tools(tmp_path)
    assert await t.run(ToolCall("LISTA", "shopping|milk")) == "Added \"milk\" to the shopping list."
    await t.run(ToolCall("LISTA", "shopping|bread and eggs"))
    assert (tmp_path / "Aria" / "Shopping list.md").read_text(encoding="utf-8") == "# Shopping list\n\n- [ ] milk\n- [ ] bread\n- [ ] eggs\n"
    assert await t.run(ToolCall("LISTA", "todo|call the bank")) == "Added \"call the bank\" to the to-do list."
    assert (tmp_path / "Aria" / "To-do list.md").exists()
    assert await t.run(ToolCall("NOTA", "call Mark tomorrow")) == "Note saved."
    note = (tmp_path / "Aria" / "Notes.md").read_text(encoding="utf-8")
    assert note.startswith("# Notes\n\n- 20") and note.endswith("— call Mark tomorrow\n")
    assert await t.run(ToolCall("LISTA", "shopping|")) == f"{F.ASK}|LISTA|shopping|What should I add to the list?"
    assert await t.run(ToolCall("NOTA", "")) == f"{F.ASK}|NOTA||What should I write in the note?"


async def test_list_read_and_summarise(tmp_path):
    t = make_tools(tmp_path, text="Plants use light. They produce oxygen. They are the base of the food chain.")
    assert await t.run(ToolCall("ELENCO", "")) == "Your folder is empty."
    await t.run(ToolCall("SCRIVI", "text|photosynthesis"))
    await t.run(ToolCall("LISTA", "shopping|milk"))
    elenco = await t.run(ToolCall("ELENCO", ""))
    assert elenco.startswith("There are two files in the folder.") and "Shopping list" in elenco and "Text - photosynthesis" in elenco
    assert await t.run(ToolCall("LEGGI", "shopping list")) == "On the shopping list there's milk."
    await t.run(ToolCall("LISTA", "shopping|eggs"))
    assert await t.run(ToolCall("LEGGI", "shopping")) == "There are two things on the shopping list: milk and eggs."
    riassunto = await t.run(ToolCall("RIASSUMI", "photosynthesis"))
    assert riassunto.startswith("\"Text - photosynthesis\": Plants use light.")
    assert "can't find any file" in await t.run(ToolCall("LEGGI", "my dreams"))


async def test_research_saves_a_note_with_sources_and_only_what_was_found(tmp_path):
    t = make_tools(tmp_path, text="Octopuses have three hearts and eight arms. They live in oceans around the world.\n\n- They have three hearts\n- Their blood is blue\n- They are very intelligent")

    async def web(arg, n=None):
        return [("Octopus - Wikipedia", "The octopus is a cephalopod mollusc.", "https://en.wikipedia.org/wiki/Octopus"), ("Fun facts", "It has three hearts.", "https://example.org/octopuses")]
    t._web_results = web
    out = await t.run(ToolCall("RICERCA", "octopuses"))
    assert out.startswith("Octopuses have three hearts and eight arms.") and out.endswith("I saved the research in \"Research - octopuses\".")
    note = (tmp_path / "Aria" / "Research - octopuses.md").read_text(encoding="utf-8")
    assert note.startswith("# Research: octopuses") and "## In brief\nOctopuses have three hearts" in note and "- Their blood is blue" in note and "## Sources" in note
    system, user, _ = t.gen_calls[0]
    assert system == F.RESEARCH_SYSTEM_EN and "The octopus is a cephalopod mollusc." in user and user.startswith("Topic: octopuses")

    async def nothing(arg, n=None):
        return []
    t._web_results = nothing
    assert await t.run(ToolCall("RICERCA", "zzz")) == "I didn't find anything about zzz."
    t2 = make_tools(tmp_path, with_ws=False)
    t2._web_results = web
    assert "pick a folder in Settings" in await t2.run(ToolCall("RICERCA", "octopuses"))


def test_creative_texts_are_not_researched_on_the_web():
    for kind, req in (("song", "a song about the sea"), ("poem", "a poem for my mother"), ("letter", "a letter to my landlord"), ("story", "a story about a dragon"), ("speech", "a wedding speech")):
        assert F.is_creative(kind, req), (kind, req)
    for kind, req in (("text", "photosynthesis"), ("recipe", "carbonara"), ("article", "the history of Rome"), ("story", "the story of Rome")):
        assert not F.is_creative(kind, req), (kind, req)


def test_split_items_in_english():
    assert F.split_items("milk and eggs") == ["milk", "eggs"]
    assert F.split_items("the bread") == ["bread"]
    assert F.split_items("milk, eggs, and a lemon") == ["milk", "eggs", "lemon"]
    assert F.split_items("baked pasta with the aubergines") == ["baked pasta with the aubergines"]
    assert F._list_title_en("groceries") == "Shopping list" and F._list_title_en("packing") == "Packing list" and F._list_title_en("to do") == "To-do list"
