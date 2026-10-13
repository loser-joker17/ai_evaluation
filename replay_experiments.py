"""Compare ways of turning the saved runs into one mark. No model calls, takes seconds.
Run from the project root:   python replay_experiments.py
Reads data/benchmark/results/fast_scores.json (needs the runs saved by the new benchmark_fast.py).
Decide on the DEV numbers only; the HELD-OUT column is a one-time check, not something to tune on."""
import json
import statistics as st
from pathlib import Path

from app.evaluator.scoring import LEVEL_TO_FRACTION, MAX_FRACTION_OF_MARKS, dimension_max, round_marks

saved = json.loads(Path("data/benchmark/results/fast_scores.json").read_text(encoding="utf-8"))
cases = []
for f in sorted(Path("data/benchmark").glob("*_examiner_golden.json")):
    cases.extend(json.loads(f.read_text(encoding="utf-8")))
cases = [c for c in cases if saved.get(c["id"], {}).get("runs")]


def frac(level):
    lo, hi = int(level), min(int(level) + 1, 5)
    w = level - lo
    return LEVEL_TO_FRACTION[lo] * (1 - w) + LEVEL_TO_FRACTION[hi] * w


def total_from_levels(levels_by_dim, max_marks):
    total = sum(frac(l) * dimension_max(d, max_marks) for d, l in levels_by_dim.items())
    total = min(total, MAX_FRACTION_OF_MARKS * max_marks)
    return round_marks(total, max_marks)


def run_totals(c):
    return [r["final_total"] for r in saved[c["id"]]["runs"] if r.get("final_total") is not None]


def v_median(c):
    return st.median(run_totals(c))


def v_mean_round(c):
    return round(st.mean(run_totals(c)) * 2) / 2


def v_mean_levels(c):
    runs = saved[c["id"]]["runs"]
    dims = {}
    for r in runs:
        for d in r["dims"]:
            dims.setdefault(d["dimension"], []).append(d["final_level"])
    return total_from_levels({k: st.mean(v) for k, v in dims.items()}, c["max_marks"])


def v_median_levels(c):
    runs = saved[c["id"]]["runs"]
    dims = {}
    for r in runs:
        for d in r["dims"]:
            dims.setdefault(d["dimension"], []).append(d["final_level"])
    return total_from_levels({k: st.median(v) for k, v in dims.items()}, c["max_marks"])


VARIANTS = {
    "median of run totals (current)": v_median,
    "mean of run totals, to 0.5": v_mean_round,
    "mean level per dimension": v_mean_levels,
    "median level per dimension": v_median_levels,
}


def metrics(cs, fn):
    if not cs:
        return None
    e = [fn(c) - c["examiner_marks"] for c in cs]
    n = len(e)
    return (sum(map(abs, e)) / n, sum(e) / n, sum(abs(x) <= 0.5 for x in e), sum(abs(x) <= 1 for x in e), n)


def fmt(m):
    return "n/a" if m is None else f"MAE {m[0]:.2f} bias {m[1]:+.2f} <=0.5: {m[2]}/{m[4]} <=1: {m[3]}/{m[4]}"


# Sanity check: does rebuilding a run's total from its levels reproduce the saved total?
ok = tot = 0
for c in cases:
    for r in saved[c["id"]]["runs"]:
        if r.get("final_total") is None:
            continue
        tot += 1
        rebuilt = total_from_levels({d["dimension"]: d["final_level"] for d in r["dims"]}, c["max_marks"])
        ok += abs(rebuilt - r["final_total"]) < 1e-9
print(f"Reconstruction check: {ok} of {tot} saved runs are reproduced exactly from their levels.")
if ok < tot:
    print("  WARNING: the two 'level per dimension' variants below are not reliable if this is not all of them.\n")

dev = [c for c in cases if not c.get("heldout")]
held = [c for c in cases if c.get("heldout")]
print(f"dev n={len(dev)}  held-out n={len(held)}\n")
for name, fn in VARIANTS.items():
    print(f"{name}\n   DEV      {fmt(metrics(dev, fn))}\n   HELD-OUT {fmt(metrics(held, fn))}")

# one global scale factor, fitted on DEV only (shrinks or stretches all marks)
base = v_median
k = sum(base(c) * c["examiner_marks"] for c in dev) / sum(base(c) ** 2 for c in dev)
print(f"\nGlobal scale k fitted on DEV only = {k:.2f}")
scaled = lambda c: round(base(c) * k * 2) / 2
print(f"   DEV      {fmt(metrics(dev, scaled))}\n   HELD-OUT {fmt(metrics(held, scaled))}")