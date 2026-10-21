"""Le richieste dette a voce in INGLESE diventano lo strumento giusto (e le chiacchiere normali non ne fanno partire nessuno). Gemello di test_intent_corpus*.py.
Ogni riga: (frase, strumento atteso o None, argomento atteso o None se non conta)."""
import pytest

from aria import intent
from aria.textutil import ToolCall

FILES = ["shopping list.txt", "notes.txt", "lease agreement.pdf"]

CORPUS = [
 ("what's the weather in Rome tomorrow", "METEO", "Rome tomorrow"),
 ("Hey Aria, could you tell me the weather in Florence?", "METEO", "Florence today"),
 ("will it rain tomorrow", "METEO", "tomorrow"),
 ("do I need an umbrella today", "METEO", "today"),
 ("how's the weather in New York this weekend", "METEO", None),
 ("set a timer for ten minutes", "TIMER", "ten minutes"),
 ("Can you please set a timer for 5 minutes for the pasta", "TIMER", None),
 ("start a 20 minute timer", "TIMER", None),
 ("wake me up in half an hour", "TIMER", None),
 ("how much time is left on the timer", "TIMER_STATO", None),
 ("cancel the timer", "TIMER_ANNULLA", ""),
 ("cancel all timers", "TIMER_ANNULLA", "all"),
 ("what time is it", "ORA", "ora"),
 ("what time is it in Tokyo", "ORA", None),
 ("what day is it today", "ORA", "data"),
 ("what's the date", "ORA", "data"),
 ("when does the sun set", "METEO", None),
 ("remind me to call Mark tomorrow at nine", "PROMEMORIA", "call Mark tomorrow at nine"),
 ("remind me in ten minutes to take the pizza out", "TIMER", None),
 ("what reminders do I have", "PROMEMORIA_LISTA", ""),
 ("add dinner with Marco to my calendar on Friday at eight", "EVENTO", None),
 ("schedule a meeting with Anna tomorrow at 3 pm", "EVENTO", None),
 ("what's on my calendar today", "AGENDA", "today"),
 ("what do I have this weekend", "AGENDA", "weekend"),
 ("what is twelve times seven", "CALCOLA", "12*7"),
 ("what's 120 divided by 8", "CALCOLA", "120/8"),
 ("what is 20 percent of 350", "CALCOLA", "350*20/100"),
 ("what's the square root of 81", "CALCOLA", "sqrt(81)"),
 ("calculate 15 plus 27", "CALCOLA", "15+27"),
 ("turn the volume up", "VOLUME", "up"),
 ("set the volume to 30", "VOLUME", "set:30"),
 ("volume down", "VOLUME", "down"),
 ("mute", "VOLUME", "mute"),
 ("a bit louder please", "VOLUME", "up"),
 ("play some music", "MUSICA", "play"),
 ("play Bohemian Rhapsody", "MUSICA", "track:Bohemian Rhapsody"),
 ("play some jazz", "MUSICA", None),
 ("pause the music", "MUSICA", "pause"),
 ("next song", "MUSICA", "next"),
 ("what song is this", "MUSICA", "now"),
 ("play Thriller on Spotify", "MUSICA", "track:Thriller|Spotify"),
 ("open Safari", "APRI_APP", "Safari"),
 ("launch Spotify", "APRI_APP", "Spotify"),
 ("search YouTube for cat videos", "WEB", "youtube|cat videos"),
 ("show me Trieste on the map", "MAPPA", "Trieste"),
 ("directions to Central Station", "MAPPA", "Central Station"),
 ("how much battery do I have", "SISTEMA", "batteria"),
 ("how much free space do I have", "SISTEMA", "spazio"),
 ("am I connected to the internet", "SISTEMA", "wifi"),
 ("who was Napoleon", "WIKI", "Napoleon"),
 ("what is photosynthesis", "WIKI", "photosynthesis"),
 ("who won the Champions League", "CERCA", None),
 ("remember that my wife's name is Sara", "RICORDA", "my wife's name is Sara"),
 ("what do you know about me", "MEMORIA", ""),
 ("forget my favorite color", "DIMENTICA", None),
 ("add milk to the shopping list", "LISTA", "shopping|milk"),
 ("add eggs and bread to my grocery list", "LISTA", None),
 ("make a note: call the accountant", "NOTA", "call the accountant"),
 ("read me the shopping list", "LEGGI", "shopping list"),
 ("what files do I have", "ELENCO", ""),
 ("write me a poem about the sea", "SCRIVI", "poem|the sea"),
 ("do some research on the Roman empire", "RICERCA", "the Roman empire"),
 ("what does the lease agreement say about the deposit", "DOCUMENTO", None),
 ("translate good morning into Italian", "TRADUCI", None),
 ("convert 10 miles to kilometers", "CONVERTI", None),
 ("roll a die", "CASO", None),
 ("how many days until Christmas", "DATA", None),
 ("what can you do", "AIUTO", ""),
 ("call Mom", "NON_SO", "call"),
 ("turn off the lights", "NON_SO", "home"),
 ("send a message to Luca", "NON_SO", "message"),
 ("read my emails", "NON_SO", "inbox"),
 ("start a stopwatch", "NON_SO", "stopwatch"),
 ("run the Morning shortcut", "SCORCIATOIA", "Morning"),
 ("give me my morning briefing", "BRIEFING", ""),
 ("I can't find the Export button", "SCHERMO", "dove|Export"),
 ("what do you see on the screen", "SCHERMO", "leggi|"),
 # negativi: devono NON scattare
 ("I love this weather", None, None),
 ("how are you today", None, None),
 ("tell me a joke", None, None),
 ("I'm feeling a bit tired", None, None),
 ("play it cool", None, None),
 ("I need some advice about my job", None, None),
 ("what do you think about love", None, None),
 ("go to sleep", None, None),
 ("it's a beautiful day", None, None),
 ("who are you", None, None),
 ("what is your name", None, None),
 ("my timer broke yesterday", None, None),
 ("thank you so much", None, None),
 ("I used to play the piano", None, None),

 # positivi con giri di parole
 ("Hey Aria, I was wondering if you could check the weather in London for me", "METEO", None),
 ("is it going to rain in Paris on Saturday", "METEO", None),
 ("what's the temperature outside", "METEO", None),
 ("how cold is it in Oslo", "METEO", None),
 ("what's the forecast for tonight", "METEO", None),
 ("could you set a ten minute timer please", "TIMER", None),
 ("timer for 3 minutes", "TIMER", None),
 ("set an alarm for seven thirty", "TIMER", None),
 ("set a timer for 25 minutes called pomodoro", "TIMER", None),
 ("how long is left on my timer", "TIMER_STATO", None),
 ("stop the timer", "TIMER_ANNULLA", None),
 ("what time is it in London", "ORA", None),
 ("do you have the time", "ORA", "ora"),
 ("what's today's date", "ORA", "data"),
 ("what day of the week is it", "ORA", "data"),
 ("remind me to buy bread this evening", "PROMEMORIA", None),
 ("set a reminder to call the dentist on Monday at 10", "PROMEMORIA", None),
 ("create an event called team lunch on Thursday at noon", "EVENTO", None),
 ("what's 15 percent of 80", "CALCOLA", None),
 ("how much is 9 times 8", "CALCOLA", "9*8"),
 ("what is 100 minus 37", "CALCOLA", "100-37"),
 ("what's two plus two", "CALCOLA", "2+2"),
 ("what's half of 50", "CALCOLA", "50/2"),
 ("make it louder", "VOLUME", "up"),
 ("turn it down a bit", "VOLUME", "down"),
 ("put the volume at fifty percent", "VOLUME", "set:50"),
 ("unmute", "VOLUME", "unmute"),
 ("what's the volume", "VOLUME", "get"),
 ("play something relaxing", "MUSICA", None),
 ("put on some Pink Floyd", "MUSICA", None),
 ("skip this song", "MUSICA", "next"),
 ("go back to the previous song", "MUSICA", "previous"),
 ("stop the music", "MUSICA", "pause"),
 ("open the Calendar app", "APRI_APP", None),
 ("open github.com", "APRI_APP", None),
 ("google best pizza in Naples", "WEB", None),
 ("search Wikipedia for the Eiffel Tower", "WEB", None),
 ("where is the nearest pharmacy", "MAPPA", None),
 ("navigate to Milan Central Station", "MAPPA", None),
 ("who is Leonardo da Vinci", "WIKI", None),
 ("who invented the telephone", "WIKI", None),
 ("what's a black hole", "WIKI", None),
 ("what's the latest news about Apple", "CERCA", None),
 ("look up the opening hours of the Louvre", "CERCA", None),
 ("remember I'm allergic to peanuts", "RICORDA", None),
 ("don't forget that my birthday is in May", "RICORDA", None),
 ("put bananas on the shopping list", "LISTA", "shopping|bananas"),
 ("add toothpaste to the list", "LISTA", None),
 ("write down: pick up the dry cleaning", "NOTA", None),
 ("take a note to ask Anna about the invoice", "NOTA", None),
 ("read me my notes", "LEGGI", "notes"),
 ("summarize the lease agreement", "RIASSUMI", None),
 ("write a short story about a dragon", "SCRIVI", None),
 ("how many liters are in a gallon", "CONVERTI", None),
 ("flip a coin", "CASO", None),
 ("pick a number between 1 and 10", "CASO", None),
 ("how do you say thank you in French", "TRADUCI", None),
 ("what does 'bonjour' mean in English", "TRADUCI", "english|bonjour"),
 ("lock the front door", "NON_SO", "home"),
 ("order a pizza", "NON_SO", "buy"),
 ("take a screenshot", "NON_SO", "media"),
 ("tell me what's on my screen", "SCHERMO", None),
 ("is my battery charging", "SISTEMA", "batteria"),
 ("what's my IP address", "SISTEMA", "ip"),
 # negativi: conversazione normale (non deve scattare niente)
 ("I had a terrible day at work", None, None),
 ("do you ever get tired of answering questions", None, None),
 ("what's your favorite color", None, None),
 ("I think the weather app lied to me", None, None),
 ("I'm so tired of this cold", None, None),
 ("my sister plays the guitar", None, None),
 ("let's talk about something fun", None, None),
 ("what should I cook tonight", None, None),
 ("how do I stay motivated", None, None),
 ("I can't find my keys", None, None),
 ("where is the love", None, None),
 ("tell me something interesting", None, None),
 ("I'm going to the gym later", None, None),
 ("it's time to go", None, None),
 ("what do you think about pineapple on pizza", None, None),
 ("good morning", None, None),
 ("remember when we talked about my dog", None, None),
 ("who do you think will win", None, None),
 ("what is the meaning of life", None, None),
 ("can you help me with something", None, None),
 ("do you like music", None, None),
 ("I was watching a movie yesterday", None, None),
 ("how are you", None, None),
 ("the volume of the crowd was crazy", None, None),
 ("what a lovely day", None, None),
]


