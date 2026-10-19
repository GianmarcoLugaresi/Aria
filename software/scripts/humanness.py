"""Quanto "umane" suonano le risposte? Fa recitare ad Aria conversazioni di prova con il chatbot VERO e misura cosa non va.

    python scripts/humanness.py --persona ../anima/persona_compatta.md --no-hints          # com'era
    python scripts/humanness.py --persona ../anima/persona_compatta.md --rhythm            # con il motore del ritmo
    python scripts/humanness.py --persona ../anima/persona_compatta.md --scenes 3 5 --show    # solo alcune scene, con il testo

Non misura il "calore" (quello lo giudica chi legge i testi) ma i difetti tipici dei modelli piccoli: risposte troppo lunghe, sempre una domanda in fondo,
sempre lo stesso inizio, formule da assistente o da psicologo, emoji, cifre, elenchi, esempi del carattere ricopiati.
"""
import argparse
import asyncio
import collections
import datetime as dt
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aria.llm import make_llm                                  # noqa: E402
from aria.persona import build_system, load_persona            # noqa: E402
from aria.speech import speechify                              # noqa: E402
from aria import examples as ex_bank, rhythm                   # noqa: E402
from aria.style import clean_reply, detect_mood, long_kind, polish, session_tone, turn_hint    # noqa: E402

SCENES = [
    ("chiacchiera", ["Ciao Aria, come stai?", "Io bene, ho appena finito di mangiare.", "Una pasta al pesto, niente di speciale.", "Sì, la preferisco alla carbonara, strano eh?"]),
    ("stanchezza", ["Sono stanchissimo, riunioni tutto il giorno.", "Sì, e domani è uguale.", "Boh, forse vado a letto presto."]),
    ("bella notizia", ["Ho preso trenta all'esame!", "Era analisi due, studiavo da un mese.", "Stasera esco con gli amici a festeggiare."]),
    ("ansia", ["Domani ho un colloquio di lavoro e sono agitato.", "È per un'azienda grande, tipo la mia occasione.", "Sì ma se vado male?"]),
    ("curiosità", ["Mi racconti una cosa curiosa sui polpi?", "Davvero? E gli altri animali?", "Ok, grazie, interessante."]),
    ("opinioni", ["Secondo te è meglio il mare o la montagna?", "Io montagna, ma d'estate vado al mare.", "Ma tu un posto preferito ce l'hai?"]),
    ("spiegazioni", ["Che cos'è la fotosintesi?", "E perché le foglie sono verdi?"]),
    ("solitudine", ["Mi sento un po' solo ultimamente.", "Boh, lavoro da casa e non vedo nessuno.", "Forse hai ragione."]),
    ("gioco", ["Dai, fammi ridere.", "Ahah, che brutta.", "Un'altra!"]),
    ("meta", ["Ma tu sei una persona vera?", "E ti diverti a parlare con me?", "Cosa fai quando nessuno ti parla?"]),
    ("risposte secche", ["Ciao", "Bene e tu?", "Niente di che", "Ok"]),
    ("consiglio", ["Secondo te dovrei cambiare lavoro?", "Mi pagano poco e mi annoio.", "Hai ragione, ci penso."]),
    ("rabbia", ["Mi sono arrabbiato con mio fratello, che nervoso.", "Non mi ha ascoltato per niente.", "Forse esagero io."]),
    ("notte", ["Non riesco a dormire.", "Penso a mille cose.", "Grazie, ci provo."]),
    ("vita pratica", ["Stasera non so cosa cucinare.", "Ho solo uova, zucchine e un po' di formaggio.", "Mmh, una frittata va bene."]),
    ("memoria", ["Ti ricordi che domani ho il dentista?", "Che palle, ho una paura matta.", "Sì lo so, è una sciocchezza."]),
    # ---- frasi VERE dette dall'utente ad Aria (come le ha scritte Whisper): chiacchiera con slang, correzioni, dubbi
    ("reale: la pianta", ["Allora, ho sulla scrivania una pianta di basilico e ha le foglie molto giù.", "Ma la luce di una lampadina va bene, gli ho tenuto tutto quanto pomeriggio la lampadina puntata",
                          "Muore se gli punto una lampadina contro al posto del sole perché è molto all'ombra", "Sei sicura?"]),
    ("reale: come va", ["Come va?", "Bene, dai, bene.", "Ma come va?", "Però ti mangi le parole.", "Sì, abbastanza."]),
    ("reale: ti buggi", ["Guardo il mio dito.", "Perché ogni tanto ti buggi?", "Controlla se funziona."]),
    ("reale: complimenti", ["Sei assurdo, sei bravissimo.", "Come faccio a capire che l'hai fatto veramente?"]),
    # ---- scene per il «motore del ritmo» (aria/rhythm.py): parere netto, spiegazione secca, sfogo, autosvalutazione, catastrofismo, scarico
    ("parere netto", ["Secondo te meglio lavorare con due monitor medi o con un ultrawide grande?", "Ma con due schermi ho più finestre aperte.", "Hmm, e per giocare?"]),
    ("parere sull'IA", ["Che ne pensi di chi usa l'IA per scrivere i testi delle canzoni?", "Io la uso solo quando sono bloccato su una strofa."]),
    ("spiegazione secca", ["Spiegami che vuol dire quando un file audio clippa.", "Ma come funziona davvero una cache?", "Ok e il modificatore booleano in 3D cos'è?"]),
    ("sfogo lungo", ["Oggi sono andato a parlare col professore per il progetto, ho aspettato due ore fuori dalla porta e quando sono entrato l'ha guardato trenta secondi dicendo che va rifatto da capo senza manco spiegarmi perché.",
                     "No, niente, mi ha detto solo che non andava bene e basta.", "Boh, adesso ricomincio da capo."]),
    ("autosvalutazione", ["Lascia stare, faccio schifo a progettare, gli altri del corso hanno già finito tutto e io sono ancora in alto mare.", "Sì ma io sono sempre indietro su tutto.", "Mah, forse hai ragione."]),
    ("catastrofismo", ["Sicuramente andrà male, non risponde nessuno alla mail da tre ore.", "Eh ma se poi mi dicono di no?", "Va bene, aspetto."]),
    ("scarico", ["Mah niente, serata vuota come al solito.", "Già, non c'ho voglia di fare niente oggi.", "Boh, giornata piatta.", "Mh."]),
]

