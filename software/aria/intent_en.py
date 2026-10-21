"""Capire le richieste dette a voce in inglese e trasformarle in strumenti (ToolCall). Gemello inglese di intent.py (stesse funzioni pubbliche, stessi strumenti e argomenti).

Le richieste ovvie le riconosce il programma con regole, non il chatbot: «what's the weather in Rome tomorrow» -> METEO(Rome tomorrow), «set a timer for ten minutes» -> TIMER(ten minutes),
«remind me to call Mark tomorrow at nine» -> PROMEMORIA(...). Tutto il resto lo decide il chatbot (o, per le richieste d'azione non capite, risponde onesto che non ha capito).
Le regole girano sul testo normalizzato (minuscolo, senza apostrofi: «what's» -> «what s»); gli argomenti si prendono dal testo originale (maiuscole, apostrofi, virgole).
"""
from __future__ import annotations

import datetime as dt
import os
import re

from .everyday_en import number_en
from .phrasing_en import canonical, fold
from .textutil import ToolCall, normalize
from .tools import parse_duration
from .timeparse import parse_when
from .workspace import match_file

_Q = "\"'«»“” "
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTH_NAMES = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
_DAYW = r"(?:today|tomorrow|tonight|the day after tomorrow|day after tomorrow|this morning|this afternoon|this evening|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"


# =============================================================================== numeri e conti
def spoken_math(text: str) -> str:
    """Apple scrive «120 ÷ 4», «5 + 3», «20% of 350» invece delle parole: qui tornano parole, cosi' «what's» le calcola. «/», «x», «-» solo dopo «what's…» (altrimenti sono date, orari, intervalli)."""
    if not re.search(r"\d\s*[÷×−+%*/:\-–xX^]", text):
        return text
    out = text
    for sym, word in (("÷", " divided by "), ("×", " times "), ("−", " minus "), ("+", " plus "), ("^", " to the power of ")):
        out = re.sub(rf"(?<=\d)\s*{re.escape(sym)}\s*(?=\d)", word, out)
    out = re.sub(r"(?<=\d)\s*%\s*(?=of\b)", " percent ", out)
    out = re.sub(r"(?<=\d)\s*%", " percent", out)
    if re.search(r"\b(?:what|how much|calculate|compute|work out|solve|equals?|result)\b", out, re.I):
        for sym, word in (("/", " divided by "), (":", " divided by "), ("*", " times "), ("-", " minus "), ("–", " minus ")):
            out = re.sub(rf"(?<=\d)\s*{re.escape(sym)}\s*(?=\d)", word, out)
        out = re.sub(r"(?<=\d)\s+[xX]\s+(?=\d)", " times ", out)
    return re.sub(r"\s{2,}", " ", out).strip()


_NW_ALL = (r"(?:zero|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
           r"hundred|thousand|million|and|half|quarter|point)")
_NUMTXT = rf"(\d+(?:punto\d+)?|{_NW_ALL}(?:[ -]{_NW_ALL}){{0,5}})"
_OPS = [("divided by", "/"), ("over", "/"), ("multiplied by", "*"), ("times", "*"), ("x", "*"), ("plus", "+"), ("and", "+"), ("minus", "-"), ("take away", "-"), ("less", "-"), ("to the power of", "**"), ("power", "**")]


def _n(txt: str) -> float | int | None:
    from .everyday_en import num
    v = num(txt.strip())
    if v is None:
        return None
    return int(v) if float(v).is_integer() else v


def parse_math(text: str) -> str | None:
    """'what's one hundred twenty divided by eight' -> '120/8'. Piu' operatori, numeri a parole o a cifre, anche con la virgola («2.5 times 4»)."""
    from .everyday_en import decimals_to_words
    t = normalize(decimals_to_words(text))
    t = re.sub(r"\bwhat s\b", "what is", t)
    m = re.search(rf"\b(?:{_NUMTXT})\s+(?:percent|per cent)\s+of\s+{_NUMTXT}\b", t)
    if m:
        a, b = _n(m.group(1)), _n(m.group(2))
        if a is not None and b is not None:
            return f"{b}*{a}/100"
    m = re.search(rf"\b(?:an?\s+|the\s+)?{_NUMTXT}\s+(?:percent|per cent)\s+tip\s+(?:on|for|of)\s+(?:a\s+)?(?:bill\s+of\s+)?{_NUMTXT}\b", t) or \
        re.search(rf"\btip\s+(?:on|for|of)\s+(?:a\s+)?(?:bill\s+of\s+)?{_NUMTXT}(?:\s+(?:dollars?|bucks?|euros?|pounds?|quid))?\s+(?:at|with|of)\s+{_NUMTXT}\s+(?:percent|per cent)\b", t)
    if m:                                                              # «what's a 15 percent tip on 80 dollars» / «the tip on 60 dollars at 20 percent»
        first, second = _n(m.group(1)), _n(m.group(2))
        if first is not None and second is not None:
            pct, amount = (first, second) if re.search(r"percent|per cent", t[m.start(1):m.end(1) + 12]) else (second, first)
            return f"{amount}*{pct}/100"
    m = re.search(rf"\b(sum|difference|product|quotient)\s+of\s+{_NUMTXT}\s+and\s+{_NUMTXT}\b", t)
    if m:
        a, b = _n(m.group(2)), _n(m.group(3))
        if a is not None and b is not None:
            return f"{a}{ {'sum': '+', 'difference': '-', 'product': '*', 'quotient': '/'}[m.group(1)] }{b}"
    m = re.search(rf"\b(half|a half|double|twice|triple|quadruple|a quarter|a third|square root|cube root|the square(?!\s+root)|the cube(?!\s+root))\s+(?:of\s+)?{_NUMTXT}\b", t)
    if m:
        a = _n(m.group(2))
        if a is not None:
            return {"half": f"{a}/2", "a half": f"{a}/2", "double": f"{a}*2", "twice": f"{a}*2", "triple": f"{a}*3", "quadruple": f"{a}*4", "a quarter": f"{a}/4", "a third": f"{a}/3",
                    "square root": f"sqrt({a})", "cube root": f"({a})**(1/3)", "the square": f"{a}*{a}", "the cube": f"{a}*{a}*{a}"}[m.group(1)]
    m = re.search(rf"\b{_NUMTXT}\s+(squared|cubed|to the (?:second|third) power)\b", t)
    if m:
        a = _n(m.group(1))
        if a is not None:
            return f"{a}*{a}" if m.group(2) in ("squared",) or "second" in m.group(2) else f"{a}*{a}*{a}"
    for rx, op, swap in ((r"\b(?:add|sum)\s+(.+?)\s+(?:and|to|with)\s+(.+)$", "+", False),
                         (r"\b(?:subtract|take)\s+(.+?)\s+(?:from|away from)\s+(.+)$", "-", True),
                         (r"\bdivide\s+(.+?)\s+(?:by|into)\s+(.+?)(?:\s+equal parts)?$", "/", False),
                         (r"\bmultiply\s+(.+?)\s+(?:by|and|with)\s+(.+)$", "*", False)):
        m = re.search(rx, t)
        if m:
            a, b = _n(m.group(1)), _n(m.group(2))
            if a is not None and b is not None:
                return f"{b}{op}{a}" if swap else f"{a}{op}{b}"
    m = re.search(r"(?:what is|how much is|how much are|calculate|compute|work out|figure out|solve|whats|what do you get (?:if you|when you)?|what does|equals?|result of|answer to|tell me)\s+(.+)", t)
    body = m.group(1) if m else t
    body = re.sub(r"\b(?:equal|equals|is|make|makes)\s*$", "", body).strip()
    parts = re.split(r"\b(divided by|multiplied by|times|plus|minus|take away|to the power of|over)\b|(?<=\d) x (?=\d)", body)
    parts = [p for p in parts if p is not None]
    if len(parts) >= 3:
        sym = {"divided by": "/", "multiplied by": "*", "times": "*", "plus": "+", "minus": "-", "take away": "-", "to the power of": "**", "over": "/", "x": "*"}
        toks = [parts[0].strip()] + [x for x in parts[1:]]
        nums = [_n(x.strip()) for x in toks[0::2]]
        ops = [x.strip() for x in toks[1::2]]
        if all(n is not None for n in nums) and len(nums) == len(ops) + 1 and all(o in sym for o in ops):
            return "".join(f"{n}{sym[o]}" for n, o in zip(nums, ops)) + str(nums[-1])
    return None


_MATH_WORD = re.compile(r"\b(?:divided by|multiplied by|times|plus|minus|take away|to the power of|squared|cubed|percent of|per cent of|sum of|difference of|product of|half of|double|twice|triple|square root of)\b|\bwhat is \d+ x \d+\b")
_MATH_ASK = re.compile(r"\b(?:what is|what s|how much is|how much are|how many is|calculate|compute|work out|figure out|solve|equals?|what do you get|what does .{1,30} (?:equal|make|come to)|whats|do the math|crunch|result of|answer to)\b")


# =============================================================================== pattern
_TIME = re.compile(r"\bwhat time it is\b|\bwhat time is it\b|\bwhat time s it\b|\bwhat s the time\b|\bwhat is the time\b|\b(?:do you have|have you got|got|do you know) the time\b|\b(?:tell|give) me the time\b|\bthe time(?: please)?$|\bwhat time do you have\b|"
                   r"\bcurrent time\b|\bwhat time is it (?:now|right now|there)\b|\btime now\b|\bwhat s the current time\b")
_DATE = re.compile(r"\bwhat day is (?:it|today)\b|\bwhat (?:day|date|day of the week) it is\b|\bwhat s (?:the )?date(?: today)?\b|\bwhat is (?:the )?date(?: today)?\b|\btoday s date\b|\bwhat day of the week is (?:it|today)\b|\bwhat date is (?:it|today)\b|"
                   r"\bwhich day is (?:it|today)\b|\bwhat s today$|\bwhat day s it\b|\bwhat s the day\b|\bwhat is the day today\b|\bwhat day of the month\b|\bwhat day are we\b|\bwhat s the date today\b")
_SUN = re.compile(r"\b(?:when|what time|at what time)\s+(?:does|will|is|s)\s+(?:the\s+)?(?:sun\s*)?(?:rise|set|sunrise|sunset|go down|come up|come out)\b|\bwhat time (?:is|s) (?:the )?(?:sunrise|sunset)\b|\bwhen (?:is|s) (?:the )?(?:sunrise|sunset)\b|"
                  r"\b(?:sunrise|sunset)\s+time\b|\bwhen does it (?:get )?dark\b|\bwhen (?:does|will) the sun (?:rise|set|go down)\b")
_TIMER_WORD = r"(?:timers?|alarms?|countdowns?|egg timer|alarm clock)"
_TIMER = re.compile(r"\b(?:timers?|alarms?|countdowns?)\b|\bwake me\b|\bwake up call\b|\b(?:remind|ping|buzz|alert|notify|ring|tell|let)\s+(?:me|us)\b|\bgive me a (?:heads up|buzz|shout|ping|nudge|reminder|ring)\b|\bheads up in\b")
_TIMER_STATUS = re.compile(rf"\bhow much longer\b.*\b(?:timer|alarm|countdown)\b|\bhow (?:much|long) (?:time )?(?:is )?(?:left|remaining)\b|\bhow long (?:until|till|before|to go)\b.*\b(?:timer|alarm)\b|\bwhen (?:does|will|is)\s+(?:the\s+|my\s+)?{_TIMER_WORD}\s+(?:go off|ring|end|finish|buzz|sound|expire)\b|"
                           rf"\bwhat {_TIMER_WORD} (?:do i have|are (?:running|active|set))\b|\b(?:is there|are there|do i have)\s+(?:a|an|any)\s+{_TIMER_WORD}\b|\bcheck\s+(?:the\s+|my\s+)?{_TIMER_WORD}\b|"
                           rf"\btime (?:left|remaining) (?:on|for|until)\s+(?:the\s+|my\s+)?{_TIMER_WORD}\b|\bhow much (?:time )?(?:is )?left (?:on|for)\b|\bhow long (?:is|s) (?:left|remaining)\b|\bhow many {_TIMER_WORD}\b")
_TIMER_CANCEL = re.compile(rf"\b(?:cancel|stop|delete|remove|turn off|switch off|clear|dismiss|kill|end|disable|abort|forget about|get rid of|never mind)\b.*\b{_TIMER_WORD}\b|\b{_TIMER_WORD}\b.*\b(?:cancel|stop|off|delete|dismiss)\b")
_TIMER_NOT = re.compile(r"\b(?:stopwatch)\b|\b(?:my|the|that|this) (?:alarm|timer)s? (?:didn t|did not|is|was|isn t|wasn t|doesn t|does not|never|keeps|always|broke|won t)\b|\b(?:hate|hated|love|loved|annoying|loud|broken|crazy) (?:the |my )?(?:alarm|timer)\b|"
                        r"\bremind (?:me|us) of\b|\balarm(?:s)? (?:system|company|bell)\b|\bsmoke alarm\b|\bfire alarm\b|\bcar alarm\b|"
                        r"^(?:(?:and|but|so|well|yeah|then) )?(?:i|we|he|she|they) (?:(?:always|usually|never|just|already|often|sometimes|also|still|even|only|normally|typically|keep|kept) )*(?:set|sets|put|use|used|had|have|forgot to set)\b")
_WEATHER = re.compile(r"\bweather\b|\bforecast\b|\btemperature\b|\bhow (?:hot|cold|warm|chilly) is it\b|\bhow s the weather\b|\bhow (?:hot|cold|warm|chilly) (?:will|is going to|would) (?:it|the weather) (?:be|get)\b|\b(?:is it|will it|are we|is it going to|going to|gonna)\s+(?:going to |gonna )?(?:rain|snow|storm|hail)\b|"
                      r"\bwill it (?:be\s+)?(?:rain|snow|sunny|cloudy|rainy|cold|hot|warm|windy|nice|clear|foggy|stormy|snowy|humid)\b|\bdo i need (?:an? )?(?:umbrella|jacket|coat|sunscreen|sunglasses|raincoat)\b|"
                      r"\bshould i (?:bring|take|wear|pack|grab) (?:an? |my )?(?:umbrella|jacket|coat|raincoat)\b|\bis it (?:raining|snowing|sunny|cold|hot|warm|cloudy|windy|nice|foggy|freezing|humid|chilly)(?: out| outside| today| now| there| right now| in\b| tomorrow)|"
                      r"\bwhat s it like outside\b|\bwhat is it like outside\b|\bhow many degrees\b|\bis it going to be (?:hot|cold|warm|sunny|rainy|cloudy|windy|nice)\b|\bis it (?:raining|snowing)\b|\bwill it be (?:hot|cold|warm|sunny|rainy|cloudy)\b|\bhow s it outside\b|\bhow s it looking (?:out|outside|today|tomorrow)\b|\bwhat s it looking like (?:out|outside)\b")
