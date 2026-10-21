"""Gli «atti» della conversazione, in inglese: saluti, thanks, «ok», «sorry?», risate. Gemello inglese di dialog.py (stesse funzioni, stessi nomi).

Rispondere a «thanks» con un giro da chatbot («You're welcome! Let me know if you need anything else...») suona finto: qui le risposte sono corte, variate e immediate.
"""
from __future__ import annotations

import datetime as dt
import random
import re

from .textutil import normalize


def _t(text: str) -> str:
    return normalize(text).strip()


def _pick(pool: list[str], last: str | None) -> str:
    options = [p for p in pool if p != last] or pool
    return random.choice(options)


_FAREWELL = re.compile(
    r"^(?:(?:ok|okay|alright|right|well|so|anyway|then)\s+)*(?:(?:thanks|thank you|cheers)(?: a lot| so much| very much| aria)*\s+)?(?:(?:ok|okay|alright|right|well|so|anyway|then)\s+)*"
    r"(?:bye(?: bye)?|goodbye|good bye|farewell|see (?:you|ya)(?: (?:later|tomorrow|soon|tonight|around|next time))?|so long|talk to you (?:later|soon|tomorrow)|gotta (?:go|run)|got to (?:go|run)|"
    r"catch you later|until next time|good night|goodnight|night night|nighty night|have a (?:good|great|nice|lovely) (?:one|day|night|evening|weekend|afternoon)|take care|cheerio|later|"
    r"i(?: am| m|m) off|i(?: am| m|m) going(?: now| to bed| to sleep)?|i have to go|i need to go|i gotta go|i must go|i(?: am| m|m) heading out|i(?: am| m|m) leaving|i(?: am| m|m) done|i(?: am| m|m) all done|"
    r"that(?: is| s|s) (?:all|it)(?: for now| for today| thanks)?|that will be all|that(?: is| s|s) everything|nothing else|nothing more|i don(?: t|'t) need anything else|no more|that is enough for now|enough for now)"
    r"(?:\s+(?:aria|thanks|thank you|bye|for now|for today|everyone|again|tomorrow|later|soon|good night|goodnight|take care|have a good one))*$")
_THANKS = re.compile(r"^(?:(?:ok|okay|alright|great|perfect|awesome|wonderful|fantastic|nice|good)\s+)*(?:thanks|thank you|thank you very much|thanks a lot|thanks so much|thank you so much|many thanks|"
                     r"thanks a million|cheers|much appreciated|i appreciate it|appreciate it|i appreciate that|you(?: are| re|re) (?:the best|great|amazing|so kind|very kind|wonderful|an angel|awesome|fantastic|a star)|"
                     r"that(?: is| s|s) (?:very )?kind(?: of you)?|how kind|you(?: are| re|re) too kind|you(?: are| re|re) so helpful|that was helpful)"
                     r"(?:\s+(?:a lot|so much|very much|aria|again|for everything|for your help|for that|anyway|though|mate|buddy|friend))*$")
_ACK = re.compile(r"^(?:(?:ah|oh)\s+)?(?:ok|okay|alright|all right|right|got it|i see|i get it|understood|i understand|sure|fine|cool|great|perfect|nice|good|fair enough|makes sense|"
                  r"sounds good|sounds great|sounds fine|of course|exactly|indeed|yes i see|mh|mhm|mmh|mm|hm|hmm|uh huh|uhuh|aha|yep|yeah okay|yeah ok|okay then|ok then|noted|all good|very well|excellent|wonderful)"
                  r"(?:\s+(?:thanks|thank you|perfect|understood|got it|ok|okay|great|cool|aria|then|i see))*$")
_LAUGH = re.compile(r"^(?:ha\s*){2,}h*$|^(?:he\s*){2,}h*$|^(?:ah\s*){2,}h*$|^haha\w*$|^hehe\w*$|^lol$|^lmao$|^rofl$|^heh$|^that(?: is| s|s) funny$|^you(?: are| re|re) funny$|^that was funny$|^that made me laugh$|^you made me laugh$|^good one$|^too funny$")
_REPEAT = re.compile(r"^(?:what|sorry|pardon|pardon me|excuse me|come again|huh|eh|say again|say that again|can you repeat that|could you repeat that|can you repeat|could you repeat|repeat that|repeat|"
                     r"repeat please|please repeat|repeat it|say it again|one more time|once more|again|what did you say|what was that|what did you just say|i didn(?: t|'t) (?:catch|hear|get) that|"
                     r"i didn(?: t|'t) (?:catch|hear|get) (?:that|it|you)(?: (?:well|properly))?|i missed that|can you say that again|could you say that again|say that once more|you(?: are| re|re) breaking up|sorry what)\??$")
