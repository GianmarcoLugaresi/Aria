"""La conversazione in INGLESE da capo a fondo: ciò che l'utente dice a voce, gli strumenti veri (con un Mac finto) e ciò che Aria risponde."""
import asyncio

import pytest

from aria import dialog
from aria.macos import Mac
from aria.textutil import ToolCall
from aria.tools import Tools
from test_human_flow import build_flow
from test_powers import Runner


@pytest.fixture(autouse=True)
def _en(english):
    pass


def flow(lines, replies=("Sure.",), calendar_out="", turns=None):
    """`lines`: le frasi dette dall'utente, una per turno."""
    a, hub, script, tts, spk = build_flow(list(lines), list(replies), turns=turns or len(lines) + 1)
    a.tools = Tools(a.cfg, a.memory)
    a.tools.generate = a._generate_text
    a.tools.mac = Mac(runner=Runner({"Calendar": (0, calendar_out, "")}), platform="darwin")                  # nessun comando raggiunge il Mac vero
    return a, hub, script, tts, spk


async def run(a):
    await asyncio.wait_for(a.session(), 40)


async def test_time_date_and_math_are_answered_in_english_without_the_chatbot():
    a, hub, script, tts, spk = flow(["what time is it", "what's the date today", "what's twelve times seven"])        # «what time is it» finisce con «it»: la frase e' completa, non si aspetta altro
    await run(a)
    said = " ".join(tts.said)
    assert "o'clock" in said or "It's " in said
    assert "Today is" in said and "That's eighty-four." in said and not script.calls


async def test_timer_lifecycle_in_english():
    a, hub, script, tts, spk = flow(["set a timer for ten minutes for the pasta", "how much time is left on the timer", "cancel the timer"])
    await run(a)
    said = " ".join(tts.said)
    assert "Timer set" in said and "ten minutes" in said and "left on the timer" in said and "cancelled the timer" in said
    assert not script.calls


async def test_a_reminder_missing_its_time_asks_for_it_and_the_answer_completes_it():
    a, hub, script, tts, spk = flow(["remind me to call Mark", "tomorrow at nine"])
    await run(a)
    assert any("When should I remind you?" in s for s in tts.said)
    assert any(s.startswith(("Done:", "All right", "Okay")) and "Call Mark" in s for s in tts.said), tts.said
    assert not script.calls


async def test_what_aria_cannot_do_is_said_plainly():
    a, hub, script, tts, spk = flow(["call my mom", "turn off the lights"])
    await run(a)
    said = " ".join(tts.said)
    assert ("phone calls" in said.lower() or "can't make phone calls" in said.lower()) and "lights" in said and not script.calls


async def test_help_in_english():
    a, hub, script, tts, spk = flow(["what can you do"])
    await run(a)
    assert any("I can tell you the weather" in s for s in tts.said) and not script.calls


async def test_small_talk_goes_to_the_chatbot_and_thanks_does_not():
    a, hub, script, tts, spk = flow(["tell me a joke", "thanks a lot"], replies=["Why did the chicken cross the road? To get to the other side."])
    await run(a)
    assert len(script.calls) == 1
    from aria import dialog_en
    assert any(s in tts.said for s in dialog_en.THANKS_REPLIES)                                       # il «grazie» non passa dal chatbot
    assert any("chicken" in s for s in tts.said)


async def test_the_chatbot_is_told_to_answer_in_english():
    a, hub, script, tts, spk = flow(["tell me about your day"], replies=["Quiet, mostly."])
    await run(a)
    system = script.calls[0][0]["content"]
    assert "English" in system and "It is now:" in system and "Sono le" not in system and "Adesso" not in system          # (la riga «Sei Aria.» e' il carattere finto del banco di prova)
    assert script.calls[0][-1]["content"] == "tell me about your day"


async def test_telling_her_the_name_is_remembered():
    a, hub, script, tts, spk = flow(["my name is Anna"])
    await run(a)
    assert a.memory.get_profile("name") == "Anna" and any("Anna" in s for s in tts.said)