_WEATHER_NOT = re.compile(r"\bunder the weather\b|\bi (?:do not|don t|dont|really|totally|absolutely|just) (?:like|love|hate|enjoy|can t stand|mind)\b[^?]*\bweather\b|\bweather (?:the|a) storm\b|\bfair weather\b|\bweather (?:app|station|vane|channel|man|girl)\b|\bi (?:love|hate|like|can t stand|am sick of|m sick of|m tired of|enjoy) (?:this|the|that) (?:\w+ )?weather\b|"
                          r"\b(?:nice|lovely|terrible|awful|horrible|great|beautiful|gorgeous|bad|crazy|weird) (?:\w+ )?weather\b(?!.*\?)|\bweather is (?:nice|bad|great|terrible|lovely|awful|crazy)\b(?!.*\?)|\b(?:it s|it is) (?:so |really |very )?(?:cold|hot|warm|sunny|rainy)\b(?!.*\?)|\bglobal warming\b|\bclimate change\b|\btemperature of (?:the )?(?:water|oven|body|engine|cpu|processor|mac)\b")
_WEATHER_ASKY = re.compile(r"^(?:(?:so|well|and|but|now|ok|okay|yeah|yo|like|um+|uh+|hey|aria)[,\s]+)*(?:what|how|will|is|are|do|does|should|tell|give|show|check|get|any|whats|hows|can|could|would|want|need|let|find|look)\b|\bweather (?:in|for|at|like|forecast|report|today|tomorrow|tonight|this|next|on|going|gonna|supposed|will)\b|^weather\b|^forecast\b|^temperature\b|\?$")
_CITY = re.compile(r"\b(?:in|for|at|near|around|of)\s+((?:the\s+)?[A-Z][\w'’\-]*(?:\s+(?:of|de|la|le|del|di|upon|on|in|the)?\s*[A-Z][\w'’\-]*){0,2})")
_NOT_CITY = {"today", "tomorrow", "tonight", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february", "march", "april", "may", "june", "july", "august",
             "september", "october", "november", "december", "weekend", "the weekend", "morning", "evening", "afternoon", "night", "next", "this", "aria", "i", "what", "how", "is", "it", "will", "the", "christmas", "easter"}
_TIMEWORD = re.compile(r"\b(?:tomorrow|tonight|today|at \d|at (?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|noon|midnight)|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next week|this evening|this afternoon|in \d+|in (?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty|forty five|sixty|half an?|a quarter of an?) (?:second|minute|hour|day|week)s?|\d)\b")
_REMEMBER = re.compile(r"^(?:remember|keep in mind|bear in mind|make a mental note|note|take note|don['’]?t forget|do not forget|memorize|memorise)\s+(?:that\s+)?(.+)$", re.I)
_NOT_A_FACT = re.compile(r"^(?:when|how|what|where|who|why|if|whether|the time|that time|last time|our|we|you|your|me|us|it|that|this|to\s+(?!\w+\s+(?:tomorrow|tonight)))\b", re.I)
_REMEMBER2 = re.compile(r"^(?:you should know|just so you know|for your information|fyi|know that)\s+(?:that\s+)?(.+)$", re.I)
_FORGET = re.compile(r"^(?:forget|erase|delete|remove|clear)\s+(?:about\s+|that\s+|what i (?:told|said to) you about\s+)?(?:my\s+)?(.+?)(?:\s+from (?:your )?memory)?$", re.I)
_MEMORY = re.compile(r"\b(?:what|everything|anything)\b.*\b(?:do you (?:know|remember)|have you (?:learned|learnt)|did i tell you|i told you)\b.*\b(?:about me|of me|on me)\b|\bwhat do you know about me\b|\bwhat do you remember about me\b|\bwhat have i told you\b|\bwhat did i tell you about myself\b|\bdo you remember (?:me|anything about me)\b")
_WHO = re.compile(r"^(?:(?:who|what)(?:['’]s|\s+(?:is|was|are|were|s))|tell me about|what do you know about|explain what|explain|define|who invented|who discovered|who wrote|who painted|who founded)\s+(?:an?\s+|the\s+)?(.+)$", re.I)
_MEANS = re.compile(r"^what\s+(?:does|do)\s+(.+?)\s+mean$", re.I)
_LIVE = re.compile(r"\b(?:who won(?! (?:the )?(?:argument|fight|bet|debate|battle|war|quarrel))|who s winning|who is winning|score of|scores? (?:of|for)|results? (?:of|for)|standings|league table|how is the traffic|how s the traffic|traffic (?:on|to|in|near)|latest news|news about|news on|news from|what s the news|breaking news|headlines|"
                   r"how much (?:does|do|is|are|would) .+ cost|price of|stock price|share price|exchange rate|opening hours|when does .+ open|is .+ open (?:now|today|tonight)|what time does .+ (?:open|close)|release date|when does .+ come out|box office|trending|top stories)\b")
_SEARCH = re.compile(r"\b(?:search the web|search the internet|search online|search for|look up|look it up|google it|find out|find information (?:on|about)|find me information|search)\b|^(?:google|bing|duckduckgo)\s+\w", re.I)
_SEARCH_NOT = re.compile(r"\b(?:tell you|tell him|tell her|let you know|trying to|going to search|search (?:and rescue|engine optimi[sz]ation)|search party|search warrant)\b")
_INTENT_STMT = re.compile(r"^(?:(?:ok|okay|well|so|and|but|now|alright)[,\s]+)*(?:i|we)(?:\s+(?:need to|have to|got to|gotta|must|should|ought to|am going to|m going to|d better)|'ll|'m going to|\s+will\s+have to)\b")
_FUTURE_STMT = re.compile(r"^(?:(?:ok|okay|well|so|and|but|now|alright)[,\s]+)*(?:(?:i|we)(?:'ll|\s+will|'m\s+(?:going|gonna)|\s+am\s+(?:going|gonna))|let me(?!\s+(?:hear|listen|see|know|find out)))\b")
_SUN_PHRASE = re.compile(r"\b(?:sunrise|sunset|sun rise|sun set)\b")

# ---- cose che Aria NON sa fare: lo dice chiaro invece di far finta
_NO_SO: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(?:call|phone|ring|dial|video ?call|facetime|make (?:a )?(?:video )?(?:phone )?call|give (?:\w+ )?a call|start (?:a )?(?:video )?call)\b(?!\s+(?:me\b|it\b|this\b|that\b|the (?:timer|alarm)))"), "call"),
    (re.compile(r"^(?:read|check|open|show|tell|see|look at|what s in|any new)\s+(?:me\s+)?(?:my\s+|the\s+|any\s+|new\s+)*(?:e ?mails?|inbox|messages?|texts?|sms|whatsapp|imessages?|notifications?|voicemails?)\b(?!.*\b(?:file|folder|document|note)\b)"), "inbox"),
    (re.compile(r"^(?:do i have|have i got|are there)\s+(?:any\s+)?(?:new\s+)?(?:e ?mails?|messages?|texts?|notifications?|voicemails?)\b"), "inbox"),
    (re.compile(r"^(?:send|text|message|whatsapp|dm|forward|reply to|respond to|write to|tell|let|notify|email|e ?mail|drop)\s+(?!my\s+(?:regards|love|best|thanks|apologies|condolences|greetings|wishes|respects|congratulations|compliments)\b)(?:an?\s+|the\s+|this\s+|that\s+)?(?:(?:message|text|sms|whatsapp|mail|email|e ?mail|voice note|dm)\s+)?(?:to\s+)?(?:him|her|them|my\s+\w+|mom|mum|dad|[A-Z]\w+)\b(?!.*\b(?:note|file|folder|list)\b)"), "message"),
    (re.compile(r"^(?:send|forward)\s+(?:me\s+)?(?:an?\s+)?(?:message|text|sms|whatsapp|mail|email|e ?mail|voice note)\b"), "message"),
    (re.compile(r"^(?:remove|delete|take|cross|strike|tick|check|scratch)\s+.+\s+(?:off|from|out of)\s+(?:the |my )?(?:\w+\s+)?(?:list|shopping|groceries)\b"), "listremove"),
    (re.compile(r"^(?:start|begin|run|use|set|turn on)\s+(?:a\s+|the\s+)?stopwatch\b|^stopwatch$"), "stopwatch"),
    (re.compile(r"^(?:bookmark|save|add)\s+(?:this|that|the)\s+(?:page|site|website|link|tab|url)\b"), "bookmark"),
    (re.compile(r"^(?:turn|switch|put|shut|close|open|lock|unlock)\s+(?:on|off|up|down)?\s*(?:the\s+)?(?:lights?|lamps?|tv|television|heating|heater|ac|air conditioning|air conditioner|fan|blinds|shutters|garage|garage door|front door|door|gate|lock|plug|thermostat|coffee machine|oven)\b"), "home"),
    (re.compile(r"^(?:turn on|switch on|turn off|switch off|dim|brighten|set)\s+(?:the\s+)?(?:living room|bedroom|kitchen|bathroom|hallway)?\s*(?:lights?|lamps?|tv|television|heating|thermostat)\b"), "home"),
    (re.compile(r"^(?:print|printing)\b"), "print"),
    (re.compile(r"^(?:download|install|uninstall|update|upgrade)\s+\w+"), "download"),
    (re.compile(r"^(?:restart|reboot|shut ?down|lock|unlock|log ?out|sign out|put (?:the |my )?(?:mac|computer|laptop) to sleep)\s+(?:the |my )?(?:mac|computer|pc|laptop|macbook|system|screen|wifi|wi fi|bluetooth)?\b|"
                r"^(?:turn on|turn off|switch on|switch off|enable|disable)\s+(?:the\s+)?(?:wifi|wi fi|bluetooth|airplane mode|do not disturb|night shift|dark mode|vpn|hotspot)\b|^(?:increase|decrease|raise|lower|turn up|turn down|dim)\s+(?:the\s+)?(?:screen\s+)?brightness\b"), "system"),
    (re.compile(r"^(?:take|snap|shoot|record|film|capture|make)\s+(?:me\s+)?(?:a\s+|an\s+)?(?:photo|picture|selfie|screenshot|video|recording|voice memo|voice note|audio|screen recording|screen capture)\b"), "media"),
    (re.compile(r"^(?:share|post|tweet|publish|tag|repost|upload)\b"), "share"),
    (re.compile(r"^(?:move|rename|copy|duplicate|compress|zip|delete|remove|drag|trash)\s+(?:the\s+|my\s+|this\s+|that\s+)?(?:file|folder|files|folders|document|documents|photo|photos|picture|pictures|image|images|pdf)\b(?!.*\b(?:in the folder|to the folder)\b)"), "files"),
    (re.compile(r"^(?:close|quit|exit|kill|force quit|terminate)\s+(?:the\s+)?(?:app\s+|application\s+|program\s+|window\s+|tab\s+)?(?:safari|chrome|firefox|music|spotify|mail|notes|calendar|reminders|finder|word|excel|zoom|slack|messages|photos|terminal|this|that|it)\b"), "app"),
    (re.compile(r"^(?:talk|speak|go|be|read)\s+(?:a (?:bit|little)\s+|slightly\s+)?(?:more\s+)?(?:slowly|slower|quickly|faster|quicker)\b|^(?:slow down|speed up|talk slower|talk faster|speak slower|speak faster)\b"), "speed"),
    (re.compile(r"^(?:pay|transfer|wire|send money|send \$|venmo|paypal|top up|recharge)\b"), "money"),
    (re.compile(r"^(?:order|buy|purchase|book|reserve|get me)\s+(?:me\s+)?(?:an?|the|some|two|three|four|five|\d+)?\s*(?:pizza|table|taxi|cab|uber|flight|ticket|tickets|hotel|room|restaurant|dinner|lunch|trip|train|food|groceries|takeout|delivery)\b"), "buy"),
]
_SYS_INFO: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bhow much battery\b|\bis (?:my |the )?battery (?:charging|low|full|dead|ok|okay|good|dying|draining)\b|\bis it (?:charging|plugged in)\b|\bbattery (?:level|percentage|left|life|status|remaining)\b|\bis (?:my|the) (?:mac|computer|laptop) (?:charging|plugged in)\b|\bam i (?:charging|plugged in)\b|\bhow much charge\b|\bbattery\?$|\bwhat s my battery\b"), "batteria"),
    (re.compile(r"\bhow much (?:free |available |disk |storage )?(?:space|storage)\b|\b(?:disk|storage) space\b|\bis (?:my|the) disk full\b|\bhow full is (?:my|the) (?:disk|drive|storage)\b|\bfree space\b"), "spazio"),
    (re.compile(r"\bwhat version of mac ?os\b|\bwhich version of mac ?os\b|\bmac ?os version\b|\bwhat mac ?os (?:do i have|am i (?:running|on)|is this)\b|\bwhat version of windows\b|\bwhich version of windows\b|\bwhat windows (?:do i have|am i (?:running|on)|is this)\b|\bwhich windows\b"), "versione"),
    (re.compile(r"\bhow long has (?:my|the) (?:mac|computer|laptop) been (?:on|running|up|awake)\b|\buptime\b|\bwhen did (?:my|the) (?:mac|computer) (?:start|boot)\b"), "accensione"),
    (re.compile(r"\bwhat wi ?fi\b|\bwhich wi ?fi\b|\bwhich network\b|\bwhat network (?:am i|are we)\b|\bwifi name\b|\bname of the (?:wi ?fi|network)\b|\bam i connected to (?:the )?wi ?fi\b"), "wifi"),
    (re.compile(r"\bam i (?:connected|online)\b|\bare we (?:connected|online)\b|\bis (?:the )?(?:internet|network|wi ?fi) (?:working|down|up|on)\b|\bdo i have (?:internet|a connection|wi ?fi)\b|\binternet (?:connection )?(?:working|status)\b|\bis there (?:internet|a connection)\b"), "wifi"),
    (re.compile(r"\bwhat s my ip\b|\bip address\b|\bmy ip\b"), "ip"),
    (re.compile(r"\bhow much ram\b|\bhow much memory\b|\bmemory (?:usage|left|free|status)\b|\bram usage\b|\bis (?:my|the) memory (?:full|free)\b"), "memoria"),
]
_BRIEFING = re.compile(r"\b(?:morning briefing|daily briefing|briefing|brief me|give me (?:a |my |the )?(?:summary|rundown|overview|update|recap) of (?:my |the )?(?:day|morning|today)|what s (?:my day|today) (?:look(?:ing)? like|going to be like|like)|"
                       r"how (?:does|is) (?:my )?(?:day|today) look|what do i need to know (?:today|this morning)|my day ahead|day ahead|daily summary|daily rundown|catch me up|what s new today|"
                       r"what s my day)\b")
