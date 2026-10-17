"""Find feedback that asks for something the question did not ask for. NO model calls.

Reads the saved judge output (fast_scores.json, or fast_replay.json with --replay) and
flags, per case (last run):

  MECHANISM  analysis feedback/cap asks for how/why/causal mechanisms, but the question
             is a "to what extent / do you agree / assess" (judgement) or a
             "describe / highlight" (descriptive) question.
  LONG_GAPS  coverage feedback lists 5+ "missing" topics: usually topics that could not
             fit in the word limit rather than a missing demand of the question.

For each flag it prints how many cases have it and their average error against the
examiner, compared with the cases without it.

    python scripts/audit_feedback.py
    python scripts/audit_feedback.py --replay     # audit fast_replay.json instead
    python scripts/audit_feedback.py --show 5     # print the judge's text for 5 cases per flag
"""
import argparse
import pickle
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import benchmark_fast as bf  # noqa: E402
from app.evaluator.scoring import directive_type  # noqa: E402

MECHANISM_RX = re.compile(
    r"causal|mechanism|how or why|why or how|underlying rationale|reasoning behind|"
    r"explain(?:s|ing)? (?:why|how)|does not explain|without explaining|bare (?:list|assertion)",
    re.I,
)
GAP_LEAD_RX = re.compile(r"\b(miss(?:es|ing)?|omit(?:s|ted)?|does not (?:address|cover|mention)|lacks?)\b", re.I)


def directive_of(case):
    """The directive the pipeline extracted, from the state cache when available."""
    p = bf.CACHE_DIR / f"{case['id']}.pkl"
    if p.exists():
        try:
            qa = pickle.loads(p.read_bytes()).get("question_analysis") or {}
            if isinstance(qa, dict):
                return qa.get("directive", "")
        except Exception:
            pass
    return ""


def gap_items(text):
    """Rough count of listed missing topics after a 'misses/omits/lacks' phrase."""
    m = GAP_LEAD_RX.search(text or "")
    if not m:
        return 0
    tail = re.split(r"[.;]\s", text[m.end():], maxsplit=1)[0]
    return len([t for t in re.split(r",|\band\b|\bor\b", tail) if t.strip()])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", action="store_true", help="audit fast_replay.json")
    ap.add_argument("--show", type=int, default=3, help="examples to print per flag")
    args = ap.parse_args()

    saved = bf.load_json(bf.REPLAY if args.replay else bf.RESULTS, {})
    cases = []
    for f in sorted(Path(".").glob(bf.GOLDEN_GLOB)):
        cases.extend(bf.load_json(f, []))

    rows = []
    for c in cases:
        runs = [r for r in saved.get(c["id"], {}).get("runs", []) if r.get("final_total") is not None]
        if not runs or not runs[-1].get("dims"):
            continue
        med = statistics.median(bf.to_ten(c, r["final_total"]) for r in runs)
        dims = {d["dimension"]: d for d in runs[-1]["dims"]}
        kind = directive_type(directive_of(c), c["question"])
        ana = dims.get("analysis_depth", {})
        cov = dims.get("coverage_balance", {})
        ana_text = " ".join(str(ana.get(k) or "") for k in ("justification", "improvement", "cap_note"))
        cov_text = " ".join(str(cov.get(k) or "") for k in ("justification", "improvement"))
        flags = []
        if kind in ("judgement", "descriptive") and MECHANISM_RX.search(ana_text):
            flags.append("MECHANISM")
        if gap_items(cov_text) >= 5:
            flags.append("LONG_GAPS")
        rows.append({
            "id": c["id"], "kind": kind, "diff": med - c["examiner_marks"], "flags": flags,
            "ana": (ana.get("final_level"), ana_text), "cov": (cov.get("final_level"), cov_text),
        })

    if not rows:
        raise SystemExit("No saved runs found.")

    def line(name, sub):
        if not sub:
            return f"{name:<26} n=0"
        d = [r["diff"] for r in sub]
        return (f"{name:<26} n={len(sub):<3} bias {sum(d) / len(d):+.2f}  "
                f"MAE {sum(map(abs, d)) / len(d):.2f}  under<=-0.75: {sum(x <= -0.75 for x in d)}")

    print(f"Cases audited: {len(rows)}\n\nBy question type:")
    for kind in ("analytical", "judgement", "balanced", "descriptive"):
        print("  " + line(kind, [r for r in rows if r["kind"] == kind]))

    for flag, key in (("MECHANISM", "ana"), ("LONG_GAPS", "cov")):
        hit = [r for r in rows if flag in r["flags"]]
        print(f"\n{flag}")
        print("  " + line("flagged", hit))
        print("  " + line("not flagged", [r for r in rows if flag not in r["flags"]]))
        for r in sorted(hit, key=lambda r: r["diff"])[: args.show]:
            level, text = r[key]
            print(f"\n  [{r['id']}] {r['kind']}, diff {r['diff']:+.2f}, level {level}\n    {text[:400]}")
        if hit:
            print("\n  all flagged: " + ", ".join(f"{r['id']} ({r['diff']:+.2f})" for r in sorted(hit, key=lambda r: r["diff"])))


if __name__ == "__main__":
    main()