_GREET = re.compile(r"^(?:hi|hello|hey|hiya|howdy|yo|good morning|good afternoon|good evening|morning|evening|afternoon|greetings|hi there|hello there|hey there|hello hello|hi hi|hey hey)(?:\s+(?:aria|there|you|everyone|again))?$")
_PRESENCE = re.compile(r"^(?:aria|are you there|are you still there|you there|you still there|are you listening|can you hear me|do you hear me|hello|hello aria|hey|hey aria|is anyone there|are you with me|still there)(?:\s+(?:aria|you there|are you there))?$")
_APOLOGY = re.compile(r"^(?:sorry|sorry aria|my bad|oops|oops sorry|excuse me|apologies|i(?: am| m|m) sorry|my apologies|forgive me|sorry sorry|pardon me)$")
_DISMISS = re.compile(
    r"^(?:(?:ok|okay|now|alright|well|thanks|thank you|then|aria|for now|please|so|anyway)\s+)*(?:(?:you can|you may|can you|could you|why don t you|go ahead and|i want you to)\s+)?"
    r"(?:go (?:to sleep|away|into the background|in the background|back to sleep|quiet|to standby|to rest)|shut (?:down|yourself down|yourself off|off)|turn (?:yourself )?off|switch (?:yourself )?off|"
    r"power (?:down|off)|stand by|standby|take a (?:break|rest)|rest(?: now)?|quit|close yourself|disappear|be quiet for now|go dormant|sleep|that will be all for now)"
    r"(?:\s+(?:now|for now|please|thanks|thank you|aria|ok|okay|yourself|in the background|for a while))*$")
DISMISS_REPLIES = ["Okay, I'll step aside. Call me when you need me.", "Alright, back to the background. Just call me when you need me.", "Sure, I'll stay quiet. Call me whenever.",
                   "Got it, shutting up for now. Just say my name to wake me."]
PRESENCE_REPLIES = ["Yes, I'm here.", "I'm here, go ahead.", "Right here, what's up?", "Yep, I'm listening."]
APOLOGY_REPLIES = ["Oh, don't worry about it.", "No problem at all.", "Nothing to be sorry about.", "It's fine, really."]
THANKS_REPLIES = ["Anytime!", "You're welcome!", "Of course.", "No problem.", "My pleasure.", "Happy to.", "Sure thing!", "Don't mention it."]
LAUGH_REPLIES = ["I do have my moments.", "Glad that landed.", "Ha, I'll take it.", "I'm happy to make you laugh.", "I thought you might like that one."]
REPEAT_PREFIX = ["I said: ", "I was saying: ", "Sure. ", "Here it is again: "]
UNCLEAR = ["Sorry, I didn't quite catch that. Can you say it again?", "Hmm, I didn't hear you well. One more time?", "Sorry, that slipped past me. Could you repeat it?",
           "I missed that, try again?", "Sorry, I didn't get that: could you repeat it?"]
UNCLEAR_AGAIN = ["I still can't make it out, sorry. Could you put it in other words?", "I really can't hear you well. Try moving a bit closer to the microphone."]

_C_VOICE = re.compile(r"\b(?:you(?: are| re|re) mumbling|you mumble|i can(?: t|'t) understand you|i can(?: t|'t) hear you(?: well| properly)?|speak up|speak louder|you(?: are| re|re) (?:talking|speaking) (?:too )?(?:fast|quickly|slowly|quietly|softly)|"
                      r"you talk too (?:fast|quickly|slowly|quietly)|you(?: are| re|re) too (?:quiet|soft|fast|slow)|your voice (?:cuts out|is breaking|sounds weird|sounds strange|is glitchy|is cracking)|you(?: are| re|re) cutting out|you sound (?:weird|strange|robotic))\b")
_C_GLITCH = re.compile(r"\b(?:you (?:froze|are frozen|keep freezing|got stuck|are stuck|crashed|hang|keep hanging|lagged|are lagging)|you(?: are| re|re) (?:so |really |too )?(?:slow|laggy|frozen|stuck)|"
                       r"it takes (?:too long|forever|ages)|you(?: are| re|re) not working|you don(?: t|'t) work|you work badly|sometimes you (?:don(?: t|'t) answer|stop|freeze))\b")
_C_WRONG = re.compile(r"\b(?:you didn(?: t|'t) understand|you misunderstood|you got it wrong|you(?: are| re|re) wrong|that(?: is| s|s) wrong|that(?: is| s|s) not what i (?:said|asked|meant|wanted)|"
                      r"you answered at random|that makes no sense|that doesn(?: t|'t) make sense|you(?: are| re|re) off track|not what i said|you don(?: t|'t) understand)\b")