_PREAMBLE = re.compile(r"^(?:tell me|show me|let me know|can you tell me|do you know|i wonder|i was wondering|any idea|do you happen to know)[\s,]+", re.I)


def _cap_words(s: str) -> list[str]:
    return s.split()


# =============================================================================== promemoria, calendario, agenda
_REMIND = re.compile(r"^(?:remind\s+(?:me|us)|set (?:me )?(?:up )?(?:a |an )?reminder|add (?:me )?(?:a |an )?reminder|create (?:a |an )?reminder|make (?:a |an )?reminder|new reminder|reminder|don t let me forget|do not let me forget|"
                     r"make sure i remember|help me remember|i need a reminder|i need to be reminded|i want a reminder|put (?:a |an )?reminder|schedule (?:a |an )?reminder|ping me|notify me|alert me|let me know|give me a (?:heads up|reminder|nudge|ring|buzz|shout|ping))\b[\s:,]*(?:to |that |about |for |of |on )?(.*)$", re.I)
_REMIND_LIST = re.compile(r"\b(?:what|which|any|read|list|show|tell|do i have|have i got|check)\b.*\breminders?\b|\breminders?\b.*\b(?:do i have|have i got|are there|pending|outstanding|left|to do|today)\b|\bwhat (?:s|is|are) (?:on )?(?:my )?reminders?\b|^reminders?\??$")
_CAL = r"(?:calendar|agenda|diary|schedule)"
_EVENT_ADD = re.compile(rf"^(?:add|put|place|schedule|book|set up|create|make|enter|log|save|block|block off|pencil in|slot in|set)\s+(?:an?\s+|the\s+)?(?:(?:new\s+)?(?:event|appointment|meeting|entry)\s+)?(.+?)\s+(?:to|in|into|on|onto|in to)\s+(?:my\s+|the\s+)?{_CAL}\b(.*)$", re.I)
_EVENT_CREATE = re.compile(r"^(?:create|add|make|set up|schedule|book|new|put in|enter|log|put)\s+(?:an?\s+|the\s+)?(?:new\s+)?(?:calendar\s+)?(?:event|appointment|meeting)\s*[:,]?\s*(?:for |called |named |titled |about )?(.*)$", re.I)
_EVENT_SCHED = re.compile(r"^(?:schedule|book|set up|arrange|pencil in)\s+(?:me\s+)?(?:an?\s+|the\s+)?(.+)$", re.I)
_EVENT_NOT = re.compile(r"\b(?:reminder|list|note|music|song|volume|timer|alarm|file|document|folder|spotify|taxi|cab|uber|flight|ticket|tickets|hotel|room|table|restaurant|dinner reservation|a car|delivery|shopping|groceries)\b")
_AGENDA_WORD = re.compile(r"\b(?:calendar|agenda|schedule|diary|appointments?|meetings?|events?|plans?|commitments?)\b")
_DAYPHRASE = re.compile(r"\b(?:today|tomorrow|tonight|this weekend|the weekend|this week|next week|the day after tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|this evening|this afternoon|this morning|on the \d+|next \w+day)\b")
_AGENDA_Q = re.compile(r"^(?:what|which|do|am|any|anything|how|show|read|tell|check|list|give|is|are|got)\b.*\b(?:calendar|agenda|schedule|diary|appointments?|meetings?|events?|plans|on|going on|free|busy|available|have)\b|\bwhat s on\b|\bam i (?:free|busy|available)\b|\bdo i have (?:anything|something|plans|any (?:appointments?|meetings?|events?))\b|\bwhat do i have\b|\bwhat have i got\b")
_AGENDA_IMPLIED = re.compile(r"\bwhat (?:do i have|have i got|am i doing|s on|is on|are my plans|do i have planned|s happening)\b|\bany plans\b|\bdo i have (?:anything|something|plans|any plans)\b|\bam i (?:free|busy|available)\b")
_AGENDA_NOT = re.compile(r"\b(?:weather|rain|sun|cold|hot|snow|temperature|wind|reminders?|timer|alarm|recipe|file|document|list|note|music|song|shopping|groceries|time is it|day is it|date is it)\b")
_SC_RUN = re.compile(r"^(?:run|launch|start|execute|trigger|activate|fire|do|use|play|kick off|begin)\s+(?:the\s+|my\s+|a\s+)?(?:shortcut\s+)?[\"“']?(.+?)[\"”']?(?:\s+shortcut)?$", re.I)
_SC_RUN2 = re.compile(r"^(?:run|launch|start|execute|trigger|activate|fire|do|use)\s+(?:the\s+|my\s+|a\s+)?shortcut\s+(?:called\s+|named\s+)?[\"“']?(.+?)[\"”']?$|^(?:run|launch|start|execute|trigger|activate|use)\s+(?:the\s+|my\s+)?[\"“']?(.+?)[\"”']?\s+shortcut$", re.I)
_SC_LIST = re.compile(r"\bwhat shortcuts\b|\b(?:list|show|read|tell)\b.*\bshortcuts\b|\bwhich shortcuts\b|\bdo i have (?:any )?shortcuts\b|\bshortcuts do i have\b|\bmy shortcuts\b$")


# =============================================================================== volume, musica, siti, mappe, app
_VOL_UP = re.compile(r"\b(?:turn|crank|pump|bring|put|move|push|make)\s+(?:it |the (?:volume|music|sound|audio|speakers?) |that )?up\b|\b(?:increase|raise|boost|lift|up)\s+(?:the\s+)?(?:volume|music|sound|audio)\b|\bvolume\s+(?:up|higher)\b|"
                     r"^(?:louder|a bit louder|a little louder|little louder|more volume|up a bit|turn it up|volume up|raise it|a little more|bit louder)$|\bmake it louder\b|\bcan(?: t| not) hear (?:you|it|anything)\b|\btoo (?:quiet|soft|low|faint)\b|\bnot (?:loud|high) enough\b|\bspeak up\b|\bsay it louder\b")
_VOL_DOWN = re.compile(r"\b(?:turn|bring|put|move|push|make)\s+(?:it |the (?:volume|music|sound|audio|speakers?) |that )?down\b|\b(?:decrease|lower|reduce|drop|cut)\s+(?:the\s+)?(?:volume|music|sound|audio)\b|\bvolume\s+(?:down|lower)\b|"
                       r"^(?:quieter|a bit quieter|a little quieter|softer|a bit softer|lower|down a bit|turn it down|volume down|less volume|bit quieter|keep it down|shh+|hush)$|\bmake it (?:quieter|softer|lower)\b|\btoo (?:loud|high|noisy)\b|\bnot so loud\b")
_VOL_SET = re.compile(r"\b(?:set|put|turn|change|bring|make|take|move|adjust)\s+(?:the\s+)?(?:volume|music|sound|audio)?\s*(?:up |down )?(?:to|at)\s+(\d{1,3}|[a-z]+(?: [a-z]+)?)(?:\s*(?:percent|per cent))?\b|\bvolume\s+(?:to|at)\s+(\d{1,3}|[a-z]+(?: [a-z]+)?)\b|"
                      r"\b(?:volume|audio)\s+(\d{1,3})\b(?!\s*(?:minutes|hours|seconds))|\b(?:max(?:imum)? volume|full volume|volume (?:to )?(?:max|maximum|full))\b|\b(?:min(?:imum)? volume|lowest volume)\b|\bvolume (?:to )?(?:half|zero)\b")
_VOLWORDS = {"zero": 0, "off": 0, "half": 50, "max": 100, "maximum": 100, "full": 100, "min": 5, "minimum": 5, "lowest": 5, "mute": 0}
_VOL_MUTE = re.compile(r"\b(?:mute|silence|turn (?:the )?(?:sound|audio|volume) off|turn off (?:the )?(?:sound|audio|volume)|put (?:it )?on mute|kill the (?:sound|audio)|shut (?:it|the (?:sound|music)) up)\b(?!.*\b(?:microphone|mic)\b)|^(?:mute|silence)$")
_VOL_UNMUTE = re.compile(r"\b(?:unmute|un mute|turn (?:the )?(?:sound|audio|volume) (?:back )?on|turn on (?:the )?(?:sound|audio|volume)|take (?:it )?off mute|restore (?:the )?(?:sound|audio|volume))\b")
_VOL_GET = re.compile(r"\bwhat s the volume\b|\bwhat is the volume\b|\bhow loud (?:is it|are we)\b|\bwhat volume (?:is it|are we|am i)\b|\bcurrent volume\b|\bhow high is the volume\b|\bvolume level\b")
_MUS_GENRES = ("jazz", "rock", "pop", "classical", "classic rock", "rap", "hip hop", "blues", "techno", "house", "reggae", "metal", "heavy metal", "lofi", "lo fi", "country", "folk", "soul", "funk", "disco", "ambient", "electronic",
               "edm", "r b", "rnb", "indie", "punk", "gospel", "latin", "salsa", "opera", "orchestral", "instrumental", "acoustic", "chill", "relaxing music", "dance", "trance", "k pop", "bossa nova", "swing", "oldies", "80s", "90s", "70s", "60s")
_MUS_VERBS = r"(?:play|put on|put|throw on|start|queue up|queue|spin|blast|stream|listen to|let s listen to|let me hear|i want to hear|i d like to hear|hear|i want to listen to|i d like to listen to|fire up|cue up|turn on|give me|get me|bring up|pull up|resume|continue)"
_MUS_APP = re.compile(r"\s+(?:on|with|in|from|through|using|via)\s+(apple\s+music|spotify|music|itunes|youtube\s+music)\s*$", re.I)
_MUS_NAMED = re.compile(rf"^{_MUS_VERBS}\s+(?:me\s+)?(?:the\s+|a\s+|an\s+|some\s+)?(song|track|album|playlist|record|single|tune|record|cd)\s+(?:called\s+|named\s+|titled\s+)?(.+)$", re.I)
_MUS_PLAY = re.compile(r"^(?:play|start|resume|continue|unpause|put on|turn on|fire up|restart|keep playing|go on playing|play it)\s*(?:the\s+|some\s+|my\s+)?(?:music|songs?|tunes|tracks?|playlist|something|anything|stuff|it|that|again|a song)?\s*(?:again|please|now)?$|^(?:music|play music|play some music|play something|music please|start the music|put some music on|put on some music|let s have some music|i want (?:some )?music|i need (?:some )?music|i d like (?:some )?music)$")
_MUS_PLAY_X = re.compile(rf"^({_MUS_VERBS})\s+(?:me\s+)?(?:(?:some|a bit of|a little|a few|any|something by|something from|songs by|music by|tracks by|stuff by|songs from|music from|the music of|the songs of|songs of|a song by|a song from|something like|a playlist of|my)\s+)?(.+)$", re.I)
_MUS_PAUSE = re.compile(r"^(?:put (?:the )?(?:music|song|track|playback|it|this|that) on (?:pause|hold)|pause|pause (?:the )?(?:music|song|track|playback|it)|stop (?:the )?(?:music|song|track|playback|playing)|stop playing|hold (?:the )?music|silence the music|shut off the music|turn (?:the )?music off|turn off (?:the )?music|mute the music|cut the music|no more music|enough (?:with the )?music|that s enough music)\b|^(?:music (?:off|stop|pause)|pause please)$")
_MUS_NEXT = re.compile(r"\b(?:next|skip|forward)\s+(?:the\s+)?(?:song|track|tune|one|this one|this song)\b|^(?:next|skip|skip it|skip this|skip that|next one|next please|play the next one|change (?:the )?(?:song|track))$|\bskip (?:this|that|the current) (?:song|track|one)\b|\bnext (?:song|track)\b|\bplay (?:the )?next (?:song|track|one)\b|\bchange (?:the )?(?:song|track)\b")
_MUS_PREV = re.compile(r"\b(?:previous|last|prior)\s+(?:song|track|tune|one)\b|\bgo back(?: a| one)?(?: song| track)?\b|\bplay (?:the )?previous\b|^(?:previous|back|go back|previous one)$|\bplay that (?:one )?again\b|\bplay the last (?:song|one)\b|\bback a song\b")
_MUS_NOW = re.compile(r"\bwhat (?:song|track|music|tune|artist|band)\s+(?:is|s)\s+(?:this|that|playing|on)\b|\bwhat s playing\b|\bwhat is playing\b|\bwhat am i listening to\b|\bwhat are we listening to\b|\bwho (?:sings|is singing|plays|is playing|s singing|s playing|is this|is that|s this|s that)\b|"
                      r"\bname (?:of )?(?:this|the) (?:song|track)\b|\bwhat s (?:this|that) (?:song|track|tune)\b|\bwhat song is this\b|\bwhich song is this\b|\bwhat is this song\b|\bwho is this (?:artist|singer|band)\b|\bwhat s on\b(?=.*\b(?:music|spotify|speakers)\b)")
_MUS_NOT = re.compile(r"\b(?:wi ?fi|bluetooth|light|lights|lamp|heating|air conditioning|airplane mode|do not disturb|video|movie|film|series|show|episode|podcast|game|games|cards|chess|football|soccer|basketball|tennis|golf|role|part|trick|joke|prank|dumb|fool|safe|fair|nice|along|around|with fire|hooky|hard|ball|dead|house|favorites?|favourites?)\b")
_MUS_STRONG = {"play", "put on", "queue up", "queue", "spin", "blast", "listen to", "let me hear", "i want to hear", "i d like to hear", "hear", "i want to listen to", "i d like to listen to", "let s listen to", "cue up", "fire up"}
_ENGINES = r"(youtube|google|wikipedia|amazon|spotify|github|bing|duckduckgo|maps|google maps|apple maps|reddit|twitter|imdb|ebay|netflix)"
_WEB_SEARCH = re.compile(rf"^(?:search|look|find|check|google|browse|look up|find me|show me|get me|pull up|watch|search for)\s+(?:for\s+)?(?:on\s+|in\s+|using\s+|with\s+)?{_ENGINES}\s+(?:for\s+|about\s+|up\s+)?(.+)$|"
                         rf"^(?:search|look up|find|google|check)\s+(?:for\s+)?(.+?)\s+(?:on|in|using|with|at)\s+{_ENGINES}$|^(?:google|youtube)\s+(.+)$", re.I)
