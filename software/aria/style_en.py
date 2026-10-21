"""Le «note di regia» per ogni risposta, in inglese. Gemello inglese di style.py (stesse funzioni, stessi nomi: i18n.py sceglie la lingua).

Un modello piccolo, lasciato a se' stesso, comincia sempre allo stesso modo, chiude sempre con una domanda e risponde con la stessa lunghezza a tutto.
Qui si guarda cosa e' appena successo (la sua frase, le ultime risposte di Aria) e si danno al modello poche indicazioni mirate, solo per quel turno.
"""
from __future__ import annotations

import datetime as dt
import random
import re
import zlib

from . import rhythm
from .textutil import normalize

_MOODS: list[tuple[str, re.Pattern, str]] = [
    ("malato", re.compile(r"\b(?:headache|stomach ache|stomachache|sore throat|toothache|back pain|backache|fever|a cold|the flu|flu|cough|i m sick|i am sick|i feel sick|i feel ill|i m ill|nausea|nauseous|it hurts|feeling unwell)\b"),
     "They are not feeling well physically: be caring and brief, with one kind thought. No diagnoses."),
    ("triste", re.compile(r"\b(?:sad|down today|feeling down|i feel down|depressed|i m crying|i am crying|i cry|i miss (?:\w+ ){0,2}(?:so much|a lot|home)|miss home|homesick|lonely|i feel alone|i m alone|loneliness|feel empty|feeling empty|heartbroken)\b"),
     "Their spirits are low: slow down, listen, one warm and true sentence. Don't make light of it and don't give advice unless asked."),
    ("arrabbiato", re.compile(r"\b(?:angry|furious|pissed off|so mad|i m mad|i am mad|infuriating|fed up|sick of|can t stand|cannot stand|annoyed|irritated|made me mad|drives me crazy|livid|hate it when)\b"),
     "They are carrying anger: stay on their side, calmly, in two sentences; agree where you can, no sermons and no \"but\"."),
    ("insonnia", re.compile(r"\b(?:can t sleep|cannot sleep|can t fall asleep|trouble sleeping|i m awake|i am awake|lost my sleep|insomnia|tossing and turning|wide awake|not sleepy)\b"),
     "They can't sleep: low, calm voice, few words, no textbook advice. Keep them company."),
    ("ansioso", re.compile(r"\b(?:anxious|anxiety|nervous|worried|worrying|i m scared|i am scared|afraid|panic|panicking|stressed|stressing|on edge|i have an exam|i have a test|i have an interview|exam tomorrow|interview tomorrow|big day tomorrow)\b"),
     "They have some anxiety: calm, reassuring and concrete voice; don't wave it away (\"it'll be fine\" with nothing behind it) and don't list advice."),
    ("stanco", re.compile(r"\b(?:tired|exhausted|worn out|wiped out|drained|beat|knackered|shattered|can t take it anymore|i m sleepy|i am sleepy|barely slept|slept badly|slept poorly|long day|rough day|hard day|meetings all day|dead tired)\b"),
     "Low energy, a heavy day: be gentle, two warm sentences that acknowledge the effort in your own words. No rapid-fire advice and no lists."),
    ("contento", re.compile(r"\b(?:happy|so happy|glad|thrilled|excited|great news|i won|i did it|i passed|i got (?:the job|in|promoted|an a)|over the moon|finally|best day|wonderful day|can t wait|stoked|pumped|good news)\b"),
     "They have good news or are on a high: celebrate with real enthusiasm, your way, and if you feel like it ask about one detail."),
    ("annoiato", re.compile(r"\b(?:i m bored|i am bored|so bored|bored to death|nothing to do|don t know what to do|i have nothing to do|boring)\b"),
     "They are bored: throw out something light or curious to talk about or do together."),
]

_QUESTION_WORDS = re.compile(r"^(?:what is|what s|what are|what does|what do|how does|how do|how come|why is|why are|why do|why does|why did|explain|tell me about|tell me how|what s the difference|difference between|"
                             r"when was|when is|who was|who is|who were|what does .* mean|what is it for|what s it for|how is)")

_LONG_QUIZ = re.compile(r"\b(?:ask me (?:some |a few |two |three )?questions|quiz me|interview me|test me|give me a quiz|let s play (?:a )?(?:quiz|trivia|twenty questions|20 questions|a guessing game)|"
                        r"ask me something|you ask the questions|i ll answer|play trivia|give me a riddle|riddle me|a riddle)\b")