COMPLAINT_REPLIES = {
    "voice": ["You're right, my voice cuts out sometimes. If you miss something just say \"repeat\" and I'll say it again.", "Yeah, I know, I swallow words now and then. Say \"repeat\" and I'll do it slowly.",
              "Sorry, my voice sometimes comes out badly. If it doesn't sound right, ask me to repeat."],
    "glitch": ["I know, I get stuck now and then. Give me a second and we'll try again.", "You're right, I freeze sometimes. If it happens, say \"hey Aria\" and I'll restart.",
               "Yeah, I jam up every so often, sorry. I'll try again."],
    "wrong": ["Sorry, I think I lost the thread. Can you say it again in other words?", "You're right, I didn't get it. Try saying it again?", "Oops, I misunderstood. Say it once more, please?"],
}
_TRAILING = {"and", "but", "or", "the", "a", "an", "of", "with", "because", "if", "when", "while", "which", "um", "uh", "erm", "hmm", "my", "your", "their", "our",
             "although", "though", "since", "until", "unless", "whether", "as", "than", "to"}          # solo parole che NON possono chiudere una frase: «what time is it», «thank you», «where are you from» sono finite

_VOICE_NAMES = {n: n for n in ("alba", "anna", "azelma", "charles", "cosette", "daan", "eponine", "estelle", "eve", "fantine", "george", "giovanni", "jane", "javert", "jean", "juergen", "lola", "marius",
                               "mary", "michael", "paul", "rafael", "vera")}
_VOICE_ALL = "|".join(_VOICE_NAMES)
_VOICE_NAT_ON = re.compile(r"^(?:(?:can you|could you|please|i want you to|i(?: would|d) like you to)\s+)*(?:turn on|activate|enable|switch to|use|try|go to|put on|start using|give me)\s+(?:the |a |your )?(?:more )?(?:natural|human|realistic|better|new|nicer)\s+voice$|"
                           r"^(?:i(?: would|d) like|i want|give me|let me hear)\s+(?:the |a |your )?(?:more )?(?:natural|human|realistic|better|new)\s+voice$")
_VOICE_NAT_OFF = re.compile(r"^(?:(?:can you|could you|please)\s+)*(?:go back to|return to|switch back to|use)\s+(?:the |your )?(?:old|previous|normal|standard|regular|original|default|earlier)\s+voice$|"
                            r"^(?:turn off|disable|deactivate|stop using)\s+(?:the |your )?(?:natural|human|realistic|new)\s+voice$")
_VOICE_CYCLE = re.compile(r"^(?:(?:can you|could you|please|i want you to)\s+)*(?:change|switch|swap|try|use|give me)\s+(?:your |the |a )?(?:another |a different |different |new |other |next )?voice$|^(?:another|different|new|next) voice(?: please)?$|^change voice$")
_VOICE_SET = re.compile(rf"^(?:(?:can you|could you|please|i(?: would|d) like(?: you)? to|i want you to)\s+)*(?:use|try|switch to|change to|talk (?:like|in)|speak (?:like|in)|go with|put on|give me|let me hear)\s+"
                        rf"(?:the |your |a )?(?:voice (?:of |called |named )?)?(?P<n>{_VOICE_ALL})(?: voice)?$|^(?:use|try|switch to|change to|talk in|speak in|give me|let me hear)\s+(?:a |the )?(?P<g>male|man s|man|men s|female|woman s|woman|women s|young|calm|mature|deeper|lower|higher)\s+voice$")
_VOICE_GENDER = {"male": "george", "man": "george", "man s": "george", "men s": "george", "deeper": "george", "lower": "george", "female": "alba", "woman": "alba", "woman s": "alba", "women s": "alba",
                 "young": "eve", "calm": "jane", "mature": "mary", "higher": "alba"}


