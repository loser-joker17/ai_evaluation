"""
Benchmark the evaluator against human marks.

  python benchmark.py                          # one run per case
  python benchmark.py --runs 3                 # also measures run-to-run variance
  python benchmark.py --label baseline         # save to data/benchmark/results/baseline.json
  python benchmark.py --label v2 --compare data/benchmark/results/baseline.json
  python benchmark.py --only weak_generic strong_pil
"""
import argparse
import json
import statistics
import time
from pathlib import Path

from app.evaluator.graph import evaluate_submission

GOLDEN = Path("data/benchmark/golden_set.json")
OUT_DIR = Path("data/benchmark/results")


# ------------------------------------------------------------- helpers

def human_mean(marks):
    if marks is None:
        return None
    if isinstance(marks, (int, float)):
        return float(marks)
    return statistics.mean(marks)


def to_10(x, max_marks):
    """Put 10- and 15-mark cases on a common 0-10 scale."""
    return x / max_marks * 10


def ranks(values):
    """Average ranks, so ties are handled correctly."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = ranks(a), ranks(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else None


def evaluate_with_retry(case, attempts=3):
    payload = {k: case[k] for k in ("question", "answer", "subject", "max_marks", "word_limit")}
    for n in range(attempts):
        try:
            return evaluate_submission(payload)
        except Exception as exc:  # network drops are transient
            print(f"    attempt {n + 1} failed: {type(exc).__name__}")
            time.sleep(3 * (n + 1))
    return None


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--label", default=None)
    ap.add_argument("--compare", default=None)
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))
    cases = [c for c in cases if c.get("human_marks") is not None]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]
    if not cases:
        print("No cases with human_marks. Fill in the golden set first.")
        return

    previous = {}
    if args.compare:
        prev = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        previous = {r["id"]: r for r in prev["cases"]}

    rows = []
    for case in cases:
        print(f"[{case['id']}]")
        finals, raws, last = [], [], None
        for _ in range(args.runs):
            res = evaluate_with_retry(case)
            if res and res["status"] == "success":
                finals.append(res["total_score"])
                raws.append(res["raw_total_score"])
                last = res
        if not finals:
            print("    FAILED, skipped")
            continue

        marks = case["human_marks"]
        multi = isinstance(marks, list) and len(marks) > 1
        rows.append({
            "id": case["id"],
            "max_marks": case["max_marks"],
            "marks_source": case.get("marks_source", "unknown"),
            "human": human_mean(marks),
            "human_spread": (max(marks) - min(marks)) if multi else None,
            "ai_mean": round(statistics.mean(finals), 2),
            "ai_final_runs": finals,
            "ai_raw_runs": raws,
            "ai_raw_std": round(statistics.pstdev(raws), 2) if len(raws) > 1 else None,
            "levels": {d["dimension"]: d["final_level"] for d in last["dimension_scores"]},
            "feedback_consistent": last["feedback_consistent"],
        })

    # ---- per-case table
    print(f"\n{'id':<20}{'max':>4}{'human':>7}{'AI':>6}{'err':>6}{'rawstd':>8}{'range':>11}  levels rel/con/ana/cov/str")
    for r in rows:
        err = r["ai_mean"] - r["human"]
        lv = r["levels"]
        lv_s = "/".join(str(lv[k]) for k in (
            "relevance", "content_substantiation", "analysis_depth",
            "coverage_balance", "structure_presentation"))
        std = "-" if r["ai_raw_std"] is None else r["ai_raw_std"]
        rng = f"{min(r['ai_final_runs'])}-{max(r['ai_final_runs'])}"
        line = (f"{r['id']:<20}{r['max_marks']:>4}{r['human']:>7.1f}{r['ai_mean']:>6.1f}"
                f"{err:>+6.1f}{std!s:>8}{rng:>11}  {lv_s}")
        if r["id"] in previous:
            line += f"   (was {previous[r['id']]['ai_mean']})"
        print(line)

    # ---- summary (errors on a common 0-10 scale)
    errs = [to_10(r["ai_mean"] - r["human"], r["max_marks"]) for r in rows]
    ai10 = [to_10(r["ai_mean"], r["max_marks"]) for r in rows]
    hu10 = [to_10(r["human"], r["max_marks"]) for r in rows]
    stds = [to_10(r["ai_raw_std"], r["max_marks"]) for r in rows if r["ai_raw_std"] is not None]
    spreads = [to_10(r["human_spread"], r["max_marks"]) for r in rows if r["human_spread"] is not None]
    rho = spearman(ai10, hu10)

    summary = {
        "n": len(rows),
        "mae_10pt": round(statistics.mean(abs(e) for e in errs), 2),
        "bias_10pt": round(statistics.mean(errs), 2),
        "within_0.5": round(sum(abs(e) <= 0.5 for e in errs) / len(errs), 2),
        "within_1.0": round(sum(abs(e) <= 1.0 for e in errs) / len(errs), 2),
        "spearman": None if rho is None else round(rho, 2),
        "mean_raw_run_std_10pt": round(statistics.mean(stds), 2) if stds else None,
        "reviewer_mean_spread_10pt": round(statistics.mean(spreads), 2) if spreads else None,
    }

    print("\n=========== SUMMARY (0-10 scale) ===========")
    for k, v in summary.items():
        print(f"{k:<28}{v}")

    placeholders = [r["id"] for r in rows if r["marks_source"] != "examiner"]
    if placeholders:
        print(f"\nWARNING: {len(placeholders)} case(s) use placeholder marks "
              f"({', '.join(placeholders)}).")
        print("Do not read bias, MAE or correlation as evidence, and do not tune knobs on them.")
    elif len(rows) < 10:
        print("\nWARNING: fewer than 10 cases. Treat these numbers as indicative only.")
    elif summary["bias_10pt"] > 0.5:
        print("Reading: generous on average. Consider lowering the ceiling or LEVEL_TO_FRACTION.")
    elif summary["bias_10pt"] < -0.5:
        print("Reading: harsh on average. Consider relaxing the level table or rounding.")

    if args.label:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUT_DIR / f"{args.label}.json"
        path.write_text(json.dumps({"summary": summary, "cases": rows}, indent=2), encoding="utf-8")
        print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()