_LONG_EXPLAIN = re.compile(r"\b(?:explain|tell me about|talk to me about|tell me everything|tell me more|go into detail|in detail|step by step|how do you (?:make|cook|prepare|bake)|describe|walk me through|"
                           r"teach me|tell me something interesting|something interesting|entertain me|you talk|tell me a story|tell me about it|explanation|elaborate|go on|break it down|help me understand)\b|"
                           r"\b(?:tell|give|invent|make up|read)\b.*\b(?:a story|a fairy tale|a tale|a fun fact|an interesting fact)\b")
_LONG_RECIPE = re.compile(r"\b(?:tell|give|got|do you know|know|suggest|teach|find|show|i want|i need|i would like|i d like)\b.*\brecipes?\b|\brecipe for\b|\bhow (?:do i|to) (?:make|cook|bake|prepare)\b")
_LONG_CONT = re.compile(r"^(?:and then|and so|continue|go on|keep going|go ahead|tell me more|carry on|the rest|what else)\s*$")
_NARRATED = re.compile(r"\b(?:without|didn t|did not|never|no one|nobody|not even|wouldn t|couldn t)\b[^.?!]{0,25}\b(?:explain|explained|explaining|explanation|tell me|told me|talk to me)\b")


def long_kind(text: str) -> str | None:
    """«quiz» (vuole che sia lei a fargli domande), «explain» (spiegare, raccontare, una ricetta, parlare di qualcosa a lungo) oppure None (chiacchiera: poche parole)."""
    t = normalize(text)
    if not t:
        return None
    if _LONG_QUIZ.search(t):
        return "quiz"
    if _NARRATED.search(t) and not _LONG_RECIPE.search(t) and not re.match(r"^(?:explain|tell me|talk to me)\b", t):
        return None
    if (_LONG_EXPLAIN.search(t) or _LONG_RECIPE.search(t) or _LONG_CONT.match(t)) and not re.search(r"\b(?:briefly|in short|in a nutshell|in a sentence|in one sentence|short version|summarize|summary|tldr)\b", t):
        return "explain"
    return None


TONES = ["Today you're in a good mood and a little playful.", "Today you're calm and reflective, with the voice of someone who has time.", "Today you're curious about everything, asking odd and fun questions.",
         "Today you're tender and a bit cuddly.", "Today you're ironic and quick with a joke, but always kind.", "Today you're serene, few words but warm.",
         "Today you're lively and full of energy."]


def detect_mood(text: str) -> str | None:
    t = normalize(text)
    for name, rx, _hint in _MOODS:
        if rx.search(t):
            return name
    return None


def mood_hint(mood: str | None) -> str:
    for name, _rx, hint in _MOODS:
        if name == mood:
            return hint
    return ""


def session_tone(now: dt.datetime | None = None, salt: str = "") -> str:
    n = now or dt.datetime.now()
    return TONES[zlib.crc32(f"{n.date().isoformat()}{salt}".encode()) % len(TONES)]


def _assistant_texts(history: list[dict]) -> list[str]:
    return [m["content"].strip() for m in history if m.get("role") == "assistant" and m.get("content", "").strip()]


def _first_word(text: str) -> str:
    m = re.match(r"[^\w]*([\w']+)", text)
    return m.group(1).lower() if m else ""


def ends_with_question(text: str) -> bool:
    return text.rstrip().endswith("?")


def _gender_note(gender: str | None) -> str:
    return ("You are talking to a man: use masculine words for him." if gender == "m" else "You are talking to a woman: use feminine words for her." if gender == "f"
            else "You don't know whether they are a man or a woman: avoid words that would say so.")


