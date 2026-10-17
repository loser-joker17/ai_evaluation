"""For every saved case: error vs examiner, the judge's levels, and the measured specifics.
NO model calls. Used to check whether under-marked answers are ones the judge called
"generic" even though they contain many specifics (named schemes, articles, examples, data).

    python scripts/show_specifics.py
"""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import benchmark_fast as bf  # noqa: E402
import app.evaluator.graph as graph_mod  # noqa: E402


def main():
    saved = bf.load_json(bf.RESULTS, {})
    cases = []
    for f in sorted(Path(".").glob(bf.GOLDEN_GLOB)):
        cases.extend(bf.load_json(f, []))
    rows = []
    for c in cases:
        runs = [r for r in saved.get(c["id"], {}).get("runs", []) if r.get("final_total") is not None]
        cache = bf.CACHE_DIR / f"{c['id']}.pkl"
        if not runs or not runs[-1].get("dims") or not cache.exists():
            continue
        feats = bf.get_state(c, graph_mod, False).get("answer_features") or {}
        med = statistics.median(bf.to_ten(c, r["final_total"]) for r in runs)
        lv = {d["dimension"]: d["final_level"] for d in runs[-1]["dims"]}
        rows.append((med - c["examiner_marks"], c["id"], lv, feats))
    rows.sort(key=lambda r: r[0])
    print(f"{'diff':>6}  {'case':<28} rel con ana cov str  spec/100w  mech  words")
    for diff, cid, lv, f in rows:
        print(f"{diff:+6.2f}  {cid[-28:]:<28} "
              f"{lv.get('relevance')!s:>3} {lv.get('content_substantiation')!s:>3} "
              f"{lv.get('analysis_depth')!s:>3} {lv.get('coverage_balance')!s:>3} "
              f"{lv.get('structure_presentation')!s:>3}  {f.get('specifics_per_100_words')!s:>9}  "
              f"{f.get('mechanisms_explained')!s:>4}  {f.get('word_count', '')!s:>5}")


if __name__ == "__main__":
    main()