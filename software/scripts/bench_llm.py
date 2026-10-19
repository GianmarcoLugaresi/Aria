"""Confronto di chatbot (MLX) sui compiti di Aria: capire richieste d'azione dette male, velocita', memoria.

    python scripts/bench_llm.py --model mlx-community/gemma-2-9b-it-4bit --name gemma2_9b [--no-think] [--limit 120]

Misura (con le STESSE istruzioni e gli STESSI controlli che usa Aria, vedi aria/llmintent.py):
  - quante richieste, che le regole non capiscono, il chatbot sa trasformare nello strumento giusto (promemoria, evento, musica, volume…);
  - quante volte inventa dettagli (orari, motivi) che l'utente non ha detto: la risposta viene scartata da `grounded`;
  - quante frasi di semplice chiacchiera scambia per un comando (falsi allarmi);
  - tempo per la risposta, parole al secondo e memoria usata.
Il confronto sulla chiacchiera (tono, lunghezza, domande…) si fa con scripts/humanness.py.
"""
import argparse
import asyncio
import collections
import json
import os
import random
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
from aria import intent, llmintent                          # noqa: E402
from aria.llm import make_llm                               # noqa: E402
from intent_corpus import FILES                              # noqa: E402

EXPECT = {"PROMEMORIA": {"PROMEMORIA"}, "EVENTO": {"EVENTO"}, "AGENDA": {"AGENDA"}, "MUSICA_NOME": {"MUSICA"}, "MUSICA_CTRL": {"MUSICA"}, "VOLUME": {"VOLUME"},
          "APRI_APP": {"APRI_APP"}, "WEB": {"WEB"}, "MAPPA": {"MAPPA"}, "LISTA": {"LISTA"}, "NOTA": {"NOTA"}, "TIMER": {"TIMER"}, "SCRIVI": {"SCRIVI"}, "RICERCA": {"RICERCA", "WEB"},
          "BRIEFING": {"BRIEFING", "AGENDA", "PROMEMORIA_LISTA"}}

# richieste VERE e plausibili che le regole non riconoscono (scritte a mano: il test dei «modi di dire» inventati dal chatbot e' pieno di frasi sgrammaticate)
HAND = [
    ("PROMEMORIA", "prepara un promemoria per domani alle nove, devo chiamare il commercialista"),
    ("PROMEMORIA", "sistemami un promemoria per venerdì: portare la macchina dal meccanico"),
    ("PROMEMORIA", "vorrei che domani mattina alle otto mi ricordassi di prendere le medicine"),
    ("PROMEMORIA", "annotami un promemoria per stasera, devo telefonare a Giulia"),
    ("EVENTO", "inserisci in agenda la riunione di lunedì alle quattro del pomeriggio"),
    ("EVENTO", "prenotami nel calendario il dentista il 15 novembre alle 10"),
    ("EVENTO", "segnami una cosa in calendario: cena dai miei sabato alle otto"),
    ("EVENTO", "fissa nel calendario una chiamata con Marco giovedì alle 17"),
    ("AGENDA", "dammi un'occhiata a cosa ho in programma venerdì"),
    ("AGENDA", "guarda se domani ho qualcosa in calendario"),
    ("MUSICA_NOME", "fammi ascoltare qualcosa di Lucio Dalla"),
    ("MUSICA_NOME", "vorrei che partisse un po' di jazz"),
    ("MUSICA_CTRL", "salta questo pezzo"),
    ("MUSICA_CTRL", "fermiamo un attimo la musica"),
    ("VOLUME", "è troppo basso, sistemalo"),
    ("VOLUME", "porta l'audio a metà"),
    ("VOLUME", "metti il volume sul minimo"),
    ("APRI_APP", "fammi vedere il calendario"),
    ("APRI_APP", "puoi tirare su Spotify"),
    ("WEB", "dai un'occhiata su google a come si fa il tiramisù"),
    ("MAPPA", "mi indichi la strada per arrivare al duomo di Milano"),
    ("LISTA", "metti il pane in lista, quella della spesa"),
    ("LISTA", "segnami il detersivo per i piatti tra le cose da comprare"),
    ("NOTA", "annotati questa cosa: il codice del garage è 4821"),
    ("NOTA", "scrivi nel quaderno degli appunti che il tecnico passa martedì"),
    ("TIMER", "avvisami quando sono passati venti minuti"),
    ("TIMER", "fammi suonare qualcosa alle sei e mezza domani"),
    ("SCRIVI", "preparami una lettera per disdire l'abbonamento della palestra"),
    ("RICERCA", "documentati sui vulcani e tienimi gli appunti"),
    ("BRIEFING", "dimmi come si presenta la mia giornata"),
]


