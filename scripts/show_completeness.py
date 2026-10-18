"""How much of each question the answer deals with, per the judge's demand check,
next to the examiner's mark and ours. NO model calls. Used to design the completeness rule
(option C) before changing any scoring.

    python scripts/show_completeness.py                 # uses fast_replay.json (current rules)
    python scripts/show_completeness.py --file data/benchmark/results/judge_gptoss20b_uno.json
    python scripts/show_completeness.py --parts         # also print each part's status

Columns: share = covered 1 / thin 0.5 / missing 0, averaged over the question's parts;
words = answer words / word limit; pts = relevant points found in the answer (from the
feature step; "-" until the cache is rebuilt with the new feature step);
exam and model are marks out of 10; diff = model - exam.
"""
import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import benchmark_fast as bf  # noqa: E402
import app.evaluator.graph as graph_mod  # noqa: E402
from app.evaluator.demands import answered_share  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="data/benchmark/results/fast_replay.json")
    ap.add_argument("--parts", action="store_true")
    ap.add_argument("--by-points", action="store_true", help="sort by relevant points instead of share")
    args = ap.parse_args()

    raws = bf.load_json(bf.RESULTS, {})          # raw judge output (demands + demand_check)
    marks = bf.load_json(Path(args.file), {})    # marks under the rules being looked at
    cases = {}
    for f in sorted(Path(".").glob(bf.GOLDEN_GLOB)):
        for c in bf.load_json(f, []):
            cases[c["id"]] = c

    rows = []
    for cid, c in cases.items():
        runs = [r for r in raws.get(cid, {}).get("runs", []) if r.get("raw")]
        finals = [r["final_total"] for r in marks.get(cid, {}).get("runs", []) if r.get("final_total") is not None]
        if not runs or not finals:
            continue
        shares, detail = [], {}
        for r in runs:
            raw = r["raw"]
            sh, det = answered_share(raw.get("demands"), raw.get("demand_check"), c["question"])
            if sh is not None:
                shares.append(sh)
                detail = det
        if not shares:
            continue
        model = statistics.median(bf.to_ten(c, f) for f in finals)
        pts = None
        if (bf.CACHE_DIR / f"{cid}.pkl").exists():
            feats = bf.get_state(c, graph_mod, False).get("answer_features") or {}
            pts = feats.get("relevant_point_count")
        words = len(c["answer"].split()) / c["word_limit"] if c.get("word_limit") else float("nan")
        rows.append((statistics.median(shares), cid, words, c["examiner_marks"], model, detail,
                     bool(c.get("heldout")), pts))

    rows.sort(key=lambda r: (r[0], r[2]))
    if args.by_points:
        rows.sort(key=lambda r: (-1 if r[7] is None else r[7]))
    print(f"{'share':>5} {'words':>5} {'pts':>4} {'exam':>5} {'model':>5} {'diff':>6}  case")
    for share, cid, words, exam, model, detail, held, pts in rows:
        flag = " [heldout]" if held else ""
        p = "-" if pts is None else str(pts)
        print(f"{share:5.2f} {words:5.2f} {p:>4} {exam:5.2f} {model:5.2f} {model - exam:+6.2f}  {cid}{flag}")
        if args.parts:
            for text, st in detail.items():
                print(f"{'':30}{st:<8} {text[:80]}")

    print("\nby answered share (cases, mean diff model - exam):")
    for lo, hi in ((0, 0.5), (0.5, 0.75), (0.75, 1.0), (1.0, 1.01)):
        d = [m - e for s, _, _, e, m, _, _, _ in rows if lo <= s < hi]
        if d:
            print(f"  {lo:.2f}-{min(hi, 1):.2f}: {len(d):3} cases, mean diff {sum(d) / len(d):+.2f}")


if __name__ == "__main__":
    main()
