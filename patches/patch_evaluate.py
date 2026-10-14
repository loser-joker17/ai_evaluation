"""One-time patch for app/retrieval/evaluate.py: per-test paper filter + per-paper summary."""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")


def sub(old, new):
    global s
    if s.count(old) != 1:
        raise SystemExit(f"expected exactly 1 match, found {s.count(old)} for:\n{old[:70]}\nNothing changed.")
    s = s.replace(old, new)


# 1. pass the paper filter (optional "papers" and "fallback" keys in each test)
sub('''    results = corpus.search_corpus(test["query"], k=K, deduplicate=deduplicate)
''', '''    results = corpus.search_corpus(test["query"], k=K, deduplicate=deduplicate,
                                   papers=test.get("papers"), fallback=test.get("fallback", True))
    paper = (test.get("papers") or ["-"])[0]
''')
sub('''"returned": len(results), "negative": True, "pass": int(len(results) == 0)}''',
    '''"returned": len(results), "negative": True, "pass": int(len(results) == 0), "paper": paper}''')
sub('''        "negative": False,
        "hit": int(any(flags)),''', '''        "negative": False, "paper": paper,
        "hit": int(any(flags)),''')

# 2. per-paper summary
sub('''        print(f"--- {name}: no-answer queries ({len(neg)}) ---")''', '''        for pp in sorted({r["paper"] for r in pos}):
            sub_ = [r for r in pos if r["paper"] == pp]
            print(f"  {pp:<5} n={len(sub_):<3} Hit@3 {avg(sub_,'hit'):.2f} | MRR {avg(sub_,'mrr'):.2f} | "
                  f"Recall {avg(sub_,'recall'):.2f}")
        print(f"--- {name}: no-answer queries ({len(neg)}) ---")''')

p.write_text(s, encoding="utf-8")
print("patched", p)