_WEB_OPENSEARCH = re.compile(rf"^(?:open|go to|go on|launch|take me to|bring up|pull up|visit)\s+{_ENGINES}(?:\.com)?\s+and\s+(?:search(?:\s+for)?|look(?:\s+up|\s+for)?|find|play|watch|show)\s+(.+)$", re.I)
_MAPS = re.compile(r"^(?:show|display|open|find|search|locate|get|bring up|pull up|look up|map|point out)\s+(?:me\s+)?(?:where\s+is\s+|where\s+s\s+|the\s+map of\s+|a\s+map of\s+|the\s+location of\s+)?(.+?)\s+(?:on|in|using|with)\s+(?:the\s+|google\s+|apple\s+)?maps?$|"
                   r"^(?:show|open|bring up|pull up)\s+(?:me\s+)?(?:the\s+)?map\s+(?:of|for|to)\s+(.+)$|^(?:directions|route|navigate|navigation|take me|guide me|drive me|get me|how (?:do i|can i|to) (?:get|go|drive|walk|travel|reach|ride|cycle))\s+(?:me\s+)?(?:to|from here to|towards|for)?\s*(.+)$|"
                   r"^(?:where is|where(?:'|’)?s|where can i find|where do i find|find|show me|locate)\s+(?:me\s+)?(?:the\s+)?(?:nearest|closest|nearby|a|an)\s+(.+?)(?:\s+(?:near me|nearby|around here|close by|near here|around me))?$", re.I)
_MAPS_NOT = re.compile(r"^(?:happiness|love|peace|myself|mind|keys?|phone|wallet|glasses|remote|charger|wifi|everything|nothing|my|your|his|her|the point|the problem|the time|the party)\b", re.I)
_PLACE_WORD = re.compile(r"\b(?:street|st|avenue|ave|road|rd|square|station|airport|hospital|university|college|center|centre|stadium|museum|park|port|harbor|restaurant|hotel|pharmacy|gas station|supermarket|bank|atm|cafe|bar|church|school|library|mall|market|city|town|beach|bridge|tower|cinema|theater|theatre|gym|post office|bus stop|parking|hospital|clinic|dentist|bakery|store|shop)\b", re.I)
_OPEN_STRONG = re.compile(r"^(?:open|launch|start|run|fire up|bring up|load|boot up|switch to|go to|show)\s+(?:up\s+)?(?:the\s+)?(?:app\s+|application\s+|program\s+)?(?:called\s+|named\s+)?(.+?)(?:\s+(?:app|application|program))?$", re.I)
_OPEN_SITE = re.compile(r"^(?:open|go to|go on|visit|take me to|bring up|pull up|browse to|navigate to|load)\s+(?:the\s+)?(?:website|web site|site|webpage|web page|page)\s+(?:of\s+|for\s+|called\s+|named\s+)?(.+)$|^(?:open|go to|visit|browse to|navigate to)\s+(?:https?://)?(?:www\.)?([\w\-]+\.[a-z]{2,}(?:/\S*)?)$", re.I)
_OPEN_WEAK = re.compile(r"^(?:go to|take me to|bring me to|navigate to)\s+(?:the\s+)?(.+)$", re.I)
_GENERIC_APP = {"it", "that", "this", "the door", "door", "window", "the window", "bed", "sleep", "work", "school", "home", "the shop", "the store", "the gym", "the bank", "the doctor", "the dentist", "lunch", "dinner", "my heart", "my mind",
                "your heart", "up", "down", "out", "away", "back", "the next one", "the bathroom", "the toilet", "the kitchen", "the car", "the room", "my account", "an account", "a window", "a tab", "a new tab", "the door for me", "me", "us", "them", "all", "everything"}


def _app_like(target: str) -> bool:
    """Il nome di un'app o di un sito e' corto e senza giri di frase: «open my heart to her» o «go to sleep, it's late» no."""
    t = target.strip(" .,!?")
    return 0 < len(t.split()) <= 3 and fold(t) not in _GENERIC_APP and not re.search(r"\b(?:to|for|when|while|because|if|so that|and then|but)\b", t, re.I)


# =============================================================================== file, liste, note, documenti
_DOC_KINDS = r"(?:text|essay|article|summary|poem|poetry|letter|e ?mail|email|story|tale|song|lyrics|speech|recipe|report|script|dialogue|biography|review|outline|abstract|paper|post|blog post|note|notes|cover letter|resume|cv|toast|joke|riddle|limerick|haiku|sonnet|paragraph|description|explanation|guide|tutorial|itinerary|plan|speech|presentation|lesson|lecture|exercise|exercises|quiz|story|fairy tale|fable|rap|verse|verses|chorus|dedication|message|card|greeting|invitation|document|doc|file|piece|writeup|write up|draft|proposal|agreement|contract|brief|pitch|manifesto|memo|minutes|transcript|analysis|essay)"
_WRITE = re.compile(rf"^(?:write|draft|compose|create|prepare|make|generate|produce|type up|put together|come up with|pen|author|whip up|knock out|craft|dictate|jot down)\s+(?:me\s+|up\s+)?(?:an?\s+|the\s+|some\s+)?(?:(?:short|long|brief|quick|simple|nice|good|beautiful|funny|formal|informal|detailed|little|new|full|complete|one page|one-page|two page|2 page|1 page|\d+ word|\d+-word)\s+)*({_DOC_KINDS})\s+(?:about|on|for|regarding|to|of|that|where|with|in which|describing|explaining|called|titled|named|from|:)?\s*(.+)$", re.I)
_WRITE2 = re.compile(rf"^(?:write|draft|compose|create|prepare|make|generate|produce|type up|put together|come up with|pen|whip up|craft)\s+(?:me\s+|up\s+)?(?:an?\s+|the\s+|some\s+)(?:(?:short|long|brief|quick|simple|nice|good|funny|formal|informal|detailed|little|new)\s+)*(?P<topic>[\w'’\- ]{{2,40}}?)\s+(?P<kind>{_DOC_KINDS})(?:\s+(?:in|into|to|inside)\s+(?:a\s+|the\s+|my\s+)?(?:new\s+)?(?:file|folder|document))?$", re.I)
_WRITE_TAIL = re.compile(r"[,;]?\s+(?:and\s+)?(?:then\s+)?(?:save|put|store|write|drop|copy|add|file)\s+(?:it|that|them|this)?\b.*$|\s+(?:and\s+)?(?:save|put|store)\s+(?:it|that|them)\b.*$|\s+(?:in|into|to|inside)\s+(?:a\s+|the\s+|my\s+)?(?:new\s+)?(?:file|folder|document|notes?)\b.*$", re.I)
_RESEARCH = re.compile(r"^(?:do|make|run|perform|conduct|carry out|start|give me|get me|i need|i want|i d like|please do)\s+(?:me\s+)?(?:some\s+|a\s+|a bit of\s+)?(?:quick\s+|short\s+|little\s+|thorough\s+|deep\s+|online\s+|web\s+)*research\s+(?:on|about|into|for|regarding|around)\s+(.+)$|"
                       r"^research\s+(?:on\s+|about\s+|into\s+)?(.+)$|^(?:look|dig)\s+into\s+(.+)$", re.I)
_RESEARCH0 = re.compile(r"^(?:do|make|run)\s+(?:some\s+|a\s+)?research(?:\s+(?:and|then)\s+(?:save|write|put)\s+(?:it|that))?$|^(?:research|do research)\s+(?:and\s+)?(?:save|write)\s+(?:it|that)$", re.I)
_LISTADD = re.compile(r"^(?:add|put|place|include|stick|throw|write|jot down|note|pop|set|insert|get)\s+(?:also\s+|too\s+)?(.+?)\s+(?:to|on|in|onto|into|at the end of|at the bottom of)\s+(?:the\s+|my\s+|our\s+|a\s+)?(?:(?:new\s+)?([a-z][\w' \-]{0,25}?)\s+)?(?:list|todo|to ?do)\b(?:\s+(?:called|named|for)\s+(.+))?$", re.I)
_LISTADD2 = re.compile(r"^(?:add|put|place|include|write|note|pop)\s+(?:also\s+|too\s+)?(.+?)\s+(?:to|on|in|onto|into)\s+(?:the\s+|my\s+|our\s+)?(shopping|groceries|grocery|to ?do|packing|wish|reading|movie|bucket|gift|errands|chores|wine|party|travel|camping|christmas)\b$", re.I)
_LISTADD3 = re.compile(r"^(?:i (?:need|have|must|got) to (?:buy|get|pick up|grab)|we (?:need|have to|must) (?:buy|get)|we (?:are|re) out of|i (?:am|m) out of|we (?:ran|have run) out of|i ran out of|we need|i need|don t forget (?:to (?:buy|get))?|remember to (?:buy|get)|buy|get|pick up)\s+(.+?)(?:\s+(?:from|at) the (?:store|shop|supermarket|market))?$", re.I)
_LISTBARE = re.compile(r"^(?:add|also add|and add|and also|also)\s+(?!(?:on|up|off|in|out|down|away|back|it|that|this|them|something|anything|a reminder|an event)\b)(.+)$", re.I)
_NOTE = re.compile(r"^(?:make|take|save|write|jot|add|create|leave|record|log|save|start)\s+(?:down\s+)?(?:a\s+|an\s+|this\s+|that\s+|me\s+a\s+)?(?:quick\s+|short\s+|new\s+|voice\s+)?(?:note|memo)(?:\s+(?:to myself|for later|of this|about|saying|that says|that|reading|:))?[\s:,\-]*(.*)$|"
                   r"^(?:note\s+(?:down|this|that)|jot\s+(?:down|this)|write\s+(?:this\s+)?down|take\s+note|note)\s*[:,\-]?\s*(?:that\s+)?(.+)$", re.I)
_READ_BARE = re.compile(r"^(?:read|tell|give|show)\s+(?:me\s+)?(?:back\s+)?(?:my\s+|the\s+)?(notes?|shopping list|grocery list|groceries|to[- ]?do list|list|lists|memos?)\b$|^what(?:['’]?\s?s| is)\s+(?:on|in)\s+(?:my|the)\s+(shopping list|grocery list|groceries list|to[- ]?do list|list|notes?)\b|^what\s+(?:do\s+i|have\s+i|do\s+we|have\s+we)\s+(?:have|got|put)\s+(?:on|in)\s+(?:my|the|our)\s+(shopping list|grocery list|groceries list|to[- ]?do list|list|notes?)\b|^what(?:\s+do\s+i\s+need|\s+should\s+i|\s+do\s+we\s+need)\s+to\s+(?:buy|get|pick up)\b()|^what\s+(?:do\s+(?:i|we)\s+(?:need|have)|is)\s+(?:left\s+)?(?:to\s+)?(?:buy|get)\b()", re.I)
_READ = re.compile(r"^(?:read|read out|read aloud|read back|open and read|play)\s+(?:me\s+)?(?:out\s+)?(?:the\s+|my\s+)?(?:file|document|note|text|list|doc)\s+(?:called\s+|named\s+)?(.+)$|^(?:read|read out)\s+(?:me\s+)?(?:out\s+)?(?:the\s+)?(.+?)\s+(?:file|document|doc)$", re.I)
_SUMMARIZE = re.compile(r"^(?:summari[sz]e|sum up|give me a summary of|give me the gist of|tl;?dr|recap|boil down|condense)\s+(?:the\s+|my\s+)?(?:file|document|doc|note|text|pdf)?\s*(?:called\s+|named\s+)?(.+)$", re.I)
_LS = re.compile(r"\b(?:what|which|how many)\s+(?:files?|documents?|notes?)\b.*\b(?:folder|do i have|have you|are there|in there|in it|do you have)\b|\b(?:list|show|what s in|whats in|what is in)\s+(?:me\s+)?(?:all\s+)?(?:the\s+|my\s+|your\s+)?(?:files?|documents?|folder)\b|\bwhat(?:s| is) in (?:the |your |my )?folder\b|\bwhat files\b")
_OPENDIR = re.compile(r"\b(?:open|show|reveal|go to)\b.*\b(?:the |your |my )?(?:aria )?folder\b")
_DOC_Q1 = re.compile(r"^(?:in|from)\s+(?:the\s+|my\s+)?(?:file|document|pdf|doc|text|contract|manual|book|article)\s+(.+?)\s*[,:]\s*(.+)$", re.I)
_DOC_Q3 = re.compile(r"^(?:what|what does|what do)\s+(?:does\s+)?(?:the\s+|my\s+)?(?:file|document|pdf|doc|contract|text)\s+(.+?)\s+say\s+(?:about|on|regarding|concerning)\s+(.+)$", re.I)
_DOC_CUE = re.compile(r"\b(?:file|document|pdf|word|docx|contract|bill|invoice|manual|book|article|notes|report|thesis|lecture|handout|minutes|quote|receipt|policy|clause|lease|agreement|chapter|paper|syllabus|resume|cv)\b")
_DOC_ASK = re.compile(r"\b(?:what|when|where|who|how|which|why|how much|how many|does it say|do they say|say|says|said|is written|mention|mentions|state|states|tell me|check|find|look for|according to|is there|summary|explain|read)\b")
_DOC_DEIXIS = re.compile(r"\b(?:this|that|the)\s+(?:document|file|pdf|contract|text|article|book|manual|report|paragraph|chapter|lease|agreement|policy|clause|paper)\b")
_REAL_WORLD = re.compile(r"\b(?:on|in)\s+(?:the\s+)?(?:wall|sign|poster|billboard|shirt|t shirt|label|package|box|board|banner|bottle|gate|mug|street|plaque|window|bar|shop|restaurant|door|menu)\b")
_DOC_SAYS = re.compile(r"\bwhat does it say\b|\bwhat does (?:it|that|this) say\b|\bwhat s written\b|\bwhat is written\b|\bit says\b|\bwhere does it say\b")

