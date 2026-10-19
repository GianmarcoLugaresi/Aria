"""Simulazione di conversazione con il chatbot VERO (Gemma 4 E4B) e strumenti FINTI (niente promemoria o eventi veri): per ogni frase mostra che strumento parte o cosa dice Aria.

    python scripts/sim_dialog.py [--screen-on] [frase ...]       (senza frasi usa un elenco di prova)
Serve il venv di Aria (mlx-lm). Non apre app, non scrive file, non tocca Promemoria o Calendario.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
from aria import persona as persona_mod                                       # noqa: E402
from aria.llm import make_llm                                                 # noqa: E402
from aria.tools import Tools                                                  # noqa: E402
from aria.textutil import ToolCall                                            # noqa: E402
from test_conversation import build, utterance                                # noqa: E402

DEFAULT = ["Domani alle otto ricordami di prendere le chiavi", "Mi faresti il gentile favore di mettere un conto alla rovescia di un'ora?", "Silenzi tutto", "Metti quella roba",
           "Stampa questo documento", "Chi ha vinto ieri la partita?", "Come funziona un motore a scoppio?", "Mi racconti una barzelletta?", "Ho paura di parlare in pubblico",
           "Fammi uno squillo fra un'ora", "Dov'è la farmacia più vicina?", "Mi indichi dov'è il pulsante Salva?", "Cosa significa questo errore?", "Che ne pensi della filosofia di Nietzsche?",
           "Potresti annotare questo dettaglio che voglio conservare?", "Apri quel coso, boh", "Digli che arrivo tardi", "Accendi la luce", "Quanto fa il venti per cento di trecentocinquanta?",
           "Vorrei che tu alzassi il suono", "Cosa ho domani?", "Che tempo fa a Roma?", "Traduci questa frase in inglese: buongiorno a tutti", "Fammi una foto", "Spegni il computer"]


class RecTools(Tools):
    async def run(self, call):
        self.seen.append(call)
        return f"[{call.name} eseguito: {call.arg[:60]}]"


async def main():
    screen_on = "--screen-on" in sys.argv
    phrases = [a for a in sys.argv[1:] if not a.startswith("--")] or DEFAULT
    cfg_llm = {"kind": "mlx-lm", "model": "mlx-community/gemma-4-e4b-it-4bit", "temperature": 0.7, "top_p": 0.92, "min_p": 0.05, "repetition_penalty": 1.05, "max_tokens": 240,
               "chat_template_kwargs": {"enable_thinking": False}}
    llm = make_llm(cfg_llm)
    a, hub, _fl, tts, spk, tools = build(utterance(), ["ciao"])
    rt = RecTools(a.cfg, a.memory)
    rt.seen = []
    rt.generate = a._generate_text
    a.tools = rt
    a.cfg["powers"] = {"screen_mac": screen_on}
    a.router.llm_stream = lambda messages, max_tokens=None, temperature=None, **kw: llm.stream(messages, max_tokens=max_tokens or 240, **({"temperature": temperature} if temperature is not None else {}))
    a._hour = lambda: 15
    a.memory.set_profile("name", "Mario")
    a.sys_prompt = a._build_system(open(os.path.expanduser("~/Library/Application Support/Aria/persona.md"), encoding="utf-8").read(), a.cfg, "")
    for ph in phrases:
        a.history = [{"role": "user", "content": ph}]
        rt.seen.clear()
        said, tools_started = [], []
        async for kind, val in a.reply_events([{"role": "system", "content": a.sys_prompt}, {"role": "user", "content": ph}]):
            if kind == "sentence":
                said.append(val)
            elif kind == "tool_start":
                tools_started.append(f"{val.name}({val.arg[:50]})")
        print(f"{ph!r}\n    STRUMENTO: {tools_started or '-'}\n    DICE: {' '.join(said)[:230]!r}", flush=True)


asyncio.run(main())