def load_sets(limit: int, seed: int = 11):
    rnd = random.Random(seed)
    S = os.environ.get("ARIA_BENCH_DATA", "")
    d = json.load(open(os.path.join(S, "paraphrases_clean.json"))) if S and os.path.exists(os.path.join(S, "paraphrases_clean.json")) else {}
    pos = list(HAND)
    for cat, sents in d.items():
        if cat not in EXPECT:
            continue
        miss = [t for t in sents if intent.detect(t, FILES) is None]
        rnd.shuffle(miss)
        pos += [(cat, t) for t in miss[:max(2, limit // 20)]]
    neg = []
    p = os.path.join(os.path.dirname(__file__), "..", "tests", "chat_sentences.json")
    neg = json.load(open(p, encoding="utf-8"))
    rnd.shuffle(neg)
    return pos, neg[:limit]


def footprint_mb() -> float:
    out = subprocess.run(["/usr/bin/footprint", "-p", str(os.getpid())], capture_output=True, text=True).stdout
    m = re.search(r"Footprint:\s+([\d.]+)\s*(GB|MB)", out)
    return float(m.group(1)) * (1024 if m.group(2) == "GB" else 1) if m else -1


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="")
    ap.add_argument("--ollama", help="nome di un modello di Ollama (es. Gemma4-12B:latest)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--limit", type=int, default=120)
    ap.add_argument("--out", default=os.path.expanduser("~/aria_bench"))
    args = ap.parse_args()
    if args.ollama:
        cfg = {"base_url": "http://127.0.0.1:11434/v1", "model": args.ollama, "temperature": 0.65, "max_tokens": 80, "extra_body": {"reasoning_effort": "none"}}
        args.model = args.ollama
    else:
        cfg = {"kind": "mlx-lm", "model": args.model, "temperature": 0.65, "top_p": 0.92, "min_p": 0.05, "max_tokens": 80}
        if args.no_think:
            cfg["chat_template_kwargs"] = {"enable_thinking": False}
    llm = make_llm(cfg)
    t0 = time.time()
    await llm.warmup()
    load_s = time.time() - t0
    mem_load = footprint_mb()
    pos, neg = load_sets(args.limit)
    print(f"{args.name}: caricato in {load_s:.1f}s, memoria {mem_load:.0f} MB | prove: {len(pos)} richieste, {len(neg)} chiacchiere", flush=True)

    async def decode(text):
        system, user = llmintent.prompt(text)
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        t = time.time()
        out = "".join([x async for x in llm.stream(msgs, max_tokens=70, temperature=0.0)])
        return out, time.time() - t

    lat, rows_pos, rows_neg = [], [], []
    for cat, text in pos:
        out, dt = await decode(text)
        lat.append(dt)
        call = llmintent.parse(out)
        rows_pos.append({"cat": cat, "text": text, "out": out.strip()[:120], "tool": call.name if call else None, "ok_tool": bool(call and call.name in EXPECT[cat]),
                         "grounded": bool(call and llmintent.grounded(call, text))})
    for text in neg:
        out, dt = await decode(text)
        lat.append(dt)
        call = llmintent.parse(out)
        rows_neg.append({"text": text, "out": out.strip()[:120], "tool": call.name if call else None, "gated": bool(intent.action_like(text))})
    n = len(rows_pos)
    tool_ok = sum(r["ok_tool"] for r in rows_pos)
    usable = sum(r["ok_tool"] and r["grounded"] for r in rows_pos)
    invented = sum(r["ok_tool"] and not r["grounded"] for r in rows_pos)
    fp_raw = sum(1 for r in rows_neg if r["tool"])
    fp_gated = sum(1 for r in rows_neg if r["tool"] and r["gated"])

    # velocita': primo testo e parole al secondo con una risposta di conversazione (senza cache del prefisso)
    chat = [{"role": "system", "content": "Sei Aria, un'amica. Rispondi in italiano in poche frasi."}, {"role": "user", "content": "Raccontami come passeresti una domenica pigra, in cinque o sei frasi."}]
    llm.max_tokens = 120
    t = time.time(); first = None; toks = 0
    async for x in llm.stream(chat, max_tokens=120, temperature=0.6):
        if first is None:
            first = time.time() - t
        toks += 1
    total = time.time() - t
    mem_run = footprint_mb()
    res = {"name": args.name, "model": args.model, "load_s": round(load_s, 1), "mem_load_mb": round(mem_load), "mem_run_mb": round(mem_run),
           "positives": n, "tool_right": tool_ok, "usable": usable, "invented_details": invented, "negatives": len(rows_neg), "false_alarms_raw": fp_raw, "false_alarms_after_gate": fp_gated,
           "latency_decode_s": round(sum(lat) / len(lat), 2), "first_token_s": round(first or 0, 2), "tok_per_s": round(max(0, toks - 1) / max(0.01, total - (first or 0)), 1)}
    os.makedirs(args.out, exist_ok=True)
    json.dump({"summary": res, "pos": rows_pos, "neg": rows_neg}, open(os.path.join(args.out, f"{args.name}.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False))
    by = collections.defaultdict(lambda: [0, 0])
    for r in rows_pos:
        by[r["cat"]][1] += 1
        by[r["cat"]][0] += int(r["ok_tool"] and r["grounded"])
    print("per categoria (usabili/totale):", {k: f"{a}/{b}" for k, (a, b) in sorted(by.items())})
    print("\nSBAGLIATE o scartate:")
    for r in rows_pos:
        if not (r["ok_tool"] and r["grounded"]):
            print(f"  [{r['cat']}] {r['text'][:80]}  ->  {r['out'][:80]!r}  {'(dettagli inventati)' if r['ok_tool'] else ''}")
    print("\nFALSI ALLARMI (chiacchiera presa per un comando):")
    for r in rows_neg:
        if r["tool"]:
            print(f"  {r['text'][:80]}  ->  {r['out'][:60]!r}  {'(passerebbe la guardia)' if r['gated'] else '(bloccato dalla guardia)'}")


asyncio.run(main())
