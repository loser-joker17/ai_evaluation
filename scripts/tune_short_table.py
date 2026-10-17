"""Try level tables for 10-mark answers on saved judge outputs. NO model calls.

For each candidate table it re-applies scoring.py to every saved run of every 10-mark case
(same as `benchmark_fast.py --replay`) and reports MAE / bias against the examiner,
overall and per institute, so you can see whether a table that fixes ForumIAS hurts the
older dev cases.

Works whatever your 10-mark table is now: it temporarily replaces scoring.level_fraction for
10-mark answers only (15 and 20 marks keep their tables). Nothing is written to scoring.py.

    python scripts/tune_short_table.py            # grid search, prints the best 10 tables
    python scripts/tune_short_table.py --top 20
"""
import argparse
import itertools
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import benchmark_fast as bf  # noqa: E402
import app.evaluator.scoring as scoring  # noqa: E402
import app.evaluator.graph as graph_mod  # noqa: E402


def ten_mark_cases():
    cases = []
    for f in sorted(Path(".").glob(bf.GOLDEN_GLOB)):
        cases.extend(bf.load_json(f, []))
    return [c for c in cases if (c.get("original_max_marks") or c.get("max_marks")) == 10]


def load_inputs(cases, saved):
    """(case, cached upstream state, saved raw judge outputs). Skips anything that would need a model call."""
    out, skipped = [], 0
    for c in cases:
        raws = [r["raw"] for r in saved.get(c["id"], {}).get("runs", []) if r.get("raw")]
        cache = bf.CACHE_DIR / f"{c['id']}.pkl"
        if not raws or not cache.exists():
            skipped += 1
            continue
        out.append((c, bf.get_state(c, graph_mod, False), raws))
    return out, skipped


_ORIG_LF = None


def evaluate(inputs, table):
    """Re-score with `table` for 10-mark answers; other marks use the current tables."""
    def lf(level, max_marks):
        return table[level] if max_marks == 10 else _ORIG_LF(level, max_marks)
    scoring.level_fraction = lf
    try:
        diffs = {}
        for c, state, raws in inputs:
            finals = []
            for raw in raws:
                r = bf.score_once(state, graph_mod, replay_raw=raw)
                if r.get("final_total") is not None:
                    finals.append(bf.to_ten(c, r["final_total"]))
            if finals:
                diffs[c["id"]] = (c.get("institute", "?"), statistics.median(finals) - c["examiner_marks"])
    finally:
        scoring.level_fraction = _ORIG_LF
    return diffs


def summary(diffs):
    d = [v for _, v in diffs.values()]
    return (sum(map(abs, d)) / len(d), sum(d) / len(d),
            sum(x >= 1.0 for x in d), sum(x <= -1.0 for x in d))


def by_institute(diffs):
    groups = {}
    for inst, v in diffs.values():
        groups.setdefault(inst, []).append(v)
    return {k: (sum(map(abs, v)) / len(v), sum(v) / len(v), len(v)) for k, v in sorted(groups.items())}


def fmt(table):
    return "{" + ", ".join(f"{k}: {table[k]:.2f}" for k in range(1, 6)) + "}"


def main():
    global _ORIG_LF
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    if not hasattr(scoring, "level_fraction"):
        raise SystemExit("scoring.py has no level_fraction(level, max_marks); paste it to me.")
    _ORIG_LF = scoring.level_fraction

    saved = bf.load_json(bf.RESULTS, {})
    inputs, skipped = load_inputs(ten_mark_cases(), saved)
    if not inputs:
        raise SystemExit("No 10-mark cases with saved raw output and cached state.")
    print(f"10-mark cases used: {len(inputs)} (skipped {skipped} without saved raw output or cache)\n")

    current = {lv: _ORIG_LF(lv, 10) for lv in range(6)}

    def show(name, table, diffs):
        mae, bias, over, under = summary(diffs)
        print(f"{name:<9}{fmt(table)}  MAE {mae:.3f}  bias {bias:+.3f}  >=+1: {over:2}  <=-1: {under:2}")
        for inst, (m, b, n) in by_institute(diffs).items():
            print(f"    {inst:<22} n={n:<3} MAE {m:.2f}  bias {b:+.2f}")

    show("current", current, evaluate(inputs, current))
    print()

    results = []
    for l1, l2, l3, l4, step5 in itertools.product(
        (0.12, 0.18, 0.24), (0.30, 0.33, 0.36), (0.40, 0.42, 0.45),
        (0.46, 0.48, 0.50, 0.52, 0.55), (0.05, 0.08),
    ):
        # keep every level a clear step above the one below, so ranking is preserved
        if not (l2 - l1 >= 0.06 and l3 - l2 >= 0.04 and l4 - l3 >= 0.04):
            continue
        table = {0: 0.0, 1: l1, 2: l2, 3: l3, 4: l4, 5: round(l4 + step5, 2)}
        diffs = evaluate(inputs, table)
        results.append((summary(diffs), table, diffs))

    # Rank by MAE, then by the number of big misses (>= 1 mark either way).
    results.sort(key=lambda r: (round(r[0][0], 3), r[0][2] + r[0][3]))
    print(f"Best {args.top} tables by MAE:")
    for _, table, diffs in results[: args.top]:
        show("", table, diffs)


if __name__ == "__main__":
    main()