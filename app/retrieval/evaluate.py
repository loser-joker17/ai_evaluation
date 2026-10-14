import json
import re
from pathlib import Path

import app.retrieval.corpus as corpus

EVAL_FILE = Path("data/retrieval_eval.json")
K = 3
DUP_THRESHOLD = 0.10


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def relevant(r: dict, expected: list[dict]) -> bool:
    return any(
        norm(item["file"]) == norm(r["file"]) and any(r["page"] <= p <= r["page_end"] for p in item["pages"])
        for item in expected
    )


def _sh(text: str, n: int = 8) -> set:
    ws = re.findall(r"\w+", text.lower())
    return {tuple(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def overlap(a: str, b: str) -> float:
    sa, sb = _sh(a), _sh(b)
    return len(sa & sb) / min(len(sa), len(sb)) if sa and sb else 0.0


def evaluate(test: dict, deduplicate: bool) -> dict:
    results = corpus.search_corpus(test["query"], k=K, deduplicate=deduplicate,
                                   papers=test.get("papers"), fallback=test.get("fallback", True))
    paper = (test.get("papers") or ["-"])[0]
    expected = test["expected"]

    if not expected:                       # the notes should NOT answer this
        return {"query": test["query"], "results": results, "flags": [False] * len(results),
                "returned": len(results), "negative": True, "pass": int(len(results) == 0), "paper": paper}

    flags = [relevant(r, expected) for r in results]
    covered = {
        (norm(item["file"]), p)
        for item in expected for p in item["pages"]
        if any(norm(r["file"]) == norm(item["file"]) and r["page"] <= p <= r["page_end"] for r in results)
    }
    total_expected = sum(len(item["pages"]) for item in expected)
    pairs = [(i, j) for i in range(len(results)) for j in range(i + 1, len(results))]
    dups = sum(overlap(results[i]["text"], results[j]["text"]) >= DUP_THRESHOLD for i, j in pairs)
    first = next((i for i, f in enumerate(flags) if f), None)
    return {
        "query": test["query"], "results": results, "flags": flags, "returned": len(results),
        "negative": False, "paper": paper,
        "hit": int(any(flags)),
        "mrr": 1 / (first + 1) if first is not None else 0.0,
        "precision": sum(flags) / len(results) if results else 0.0,
        "recall": len(covered) / total_expected if total_expected else 0.0,
        "dup": dups / len(pairs) if pairs else 0.0,
    }

def avg(reports, key):
    return sum(r[key] for r in reports) / len(reports)

def main():
    tests = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    for name, flag in (("baseline", False), ("filtered", True)):
        reports = [evaluate(t, flag) for t in tests]
        print(f"\n===== {name.upper()} =====")
        for r in reports:
            tag = "  [expects nothing]" if r["negative"] else ""
            print(f"\n{r['query']}  (returned {r['returned']}){tag}")
            for res, ok in zip(r["results"], r["flags"]):
                print(f"  {'OK ' if ok else '-- '}[{res['score']}] {res['url']}")

        pos = [r for r in reports if not r["negative"]]
        neg = [r for r in reports if r["negative"]]
        print(f"\n--- {name}: answerable queries ({len(pos)}) ---")
        if pos:
            print(f"Hit@3 {avg(pos,'hit'):.2f} | MRR {avg(pos,'mrr'):.2f} | "
                  f"Precision {avg(pos,'precision'):.2f} | Recall {avg(pos,'recall'):.2f} | "
                  f"Dup {avg(pos,'dup'):.2f} | Avg returned {avg(pos,'returned'):.1f}")
        for pp in sorted({r["paper"] for r in pos}):
            sub_ = [r for r in pos if r["paper"] == pp]
            print(f"  {pp:<5} n={len(sub_):<3} Hit@3 {avg(sub_,'hit'):.2f} | MRR {avg(sub_,'mrr'):.2f} | "
                  f"Recall {avg(sub_,'recall'):.2f}")
        print(f"--- {name}: no-answer queries ({len(neg)}) ---")
        if neg:
            print(f"Correctly returned nothing: {sum(r['pass'] for r in neg)} of {len(neg)}")


if __name__ == "__main__":
    main()