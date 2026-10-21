"""I poteri di Aria sul Mac, in INGLESE: stessi strumenti di test_powers.py, con l'esecutore finto (nessun test tocca il Mac vero)."""
import httpx
import pytest

from aria import powers as PW
from aria.macos import Mac, MacError, search_url, site_url
from aria.textutil import ToolCall
from test_powers import args_of, make, script_of


@pytest.fixture(autouse=True)
def _en(english, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))


async def test_reminder_with_and_without_a_date(tmp_path):
    t, r = make(tmp_path)
    out = await t.run(ToolCall("PROMEMORIA", "call Mark tomorrow at nine"))
    assert out == "Done: I'll remind you about \"Call Mark\" tomorrow at nine a m.", out
    assert args_of(r.calls[-1]) == ["Call Mark", "2026", "10", "7", "9", "0"]
    assert await t.run(ToolCall("PROMEMORIA", "buy bread")) == "@CHIEDI|PROMEMORIA|buy bread|When should I remind you?"
    out = await t.run(ToolCall("PROMEMORIA", "!buy bread"))
    assert "Buy bread" in out and args_of(r.calls[-1]) == ["Buy bread"]
    assert await t.run(ToolCall("PROMEMORIA", "tomorrow at 9")) == "@CHIEDI|PROMEMORIA|tomorrow at 9|What should I remind you about?"


async def test_reminder_titles_lose_their_lead_in(tmp_path):
    t, r = make(tmp_path)
    await t.run(ToolCall("PROMEMORIA", "to take out the trash tomorrow at 8 pm"))
    assert args_of(r.calls[-1])[0] == "Take out the trash" and args_of(r.calls[-1])[4:] == ["20", "0"]


async def test_reminders_list(tmp_path):
    t, r = make(tmp_path, {"Reminders": (0, "Buy bread\nCall Mark\n", "")})
    assert await t.run(ToolCall("PROMEMORIA_LISTA", "")) == "You have two reminders: Buy bread, Call Mark."
    t2, _ = make(tmp_path, {"Reminders": (0, "", "")})
    assert await t2.run(ToolCall("PROMEMORIA_LISTA", "")) == "You have no reminders to do."


async def test_calendar_event_and_agenda(tmp_path):
    t, r = make(tmp_path, {"Calendar": (0, "Personal", "")})
    out = await t.run(ToolCall("EVENTO", "dinner with Marco on Friday at eight pm"))
    assert "\"Dinner with Marco\"" in out and "in the Personal calendar" in out and "Friday" in out, out
    a = args_of(r.calls[-1])
    assert a[:8] == ["Dinner with Marco", "0", "2026", "10", "9", "20", "0", "60"]
    await t.run(ToolCall("EVENTO", "dentist tomorrow"))
    assert args_of(r.calls[-1])[1] == "1"
    assert "When should I put it" in await t.run(ToolCall("EVENTO", "dinner with Marco"))
    t2, _ = make(tmp_path, {"Calendar": (0, "NOCAL", "")})
    assert "can't find a calendar" in await t2.run(ToolCall("EVENTO", "dinner tomorrow at 8 pm"))
    t3, r3 = make(tmp_path, {"Calendar": (0, "Dentist|false|15|0\nMeeting|false|9|30\nAnna's birthday|true|0|0\n", "")})
    out = await t3.run(ToolCall("AGENDA", "tomorrow"))
    assert out == "Tomorrow, you have three events: all day \"Anna's birthday\", at nine thirty a m \"Meeting\", at three p m \"Dentist\".", out
    assert args_of(r3.calls[-1]) == ["2026", "10", "7"]
    t4, _ = make(tmp_path, {"Calendar": (0, "", "")})
    assert await t4.run(ToolCall("AGENDA", "today")) == "Today, you have nothing on your calendar."


async def test_week_and_weekend_agenda(tmp_path):
    t, _ = make(tmp_path, {"Calendar": (0, "", "")})
    assert await t.run(ToolCall("AGENDA", "weekend")) == "This weekend, you have nothing on your calendar."
    assert await t.run(ToolCall("AGENDA", "settimana")) == "Over the next few days, you have nothing on your calendar."


