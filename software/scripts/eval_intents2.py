"""Seconda valutazione, piu' severa (frasi non previste dalle regole). Stampa i casi sbagliati.

    python scripts/eval_intents2.py [--screen-on] [--corpus3|--corpus4|--corpus5|--corpus6|--corpus7|--corpus8]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
from aria import intent                       # noqa: E402
if "--corpus3" in sys.argv:
    from intent_corpus3 import FILES, NEG3 as NEG2, POS3 as POS2    # noqa: E402
elif "--corpus8" in sys.argv:
    from intent_corpus8 import FILES, NEG8 as NEG2, POS8 as POS2    # noqa: E402
elif "--corpus7" in sys.argv:
    from intent_corpus7 import FILES, NEG7 as NEG2, POS7 as POS2    # noqa: E402
elif "--corpus6" in sys.argv:
    from intent_corpus6 import FILES, NEG6 as NEG2, POS6 as POS2    # noqa: E402
elif "--corpus5" in sys.argv:
    from intent_corpus5 import FILES, NEG5 as NEG2, POS5 as POS2    # noqa: E402
elif "--corpus4" in sys.argv:
    from intent_corpus4 import FILES, NEG4 as NEG2, POS4 as POS2    # noqa: E402
else:
    from intent_corpus2 import FILES, NEG2, POS2           # noqa: E402


def main() -> int:
    screen_on = "--screen-on" in sys.argv
    miss, wrong, badarg, fp = [], [], [], []
    by_tool: dict[str, list[int]] = {}
    for text, tools, parts in POS2:
        c = intent.detect(text, FILES, screen_on=screen_on)
        key = "/".join(sorted(tools))
        ok = by_tool.setdefault(key, [0, 0])
        ok[1] += 1
        if c is None:
            miss.append((text, key))
        elif c.name not in tools:
            wrong.append((text, key, f"{c.name}({c.arg})"))
        elif any(p not in c.arg.lower() for p in parts):
            badarg.append((text, key, c.arg, parts))
        else:
            ok[0] += 1
    for text in NEG2:
        c = intent.detect(text, FILES, screen_on=screen_on)
        if c is not None:
            fp.append((text, f"{c.name}({c.arg})"))
    n = len(POS2)
    good = sum(v[0] for v in by_tool.values())
    print(f"CAPITE BENE: {good}/{n} ({100 * good // n}%)  | mancate {len(miss)} | strumento sbagliato {len(wrong)} | argomento incompleto {len(badarg)} | falsi allarmi {len(fp)}/{len(NEG2)}")
    for tool, (a, b) in sorted(by_tool.items(), key=lambda kv: kv[1][0] / kv[1][1]):
        if a < b:
            print(f"  {tool:28} {a}/{b}")
    for title, items, fmt in (("NON CAPITE", miss, lambda t: f"  [{t[1]}] {t[0]}"), ("STRUMENTO SBAGLIATO", wrong, lambda t: f"  [{t[1]}] {t[0]}  ->  {t[2]}"),
                              ("ARGOMENTO INCOMPLETO", badarg, lambda t: f"  [{t[1]}] {t[0]}  ->  {t[2]!r} (mancano: {[p for p in t[3] if p not in t[2].lower()]})"),
                              ("FALSI ALLARMI", fp, lambda t: f"  {t[0]}  ->  {t[1]}")):
        if items:
            print(f"\n{title}:")
            for it in items:
                print(fmt(it))
    return 0


if __name__ == "__main__":
    sys.exit(main())