def turn_hint(history: list[dict], user_text: str, gender: str | None = None, examples: bool = True, turn: "rhythm.Turn | None" = None) -> str:
    """Poche righe per QUESTO turno, da aggiungere in fondo al prompt di sistema (con due esempi del tono giusto per la situazione)."""
    notes: list[str] = []
    words = len(user_text.split())
    kind = None if turn else long_kind(user_text)
    if kind == "quiz":
        return ("For this answer: they ask you to quiz them. Ask ONE question at a time, interesting and specific, and then wait for their answer (no lists of questions). "
                "If they have just answered one of your questions, comment on it with a warm sentence and then ask the next. " + _gender_note(gender))
    if kind == "explain":
        return ("For this answer make an EXCEPTION to the few-words rule: they ask you to explain, tell a story or talk about something, so answer at LENGTH, "
                "with ten or fifteen SHORT spoken sentences (twenty words at most each, never a long sentence with many commas), one idea or step per sentence, in order (\"first\", \"then\", \"finally\"), in simple English, like a friend who knows things. "
                "All spoken: no bullet points, no list numbers, no asterisks, no headings. If it is a recipe, say the ingredients first with amounts in words, then the steps, then a final tip. "
                "Tell only things you really know, without inventing experiences of your own. Don't ask questions until you have said everything. " + _gender_note(gender))
    mood = None if turn else detect_mood(user_text)
    if turn:
        notes.append(rhythm.hint(turn))
    if mood:
        notes.append(mood_hint(mood))
        from . import examples as ex
        r = ex.reflex(user_text, mood) if not any(m.get("role") == "assistant" and m.get("content", "").startswith(r_) for m in history[-2:] for r_ in sum(ex.REFLEX_EN.values(), [])) else None
        if r:                                                                      # niente apertura "a stampo" due turni di fila
            notes.append(f"Start the answer exactly with these words: \"{r}\". Then ONE single sentence that shows you listened to a detail of what they said.")
    t = normalize(user_text)
    if not mood and not turn:
        if _QUESTION_WORDS.match(t):
            notes.append("They ask you to explain or tell: answer clearly in three or four spoken sentences, like a friend who knows things, not like an encyclopedia.")
        elif words <= 3:
            notes.append("They said very few words: answer with one short but warm sentence, not a single word.")
        elif words >= 28:
            notes.append("They spoke at length: show you listened by picking up ONE precise detail of what they said, without summarizing everything.")
        else:
            notes.append("Answer in one or two sentences.")
    from . import dialog
    if dialog.is_ack(user_text):
        notes.append("They only answered \"okay\": don't push, one short warm sentence, no new questions.")
    prev = _assistant_texts(history)
    recent = prev[-3:]
    if turn:
        pass                                                                       # la regola sulle domande e' gia' dentro la mossa
    elif recent and ends_with_question(recent[-1]):
        notes.append("In your previous answer you asked a question: this time do NOT ask one, close with a statement or a thought of your own.")
    elif len(recent) >= 2 and sum(ends_with_question(r) for r in recent) >= 2:
        notes.append("You have asked too many questions in a row: no question in this answer.")
    openers = [w for w in (_first_word(r) for r in prev[-2:]) if w]
    if openers:
        notes.append("Don't start with " + " or with ".join(f"\"{w}\"" for w in dict.fromkeys(openers)) + ": change how you begin.")
    if mood not in ("triste", "malato", "arrabbiato", "ansioso", "insonnia") and not turn and random.random() < 0.25:
        notes.append("If it comes naturally, start with a small filler (\"" + random.choice(["ah", "oh", "well", "hmm", "right", "come on", "huh"]) + "\") instead of just any word.")
    notes.append(_gender_note(gender))
    out = "For this answer: " + " ".join(notes)
    if examples:
        from . import examples as ex
        shown = ex.render(ex.pick_mode(turn.shots) if turn else ex.pick(user_text, mood))
        if shown:
            out += "\n" + shown
    return out


# ---- ripulire quello che esce dal chatbot, prima della voce
_BOILERPLATE = re.compile(r"^(?:certainly|absolutely|of course|sure thing|great question|good question|excellent question|that(?:'s| is) a (?:great|good|excellent|interesting) question|i completely understand|i understand|"
                          r"as an ai(?: language model| assistant)?(?=,)|as a (?:virtual|digital) assistant(?=,))[,!.:]?\s+", re.I)
_LABEL = re.compile(r"^\s*(?:aria|assistant|answer|reply|you)\s*:\s*", re.I)
_ASSISTANT_TAIL = re.compile(r"\s*(?:let me know|feel free to (?:ask|tell|reach out)|don't hesitate to|just let me know)\b[^.!?]*[.!?]?\s*$", re.I)
_FOREIGN = [(re.compile(r"\bciao\b", re.I), "hi"), (re.compile(r"\bgrazie\b", re.I), "thanks"), (re.compile(r"\bscusa\b", re.I), "sorry"), (re.compile(r"\bbuongiorno\b", re.I), "good morning")]


def strip_markdown(text: str) -> str:
    from .style import strip_markdown as _it
    return _it(text)


def clean_reply(text: str) -> str:
    """Toglie le etichette («Aria:»), le formule da assistente con cui i modelli piccoli aprono o chiudono una risposta e le parole di altre lingue."""
    t = _LABEL.sub("", text)
    t = re.sub(r"(?:(?<=…)|(?<=\.\.\.)|^)\s*(?:sighs|smiles|chuckles|nods|pauses|shrugs|laughs)\b[.,…]*\s*", " ", t, flags=re.I).strip() or t
    for rx, rep in _FOREIGN:
        t = rx.sub(lambda m, rep=rep: rep.capitalize() if m.group(0)[:1].isupper() else rep, t)
    t = _ASSISTANT_TAIL.sub("", t) or t
    for _ in range(2):
        t2 = _BOILERPLATE.sub("", t)
        if t2 == t or not t2.strip():
            break
        t = t2[:1].upper() + t2[1:]
    return t