async def test_goodbye_ends_the_conversation():
    a, hub, script, tts, spk = flow(["hello how are you", "thanks, goodbye"], replies=["Hi, doing well. And you?"])
    await run(a)
    assert len(script.calls) == 1 and not a.in_session                                              # il congedo non passa dal chatbot
    assert tts.said[-1] != "Hi, doing well. And you?" and len(tts.said) == 2                         # e Aria saluta, con una frase sua


async def test_a_request_not_understood_is_said_honestly():
    a, hub, script, tts, spk = flow(["cancel my reminder to call Mark"])
    await run(a)
    assert any("can't cancel or change reminders" in s or "I'm not sure I understood" in s for s in tts.said), tts.said
    assert not script.calls


# ---------------------------------------------------------------- il chatbot non puo' lanciare azioni da solo, nemmeno in inglese
def flow_with_tools(lines, replies, tool_results=("Done.",)):
    a, hub, script, tts, spk = build_flow(list(lines), list(replies), tool_results=list(tool_results), turns=len(lines) + 1)
    return a, hub, script, tts, spk


@pytest.mark.parametrize("tag", ["[[APRI_APP: Safari]]", "[[SCRIVI: poem|the sea]]", "[[PROMEMORIA: tomorrow at nine call Mark]]", "[[SCORCIATOIA: Goodnight]]", "[[VOLUME: up]]", "[[MUSICA: play]]",
                                 "[[NON_SO: call]]", "[[SCHERMO: leggi|]]", "[[LISTA: shopping|milk]]", "[[EVENTO: dinner on Friday at eight]]"])
async def test_the_chatbot_cannot_start_actions_by_itself(tag):
    a, hub, script, tts, spk = flow_with_tools(["tell me something interesting"], [f"Sure! {tag}"], tool_results=["SHOULD NOT RUN"])
    await run(a)
    assert a.tools.seen == [], tag                                                     # nessuno strumento e' partito
    fed_back = " ".join(m["content"] for m in script.calls[-1])
    assert "I only do that when you ask me yourself" in fed_back and "Questa cosa la faccio" not in fed_back      # al chatbot torna il rifiuto, in inglese


async def test_the_chatbot_can_fetch_facts_when_the_user_asked_for_them():
    a, hub, script, tts, spk = flow_with_tools(["what is the weather going to be like"], ["[[METEO: Rome tomorrow]]", "Tomorrow it'll be cloudy in Rome."], tool_results=["Tomorrow in Rome: cloudy."])
    await run(a)
    assert [c.name for c in a.tools.seen] == ["METEO"] and any("cloudy" in s for s in tts.said)


async def test_a_made_up_timer_is_refused_in_english():
    a, hub, script, tts, spk = flow_with_tools(["what should I do this morning"], ["[[TIMER: 10:00 | coffee]]"], tool_results=["SHOULD NOT RUN"])
    await run(a)
    assert a.tools.seen == [] and any("I didn't catch how long or at what time" in s for s in tts.said), tts.said


# ---------------------------------------------------------------- cambiare voce in inglese
def _with_pocket_voice(a, tmp_path, tts):
    from aria.tts import AutoTTS
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("brains: []\n")
    auto = AutoTTS({"kind": "natural", "voice": "alba", "_config_path": str(cfg_path)})
    auto.pocket = tts
    tts.voice, tts.set = "alba", []
    tts.set_voice = lambda n: (tts.set.append(n), setattr(tts, "voice", n))
    a.router._objs[("t", "tts")] = auto
    a.cfg["_config_path"] = str(cfg_path)


@pytest.mark.parametrize("lines,voices", [(["use the voice of George"], ["george"]), (["use a male voice"], ["george"]), (["use a female voice"], ["alba"]), (["talk like Paul"], ["paul"]),
                                          (["change your voice"], ["anna"]), (["change voice", "change voice"], ["anna", "azelma"])])