# ---- schermo
_SCR_NOUN = r"(?:button|key|menu|item|tab|option|link|icon|field|box|checkbox|word|title|name|number|text|label|setting|settings|toggle|switch|slider|bar|menu item|entry|section|heading)"
_SCR_WHERE = r"(?:(?:right\s+)?(?:here\s+)?(?:on|in)\s+(?:my\s+|the\s+|this\s+)?(?:screen|computer|mac|desktop|monitor|display|page|window|app|site|website)|here|on screen|onscreen)"
_SCR_WHERE_RX = re.compile(r"\b" + _SCR_WHERE + r"$|\b(?:on|in)\s+(?:my\s+|the\s+|this\s+)?(?:screen|computer|mac|desktop|monitor|display|page|window)\b")
_SCR_FIND = [
    re.compile(rf"^(?:(?:but|hey|listen|aria|sorry)\s+)*(?:i\s+can(?:'|’)?t\s+(?:find|see|locate)|i\s+cannot\s+(?:find|see|locate)|i\s+don(?:'|’)?t\s+see|where(?:'|’)?s|where\s+is|where\s+can\s+i\s+(?:find|see)|where\s+do\s+i\s+(?:find|see)|"
               rf"(?:show|point|point out|tell|help)\s+me\s+(?:where\s+(?:is|s)|where|to find|how to find))\s*(?:the\s+|a\s+|an\s+|that\s+|this\s+)?(?P<t>.+?)(?:\s+(?:is|are))?(?:\s+{_SCR_WHERE})?$", re.I),
    re.compile(rf"^(?:(?:ok|but|hey|well|aria|sorry)\s+)*(?:(?:can|could) you\s+)?(?:find|locate|highlight|point (?:out|to|at)|show|mark)\s+(?:me\s+)?(?:the\s+|a\s+|an\s+|that\s+|this\s+)?(?P<t>.+?)\s+{_SCR_WHERE}$", re.I),
    re.compile(rf"^(?:how\s+(?:do|can)\s+i|where\s+do\s+i|where\s+can\s+i)\s+(?:find|access|open|see)\s+(?:the\s+)?(?:{_SCR_NOUN}\s+)?(?:called\s+|labeled\s+|that says\s+)?(?P<t>.+)$", re.I),
    re.compile(rf"^(?:how\\s+(?:do|can)\\s+i|where\\s+do\\s+i|where\\s+can\\s+i)\\s+(?:get to|reach)\\s+(?:the\\s+)?(?:{_SCR_NOUN}\\s+)?(?:called\\s+|labeled\\s+|that says\\s+)?(?P<t>(?=.*\\b(?:button|menu|tab|option|settings?|preferences|icon|panel|section|toolbar|sidebar|field|link|window|screen|page)\\b).+)$", re.I),
    re.compile(r"^(?:where\s+(?:do\s+i|should\s+i|can\s+i)\s+(?:click|press|tap|touch|hit|select)|which\s+(?:button|key|icon|link|item|option|menu item)\s+(?:do\s+i|should\s+i|can\s+i)\s+(?:click|press|tap|touch|hit|use|select))\s+(?:to|if i want to|in order to)\s+(?P<t>.+)$", re.I),
]
_SCR_SOFT = [re.compile(rf"^(?:(?:ok|but|hey|well|aria|sorry|so)\s+)*(?:(?:can you\s+)?(?:tell|show|point out)\s+me\s+)?(?:where\s+(?:does it say|is it written|do you see|can you see|is the word|is the text|is the phrase|do you find|can i see)|where(?:'|’)?s the word|where(?:'|’)?s the text)\s+(?:the (?:word|text|phrase)\s+)?[\"“']?(?P<t>.+?)[\"”']?(?:\s+{_SCR_WHERE})?$", re.I)]
_SCR_ALL = re.compile(rf"^(?:(?:ok|but|hey|well|aria|sorry)\s+)*(?:show|point out|highlight|find|mark)\s+(?:me\s+)?(?:all\s+(?:the\s+)?|every\s+)(?:places|spots|occurrences|instances|times|points|lines)\s+(?:where|that|which|with)\s+(?:(?:it\s+says|there(?:'|’)?s|you see|it is written|appears?|is written|shows?)\s+)?(?:the\s+(?:word|text|phrase)\s+)?[\"“']?(?P<t>.+?)[\"”']?(?:\s+{_SCR_WHERE})?$", re.I)
_SCR_POINT = re.compile(r"^(?:(?:ok|but|hey|well|aria|sorry)\s+)*(?:(?:can you|could you)\s+)?(?:point it out|point to it|point at it|show me where|show me where exactly|highlight it|mark it|show it to me|show me|where exactly|where is it exactly|point to where|can you point)(?:\s+(?:on the screen|with a circle|please|now|again))*$", re.I)
_SCR_CUE = re.compile(r"\b(?:on (?:the |my )?screen|on my display|(?:on )?this (?:screen|page|window)|what(?:'|’)?s on (?:the |my )?screen|what i(?:'|’)?m (?:looking at|reading|seeing|doing|working on)|what (?:you|do you) see|what you can see|what(?:'|’)?s here|on screen|on the page|on this page|on the display)\b", re.I)
_SCR_REQ = re.compile(r"\b(?:can you|could you|please|tell me|show me|give me|read|look|check|describe|explain|summari[sz]e|translate|help|what|how|where|which|is there|do you|are there|would you|will you|let me|i need|i want|i d like)\b", re.I)
_SCR_NOT = re.compile(r"\b(?:print|turn off|switch off|close|lower|raise|brightness|dim|broken|cracked|lock|share|record|screenshot|capture|screen ?saver|screen time|i (?:looked|saw|read) (?:at )?(?:the|my)|phone screen|tv screen|full screen|blue screen|black screen|screen ?shot|split screen|touch screen|screen protector|cinema screen|big screen)\b", re.I)
_SCR_DEIXIS = re.compile(r"\b(?:this|that|these|those)\s+(?:error|message|alert|warning|popup|pop up|window|page|site|website|article|e ?mail|mail|chart|graph|table|image|picture|photo|screen|button|menu|app|program|form|link|post|notification|video|invoice|data|diagram|slide|presentation|screenshot|dialog|prompt|text|sentence|paragraph|code|list|number|result|tweet|comment|review|ad|advert|spreadsheet|dashboard|log|stack trace|exception)\b", re.I)
_SCR_DEIXIS_STRONG = re.compile(r"\b(?:this|that)\s+(?:error|alert|warning|popup|pop up|window|screen|button|notification|dialog|prompt|exception|stack trace)\b", re.I)
_SCR_DEIXIS_WEAK = re.compile(r"\b(?:this|that)\s+(?:text|sentence|paragraph|title|code|list|number|result)\b", re.I)
_SCR_DOCNOUN = re.compile(r"\b(?:file|document|pdf|contract|bill|lecture|manual|report|thesis|minutes|quote|receipt|policy|recipe)\b", re.I)
_SCR_ASKV = re.compile(r"\b(?:summari[sz]e|summary|explain|translate|read|what does .{1,40} mean|what(?:'|’)?s .{1,30} mean|what does (?:it|this|that) say|what(?:'|’)?s (?:it|this|that) say|what do you think|what do you make|is (?:it|this|that) (?:clear|correct|right|ok|okay|good|fine|safe|legit|real|true|wrong)|describe|analy[sz]e|comment|review|judge|correct|check|help|any thoughts|thoughts on|your (?:opinion|view|take)|what is (?:it|this|that)|what(?:'|’)?s (?:this|that)|tell me about)\b", re.I)
_SCR_BARE = re.compile(r"^(?:(?:ok|but|hey|well|aria|sorry|please)\s+)*(?:(?:can you\s+|could you\s+)?(?:please\s+)?(?:look at|take a look at|have a look at|check|read|describe|summari[sz]e|scan)\s+(?:the |my |this )?(?:screen|display|page|window|screenshot)|what(?:'|’)?s on (?:the |my )?screen|what(?:'|’)?s on my (?:display|monitor)|"
                       r"what (?:do you see|can you see|am i (?:looking at|reading|seeing)|is (?:on|there on) (?:the |my )?screen|are you seeing)(?: here| on the screen| on my screen)?|what do you see here|(?:can|could) you see (?:the |my )?screen)$", re.I)
_SCR_POINTWORD = re.compile(r"\b(?:point|show|highlight|find|locate|mark|indicate|where)\b", re.I)
_SCR_THING = re.compile(r"\b(?:word|button|key|icon|link|menu|text|label|screen|page|field|tab|option|setting)\b", re.I)


def _peel_noun(t: str) -> str:
    """«Export button» -> «Export», «button called Export» -> «Export», «Settings menu» -> «Settings»: si cerca il nome, non la categoria."""
    u = re.sub(rf"^{_SCR_NOUN}\s+(?:called|named|labell?ed|that says|saying|with|to|for)\s+", "", t, flags=re.I)
    if len(u.split()) > 1 and re.search(rf"\s{_SCR_NOUN}$", u, re.I):
        u = re.sub(rf"\s+{_SCR_NOUN}$", "", u, flags=re.I)                              # «settings icon» -> «settings»
    elif len(u.split()) > 1:
        u = re.sub(rf"^{_SCR_NOUN}\s+", "", u, flags=re.I)                              # «button Export» -> «Export»
    return u.strip(" .,;:!?\"'")


def _span_t(raw: str, m, grp: str = "t") -> str:
    return raw[m.start(grp):m.end(grp)].strip(" .,;:!?\"'«»“”")


def _last_sentence(text: str) -> str | None:
    parts = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]
    if len(parts) >= 2 and sum(len(p.split()) for p in parts[:-1]) <= 8:
        return parts[-1]
    return None


_QUESTION_START = re.compile(r"^(?:what|why|how|which|when|where|who|whom|whose|is|are|was|were|do|does|did|will|would|could|should|can|may|might)\b")


def screen_attempt(text: str) -> tuple[str, str, bool] | None:
    """Chiede di indicare/trovare qualcosa «sullo schermo» ma nessuna regola l'ha capita: il chatbot, lasciato solo, direbbe «I'll point it out right away» senza fare niente."""
    c = canonical(text)
    t = normalize(c)
    if not t or len(t.split()) > 30 or _SCR_NOT.search(t):
        return None
    if _SCR_POINTWORD.search(t) and _SCR_THING.search(t) and re.search(r"\b(?:screen|page|window|display|here)\b", t):
        return ("screen", "\"I can't find the Export button\" or \"where is the Save button\"", False)
    return None


def screen_request(text: str, screen_on: bool = False) -> ToolCall | None:
    """«I can't find the Export button» -> SCHERMO(dove|Export); «what do you see on the screen?» -> SCHERMO(leggi|); «what do you think of this chart?» -> SCHERMO(parere|<la frase>).
    Serve un riferimento esplicito allo schermo (o a «what I'm looking at»): «where is Rome?» e «what do you think of my cousin?» non sono richieste sullo schermo."""
    last = _last_sentence(text)
    cands = [(raw, fold(raw).strip(" .!?")) for raw in (canonical(text), text.strip()) + ((canonical(last), last) if last else ())]
    cands = [(r, f) for r, f in cands if f and len(f.split()) <= 40]
    for raw, f in cands:
        for rx in (_SCR_FIND + _SCR_SOFT if screen_on else _SCR_FIND):
            m = rx.match(raw.strip(" .!?")) or rx.match(f)
            if m:
                t = _span_t(raw.strip(" .!?"), m) if m.string == raw.strip(" .!?") else _span_t(f, m)
                t = re.sub(r"^(?:the|a|an)\s+", "", t, flags=re.I)
                t = re.sub(r"[\s,;:]*\b(?:please|thanks|thank you)\W*$", "", t, flags=re.I).strip(" .,;:!?")
                t = re.sub(r"^(?:all\s+(?:the\s+)?(?:places|spots)\s+(?:where|that)\s+(?:it\s+says\s+)?)", "", t, flags=re.I)
                t = _peel_noun(t)
                if rx in (_SCR_FIND[0], _SCR_FIND[1]) and not (_SCR_WHERE_RX.search(f) or re.search(rf"\b{_SCR_NOUN}\b", f)):
                    continue                                                                     # «where is Rome?», «I can't find my keys»: niente a che fare con lo schermo
                if rx in _SCR_SOFT and re.search(r"\b(?:document|file|pdf|contract|manual|in the text|recipe)\b", t, re.I):
                    continue
                if t and len(t.split()) <= 6 and not re.match(r"^(?:it|that|this|here|there|everything|nothing|something|anything)$", t, re.I):
                    return ToolCall("SCHERMO", f"dove|{t}")
    for raw, f in cands:
        m = _SCR_ALL.match(raw.strip(" .!?"))
        if m:
            t = _span_t(raw.strip(" .!?"), m)
            if t and len(t.split()) <= 6:
                return ToolCall("SCHERMO", f"dove|{t}")
    for _raw, f in cands:
        given = bool(re.search(r"[:\"“]", _raw))
        if given and not screen_on:
            continue
        deixis = _SCR_DEIXIS.search(f) if screen_on else _SCR_DEIXIS_STRONG.search(f)
        if (deixis or (screen_on and _SCR_DEIXIS_WEAK.search(f) and not given)) and _SCR_ASKV.search(f) and not _SCR_NOT.search(f) and not _SCR_DOCNOUN.search(f):
            return ToolCall("SCHERMO", f"parere|{text.strip(' .!?')}")
    if any(_SCR_POINT.match(f) for _r, f in cands):
        return ToolCall("SCHERMO", "indica|")
    if any(_SCR_BARE.match(f) for _r, f in cands):
        return ToolCall("SCHERMO", "leggi|")
    for _raw, f in cands:
        if _SCR_CUE.search(f) and not _SCR_NOT.search(f) and (text.rstrip().endswith("?") or _SCR_REQ.search(f)):
            return ToolCall("SCHERMO", f"parere|{text.strip(' .!?')}")
    return None