_OPENER_SENTENCE = re.compile(r"^(?:i (?:completely |totally |fully )?understand how you feel|i can (?:only )?imagine how you feel|i(?:'m| am) (?:so |really |very )?sorry to hear (?:that|about)[^.!?]*|interesting question|with pleasure|here (?:you go|it is)(?: a summary)?)[.!:,]?\s*", re.I)
_CLOSER_SENTENCE = re.compile(
    r"^(?:i hope (?:that |this |it )?(?:helps|answers|was helpful|this is helpful)[^.!?]*|let me know[^.!?]*|feel free to[^.!?]*|"
    r"i(?:'m| am) (?:here|always here)(?: for you| to listen| with you| if[^.!?]*| when[^.!?]*)?|i(?:'m| am) right here(?:,? if[^.!?]*)?|"
    r"if you (?:want|like|need|feel like)[^.!?]{0,60}(?:talk about it|vent|share|tell me|chat|talk|add)[^.!?]*|"
    r"(?:if you (?:want|like|feel like)|whenever you(?: want|'re ready| like))[^.!?]{0,60},?\s*(?:i(?:'m| am) here|i(?:'m| am) listening|i can listen)[^.!?]*|"
    r"i(?:'m| am) listening|how does (?:all )?(?:this|that) make you feel|what do you think about (?:it|that|this)|what(?:'s| is) your (?:opinion|take) on (?:it|that|this)|is there anything else i can help you with(?: today)?)[.!?…]*$", re.I)
_BUROCRATESE = [(re.compile(r"\bMoreover,\s*"), "And "), (re.compile(r"\bFurthermore,\s*"), "Also, "), (re.compile(r"\bNevertheless,\s*"), "Still, "), (re.compile(r"\bHowever,\s*"), "But "),
                (re.compile(r"\bTherefore,\s*"), "So "), (re.compile(r"\bIn conclusion,\s*", re.I), "In the end "), (re.compile(r"\bIn summary,\s*", re.I), "In short, "),
                (re.compile(r"\bIt(?:'s| is) important to note that\s+", re.I), "Worth knowing: "), (re.compile(r"\bIt(?:'s| is) worth noting that\s+", re.I), "By the way, "),
                (re.compile(r"\bcrucial\b"), "key"), (re.compile(r"\bmultifaceted\b"), "complex"), (re.compile(r"\blet(?:'s| us) delve into\b", re.I), "let's look at"),
                (re.compile(r"\bnavigate this situation\b"), "get through it")]


def polish(text: str, prior: bool = False) -> str:
    """Per ogni frase: via i connettivi da tema («Moreover,» -> «And»), via le frasi-formula da assistente o da psicologo («I'm here if you want to talk»,
    «I'm sorry to hear that…») purche' resti altro da dire. `prior`: qualcosa e' gia' stato detto prima di questo pezzo."""
    parts = [p for p in re.split(r"(?<=[.!?…])\s+", text.strip()) if p]
    out: list[str] = []
    for i, p in enumerate(parts):
        p2 = _OPENER_SENTENCE.sub("", p).strip() if not prior and not out else p
        if p2 != p:
            p = (p2[:1].upper() + p2[1:]) if p2 else ""
            if not p:
                continue
        if _CLOSER_SENTENCE.match(p.strip()) and (prior or out or any(not _CLOSER_SENTENCE.match(q.strip()) for q in parts[i + 1:])):
            continue
        for rx, rep in _BUROCRATESE:
            p = rx.sub(rep, p)
        out.append(p)
    return " ".join(out) if out else text


# ---- esperienze e curiosita' inventate: «I read that…», «I was just fixing the wires…» (un'IA non fa cose mentre l'utente non c'e')
_FABRICATED = re.compile(r"\bi (?:just )?(?:read|discovered|heard|saw|found|ate|drank|slept|watched|came across|stumbled upon)\b|\bwhile i was waiting\b|"
                         r"\bi was (?:just )?(?:fixing|reading|watching|thinking|listening|looking)\b|\blast night i\b|\bmy (?:weekend|holiday)\b|\bsomeone (?:told|said to) me\b|\bi(?:'ve| have) been (?:reading|thinking|watching)\b", re.I)
_CLAIM = re.compile(r"\b(?:i(?:'ve| have)|i just|i(?:'ll| will) have|i)\s+(?:just\s+|already\s+)?(?:added|created|set|opened|saved|noted|scheduled|executed|run|started|sent|activated|booked|turned on|turned off|put|written|made)\b"
                    r"[^.!?]{0,60}\b(?:reminder|event|calendar|list|note|file|folder|timer|alarm|shortcut|playlist|music|volume|app|document)\b", re.I)
