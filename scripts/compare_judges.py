"""Compare two judges on the cases both have scored. NO model calls.

    python scripts/compare_judges.py data/benchmark/results/fast_scores.json data/benchmark/results/judge_gptoss120b.json

For each case scored by both: median mark (/10) of each judge vs the examiner.
Prints MAE, bias, big misses (>= 1 mark either way) for each judge, then the cases where
the two judges disagree most.
"""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import benchmark_fast as bf  # noqa: E402


def medians(path, cases):
    saved = bf.load_json(Path(path), {})
    out = {}
    for cid, c in cases.items():
        finals = [r["final_total"] for r in saved.get(cid, {}).get("runs", []) if r.get("final_total") is not None]
        if finals:
            out[cid] = statistics.median(bf.to_ten(c, f) for f in finals)
    return out


def stats(diffs):
    d = list(diffs)
    return (sum(map(abs, d)) / len(d), sum(d) / len(d), sum(x >= 1 for x in d), sum(x <= -1 for x in d))


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    a_path, b_path = sys.argv[1:]
    cases = {}
    for f in sorted(Path(".").glob(bf.GOLDEN_GLOB)):
        for c in bf.load_json(f, []):
            cases[c["id"]] = c
    a, b = medians(a_path, cases), medians(b_path, cases)
    both = sorted(set(a) & set(b))
    if not both:
        raise SystemExit("No case is scored in both files yet.")
    ex = {cid: cases[cid]["examiner_marks"] for cid in both}
    print(f"cases scored by both: {len(both)}\n")
    for name, m in ((Path(a_path).name, a), (Path(b_path).name, b)):
        mae, bias, over, under = stats(m[c] - ex[c] for c in both)
        print(f"{name:<34} MAE {mae:.2f}  bias {bias:+.2f}  over>=+1: {over:2}  under<=-1: {under:2}")
    print("\nlargest disagreements between the two judges (/10):")
    print(f"{'case':<30} {'examiner':>8} {'A':>6} {'B':>6}")
    for cid in sorted(both, key=lambda c: -abs(a[c] - b[c]))[:15]:
        print(f"{cid[-30:]:<30} {ex[cid]:>8.2f} {a[cid]:>6.2f} {b[cid]:>6.2f}")


if __name__ == "__main__":
    main()