@pytest.mark.parametrize("text,tool,arg", CORPUS)
def test_english_intent(english, text, tool, arg):
    got = intent.detect(text, FILES)
    if tool is None:
        assert got is None, f"{text!r} -> {got}"
        return
    assert got is not None and got.name == tool, f"{text!r} -> {got}"
    if arg is not None:
        assert got.arg.strip() == arg, f"{text!r} -> {got}"


def test_dispatch_follows_the_language(english):
    assert intent.detect("set a timer for ten minutes").name == "TIMER"


def test_italian_is_untouched_by_the_english_rules():
    assert intent.detect("metti un timer di dieci minuti").name == "TIMER"


def test_math_words_and_symbols(english):
    assert intent.spoken_math("what's 120 \u00f7 4") == "what's 120 divided by 4"
    assert intent.spoken_math("what is 5 + 3") == "what is 5 plus 3"
    assert intent.parse_math("twelve times seven") == "12*7"
    assert intent.parse_math("what's 2.5 times 4") == "2.5*4"
    assert intent.parse_math("one hundred twenty divided by eight") == "120/8"
    assert intent.parse_math("add 5 and 7") == "5+7"
    assert intent.parse_math("subtract 3 from 10") == "10-3"
    assert intent.parse_math("what is 3 plus 4 times 2") == "3+4*2"
    assert intent.parse_math("20 squared") == "20*20"


