"""Print every dimension of the last saved run for the given cases: level, judge reasoning,
improvement, and the examiner's comment for comparison. No model calls.

    python scripts\\show_case.py visionias_gs3_q13,visionias_gs3_q15
    python scripts\\show_case.py visionias_gs3_q13 --all-runs
"""
import json
import sys
from pathlib import Path

RESULTS = Path("data/benchmark/results/fast_scores.json")
GOLDEN_GLOB = "data/benchmark/*_examiner_golden.json"


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    ids = sys.argv[1].split(",")
    all_runs = "--all-runs" in sys.argv
    saved = json.loads(RESULTS.read_text(encoding="utf-8"))
    golden = {}
    for f in Path(".").glob(GOLDEN_GLOB):
        for c in json.loads(f.read_text(encoding="utf-8")):
            golden[c["id"]] = c

    for cid in ids:
        runs = saved.get(cid, {}).get("runs", [])
        c = golden.get(cid, {})
        print("=" * 90)
        print(f"{cid}  examiner {c.get('original_marks', c.get('examiner_marks'))}"
              f"/{c.get('original_max_marks', c.get('max_marks'))}  "
              f"evaluator finals {[r.get('final_total') for r in runs]}")
        print(f"Q: {c.get('question', '?')}")
        print(f"EXAMINER: {c.get('examiner_comment_not_for_model', '-')}")
        for i, run in enumerate(runs if all_runs else runs[-1:]):
            if all_runs:
                print(f"\n--- run {i + 1}: final {run.get('final_total')}")
            for d in run.get("dims", []):
                print(f"\n[{d['dimension']}] raw {d.get('raw_level')} -> final {d.get('final_level')}")
                print(f"  why: {d.get('justification')}")
                print(f"  fix: {d.get('improvement')}")
        print()


if __name__ == "__main__":
    main()