def is_greeting(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 3 and bool(_GREET.match(t))


def is_farewell(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 7 and bool(_FAREWELL.match(t))


def is_dismissal(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 9 and bool(_DISMISS.match(t))


def voice_request(text: str):
    t = _t(text)
    if not t or len(t.split()) > 10:
        return None
    if _VOICE_NAT_ON.match(t):
        return ("natural_on", "")
    if _VOICE_NAT_OFF.match(t):
        return ("natural_off", "")
    m = _VOICE_SET.match(t)
    if m:
        n = m.group("n")
        return ("set", _VOICE_NAMES[n] if n else _VOICE_GENDER.get(m.group("g"), "alba"))
    if _VOICE_CYCLE.match(t):
        return ("cycle", "")
    return None


def is_thanks(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 8 and bool(_THANKS.match(t))


def is_ack(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 4 and bool(_ACK.match(t))


def is_laugh(text: str) -> bool:
    t = _t(text)
    return bool(t) and bool(_LAUGH.match(t))


def is_presence_check(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 4 and bool(_PRESENCE.match(t))


def is_apology(text: str) -> bool:
    t = _t(text)
    return bool(t) and bool(_APOLOGY.match(t))


def is_repeat_request(text: str) -> bool:
    t = _t(text)
    return bool(t) and len(t.split()) <= 8 and bool(_REPEAT.match(t))


def complaint_kind(text: str) -> str | None:
    t = _t(text)
    if not t or len(t.split()) > 14:
        return None
    for kind, rx in (("voice", _C_VOICE), ("glitch", _C_GLITCH), ("wrong", _C_WRONG)):
        if rx.search(t):
            return kind
    return None


def presence_reply(last: str | None = None) -> str:
    return _pick(PRESENCE_REPLIES, last)


def apology_reply(last: str | None = None) -> str:
    return _pick(APOLOGY_REPLIES, last)


def thanks_reply(last: str | None = None) -> str:
    return _pick(THANKS_REPLIES, last)


def complaint_reply(kind: str, last: str | None = None) -> str:
    return _pick(COMPLAINT_REPLIES[kind], last)


def laugh_reply(last: str | None = None) -> str:
    return _pick(LAUGH_REPLIES, last)


def repeat_reply(previous: str) -> str:
    return random.choice(REPEAT_PREFIX) + previous


def unclear_reply(times: int = 0, last: str | None = None) -> str:
    return _pick(UNCLEAR_AGAIN if times >= 1 else UNCLEAR, last)


def farewell_reply(now: dt.datetime | None = None, name: str | None = None, text: str = "", last: str | None = None) -> str:
    n = now or dt.datetime.now()
    t = _t(text)
    nm = f", {name}" if name else ""
    if re.search(r"\b(?:good night|goodnight|going to bed|going to sleep|night night)\b", t) or n.hour >= 23 or n.hour < 5:
        pool = [f"Good night{nm}!", f"Sleep well{nm}.", "Good night, see you tomorrow!", "Sweet dreams!"]
    elif 18 <= n.hour < 23:
        pool = [f"Have a good evening{nm}!", f"Talk to you later{nm}!", "Bye, see you soon!", f"Catch you later{nm}."]
    elif n.hour < 12:
        pool = [f"Have a great day{nm}!", f"Bye{nm}, talk later!", "See you soon!", f"Catch you later{nm}."]
    else:
        pool = [f"Have a good afternoon{nm}!", f"Bye{nm}, talk later!", "See you soon!", f"Catch you later{nm}."]
    return _pick(pool, last)


def greeting_and_name(now: dt.datetime | None = None) -> str:
    n = now or dt.datetime.now()
    hello = "Good morning" if 5 <= n.hour < 12 else "Good evening" if 18 <= n.hour < 23 else "Hi"
    return random.choice([f"{hello}! Nice to meet you, I'm Aria. What's your name?", f"{hello}, I'm Aria. And you are?", "Here I am, I'm Aria! Can you tell me your name?"])


def greeting(now: dt.datetime | None = None, name: str | None = None, since_last_s: float | None = None, followup: str | None = None) -> str:
    n = now or dt.datetime.now()
    nm = f" {name}" if name else ""
    if followup:
        return random.choice([f"Hey{nm}! {followup}", f"Hi{nm}! {followup}", f"There you are{nm}. {followup}"])
    if since_last_s is not None and since_last_s < 20 * 60:
        return random.choice(["I'm back!", f"Here again{nm}.", "Go ahead.", "Yes, go on."])
    if n.hour >= 23 or n.hour < 5:
        return random.choice([f"Hey{nm}, still up? Go ahead.", f"Hi{nm}. At this hour? Tell me.", f"I'm here{nm}, go ahead."])
    if n.hour < 12:
        return random.choice([f"Good morning{nm}!", f"Hi{nm}, good morning!", f"I'm here{nm}, good morning.", "Hi! Go ahead."])
    if n.hour < 18:
        return random.choice([f"Hi{nm}!", f"I'm here{nm}, go ahead.", "Hi! Tell me.", f"Hey{nm}, hi!"])
    return random.choice([f"Good evening{nm}!", f"Hi{nm}, good evening.", f"I'm here{nm}, go ahead.", "Hi! Go ahead."])


def looks_unfinished(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t.split()) < 2:
        return False
    if t.endswith(("?", "!")):
        return False
    if t.endswith((",", "…", "...", ";", ":", "-")):
        return True
    if t.endswith("."):
        return False
    words = normalize(t).split()
    return bool(words) and words[-1] in _TRAILING