# =============================================================================== file
def file_request(text: str) -> tuple[str, str | None] | None:
    """«write the recipe for carbonara in a file», «in a file in the folder, write me the story of Rome»: una richiesta di SCRIVERE UN DOCUMENTO nella cartella, comunque sia ordinata la frase.
    Restituisce (tipo, argomento): senza argomento («write all of that to a file») l'argomento e' None e significa «quello di cui stavamo parlando»."""
    raw = canonical(text)
    f = fold(raw)
    if not re.search(r"\b(?:file|folder|document)\b", f) or re.search(r"\b(?:i|we)\s+(?:have\s+)?(?:already\s+)?(?:put|saved|written|created|copied|added)\b", f):
        return None
    if not re.search(r"\b(?:write|save|put|create|prepare|copy|store|draft|make|type|add|dump|drop)\b", f):
        return None
    km = re.search(rf"\b({_DOC_KINDS})\b", f)
    dest = re.sub(r"\b(?:in|into|to|inside|within|on)\s+(?:a\s+|the\s+|my\s+|your\s+|new\s+)*(?:file|folder|document)s?(?:\s+(?:in|inside|within|of)\s+(?:the\s+|my\s+|your\s+)?(?:folder|aria folder))?", " ", raw, flags=re.I)
    body = re.sub(r"\s+", " ", dest).strip(" .,;:!?")
    if not km or not re.search(rf"\b({_DOC_KINDS})\b", body, re.I):
        return ("text", None) if re.search(r"\b(?:that|this|it|all of that|everything|all that|the whole thing|the recipe|the research|the story|what you (?:just )?said|what we (?:just )?(?:said|discussed))\b", f) else None
    m = re.search(rf"\b({_DOC_KINDS})\b\s*(?:about|on|for|regarding|of|to|:)?\s*(.*)$", body, re.I)
    if not m:
        return ("text", None)
    kind, topic = m.group(1).lower(), m.group(2).strip(" .,;:!?")
    if len(topic) < 3:                                                                    # «write me the carbonara recipe in a file»: l'argomento sta prima
        before = re.sub(r"^(?:write|save|put|create|prepare|copy|store|draft|make|type|add|dump|drop)\s+(?:me\s+|up\s+)?(?:an?\s+|the\s+|some\s+|my\s+|all\s+(?:of\s+)?(?:the\s+)?)?(?:(?:short|long|brief|quick|simple|nice|good|funny|formal|detailed|little|new|whole|full|complete)\s+)*", "", body[:m.start(1)].strip() + " ", flags=re.I).strip(" ,.;:")
        before = "" if re.fullmatch(r"(?:the|a|an|my|some|all|me)", before, re.I) else before
        if 1 <= len(before.split()) <= 3 and not re.search(r"\b(?:that|this|it|them|everything|all|what|you|we|said|just)\b", before, re.I):
            return (kind, before)
    topic = _WRITE_TAIL.sub("", topic).strip(" .,;:!?")
    if len(topic) < 3 or re.search(r"\b(?:that|this|it|what you said|what we said|everything|all of it|you just said)\b", topic, re.I) and len(topic.split()) <= 4:
        return (kind, None)
    return (kind, topic)


def _file_intent(raw: str, files: list[str] | None = None) -> ToolCall | None:
    """Gli strumenti della cartella di Aria. Gli argomenti si prendono dal testo originale, non da quello normalizzato."""
    ft = raw.strip(" .!?")
    mn = _NOTE.match(ft)
    if mn and not _TIMEWORD.search(normalize(ft)) or (mn and re.search(r"\b(?:note|memo)\b", ft, re.I)):
        body = next((g for g in mn.groups() if g), "") if mn else ""
        body = body.strip(" .,;:!?")
        if re.fullmatch(r"(?:for\s+\w+|about\s+\w+(?:\s+\w+)?|please|thanks)?", body.lower()):
            body = ""
        return ToolCall("NOTA", body)
    fr = file_request(raw)
    if fr and fr[1]:
        return ToolCall("SCRIVI", f"{fr[0]}|{fr[1]}")
    m = _WRITE.match(ft)
    if m:
        topic = _WRITE_TAIL.sub("", m.group(2)).strip(" .,;:!?")
        if topic and not re.match(r"^(?:down|this|that|it|them)\b", topic, re.I):
            return ToolCall("SCRIVI", f"{m.group(1).lower()}|{topic}")
    m = _WRITE2.match(ft)
    if m and len(m.group("topic").split()) <= 4 and not re.match(r"^(?:down|this|that|it|them|me|us|up)\b", m.group("topic"), re.I) and not re.search(r"\b(?:and|to|for|about|on|of|in|with|that)\b", m.group("topic"), re.I):
        return ToolCall("SCRIVI", f"{m.group('kind').lower()}|{m.group('topic').strip()}")
    if _RESEARCH0.match(ft):
        return ToolCall("RICERCA", "")
    m = _RESEARCH.match(ft)
    if m:
        topic = next(g for g in m.groups() if g)
        return ToolCall("RICERCA", _WRITE_TAIL.sub("", topic).strip(" .,;:!?"))
    ftq = re.sub(r"[\"“”«»]", " ", ft)
    mrb = _READ_BARE.match(ft)
    if mrb:
        which = next((g for g in mrb.groups() if g), "").lower().replace("-", " ").strip()
        if not which or "shopping" in which or "grocer" in which or which in ("list", "lists"):
            return ToolCall("LEGGI", "shopping list")
        return ToolCall("LEGGI", "to-do list" if re.fullmatch(r"to ?do list", which) else "notes")
    m = _LISTADD.match(re.sub(r"[,;]\s*(?:because|since|so|for|we|i)\b.*$", "", ftq, flags=re.I))
    if m:
        which = (m.group(2) or m.group(3) or "shopping").lower().strip()
        which = {"groceries": "shopping", "grocery": "shopping", "to do": "todo"}.get(which, which)
        return ToolCall("LISTA", f"{which}|{m.group(1).strip()}")
    m = _LISTADD2.match(ftq)
    if m:
        which = m.group(2).lower()
        which = {"groceries": "shopping", "grocery": "shopping", "to do": "todo", "todo": "todo"}.get(which, which)
        return ToolCall("LISTA", f"{which}|{m.group(1).strip()}")
    if files is not None and any("shopping" in normalize(f) or "grocer" in normalize(f) for f in files):
        mb = _LISTBARE.match(ftq)
        if mb and 0 < len(mb.group(1).split()) <= 5 and not re.search(r"\b(?:to taste|pinch|dash|teaspoons?|tablespoons?|tsp|tbsp|cups? of|calendar|agenda|reminder|note|music|volume|timer|alarm|folder|file|document|appointment|event|a ?ok|in order)\b", mb.group(1), re.I):
            return ToolCall("LISTA", f"shopping|{mb.group(1).strip()}")
    m = _READ.match(ft)
    if m:
        return ToolCall("LEGGI", next(g for g in m.groups() if g).strip(" .,;:!?"))
    m = _SUMMARIZE.match(ft)
    if m and files is not None:
        name = m.group(1).strip(" .,;:!?")
        if match_file(name, files):
            return ToolCall("RIASSUMI", name)
    if _LS.search(normalize(ft)):
        return ToolCall("ELENCO", "")
    if _OPENDIR.search(normalize(ft)):
        return ToolCall("APRI", "")
    return None


# =============================================================================== i poteri sul Mac
def _music_ok(verb: str, lead: str, target: str) -> bool:
    """«play Bohemian Rhapsody» si', «play a prank» no: con «play» serve un titolo/artista (maiuscole), un genere o la parola musica."""
    t = fold(target).strip(" .!?")
    if _MUS_NOT.search(t) or not t:
        return False
    if re.search(r"\b(?:something|anything|some music|music|songs?|tunes?|tracks?|playlist|album|stuff)\b", t) and len(t.split()) <= 6:
        return True
    if any(g == t or t.endswith(" " + g) or t.startswith(g + " ") for g in _MUS_GENRES):
        return True
    if verb.lower() in _MUS_STRONG and verb.lower() not in ("play", "put on", "hear", "give me", "get me") and not re.search(r"\b(?:to|the)\b", t.split()[0]):
        return len(t.split()) <= 8
    return bool(re.match(r"[A-Z0-9]", target.strip())) and len(t.split()) <= 8 and not re.search(r"\b(?:with|for|against|at|when|while|because|if|and then|to the|the (?:game|piano|guitar|violin|drums))\b", t)


def _place_ok(folded: str, original: str) -> bool:
    return bool(_PLACE_WORD.search(folded) or re.match(r"[A-Z]", original.strip()))


def _power_intent(raw: str, files: list[str] | None = None) -> ToolCall | None:
    """Gli strumenti sul Mac. Gli argomenti si prendono dal testo originale (maiuscole, apostrofi, virgole)."""
    ft = raw.strip(" .!?")
    t = normalize(ft)
    # ---- prima i comandi il cui testo conta per intero (shortcuts, eventi, promemoria, documenti)
    if _SC_LIST.search(t):
        return ToolCall("SCORCIATOIE", "")
    m = _SC_RUN2.match(ft)
    if m:
        return ToolCall("SCORCIATOIA", (m.group(1) or m.group(2)).strip(_Q))
    if re.search(r"\bshortcut\b", t) and not re.search(r"\b(?:keyboard|key|windows|excel|word|chrome|desktop|home screen|cut|shortcut to)\b", t):
        m = _SC_RUN.match(ft)
        if m and len(m.group(1).split()) <= 6:
            return ToolCall("SCORCIATOIA", re.sub(r"\s+shortcut$", "", m.group(1), flags=re.I).strip(_Q))
    m = _EVENT_ADD.match(ft)
    if m and not _EVENT_NOT.search(fold(m.group(1))):
        return ToolCall("EVENTO", (m.group(1) + " " + (m.group(2) or "")).strip(" .,;:!?"))
    m = _EVENT_CREATE.match(ft)
    if m and m.group(1).strip():
        return ToolCall("EVENTO", m.group(1).strip(" .,;:!?"))
    m = _EVENT_SCHED.match(ft)
    if m and not _EVENT_NOT.search(fold(m.group(1))) and re.search(r"\b(?:meeting|appointment|call|lunch|dinner|visit|event|interview|session|class|lesson|party|check ?up|exam|review|presentation|conference|workshop|date|haircut|dentist|doctor|trip)\b", fold(m.group(1))) \
            and parse_when(m.group(1), dt.datetime.now()) is not None:
        return ToolCall("EVENTO", m.group(1).strip(" .,;:!?"))
    m = _REMIND.match(ft)
    if m:
        body = m.group(1).strip(" .,;:!?")
        rel = re.match(r"^in\s+(?:an?|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty|forty five|sixty|\d+|half an?|a quarter of an?)(?:\s+and\s+a\s+half)?\s+(?:second|minute|hour)s?\b", fold(body))
        if not rel:
            return ToolCall("PROMEMORIA", body)
    if _REMIND_LIST.search(t) and not re.match(r"^(?:add|create|put|set|make|remind)", t):
        return ToolCall("PROMEMORIA_LISTA", "")
    for pat in (_DOC_Q1,):
        m = pat.match(ft)
        if m and (files is None or match_file(m.group(1), files)):
            return ToolCall("DOCUMENTO", f"{m.group(1).strip()}|{m.group(2).strip()}")
    m = _DOC_Q3.match(ft)
    if m:
        return ToolCall("DOCUMENTO", f"{m.group(1).strip()}|What does it say about {m.group(2).strip()}?")
    says = _DOC_SAYS.search(t)
    if files and ((_DOC_CUE.search(t) and _DOC_ASK.search(t)) or says):
        hit = match_file(t, files)
        on_screen = bool(_SCR_CUE.search(t) or re.search(r"\b(?:screen|computer|mac|desktop|monitor)\b", t) or _REAL_WORLD.search(t))
        if hit is None and (_DOC_DEIXIS.search(t) or says) and not on_screen:
            docs = [f for f in files if f.lower().endswith((".pdf", ".docx"))]
            hit = (docs or files)[0]
        if hit:
            return ToolCall("DOCUMENTO", f"{os.path.splitext(hit)[0]}|{ft}")
    # ---- da qui in poi conta solo il comando
    ft0, t0 = ft, t
    music_app = ""
    ma = _MUS_APP.search(ft)
    if ma and re.search(r"\b(?:music|songs?|tracks?|playlist|album|play|put on|listen|resume|pause)\b", ft[:ma.start()], re.I):
        music_app = "Spotify" if "spotify" in fold(ma.group(1)) else "Music"
        ft = ft[:ma.start()]
        t = normalize(ft)
    if _BRIEFING.search(t0):
        return ToolCall("BRIEFING", "")
    if (_AGENDA_Q.search(t0) and _AGENDA_WORD.search(t0) or _AGENDA_IMPLIED.search(t0) and _DAYPHRASE.search(t0)) and not _AGENDA_NOT.search(t0):
        from . import everyday_en as ev
        wp = ev.when_phrase(ft0)
        if re.search(r"\bweekend\b", wp or t0):
            return ToolCall("AGENDA", "weekend")
        if re.search(r"\b(?:this week|next week|the week|coming week|upcoming week|next few days|coming days|this week s)\b", t0):
            return ToolCall("AGENDA", "settimana")
        return ToolCall("AGENDA", wp or "today")
    mfree = re.search(r"\bam i (?:free|busy|available)\b", t0)
    if mfree:
        from . import everyday_en as ev
        wp = ev.when_phrase(ft0)
        if wp:
            return ToolCall("AGENDA", "weekend" if "weekend" in wp.lower() else wp)
    # volume (prima della musica: «turn the music down» e' il volume)
    m = _VOL_SET.search(t)
    if m and not re.search(r"\b(?:timer|alarm|brightness|heating|temperature|degrees|thermostat|mic|microphone)\b", t):
        word = next((g for g in m.groups() if g), None)
        if word is None:
            word = "max" if re.search(r"\bmax|full\b", t) else "min" if re.search(r"\bmin|lowest\b", t) else "half" if "half" in t else "zero"
        word = re.sub(r"\s*(?:percent|per cent)$", "", word)
        n = int(word) if word.isdigit() else _VOLWORDS.get(word.split()[0], number_en(word))
        if n is not None:
            return ToolCall("VOLUME", f"set:{max(0, min(100, n))}")
    if _VOL_UNMUTE.search(t):
        return ToolCall("VOLUME", "unmute")
    if _VOL_MUTE.search(t) and "microphone" not in t and "mic" not in t.split():
        return ToolCall("VOLUME", "mute")
    past = re.search(r"\b(?:was|were|yesterday|last night|last week|last time|earlier|used to)\b", t)      # «the music was too loud last night»: un racconto, non una richiesta
    if not past:
        if _VOL_UP.search(t) and not re.search(r"\b(?:heat|heating|temperature|brightness|oven|thermostat|light|lights)\b", t):
            return ToolCall("VOLUME", "up")
        if _VOL_DOWN.search(t) and not re.search(r"\b(?:heat|heating|temperature|brightness|oven|thermostat|light|lights)\b", t):
            return ToolCall("VOLUME", "down")
    if _VOL_GET.search(t):
        return ToolCall("VOLUME", "get")
    # musica
    app = f"|{music_app}" if music_app else ""
    m = _MUS_NAMED.match(ft)
    if m and not _MUS_NOT.search(t) and not re.match(r"(?:on|in|at|off)\b", m.group(2).strip(), re.I):          # «put the song on pause»: «on pause» non e' un titolo
        return ToolCall("MUSICA", f"{'playlist' if m.group(1).lower() == 'playlist' else 'track'}:{m.group(2).strip(_Q)}{app}")
    if _MUS_PLAY.match(ft.lower().strip()):
        return ToolCall("MUSICA", "play" + app)
    if _MUS_PAUSE.search(t) and not re.search(r"\b(?:timer|alarm|video|movie|game|podcast|download|recording)\b", t):
        return ToolCall("MUSICA", "pause" + app)
    if _MUS_NEXT.search(t) and not re.search(r"\b(?:slide|page|tab|episode|photo|picture|email|message|reminder|meeting|appointment|step|question|week|month|year|bus|train|flight)\b", t):
        return ToolCall("MUSICA", "next" + app)
    if _MUS_PREV.search(t) and not re.search(r"\b(?:slide|page|tab|episode|photo|picture|email|message|step|question|screen|window)\b", t):
        return ToolCall("MUSICA", "previous" + app)
    if _MUS_NOW.search(t):
        return ToolCall("MUSICA", "now" + app)
    m = _MUS_PLAY_X.match(ft)
    if m and re.search(r"\b(?:timer|alarm|stopwatch|countdown|reminder|video|movie|game|podcast|youtube)\b", t):
        m = None
    if m:
        what = re.sub(r"\s+on$", "", m.group(2).strip(_Q), flags=re.I)                 # «put some jazz on»
        norm_what = fold(what)
        if norm_what in ("spotify", "apple music", "music", "itunes", "youtube music", "the music app", "the spotify app", "music app"):
            return ToolCall("APRI_APP", "Music" if "music" in norm_what or "apple" in norm_what else "Spotify")
        if _music_ok(m.group(1), "", what):
            what = re.sub(r"^(?:the\s+|some\s+|a\s+)", "", what, flags=re.I) if not re.match(r"[A-Z]", what) else what
            if re.fullmatch(r"(?:something|anything|some music|music|songs?|tunes?|tracks?|stuff|something good|something nice|something relaxing|something chill)", fold(what)):
                return ToolCall("MUSICA", "play" + app)
            return ToolCall("MUSICA", f"track:{what}{app}")
    m = _WEB_SEARCH.match(ft)
    if m:
        g = m.groups()
        if g[0]:
            return ToolCall("WEB", f"{fold(g[0])}|{g[1].strip(_Q)}")
        if g[2]:
            return ToolCall("WEB", f"{fold(g[3])}|{g[2].strip(_Q)}")
        return ToolCall("WEB", f"{fold(ft.split()[0])}|{g[4].strip(_Q)}")
    m = _WEB_OPENSEARCH.match(ft)
    if m:
        return ToolCall("WEB", f"{fold(m.group(1))}|{m.group(2).strip(_Q)}")
    m = _MAPS.match(ft)
    if m:
        place = next((g for g in m.groups() if g), "").strip(_Q)
        place = re.sub(r"\s+(?:from here|from my location|from where i am|please)$", "", place, flags=re.I)
        if place and not _MAPS_NOT.match(place) and _place_ok(fold(place), place):
            if re.match(r"^(?:where is|where s|where can i find|where do i find|find|show me|locate)\s+(?:me\s+)?(?:the\s+)?(?:nearest|closest|nearby|a|an)\b", ft, re.I):
                return ToolCall("MAPPA", place + " near me")
            return ToolCall("MAPPA", place)
    m = _OPEN_SITE.match(ft)
    if m:
        target = (m.group(1) or m.group(2)).strip(_Q)
        if m.group(2):
            return ToolCall("APRI_APP", "sito:" + target)
        if _app_like(target):
            return ToolCall("APRI_APP", "sito:" + target)
    m = _OPEN_STRONG.match(ft)
    has_app_word = bool(re.search(r"\b(?:app|application|program)\b", t))                       # «open the Notes app» e' l'app Note, «open my notes» e' un'altra cosa
    if m and not re.search(r"\b(?:timer|alarm|stopwatch|folder|window|door|countdown|file|document|your heart|my heart)\b" + ("" if has_app_word else r"|\b(?:email|mail|message|note|notes|reminder)\b"), t) and _app_like(m.group(1)) \
            and not re.match(r"(?:an?|some|any|another)\s", m.group(1).strip(), re.I):
        verb = fold(ft.split()[0])
        target = m.group(1).strip(_Q)
        if verb in ("open", "launch", "start", "run", "fire", "bring", "load", "boot", "switch") or re.match(r"[A-Z]", target):
            return ToolCall("APRI_APP", target)
        return ToolCall("APRI_APP", "~" + target)
    m = _OPEN_WEAK.match(ft)
    if m and _app_like(m.group(1)) and re.match(r"[A-Z]", m.group(1)):
        return ToolCall("APRI_APP", "~" + m.group(1).strip(_Q))
    return None