async def test_music_controls(tmp_path):
    t, r = make(tmp_path)
    r.replies = {'application "Spotify" is running': (0, "false", ""), 'application "Music" is running': (0, "true", ""), "tell application \"Music\"": (0, "ok", "")}
    assert await t.run(ToolCall("MUSICA", "play")) in ("Here's the music.", "Music coming up.", "Here it comes.") and args_of(r.calls[-1]) == ["play"]
    assert await t.run(ToolCall("MUSICA", "pause")) in ("Paused.", "Done, silence.", "Okay, pausing.")
    r.replies["tell application \"Music\""] = (0, "Bohemian Rhapsody|Queen", "")
    assert await t.run(ToolCall("MUSICA", "now")) == "It's \"Bohemian Rhapsody\" by Queen."
    out = await t.run(ToolCall("MUSICA", "track:Queen"))
    assert "Bohemian Rhapsody" in out and "by Queen" in out and args_of(r.calls[-1]) == ["track", "Queen"]
    r.replies["tell application \"Music\""] = (0, "NONE", "")
    out = await t.run(ToolCall("MUSICA", "track:Boh"))
    assert "Boh" in out and "Apple Music" in out and r.calls[-1][:2] == ["open", "music://music.apple.com/us/search?term=Boh"]
    r.replies["tell application \"Music\""] = (0, "STOP", "")
    assert await t.run(ToolCall("MUSICA", "now")) == "Nothing is playing right now."


async def test_volume(tmp_path):
    vol = {"v": 40}

    def fake(argv):
        s = script_of(argv)
        if "output volume of" in s:
            return 0, str(vol["v"]), ""
        if "set volume output volume" in s:
            vol["v"] = int(args_of(argv)[0])
        return 0, "", ""
    t, r = make(tmp_path, {"volume": fake})
    assert await t.run(ToolCall("VOLUME", "up")) in ("Volume at fifty-two percent.", "There, fifty-two percent.", "Done: fifty-two percent.")
    assert await t.run(ToolCall("VOLUME", "set:30")) in ("Volume at thirty percent.", "There, thirty percent.", "Done: thirty percent.") and vol["v"] == 30
    assert await t.run(ToolCall("VOLUME", "get")) == "The volume is at thirty percent."
    assert await t.run(ToolCall("VOLUME", "set:x")) == "What volume should I set it to?"
    assert await t.run(ToolCall("VOLUME", "mute")) in ("Sound off.", "Done, silence.", "Muted.")
    assert await t.run(ToolCall("VOLUME", "unmute")) in ("Sound back on.", "There, the sound is back.", "Unmuted.")


async def test_open_apps_and_sites(tmp_path):
    t, r = make(tmp_path)
    assert await t.run(ToolCall("APRI_APP", "Safari")) in ("I opened Safari.", "Here's Safari.", "Opening Safari.") and r.calls[-1] == ["open", "-a", "Safari"]
    assert await t.run(ToolCall("APRI_APP", "calendar")) in ("I opened Calendar.", "Here's Calendar.", "Opening Calendar.")
    assert await t.run(ToolCall("APRI_APP", "the mail app")) in ("I opened Mail.", "Here's Mail.", "Opening Mail.")
    assert await t.run(ToolCall("APRI_APP", "YouTube")) == "I opened the YouTube website." and r.calls[-1] == ["open", "https://www.youtube.com"]
    assert await t.run(ToolCall("APRI_APP", "sito:Wikipedia")) == "I opened the Wikipedia website." and r.calls[-1] == ["open", "https://en.wikipedia.org"]
    assert "can't find an app or website called \"Photoshop\"" in await t.run(ToolCall("APRI_APP", "Photoshop"))
    assert await t.run(ToolCall("APRI_APP", "your heart")) == PW.PASS
    assert await t.run(ToolCall("APRI_APP", "~Photoshop")) == PW.PASS
    out = await t.run(ToolCall("WEB", "youtube|cat videos"))
    assert "cat videos" in out and r.calls[-1][1].endswith("search_query=cat%20videos")
    out = await t.run(ToolCall("MAPPA", "Central Station, Milan"))
    assert "Central Station, Milan" in out and "maps.apple.com/?q=Central%20Station%2C%20Milan" in r.calls[-1][1]
    assert await t.run(ToolCall("WEB", "unknownengine|x")) == "I can't search there."


def test_english_site_names_and_search_urls():
    assert site_url("the YouTube website") == "https://www.youtube.com" and site_url("repubblica dot it") == "https://repubblica.it"
    assert site_url("Wikipedia") == "https://en.wikipedia.org" and site_url("amazon") == "https://www.amazon.com"
    assert search_url("wikipedia", "Eiffel Tower") == "https://en.wikipedia.org/w/index.php?search=Eiffel%20Tower"
    assert search_url("amazon", "usb cable") == "https://www.amazon.com/s?k=usb%20cable"


