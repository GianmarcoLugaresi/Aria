"""Quante richieste dette "come le direbbe una persona" Aria capisce? Stampa i casi sbagliati.

    python scripts/eval_intents.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
from aria import intent                       # noqa: E402
from intent_corpus import FILES, NEG, POS            # noqa: E402


def main() -> int:
    miss, wrong, badarg, fp = [], [], [], []
    by_tool: dict[str, list[int]] = {}
    for text, tool, parts in POS:
        c = intent.detect(text, FILES)
        ok = by_tool.setdefault(tool, [0, 0])
        ok[1] += 1
        if c is None:
            miss.append((text, tool))
        elif c.name != tool:
            wrong.append((text, tool, f"{c.name}({c.arg})"))
        elif any(p not in c.arg.lower() for p in parts):
            badarg.append((text, tool, c.arg, parts))
        else:
            ok[0] += 1
    for text in NEG:
        c = intent.detect(text, FILES)
        if c is not None:
            fp.append((text, f"{c.name}({c.arg})"))
    n = len(POS)
    good = sum(v[0] for v in by_tool.values())
    print(f"RICHIESTE CAPITE BENE: {good}/{n} ({100 * good // n}%)   |   falsi allarmi su chiacchiera: {len(fp)}/{len(NEG)}")
    for tool, (a, b) in sorted(by_tool.items(), key=lambda kv: kv[1][0] / kv[1][1]):
        print(f"  {tool:18} {a}/{b}")
    if miss:
        print("\nNON CAPITE (parte la chiacchiera):")
        for t, tool in miss:
            print(f"  [{tool}] {t}")
    if wrong:
        print("\nSTRUMENTO SBAGLIATO:")
        for t, tool, got in wrong:
            print(f"  [{tool}] {t}  ->  {got}")
    if badarg:
        print("\nARGOMENTO INCOMPLETO:")
        for t, tool, arg, parts in badarg:
            print(f"  [{tool}] {t}  ->  {arg!r}  (mancano: {[p for p in parts if p not in arg.lower()]})")
    if fp:
        print("\nFALSI ALLARMI:")
        for t, got in fp:
            print(f"  {t}  ->  {got}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