def test_a_half_finished_request_is_completed_by_the_answer(english):
    assert intent.slot_cancelled("no thanks") and intent.slot_cancelled("never mind") and not intent.slot_cancelled("tomorrow at nine")
    assert intent.merge_slot(ToolCall("PROMEMORIA", "call Mark"), "tomorrow at nine") == ToolCall("PROMEMORIA", "call Mark tomorrow at nine")
    assert intent.merge_slot(ToolCall("PROMEMORIA", "call Mark"), "without a time") == ToolCall("PROMEMORIA", "!call Mark")


def test_list_followups(english):
    assert intent.list_followup("and eggs", "shopping") == ToolCall("LISTA", "shopping|eggs")
    assert intent.list_followup("also add the milk", "shopping") == ToolCall("LISTA", "shopping|milk")
    assert intent.list_followup("and what about you", "shopping") is None


def test_requests_that_were_not_understood_get_an_honest_answer(english):
    assert intent.action_like("set a reminder for the thing")[0] == "reminders"
    assert intent.action_like("cancel my reminder")[2] is True
    assert intent.action_like("how are you") is None
    assert "calendar" in intent.unmatched_action("add the thing to my calendar please")
    assert intent.file_attempt("put the recipe in a file somewhere")[0] == "files"
    assert intent.request_like("can you send a message to Luca") and not intent.request_like("I felt sad yesterday")