BAD = {
    "formula da assistente": re.compile(r"\b(?:come posso aiutarti|come posso esserti utile|sono qui per aiutarti|fammi sapere se|se hai altre domande|ottima domanda|bella domanda|certamente|assolutamente|come assistente|come intelligenza artificiale|non esitare)\b", re.I),
    "da psicologo": re.compile(r"\b(?:capisco come ti senti|è (?:del tutto )?normale|è comprensibile|comprendo|capisco perfettamente|è importante (?:che|ricordare|prendersi)|ricorda che|non sei solo|vuoi parlarne|ti ascolto)\b", re.I),
    "inglese": re.compile(r"\b(?:okay|ok|wow|well|good|nice|sorry|thanks|hello|yes|no problem)\b", re.I),
    "emoji/simboli": re.compile(r"[\U0001F000-\U0001FAFF☀-➿*#]"),
    "cifre": re.compile(r"\d"),
    "elenco": re.compile(r"^\s*(?:[-•]|\d+[.)])\s", re.M),
    "neutrale (dipende/pro e contro)": re.compile(r"\b(?:dipende (?:da|dalle|dai)|pro e contro|vantaggi e svantaggi|entrambe le (?:soluzioni|opzioni|scelte)|da un lato)\b", re.I),
    "connettivi da tema": re.compile(r"\b(?:inoltre|tuttavia|ciononostante|pertanto|in conclusione|in sintesi|è importante sottolineare|vale la pena notare|per quanto riguarda)\b", re.I),
}


def first_word(t: str) -> str:
    m = re.match(r"[^\wÀ-ÿ]*([\wÀ-ÿ']+)", t)
    return m.group(1).lower() if m else ""


def sentences(t: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?…])\s+", t.strip()) if s])


