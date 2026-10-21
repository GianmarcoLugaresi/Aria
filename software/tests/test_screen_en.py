"""Guardare lo schermo, in INGLESE: le frasi, la ricerca di una scritta, i due modi di leggere e le risposte."""
import os

import pytest

from aria import intent, screen as S
from aria.textutil import ToolCall
from test_screen import FakeAX, FakeOCR, L, make


@pytest.fixture(autouse=True)
def _en(english):
    pass


SCREEN_EN = [L("File", 0.03, 0.02), L("Edit", 0.07, 0.02), L("Share", 0.86, 0.06), L("Export", 0.93, 0.06), L("Export as PDF", 0.5, 0.4),
             L("Revenue for the quarter rose by twelve percent.", 0.4, 0.5), L("Listening", 0.5, 0.9), L("Save As", 0.2, 0.8)]


def test_screen_requests_need_an_explicit_reference_to_the_screen():
    assert intent.detect("I can't find the Export button") == ToolCall("SCHERMO", "dove|Export")
    assert intent.detect("Where is the button to save as") == ToolCall("SCHERMO", "dove|save as")
    assert intent.detect("where do I click to export") == ToolCall("SCHERMO", "dove|export")
    assert intent.detect("I can't find the settings icon on the screen") == ToolCall("SCHERMO", "dove|settings")
    for t in ("what do you see on the screen", "can you see my screen", "look at the screen"):
        assert intent.detect(t) == ToolCall("SCHERMO", "leggi|"), t
    for t in ("where is Rome?", "what do you think of my cousin?", "I can't find my keys", "where is the bathroom", "turn off the screen", "the phone screen is broken"):
        c = intent.detect(t)
        assert not (c and c.name == "SCHERMO"), t
    on = lambda t: intent.detect(t, None, screen_on=True)
    assert on("where does it say Export?") == ToolCall("SCHERMO", "dove|Export")


def test_where_is_said_in_words_and_the_best_match_is_the_short_label():
    assert S.where(0.9, 0.05) == "at the top right" and S.where(0.5, 0.5) == "in the middle of the screen" and S.where(0.1, 0.9) == "at the bottom left"
    found = S.locate(SCREEN_EN, "Export")
    assert found[0][1].t == "Export" and found[1][1].t == "Export as PDF"
    assert S.locate(SCREEN_EN, "the Save As button")[0][1].t == "Save As"
    assert S.locate(SCREEN_EN, "Print") == []
    said = S.describe_matches(S.locate(SCREEN_EN, "Export"), SCREEN_EN, "Export")
    assert said.startswith("I see \"Export\" at the top right") and "next to \"Share\"" in said and "Export as PDF" in said


async def test_with_both_switches_off_the_screen_is_not_looked_at(tmp_path, monkeypatch):
    t, img = make(tmp_path, monkeypatch, {})
    assert await t.run(ToolCall("SCHERMO", "leggi|")) == S.SCREEN_OFF_EN and img.exists()


async def test_the_mac_ocr_finds_a_label_and_says_where_it_is(tmp_path, monkeypatch):
    t, img = make(tmp_path, monkeypatch, {"screen_mac": True}, ocr=FakeOCR(SCREEN_EN))
    out = await t.run(ToolCall("SCHERMO", "dove|Export"))
    assert out.startswith("I see \"Export\" at the top right") and not img.exists()
    assert "I don't see any text \"Print\" on the screen" in await t.run(ToolCall("SCHERMO", "dove|Print"))
    t2, _ = make(tmp_path, monkeypatch, {"screen_mac": True}, ocr=FakeOCR([L("Listening", 0.5, 0.9), L("Ready", 0.5, 0.95)]))
    out = await t2.run(ToolCall("SCHERMO", "leggi|"))
    assert out.startswith("I don't see any text on the screen.") and "Screen Recording" in out


async def test_the_mac_ocr_text_is_summarized_by_the_chatbot_without_aria_own_window(tmp_path, monkeypatch):
    seen = {}

    async def gen(system, user, max_tokens, temperature=None):
        seen["system"], seen["user"] = system, user
        return "It's about revenue, up twelve percent."
    t, _ = make(tmp_path, monkeypatch, {"screen_mac": True}, ocr=FakeOCR(SCREEN_EN), generate=gen)
    assert "revenue" in await t.run(ToolCall("SCHERMO", "leggi|"))
    assert seen["system"] == S.SCREEN_SYSTEM_EN
    assert "Revenue for the quarter" in seen["user"] and "Listening" not in seen["user"] and "Summarise" in seen["user"] and seen["user"].startswith("User request:")
    await t.run(ToolCall("SCHERMO", "parere|read this out loud"))
    assert seen["system"] == S.SCREEN_READ_SYSTEM_EN                                                  # «read» = leggere ad alta voce
    await t.run(ToolCall("SCHERMO", "parere|summarize what I'm reading"))
    assert seen["system"] == S.SCREEN_SYSTEM_EN


async def test_the_model_that_sees_answers_about_the_picture_and_needs_to_be_installed(tmp_path, monkeypatch):
    calls = []

    async def fake_vision(image, prompt, model, cfg, max_tokens=260):
        calls.append((os.path.exists(image), prompt, model))
        return "**At the top** right there is a button with a cog."
    monkeypatch.setattr(S, "run_vision", fake_vision)
    monkeypatch.setattr(S, "_vision_ready", lambda m: True)
    t, img = make(tmp_path, monkeypatch, {"screen_model": True})
    out = await t.run(ToolCall("SCHERMO", "parere|what is in the corner?"))
    assert out == "At the top right there is a button with a cog." and calls[0][1].startswith(S.VISION_PROMPT_EN) and calls[0][1].endswith("what is in the corner?")
    monkeypatch.setattr(S, "_vision_ready", lambda m: False)
    assert "isn't on this Mac yet" in await t.run(ToolCall("SCHERMO", "leggi|"))


def test_ax_description_in_english():
    m = L("Share", 0.9, 0.05)
    m.role = "AXButton"
    assert S.describe_ax([(1.0, m)]) == "I see the button \"Share\" at the top right."