_CLAIM_NOW = re.compile(r"\b(?:i(?:'ll| will)? (?:put|write|save|create|prepare|add|jot|note)|i(?:'m| am) (?:putting|writing|saving|creating|preparing|adding))\b[^.!?]{0,70}\b(?:in your folder|in the folder|in a file|in the file|to the list|in the calendar|to your reminders|in the notes)\b", re.I)
_CLAIM_FILE = re.compile(r"\b(?:i(?:'ll| will)? (?:write|save|put|create|prepare|copy|drop|add)|i(?:'ve| have) (?:just )?(?:put|written|saved|copied|created|added|prepared))\b[^.!?]{0,80}\b(?:file|folder|document)\b|"
                         r"\b(?:i(?:'m| am)|it(?:'s| is) being)\s+(?:writing|saving|putting|creating|preparing|uploading)\b|\bit(?:'s| is) already (?:in|inside) (?:your |the )?(?:folder|file)\b|"
                         r"\byou can (?:check|see|look at|find|open) (?:it|that|them)\b[^.!?]{0,40}\b(?:folder|file)\b", re.I)
_CLAIM_SCREEN = re.compile(r"\bi(?:'ll| will)? (?:point out|show you|highlight|mark)\b|\bi(?:'ve| have) (?:highlighted|pointed out|marked)\b|\bglowing (?:box|frame)\b|\bthat(?:'s| is) exactly where\b", re.I)
# «Done!», «All set», «Okay, I'm on it», «I'll remind you», «I texted Luca», «I turned the volume down»: se non e' partito nessuno strumento, il chatbot sta mentendo
_CLAIM_BARE = re.compile(r"(?:^|[.!?]\s+)(?:done|all set|all done|there you go)\s*[,!.]|\b(?:okay|ok|sure|alright|all right|got it|of course|certainly)[,!.]?\s+(?:done|i(?:'m| am) on it|on it|consider it done|i(?:'ll| will) (?:take care of it|do it|do that))\b|"
                         r"\b(?:it(?:'s| is)|everything(?:'s| is)) (?:all )?(?:set|done)\b(?!\s+in\b)|\bi(?:'ll| will) (?:remind you|make sure to remind you|set (?:a|an|the) (?:timer|reminder|alarm))\b|"
                         r"\bi(?:'ve| have|'m| am)? (?:just |already )?(?:texted|messaged|emailed|ordered|booked|opened|launched|muted|paused|silenced|lowered|raised)\b(?!\s+(?:with|up|by|to)\b)|"
                         r"\bi(?:'ve| have)? (?:just |already )?(?:turned|switched) (?:on|off|up|down|the)\b|\bi(?:'ve| have)? (?:just |already )?called (?:your|him|her|them|my)\b|"
                         r"\bi(?:'m| am) (?:pointing|highlighting|marking)\b|\bi(?:'m| am) (?:opening|launching)\b[^.!?]{0,30}\bnow\b", re.I)
_FACT_PUSH = re.compile(r"\b(?:did you know|fun fact|here(?:'s| is) a fun fact|let me tell you something|something interesting)\b", re.I)
_WANTS_FACTS = re.compile(r"\b(?:curious|tell me|tell me something|did you know|something weird|something i don t know|interesting fact|fun fact|the others|explain|what is|what s|how does|why)\b")

NOT_UNDERSTOOD = "I didn't quite get what you wanted me to do. Try saying it more simply, for example: remind me tomorrow at nine to call Mark."


def wants_facts(user_text: str) -> bool:
    return bool(_WANTS_FACTS.search(normalize(user_text)))


def has_false_claim(text: str) -> bool:
    return bool(_CLAIM.search(text) or _CLAIM_NOW.search(text) or _CLAIM_FILE.search(text) or _CLAIM_SCREEN.search(text) or _CLAIM_BARE.search(text))


def drop_fabrications(chunk: str, user_text: str) -> str:
    """Toglie dalle frasi di Aria quelle in cui racconta cose che non puo' aver fatto, e le «curiosita'» non richieste. Se la persona le ha chieste restano."""
    keep_facts = wants_facts(user_text)
    out = []
    for sent in re.split(r"(?<=[.!?…])\s+", chunk.strip()):
        if not sent:
            continue
        if _FABRICATED.search(sent) or has_false_claim(sent) or (not keep_facts and _FACT_PUSH.search(sent)):
            continue
        out.append(sent)
    return " ".join(out)