# =============================================================================== slot, liste, correzioni
_SLOT_CANCEL = re.compile(r"^(?:no|nope|nothing|cancel|cancel it|forget it|never mind|nevermind|leave it|skip it|stop|don t|dont|it s fine|it is fine|that s ok|that s okay|no thanks|no need|forget that|drop it)\b")
_SLOT_NOTIME = re.compile(r"^(?:without (?:a )?(?:time|date)|no time|no date|doesn t matter|does not matter|whenever|anytime|any time|i don t know|just add it|just save it|no specific time|without)\b")


def slot_cancelled(answer: str) -> bool:
    return bool(_SLOT_CANCEL.match(normalize(answer)))


def merge_slot(slot: ToolCall, answer: str) -> ToolCall:
    """Completa una richiesta lasciata a meta' con la risposta data a voce: la parte gia' detta + quella nuova."""
    ans = answer.strip(" .!?")
    if slot.name == "PROMEMORIA" and _SLOT_NOTIME.match(normalize(ans)):
        return ToolCall("PROMEMORIA", "!" + slot.arg)
    if slot.name in ("PROMEMORIA", "EVENTO"):
        return ToolCall(slot.name, f"{slot.arg} {ans}".strip())
    if slot.name in ("LISTA", "SCRIVI"):
        return ToolCall(slot.name, f"{slot.arg}|{ans}")
    return ToolCall(slot.name, ans)


_LIST_MORE = re.compile(r"^(?:and\s+)?(?:(?:add|put|write|include)\s+)?(?:also|too)\s+(?:(?:add|put|write|include)\s+)?(.+)$|^(?:and\s+)?(?:add|put|include)\s+(.+?)(?:\s+too|\s+as well)?$|^and\s+(.+)$", re.I)


def list_followup(text: str, which: str) -> ToolCall | None:
    """«and eggs», «also add the milk»: continua l'ultima lista aperta."""
    ft = text.strip(" .!?")
    if len(ft.split()) > 8 or re.search(r"\b(?:calendar|reminder|timer|alarm|note|file|folder|music|volume|weather)\b", ft, re.I):
        return None
    m = _LIST_MORE.match(ft)
    if not m:
        return None
    item = re.sub(r"^(?:the|some|a|an)\s+", "", next(g for g in m.groups() if g).strip(" .,;:!?"), flags=re.I)
    if not item or re.match(r"^(?:then|so|what|how|why|when|where|who|do|does|did|is|are|can|could|will|would|i|we|you|it|that|this)\b", item, re.I):
        return None
    return ToolCall("LISTA", f"{which}|{item}")


# =============================================================================== il filo di tutto
def detect(text: str, files: list[str] | None = None, screen_on: bool = False) -> ToolCall | None:
    """Restituisce lo strumento da lanciare per questa frase, oppure None (decide il modello).
    `files` = i file nella cartella di Aria (serve per riconoscere le domande sui documenti dai nomi veri)."""
    text = spoken_math(text)
    if _FUTURE_STMT.match(fold(text)):
        return None
    sc = screen_request(text, screen_on)
    if sc:
        return sc
    raw = canonical(text)
    hit = _detect(raw, files, text)
    if hit is None:
        m = _PREAMBLE.match(raw)
        if m and m.end() < len(raw):
            hit = _detect(canonical(raw[m.end():]), files, text)
    return hit


def _clean_city(city: str) -> str:
    c = re.sub(r"^(?:the\s+)", "", city.strip(), flags=re.I)
    return "" if fold(c) in _NOT_CITY else c


_NW = r"(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[ -](?:one|two|three|four|five|six|seven|eight|nine))?|hundred|a hundred|one hundred)"
_DURATION = re.compile(r"\b((?:half an hour|a quarter of an hour|three quarters of an hour|an hour and a half|an hour and a quarter|an hour|a minute|a second)(?:\s+and\s+(?:a half|a quarter|\d+ minutes?))?|"
                       rf"(?:\d+(?:punto\d+)?|{_NW})(?:\s+and\s+a\s+half)?\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|h)\b(?:\s+and\s+(?:a half|a quarter|\d+ minutes?|{_NW}\s+minutes?))?)")


def _duration_text(t: str) -> str:
    m = _DURATION.search(t)
    return m.group(1) if m else t


def _detect(raw: str, files: list[str] | None = None, orig: str = "") -> ToolCall | None:
    if not raw:
        return None
    t = normalize(raw)
    t_orig = normalize(orig) if orig else t
    rawq = raw.strip(" .!?")

    m = _REMEMBER.match(rawq)
    if m:
        body = m.group(1).strip(" .!")
        if re.match(r"to\s", body, re.I):                                   # «remember to call Mark tomorrow» e' un promemoria; «remember to breathe» e' solo un consiglio
            if _TIMEWORD.search(normalize(body)) and re.match(r"to\s+[a-z]+", normalize(body)):
                return ToolCall("PROMEMORIA", body)
            return None
        if not re.match(r"^(?:me|us|it|that|this|\w+\?)$", body, re.I) and len(body.split()) >= 2 and (not _NOT_A_FACT.match(body) or re.match(r"^(?:remember|keep|bear|don|do not|make|note|take)\b.*\bthat\b", rawq, re.I)):
            return ToolCall("RICORDA", body)
    m = _REMEMBER2.match(rawq)
    if m and len(m.group(1).split()) >= 3:
        return ToolCall("RICORDA", m.group(1).strip(" .!"))
    m = _FORGET.match(rawq)
    if m and len(m.group(1).split()) <= 8 and not re.search(r"\b(?:timer|alarm|reminder|it)\b", m.group(1), re.I) and re.match(r"(?:forget|erase)", rawq, re.I):
        return ToolCall("DIMENTICA", m.group(1).strip(" .!"))

    intend = bool(_INTENT_STMT.match(fold(orig or raw)))                               # «I need to send an email», «I have to call my mom»: lo dice per se', non lo chiede a Aria
    for pat, kind in _NO_SO:
        if not intend and kind in ("message", "bookmark", "stopwatch") and pat.match(rawq if kind == "message" else t):
            return ToolCall("NON_SO", kind)
    from . import everyday_en as everyday
    if everyday.chance_kind(raw):
        return ToolCall("CASO", raw)
    ck = everyday.conversion_kind(raw)
    if ck == "unita":
        return ToolCall("CONVERTI", raw)
    if ck == "valuta":
        return ToolCall("CERCA", normalize(everyday.symbols_to_words(raw)))
    if everyday.date_kind(raw):
        return ToolCall("DATA", raw)
    if everyday.help_kind(raw):
        return ToolCall("AIUTO", "")
    tr = everyday.translation_request(orig or raw) or everyday.translation_request(raw)
    if tr:
        return ToolCall("TRADUCI", f"{tr[0]}|{tr[1]}")
    fc = _file_intent(raw, files) or _power_intent(raw, files)
    if fc:
        return fc
    if _MEMORY.search(t):
        return ToolCall("MEMORIA", "")
    if _SUN.search(t) and not _WEATHER_NOT.search(t_orig):
        cm = _CITY.search(raw)
        city = _clean_city(cm.group(1)) if cm else ""
        day = everyday.when_phrase(orig or raw) or "today"
        return ToolCall("METEO", f"@sole {city} {day}".replace("  ", " "))
    if _TIME.search(t):
        from . import worldclock
        if worldclock.find_zone(t):
            return ToolCall("ORA", "citta:" + t)
        return ToolCall("ORA", "ora")
    if _DATE.search(t):
        return ToolCall("ORA", "data")

    if _TIMER_STATUS.search(t) and not _TIMER_NOT.search(t) and re.search(r"\b(?:timers?|alarms?|countdowns?|left|remaining)\b", t):
        m = re.search(r"\b(?:for|on|of)\s+(?:the |my |a )?([a-z]+(?: [a-z]+)?)\s*(?:timer|alarm)?$", t)
        return ToolCall("TIMER_STATO", m.group(1) if m and not re.fullmatch(_TIMER_WORD, m.group(1)) and m.group(1) not in ("timer", "alarm") else "")
    if _TIMER_CANCEL.search(t) and not _TIMER_NOT.search(t):
        if re.search(r"\b(?:all|every|everything)\b", t):
            return ToolCall("TIMER_ANNULLA", "all")
        m = re.search(r"\b(?:the|my)\s+([a-z]+(?: [a-z]+)?)\s+(?:timer|alarm)\b", t) or re.search(r"\b(?:timer|alarm)\s+(?:for|called|named)\s+(?:the\s+|my\s+)?([a-z]+(?: [a-z]+)?)$", t)
        label = m.group(1) if m else ""
        return ToolCall("TIMER_ANNULLA", "" if label in ("a", "an", "this", "that", "current", "last", "first", "second") else label)
    mn = re.match(r"(?:please )?(?:let me know|lemme know|tell me|notify me|alert me|ping me|buzz me|warn me) (?:when|once|after|in) (.+?)(?: (?:are|is|have|has|been))?(?: (?:up|passed|gone by|gone|elapsed|over|done))?$", t_orig)           # (sul testo originale: «let me know…» e' un'apertura di cortesia per canonical)
    if mn and parse_duration(mn.group(1)) and not _DURATION.sub(" ", mn.group(1)).split():             # «let me know when ten minutes are up» e' un timer
        return ToolCall("TIMER", _duration_text(mn.group(1)))
    if _TIMER.search(t) and not _TIMER_NOT.search(t):
        d = parse_duration(t)
        label = ""
        todo = re.search(r"\b(?:remind|ping|buzz|alert|notify|tell|let)\s+(?:me|us)\b.*?\b(to\s+[a-z].*|that\s+[a-z].*)$", rawq, re.I)
        if todo:
            label = todo.group(1).strip(" .,;:!?")
        else:
            lm = re.match(r"^.*\b(?:for|called|named|labell?ed)\s+(?:the\s+|my\s+|a\s+|an\s+)?([a-z][a-z' ]{1,25}?)\s*$", rawq, re.I)        # (l'ultimo «for»: «for ten minutes for the pasta»)
            if lm and not re.search(r"\b(?:minutes?|hours?|seconds?|mins?|secs?|half|quarter|day|days|week)\b", lm.group(1), re.I) and not lm.group(1).strip().isdigit() \
                    and number_en(lm.group(1)) is None:
                label = lm.group(1).strip()
        if not label:
            lm2 = re.search(r"\b(?:called|named)\s+(?:the\s+|my\s+)?([a-z][a-z']*(?: [a-z']+){0,2}?)\s+(?:for|of|in)\b", rawq, re.I)        # «a timer called pizza for 5 minutes»
            if lm2 and number_en(lm2.group(1)) is None:
                label = lm2.group(1).strip()
        if d:
            return ToolCall("TIMER", f"{_duration_text(t)} | {label}".rstrip(" |"))
        w = parse_when(raw, dt.datetime.now())
        if w and w.has_time and re.search(r"\b(?:alarm|wake me|timer|ping me|notify me|alert me|remind me)\b", t):
            return ToolCall("TIMER", f"{re.sub(chr(10), ' ', raw)} | {label}".rstrip(" |"))
        if re.match(r"(?:set|start|create|make|put|begin|get)\s+(?:me\s+)?(?:an?|the|my)\s+(?:timer|alarm|countdown)\b|(?:timer|alarm)$", t):
            return ToolCall("TIMER", "")

    if (_WEATHER.search(t) and _WEATHER_ASKY.search(t_orig) or (_WEATHER.search(t) and re.search(r"\bweather\b", t) and len(t.split()) <= 7 and not re.search(r"\b(?:has|have|had|been|was|were|so|very|really|always|lately|year|years|these days)\b", t))) and not _WEATHER_NOT.search(t_orig):
        city = ""
        cm = _CITY.search(raw)
        if cm:
            city = _clean_city(cm.group(1))
        day = everyday.when_phrase(orig or raw) or "today"
        return ToolCall("METEO", f"{city} {day}".strip())

    if (_MATH_WORD.search(t) or re.search(r"\b\d+\s*(?:x|\*)\s*\d+\b", raw)) and (_MATH_ASK.search(t) or re.match(rf"^{_NUMTXT}\s+(?:plus|minus|times|divided by|multiplied by)\b", t) or re.match(r"^(?:add|subtract|multiply|divide|double|triple)\b", t)) \
            or re.search(r"\b(?:percent|per cent)\s+of\b", t) and _MATH_ASK.search(t) or re.search(r"\btip\b", t) and re.search(r"\b(?:percent|per cent)\b", t) and _MATH_ASK.search(t) or re.search(r"\b(?:squared|cubed|square root of|cube root of|the square of|the cube of)\b", t) and _MATH_ASK.search(t):
        expr = parse_math(raw)
        if expr:
            return ToolCall("CALCOLA", expr)

    for pat, kind in _SYS_INFO:
        if pat.search(t):
            return ToolCall("SISTEMA", kind)
    for pat, kind in _NO_SO:
        if not intend and pat.match(rawq if kind in ("message",) else t):
            return ToolCall("NON_SO", kind)
    m = _WHO.match(rawq)
    if m and not _LIVE.search(t):
        topic = m.group(1).strip(" .?!")
        tn = normalize(topic)
        if (topic and len(topic.split()) <= 6 and not re.search(r"\b(?:you|your|yours|my|mine|me|we|our|us|this|that|these|those|it|its|there|here|going|wrong|up|new|time|date|day|weather|plan|point|problem|matter|difference|deal|use|best|worst|better|worse|good|bad|right|left|next|last|first|today|tomorrow|tonight|now|happening|the news|your name|meaning of life|life|love|happiness)\b", tn)
                and not re.match(r"^(?:you|u)$", tn) and not re.match(r"^(?:at|in|on|by|with|behind|outside|inside|next|near|over|under|for|from|about|to|there|here)\b", tn)):
            return ToolCall("WIKI", topic)
    m = _MEANS.match(rawq)
    if m and len(m.group(1).split()) <= 3 and not re.search(r"\b(?:you|that|this|it|life|love)\b", m.group(1), re.I):
        return ToolCall("WIKI", m.group(1).strip(_Q))
    if _LIVE.search(t) and not _SEARCH_NOT.search(t):
        q = re.sub(r"\b(?:search|please|tell me|do you know|can you|for me|on the internet|online)\b", " ", t)
        return ToolCall("CERCA", re.sub(r"\s+", " ", q).strip())
    if _SEARCH.search(t) and not _SEARCH_NOT.search(t) and not re.search(r"\b(?:youtube|google maps|maps|spotify|amazon|wikipedia|github)\b", t):
        q = re.sub(r"\b(?:search the web for|search the internet for|search online for|search the web|search the internet|search online|search for|look up|look it up|google it|find out|find information (?:on|about)|find me information (?:on|about)|search|please)\b", " ", t)
        q = re.sub(r"^(?:google|bing|duckduckgo)\s+", "", re.sub(r"\s+", " ", q).strip())
        if len(q.split()) >= 1 and q.strip():
            return ToolCall("CERCA", q.strip())
    return None


