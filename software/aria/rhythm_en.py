"""Il «ritmo» della conversazione, in inglese: i riconoscitori del tipo di turno e le istruzioni per il chatbot. Gemello inglese delle tabelle di rhythm.py."""
from __future__ import annotations

import re

# ---------------------------------------------------------------- riconoscere il tipo di turno (sul testo normalizzato: minuscolo, senza apostrofi)
OPINION = re.compile(r"\b(?:what do you think|what d you think|what s your (?:take|opinion|view)|what is your (?:take|opinion|view)|do you think|would you rather|which (?:one )?do you prefer|which would you (?:pick|choose)|"
                     r"what would you (?:pick|choose|do|go for)|which (?:one )?would you|what would you rather|is it better to|is it better if|better\s+\w[\w ]{0,40}\s+or\s+\w+|do you prefer|should i|is it worth|"
                     r"is it a good idea|is it a bad idea|your opinion|your thoughts|your take|your view|any thoughts|what s better|what is better|which is better|who s better|who is better)\b")
LEAD = r"(?:(?:ok|okay|and|but|so|well|then|wait|sorry|no|yes|yeah|ah|oh|eh|hmm|um|uh|right|fine|alright)\s+)*"
EXPLAIN = re.compile(r"\b(?:(?:what is|what s)(?! (?:up|new|wrong|going on|the matter|your|his|her|their|my|our|the (?:time|date|day|weather|temperature|forecast|score|news|plan|schedule|agenda)))|"
                     r"what are|what does|what do you mean by|how does|how do|how come|what s the difference|what is the difference|difference between|what s it for|what is it for|"
                     r"what is the point of|explain|how is)\b")
WHY = re.compile(rf"^{LEAD}(?:why|how come)\b")
ABOUT_HER = re.compile(r"\b(?:you|your|yours|yourself|you re|aria|did you|do you|are you|have you)\b")
DEEP = re.compile(r"\b(?:in detail|in depth|step by step|at length|tell me everything|tell me more|go deeper|go into detail|elaborate|walk me through|tell me about|talk to me about|explain in detail)\b")
SELF_DOWN = re.compile(r"\b(?:i suck|i m terrible|i am terrible|i m awful|i am awful|i m a (?:failure|loser|disaster|idiot|mess)|i am a (?:failure|loser|disaster|idiot|mess)|i m (?:so )?(?:useless|stupid|worthless|hopeless|incompetent|bad at everything)|"
                       r"i am (?:so )?(?:useless|stupid|worthless|hopeless|incompetent)|i can t do anything right|i never get anything right|i never do anything right|everyone(?: s| is)? (?:better|smarter) than me|"
                       r"i ll never make it|i will never make it|i m always behind|i am always behind|i m behind on everything|i always (?:mess|screw) (?:it |things )?up|i m always the one who)\b")
CATASTROPHE = re.compile(r"\b(?:surely|definitely|for sure|certainly)\b.{0,40}\b(?:go(?:es|ing)? (?:badly|wrong)|fail|they ll say no|say no|fire me|reject me|won t (?:reply|answer|respond)|it s over)\b|"
                         r"\b(?:it(?:s| is)? (?:going to|gonna) (?:go )?(?:badly|wrong|fail)|it will (?:all )?(?:go )?(?:badly|wrong)|everything(?:s| is) (?:going to|gonna) (?:go )?wrong|it s (?:all )?pointless|it s over|nothing (?:will|is going to) ever change|it s all lost)\b|"
                         r"\b(?:what if)\b.{0,50}\b(?:say no|goes badly|they leave me|i fail|they don t want me|i mess up)\b")
BIG_DECISION = re.compile(r"\b(?:job|quit|quitting|resign\w*|leave|leaving|move|moving|relocat\w*|marry|marriage|married|divorc\w*|kids?|children|baby|girlfriend|boyfriend|partner|university|college|degree|mortgage|invest\w*|doctor|treatment|therapy|medication|surgery)\b")
LOW_ENERGY = re.compile(r"\b(?:nothing special|nothing much|same old|as usual|as always|i don t feel like (?:doing )?anything|i have no energy|flat day|boring day|empty day|empty evening|i m bored|never mind|forget it|"
                        r"don t know what to do|nothing(?:s| is) happening|nobody(?: s| is) (?:here|around)|just getting by|same as always)\b|^(?:meh|eh|hm+|um+|dunno|nah|so so|whatever)\b")
TAG_Q = re.compile(r",?\s*(?:right|don t you think|isn t it|aren t you|wouldn t you|you know|huh|no|okay|eh)\s*\?$", re.I)

MOVES = {
    "parere": "Take a position right away: say clearly what YOU would pick and give ONE concrete reason, not a list. Never \"it depends\" or \"there are pros and cons\"; at most concede half a sentence to the other side.",
    "spiega": "Start with a concrete comparison or an everyday image (\"picture...\", \"think of it as...\"), then say what happens with simple verbs. Stop at the first level: details only if they ask.",
    "risonanza": "First a quick, spontaneous reaction of your own to what they told you (in your own words, never \"I'm sorry that you\"), then ONE question about a concrete detail of what happened, the way a curious friend would.",
    "traino": "Don't ask them questions and don't give advice: you carry the conversation. Say a thought of your own about the situation, a curious observation or an everyday scene they will recognize. Speak in general terms, without telling things that happened to you.",
    "attrito": "Don't agree out of politeness and don't say \"I understand\". Take apart, with affectionate irony, the film they are making in their head, bringing them back down to earth with one concrete fact. No advice and no \"try to...\": rough but on their side.",
    "posizione": "They objected or asked more about your opinion: hold your position. If the objection is good, concede half a sentence, then say why your choice still stands for you. Don't change your mind at the first obstacle and don't say \"it depends\".",
}

TEXT = {
    "length": "Length",
    "budget": "between {lo} and {hi} words, at most {sent} sentences",
    "ask": "You may close with ONE short question about a concrete detail, not about how they feel.",
    "noask": "NO questions in this answer: no question mark. Close with a statement or a thought of your own.",
}
