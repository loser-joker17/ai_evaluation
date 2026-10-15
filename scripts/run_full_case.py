"""Run the FULL evaluator (with fact-check and feedback) on golden cases, the way
the product would, and compare with the examiner. Slower than benchmark_fast.py.
Cases run one after another, never at the same time.

    python scripts\\run_full_case.py visionias_gs3_q13
    python scripts\\run_full_case.py visionias_gs3_q13,visionias_gs3_q17

Results are appended to data/benchmark/results/full_runs.json.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluator.graph import evaluate_submission  # noqa: E402

GOLDEN_GLOB = "data/benchmark/*_examiner_golden.json"
OUT = Path("data/benchmark/results/full_runs.json")
ATTEMPTS = 3          # whole-case attempts when the model endpoint times out
WAIT_SECONDS = 60     # pause before the next attempt, so a busy endpoint can recover


def get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def run_with_retry(payload: dict, cid: str):
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return evaluate_submission(payload)
        except Exception as exc:  # timeouts, 503s, connection resets
            print(f"[attempt {attempt}/{ATTEMPTS}] {cid}: {type(exc).__name__}: {str(exc)[:120]}")
            if attempt < ATTEMPTS:
                time.sleep(WAIT_SECONDS * attempt)
    return None


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    ids = sys.argv[1].split(",")
    golden = {}
    for f in Path(".").glob(GOLDEN_GLOB):
        for c in json.loads(f.read_text(encoding="utf-8")):
            golden[c["id"]] = c
    saved = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}

    for cid in ids:
        c = golden[cid]
        marks = c.get("original_max_marks") or c["max_marks"]
        t0 = time.time()
        res = run_with_retry({
            "question": c["question"], "answer": c["answer"], "subject": c["subject"],
            "max_marks": marks, "word_limit": c["word_limit"],
        }, cid)
        secs = round(time.time() - t0)
        if res is None:
            print(f"[failed] {cid} after {ATTEMPTS} attempts ({secs}s). Try again later.")
            continue
        total = res.get("total_score")
        print("=" * 90)
        print(f"{cid}: evaluator {total}/{marks}  examiner "
              f"{c.get('original_marks', c['examiner_marks'])}/{marks}  ({secs}s)")
        for d in res.get("dimension_scores") or []:
            print(f"  {get(d, 'dimension'):<24} level {get(d, 'final_level')} "
                  f"(raw {get(d, 'raw_level')})  {get(d, 'cap_note') or ''}")
        print("\n  Fact-check:")
        for v in res.get("claim_verifications") or []:
            print(f"   - {get(v, 'label', '?')}: {str(get(v, 'claim', ''))[:90]}")
        for g in res.get("evidence_gaps") or []:
            print(f"   gap: {g}")
        saved.setdefault(cid, []).append({"total": total, "max_marks": marks, "seconds": secs,
                                          "result": res})
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(saved, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print()


if __name__ == "__main__":
    main()