def test_mac_errors_are_explained_in_english():
    from test_powers import Runner
    for err, expect in (("execution error: Not authorized to send Apple events to Calendar. (-1743)", "Automation"),
                        ("Application isn't running. (-600)", "isn't open"), ("boh (-1728)", "couldn't find")):
        with pytest.raises(MacError, match=expect):
            Mac(runner=Runner(default=(1, "", err)), platform="darwin").osa("return 1", app="Calendar")
    with pytest.raises(MacError, match="only works on the Mac"):
        Mac(runner=Runner(), platform="linux").osa("return 1")
    for italian, english in (("Promemoria", "Reminders"), ("Calendario", "Calendar"), ("Musica", "Music")):        # i poteri passano il nome italiano dell'app: in inglese si dice quello inglese
        for err in ("Not authorized to send Apple events. (-1743)", "Application isn't running. (-600)"):
            with pytest.raises(MacError) as e:
                Mac(runner=Runner(default=(1, "", err)), platform="darwin").osa("return 1", app=italian)
            assert english in str(e.value) and italian not in str(e.value), str(e.value)


async def test_things_i_cannot_do_are_said_plainly_in_english(tmp_path):
    t, _ = make(tmp_path)
    for kind in ("call", "message", "home", "buy", "inbox", "print", "download", "system", "media", "share", "files", "app", "money", "stopwatch", "bookmark", "speed", "listremove"):
        out = await t.run(ToolCall("NON_SO", kind))
        assert out and not any(w in out.lower() for w in (" non ", " che ", " sono ", " per ")), (kind, out)
    assert await t.run(ToolCall("NON_SO", "xyz")) == "I can't do that one."


async def test_shortcuts_ask_for_confirmation_first(tmp_path):
    t, r = make(tmp_path, {"shortcuts": lambda a: (0, "Goodnight\nLiving room lights\n", "") if a[1] == "list" else (0, "Done!", "")})
    assert await t.run(ToolCall("SCORCIATOIE", "")) == "You have two shortcuts: Goodnight, Living room lights."
    out = await t.run(ToolCall("SCORCIATOIA", "goodnight"))
    assert out == f"{PW.CONFIRM}|SCORCIATOIA_OK|Goodnight|Do you want me to run the shortcut \"Goodnight\"?"
    assert await t.run(ToolCall("SCORCIATOIA_OK", "Goodnight")) == "Done: I ran \"Goodnight\". Done!"
    assert "can't find a shortcut called \"pippo\"" in await t.run(ToolCall("SCORCIATOIA", "pippo"))


async def test_questions_about_a_document_are_asked_in_english(tmp_path):
    t, r = make(tmp_path, text="The warranty lasts twenty-four months from the purchase date.")
    (tmp_path / "Aria" / "Sales contract.txt").write_text("\n".join(["General preamble of the contract."] * 40 + ["Art. 7 Warranty: the warranty lasts 24 months from delivery."] + ["Other clauses."] * 40))
    out = await t.run(ToolCall("DOCUMENTO", "contract|how long is the warranty"))
    assert out == "\"Sales contract\": The warranty lasts twenty-four months from the purchase date." or out.endswith("from the purchase date."), out
    system, user, _ = t.gen_calls[0]
    assert system.startswith("Answer the question in English") and "Question: how long is the warranty" in user and "warranty lasts 24 months" in user
    assert "can't find any file that looks like \"manual\"" in await t.run(ToolCall("DOCUMENTO", "manual|boh"))


async def test_morning_briefing_in_english(tmp_path):
    rss = '<?xml version="1.0"?><rss><channel><item><title>First headline</title></item><item><title>Second headline</title></item><item><title>Third</title></item><item><title>Fourth</title></item></channel></rss>'
    t, r = make(tmp_path, {"Calendar": (0, "Meeting|false|10|0\n", ""), "Reminders": (0, "Buy bread\n", "")})
    t.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=rss.encode())))
    t.memory.set_profile("name", "Mario")
    asked = []

    async def weather(arg):
        asked.append(arg)
        return "Today in Rome: clear, between 8 and 19 degrees."
    t._weather = weather
    out = await t.run(ToolCall("BRIEFING", ""))
    assert out.startswith("Good afternoon, Mario! Today is Tuesday")
    assert asked == ["today"] and "Today in Rome: clear" in out
    assert "On your calendar: at ten a m \"Meeting\"." in out and "Among your reminders: Buy bread." in out
    assert "From the news: First headline; Second headline; Third." in out and "Fourth" not in out


async def test_switched_off_powers_say_so_in_english(tmp_path):
    t, _ = make(tmp_path, powers={"music": False})
    assert await t.run(ToolCall("MUSICA", "play")) == PW.POWER_OFF_EN