# =============================================================================== «sembra una richiesta d'azione ma non l'ho capita»
_ACTION_VERBS = (r"(?:set|put|create|add|make|schedule|book|open|launch|start|run|turn|increase|decrease|raise|lower|stop|resume|pause|play|skip|remind|note|save|delete|remove|cancel|change|edit|move|send|call|phone|"
                 r"switch|mute|unmute|search|find|read|summari[sz]e|write|draft|show|display|give|tell|get|take|record|print|download|install|share|post|order|buy|pay|clear|reset|update|check|do|fire|execute|trigger)")
_DOMAINS: list[tuple[str, str, str]] = [
    ("reminders", r"\b(?:reminders?|remind me)\b", "\"remind me tomorrow at nine to call Mark\""),
    ("calendar", r"\b(?:event|appointment|calendar|agenda|meeting)\b", "\"add dinner with Marco to my calendar on Friday at eight\""),
    ("timers and alarms", r"\b(?:alarm|timer|countdown)\b", "\"set a timer for ten minutes\" or \"set an alarm for seven thirty\""),
    ("music", r"\b(?:music|song|songs|track|tracks|playlist|album|spotify|apple music)\b", "\"play some music\", \"pause\", \"next song\""),
    ("volume", r"\b(?:volume|sound|audio)\b", "\"turn the volume up\" or \"set the volume to thirty\""),
    ("lists", r"\b(?:list|shopping|groceries)\b", "\"add milk to the shopping list\""),
    ("notes", r"\b(?:note|notes|memo)\b", "\"make a note: call the accountant\""),
    ("apps and websites", r"\b(?:app|application|website|site|safari|youtube|spotify)\b", "\"open Safari\" or \"open YouTube\""),
    ("files", r"\b(?:file|folder|document|pdf)\b", "\"write me a text about photosynthesis\" or \"read me the shopping list\""),
]
_EDIT_VERBS = re.compile(r"^(?:cancel|delete|remove|clear|change|edit|move|reset|update)\b")


def action_like(text: str) -> tuple[str, str, bool] | None:
    """(ambito, esempio, e'_una_modifica) se la frase ha l'aria di una richiesta d'azione («set…», «add…» + reminder, music, volume…), altrimenti None."""
    c = canonical(text)
    t = normalize(c)
    if not t or len(t.split()) > 22 or _QUESTION_START.match(t) or (c.rstrip().endswith("?") and not re.match(_ACTION_VERBS, t)):
        return None
    if not re.match(_ACTION_VERBS + r"\b", t):
        return None
    for name, rx, example in _DOMAINS:
        if re.search(rx, t):
            return name, example, bool(_EDIT_VERBS.match(t))
    return None


def file_attempt(text: str) -> tuple[str, str, bool] | None:
    """Parla di un file/cartella con un verbo da «scrivere» o «dire» ma nessuna regola l'ha capita: il chatbot, lasciato solo, la RACCONTEREBBE a voce e direbbe di averla messa nel file."""
    c = canonical(text)
    f, t = fold(c), normalize(c)
    if not t or len(t.split()) > 30 or _QUESTION_START.match(t) or re.search(r"\b(?:i|we)\s+(?:have\s+)?(?:already\s+)?(?:put|saved|written|created|copied)\b", f) or not re.search(r"\b(?:file|folder|document)\b", f):
        return None
    if re.search(r"\b(?:write|save|put|create|prepare|copy|store|draft|make|tell|give|dump|drop)\b", f):
        return ("files", "\"write me the carbonara recipe in a file\"", False)
    return None


_REQ_KEYS = re.compile(r"\b(?:reminders?|remind|remember|forget|calendar|agenda|appointments?|events?|meetings?|schedule|timers?|alarms?|wake me|countdown|stopwatch|minutes|weather|rain|umbrella|temperature|degrees|forecast|what time|what day|what date|"
                       r"how much is|calculate|percent|sum|music|songs?|tracks?|playlist|album|volume|sound|audio|mute|silence|battery|wi ?fi|open|launch|start|website|app|search|google|youtube|amazon|wikipedia|"
                       r"map|directions|route|list|shopping|groceries|notes?|memo|write|text|letter|poem|file|documents?|folder|research|summari[sz]e|brief|summary|screen|window|button|icon|menu|call|phone|messages?|whatsapp|mail|email|"
                       r"light|lights|tv|heating|order|book|buy|print|download|install|translate|convert|how many|roll|flip|shortcut)\b")
_REQ_SHAPE = re.compile(r"^(?:tell me|give me|show me|let me|can you|could you|would you|will you|please|i want|i need|i d like|i would like|how|what|where|when|which|who|why|is there|are there|do you|does|did|can i|could i|may i|should i|"
                        r"set|put|create|add|make|schedule|open|launch|start|run|turn|increase|decrease|raise|lower|stop|resume|pause|play|skip|remind|note|save|delete|remove|cancel|change|send|call|switch|mute|search|find|read|write|show|get|take|record|"
                        r"print|download|install|share|order|buy|pay|translate|convert|roll|flip|tomorrow|tonight|today|next)\b")
_REQ_STORY = re.compile(r"\b(?:i feel|i felt|i was|i have been|i went|i heard|i ate|i saw|i read|i watched|i like|i love|i hate|i enjoy|my (?:day|week|weekend)|yesterday i|last night i)\b")


def request_like(text: str) -> bool:
    """Ha la forma di una richiesta (comando, domanda, «I'd like…») e parla di una cosa che Aria sa fare o NON sa fare (reminders, timer, music, screen, calls…)."""
    c = canonical(text)
    t = normalize(c)
    if not t or len(t.split()) > 30:
        return False
    shape = bool(_REQ_SHAPE.match(t)) or c.rstrip().endswith("?") or bool(re.match(_ACTION_VERBS + r"\b", t))
    return shape and bool(_REQ_KEYS.search(normalize(text))) and not _REQ_STORY.search(t)


def not_understood(domain: tuple[str, str, bool]) -> str:
    name, example, edit = domain
    if name == "files":
        return "I didn't quite get what to write in the file. Tell me, for example: write me the carbonara recipe in a file."
    if name == "screen":
        return "I didn't quite get what you want me to point at or look for on the screen. Tell me, for example: I can't find the Export button, or where is the Save button."
    if edit and name in ("reminders", "calendar"):
        return "I can't cancel or change reminders and events yet: I can only create new ones. To remove them, open the Reminders or Calendar app."
    if edit and name in ("lists", "notes"):
        return "I can only add lines to lists and notes: to remove or change them, open the file in your folder."
    return f"I'm not sure I understood what you want me to do. For {name} you can say, for example: {example}."


def unmatched_action(text: str, files: list[str] | None = None) -> str | None:
    d = action_like(text)
    return not_understood(d) if d else None


_SV_VERB = re.compile(r"\b(?:write|save|put|copy|store|record|jot|create|add|drop|dump|transfer|type)\b")
_SV_DEST = re.compile(r"\b(?:file|folder|document|documents|doc)\b")
_SV_THING = re.compile(r"\b(?:all (?:of )?(?:that|it|this)|everything|the whole (?:thing|recipe|story|text)|recipe|research|explanation|story|text|answer|what you (?:just )?said|what we (?:just )?(?:said|discussed|talked about)|that|this|it|them)\b")


def is_save_last(text: str) -> bool:
    """«put it in the folder», «write all the research to a file»: salvare quello che e' appena stato cercato (serve il contesto: lo sa Aria)."""
    ft = fold(canonical(text)).strip(" .!?")
    return bool(re.match(r"^(?:save|put|write|copy|store|drop|dump)\s+(?:all\s+(?:of\s+)?)?(?:that|it|this|the research|the results|everything)\b.*\b(?:file|folder|document)\b", ft) or re.match(r"^(?:save|store)\s+(?:the\s+)?(?:research|results)\b", ft))


def is_save_reply(text: str) -> str | None:
    """«could you write the whole recipe to a file?», «save it in the folder», «copy everything into a document»: salvare in un file quello che Aria ha APPENA detto.
    Restituisce che cosa si vuole salvare («recipe», «research», «explanation», «story», «text») oppure None. Si usa solo quando nessuno strumento ha capito la frase."""
    ft = fold(canonical(text)).strip(" .!?")
    if not (_SV_VERB.search(ft) and _SV_DEST.search(ft) and _SV_THING.search(ft)):
        return None
    for kind in ("recipe", "research", "explanation", "story"):
        if kind in ft:
            return kind
    return "text"


_CONVERT = re.compile(r"^(?:no\s+|but\s+)?(?:make it|put it|do it|set it|save it|file it)\s+(?:as|in|into|on|to)\s+(?:a\s+|an\s+|the\s+|my\s+)?(reminder|event|calendar|reminders)\b|^(?:as|make it)\s+(?:a\s+|an\s+)(reminder|event)\b|^(?:i meant|i said)\s+(?:a\s+|an\s+)?(reminder|event)\b|^not\s+(?:as\s+)?(?:a\s+|an\s+)?(?:reminder|event)\b.*\b(?:reminder|event)\b")
_REPLACE = re.compile(r"^(?:change|replace|swap|switch|correct|fix)\s+(.+?)\s+(?:with|to|for|by)\s+(.+)$", re.I)


def convert_target(text: str) -> str | None:
    """«make it a reminder, not an event»: restituisce lo strumento voluto («PROMEMORIA» o «EVENTO»)."""
    ft = fold(canonical(text)).strip(" .!?")
    m = _CONVERT.match(ft)
    if not m:
        return None
    what = next((g for g in m.groups() if g), "")
    if not what:
        what = "reminder" if re.search(r"\bnot (?:as )?(?:a |an )?event\b", ft) else "event"
    return "EVENTO" if what in ("event", "calendar") else "PROMEMORIA"


def replace_words(text: str) -> tuple[str, str] | None:
    """«change coffee to tobacco papers» -> («coffee», «tobacco papers»), con le maiuscole dette dall'utente."""
    raw = canonical(text).strip(" .!?")
    m = _REPLACE.match(raw)
    if not m:
        return None
    return m.group(1).strip(" ,.;:\"'"), m.group(2).strip(" ,.;:\"'")