def test_saving_what_was_just_said(english):
    assert intent.is_save_last("put all that in a file") and not intent.is_save_last("hello")
    assert intent.is_save_reply("could you write the whole recipe to a file?") == "recipe"
    assert intent.is_save_reply("save it in the folder") == "text"
    assert intent.is_save_reply("how are you") is None
    assert intent.file_request("write me the carbonara recipe in a file") == ("recipe", "carbonara")
    assert intent.file_request("write all of that to a file") == ("text", None)


def test_corrections(english):
    assert intent.convert_target("make it a reminder") == "PROMEMORIA"
    assert intent.convert_target("no, as an event") == "EVENTO"
    assert intent.convert_target("hello") is None
    assert intent.replace_words("change coffee to tobacco papers") == ("coffee", "tobacco papers")


def test_screen_requests(english):
    assert intent.screen_request("where is the Save button").arg == "dove|Save"
    assert intent.screen_request("what do you think of this chart?", True).name == "SCHERMO"
    assert intent.screen_request("point it out").arg == "indica|"
    assert intent.screen_request("where is Rome") is None
    assert intent.screen_request("where is the nearest pharmacy") is None
    assert intent.screen_attempt("can you point to the save button on the screen")[0] == "screen"


def _negatives():
    import os
    with open(os.path.join(os.path.dirname(__file__), "negatives_en.txt"), encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


@pytest.mark.parametrize("text", _negatives())
def test_everyday_english_never_starts_a_tool(english, text):
    """Frasi di tutti i giorni (chiacchiere, racconti, opinioni, propositi): nessuno strumento deve partire, nemmeno con la lettura dello schermo accesa."""
    for screen_on in (False, True):
        got = intent.detect(text, FILES, screen_on)
        assert got is None, f"{text!r} -> {got}"


def _positives():
    import os
    with open(os.path.join(os.path.dirname(__file__), "positives_en.txt"), encoding="utf-8") as f:
        return [tuple(ln.strip().split("|", 1)) for ln in f if "|" in ln]


@pytest.mark.parametrize("tool,text", _positives())
def test_english_requests_said_in_different_ways(english, tool, text):
    """Richieste dette in modi diversi da quelli con cui sono state scritte le regole (scritte dopo, da un altro elenco): lo strumento giusto."""
    got = intent.detect(text, FILES, True)
    assert got is not None and got.name == tool, f"{text!r} -> {got}"


def test_tips_lists_and_pausing_with_put(english):
    assert intent.detect("what's a 15 percent tip on 80 dollars", FILES, False) == ToolCall("CALCOLA", "80*15/100")
    assert intent.detect("how much is a twenty percent tip on forty dollars", FILES, False) == ToolCall("CALCOLA", "40*20/100")
    assert intent.detect("what's the tip on 60 dollars at 20 percent", FILES, False) == ToolCall("CALCOLA", "60*20/100")
    assert intent.detect("what's on my to-do list", FILES, False) == ToolCall("LEGGI", "to-do list")
    assert intent.detect("what's on the shopping list", FILES, False) == ToolCall("LEGGI", "shopping list")
    assert intent.detect("what's in my notes", FILES, False) == ToolCall("LEGGI", "notes")
    assert intent.detect("put the music on pause", FILES, False) == ToolCall("MUSICA", "pause")
    assert intent.detect("put the song on pause", FILES, False) == ToolCall("MUSICA", "pause")
    assert intent.detect("put some jazz on", FILES, False) == ToolCall("MUSICA", "track:jazz")