async def test_the_english_voice_can_be_changed_by_speaking(tmp_path, lines, voices):
    a, hub, script, tts, spk = flow(lines)
    _with_pocket_voice(a, tmp_path, tts)
    await run(a)
    assert tts.set == voices and any("Do you like it?" in s for s in tts.said) and not script.calls


async def test_the_natural_voice_is_italian_only(tmp_path):
    a, hub, script, tts, spk = flow(["turn on the natural voice"])
    _with_pocket_voice(a, tmp_path, tts)
    await run(a)
    from aria import profiles as P
    assert any("only available in Italian" in s or "in Italian for now" in s for s in tts.said)
    assert P.get_powers(a.cfg["_config_path"])["voice_natural"] is False and tts.set == []


def test_the_english_voice_lists_agree():
    """Le voci che offre il menu dell'app e quelle che Aria sa scegliere a voce sono le stesse, e hanno tutte un nome vero di Pocket TTS."""
    import os
    import re
    from aria import i18n
    swift = open(os.path.join(os.path.dirname(__file__), "..", "..", "app", "Sources", "Aria", "AppDelegate.swift"), encoding="utf-8").read() if os.path.exists(
        os.path.join(os.path.dirname(__file__), "..", "..", "app", "Sources", "Aria", "AppDelegate.swift")) else ""
    known = {"cosette", "marius", "javert", "alba", "jean", "anna", "vera", "fantine", "charles", "paul", "eponine", "azelma", "george", "mary", "jane", "michael", "eve",
             "bill_boerst", "peter_yearsley", "stuart_bell", "caro_davy", "giovanni", "lola", "juergen", "rafael", "daan", "estelle"}
    assert set(i18n.EN_VOICES) <= known and i18n.EN_DEFAULT_VOICE in i18n.EN_VOICES
    if swift:
        menu = set(re.findall(r'"(\w+)"', " ".join(re.findall(r'(?:female|male)VoicesEn = \[([^\]]*)\]', swift))))
        assert menu == set(i18n.EN_VOICES), menu ^ set(i18n.EN_VOICES)


def test_the_english_voice_is_saved_apart_and_the_default_is_shown(tmp_path):
    from aria import i18n
    from aria.main import _restore_voice
    from aria.state import Hub
    cfg = i18n.adapt_config({"data_dir": str(tmp_path), "brains": [{"name": "x", "tts": {"kind": "pocket", "language": "italian", "voice": "lola"}}]}, "en")      # come config.app.yaml
    hub = Hub()
    _restore_voice(cfg, hub)
    assert hub.info["voice"] == "alba"                                                                # nessuna scelta: la voce di fabbrica dell'inglese
    hub.dispatch_command({"cmd": "voice", "name": "george"})
    assert (tmp_path / "voce.en.txt").read_text() == "george" and not (tmp_path / "voce.txt").exists()      # quella italiana non si tocca
    cfg2 = i18n.adapt_config({"data_dir": str(tmp_path), "brains": [{"name": "x", "tts": {"kind": "pocket", "language": "italian", "voice": "lola"}}]}, "en")
    hub2 = Hub()
    _restore_voice(cfg2, hub2)
    assert hub2.info["voice"] == "george" and cfg2["brains"][0]["tts"]["voice"] == "george"


async def test_the_thing_just_created_can_be_converted_or_corrected_by_voice():
    a, hub, script, tts, spk = flow(["add a meeting tomorrow at three called dentist to my calendar", "make it a reminder instead"])
    await run(a)
    assert any("on your calendar" in x for x in tts.said) and any(x.startswith("Done: I'll remind you about") and "Dentist" in x for x in tts.said), tts.said
    assert any("stays in the calendar" in x for x in tts.said) and not script.calls                          # (e dice che l'evento di prima resta)
    a, hub, script, tts, spk = flow(["remind me tomorrow at nine to buy coffee", "change coffee to tea"])
    await run(a)
    assert any("Buy coffee" in x for x in tts.said) and any("Buy tea" in x for x in tts.said) and not script.calls, tts.said