def ngrams(text: str, n: int = 6) -> set:
    w = re.findall(r"[\wÀ-ÿ']+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", required=True)
    ap.add_argument("--model", default="mlx-community/gemma-3-text-4b-it-4bit")
    ap.add_argument("--ollama", help="nome di un modello di Ollama da provare al posto di quello MLX (es. Gemma4-12B:latest)")
    ap.add_argument("--no-think", action="store_true", help="spegne il «ragionamento» (Qwen3.5, Gemma 4…)")
    ap.add_argument("--no-hints", action="store_true")
    ap.add_argument("--no-examples", action="store_true", help="senza gli esempi pescati per situazione")
    ap.add_argument("--no-tone", action="store_true", help="senza la riga «oggi sei di buonumore…»")
    ap.add_argument("--rhythm", action="store_true", help="il motore del ritmo (aria/rhythm.py): mossa, budget di parole, regola sulle domande, temperatura e filtro per ogni turno")
    ap.add_argument("--scenes", nargs="*", type=int, help="numeri (da 1) delle scene da provare")
    ap.add_argument("--show", action="store_true", help="stampa tutti i testi")
    ap.add_argument("--temp", type=float, default=0.85)
    ap.add_argument("--rep", type=float, default=None, help="repetition_penalty")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--top-p", dest="top_p", type=float, default=0.92)
    ap.add_argument("--min-p", dest="min_p", type=float, default=0.0)
    args = ap.parse_args()
    random.seed(args.seed)
    if not args.ollama:
        import mlx.core as mx
        mx.random.seed(args.seed)
    persona = load_persona(args.persona, [os.getcwd(), os.path.dirname(os.path.abspath(args.persona))])
    examples = ngrams(persona.split("ESEMPI")[-1]) if "ESEMPI" in persona else set()
    cfg = {"name": "Aria"}
    if args.ollama:
        llm = make_llm({"base_url": "http://127.0.0.1:11434/v1", "model": args.ollama, "temperature": args.temp, "max_tokens": 200, "extra_body": {"reasoning_effort": "none"}})
    else:
        mcfg = {"kind": "mlx-lm", "model": args.model, "temperature": args.temp, "max_tokens": 200, "repetition_penalty": args.rep, "top_p": args.top_p, "min_p": args.min_p}
        if args.no_think:
            mcfg["chat_template_kwargs"] = {"enable_thinking": False}
        llm = make_llm(mcfg)
    now = dt.datetime(2026, 10, 6, 21, 40)
    scenes = [SCENES[i - 1] for i in args.scenes] if args.scenes else SCENES
    tot, raw = collections.Counter(), collections.Counter()
    words_all, q_all, firsts, lat = [], [], collections.Counter(), []
    copies = bank_copies = 0
    consecutive_q = over_budget = q_violations = 0
    bank = set().union(*(ngrams(a) for rows in ex_bank.BANK.values() for _u, a in rows))
    by_mode: dict[str, list[tuple[int, bool]]] = collections.defaultdict(list)
    for name, lines in scenes:
        if args.show:
            print(f"\n=== {name}")
        hist: list[dict] = []
        replies = []
        prev_mode = None
        for u in lines:
            hist.append({"role": "user", "content": u})
            past = hist[:-1]
            turn = rhythm.plan(past, u, detect_mood(u), long_kind(u), prev=prev_mode)   # sempre calcolata (per misurare); si usa solo con --rhythm
            prev_mode = turn.mode if turn else None
            use = turn if args.rhythm else None
            ctx = "" if args.no_hints else "\n".join(([] if args.no_tone else [session_tone(now)]) + [turn_hint(past, u, None, not args.no_examples, turn=use)])
            system = build_system(persona, cfg, ctx, now)
            msgs = [{"role": "system", "content": system}] + hist[-12:]
            kw = {"max_tokens": use.max_tokens, "temperature": rhythm.temperature(use, args.temp)} if use else {}
            t0 = time.time()
            out = "".join([t async for t in llm.stream(msgs, **kw)])
            lat.append(time.time() - t0)
            text = clean_reply(out)
            if args.rhythm:
                text = rhythm.enforce(polish(text), use)
            reply = speechify(text).strip()
            hist.append({"role": "assistant", "content": reply})
            replies.append(reply)
            nw = len(reply.split())
            words_all.append(nw)
            q_all.append(reply.rstrip().endswith("?"))
            firsts[first_word(reply)] += 1
            if turn:
                by_mode[turn.mode].append((nw, reply.rstrip().endswith("?")))
                if nw > turn.max_words * 1.25:
                    over_budget += 1
                    if args.show:
                        print(f"   !! fuori budget ({nw} parole, tetto {turn.max_words})")
                if reply.rstrip().endswith("?") and not turn.allow_question:
                    q_violations += 1
                    if args.show:
                        print("   !! domanda dove non era ammessa")
            for k, rx in BAD.items():
                if rx.search(out):
                    raw[k] += 1                                            # quello che dice il modello (prima dei filtri)
                if rx.search(reply):
                    tot[k] += 1                                            # quello che sente l'utente
                    if args.show:
                        print(f"   !! {k}")
            if examples and ngrams(reply) & examples:
                copies += 1
                if args.show:
                    print("   !! ricopia un esempio")
            if ngrams(reply) & bank:
                bank_copies += 1
                if args.show:
                    print("   !! ricopia un esempio del libro")
            if args.show and turn:
                print(f"   [{turn.mode}{'' if args.rhythm else ' (non applicata)'}]")
            if args.show:
                print(f"  TU:   {u}\n  ARIA: {reply}")
        # inizi uguali nella stessa scena
        consecutive_q += sum(1 for a, b in zip(replies, replies[1:]) if a.rstrip().endswith("?") and b.rstrip().endswith("?"))
        fw = [first_word(r) for r in replies]
        tot["inizio ripetuto nella scena"] += sum(1 for a, b in zip(fw, fw[1:]) if a == b)
    n = len(words_all)
    print(f"\nRISPOSTE: {n} | parole medie {sum(words_all) / n:.1f} (max {max(words_all)}) | finiscono con domanda {100 * sum(q_all) // n}% | tempo medio {sum(lat) / n:.1f}s")
    print("inizi più comuni:", ", ".join(f"{w} ({c})" for w, c in firsts.most_common(6)))
    print("difetti (sentiti):", dict(tot) if tot else "nessuno", "| esempi ricopiati:", copies)
    print("difetti (grezzi del modello):", dict(raw) if raw else "nessuno")
    print("domande in due risposte di fila:", consecutive_q, "| fuori budget di parole:", over_budget, "| domande dove non ammesse:", q_violations, "| ricopiati dal libro:", bank_copies)
    for mode, rows in sorted(by_mode.items()):
        print(f"  mossa {mode:10} n={len(rows):2}  parole medie {sum(w for w, _q in rows) / len(rows):5.1f} (max {max(w for w, _q in rows)})  domande {100 * sum(q for _w, q in rows) // len(rows)}%")


asyncio.run(main())
