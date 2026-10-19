"""Our feedback next to the examiner's comment, for a handful of answers.

Runs the FULL evaluator (fact-check + feedback), the way a student would get it, then
writes a side-by-side report and a rough automatic match: for each point in the
examiner's comment, does our feedback mention the same thing (shared key words)?
The match is a first pass only; read the report to judge.

    python scripts/compare_feedback.py                    # the default sample (8 answers)
    python scripts/compare_feedback.py forumias_gs2_flt1_q2,forumias_gs4_flt2_q9
    python scripts/compare_feedback.py --reuse            # no model calls: reuse saved full runs
    python scripts/compare_feedback.py --reuse --reclean  # also re-apply today's feedback filters

Full results are saved to data/benchmark/results/full_runs.json (same file as
run_full_case.py); the report goes to data/benchmark/results/feedback_compare.md.
Both are ignored by git (they contain candidate answers).
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

GOLDEN_GLOB = "data/benchmark/*_examiner_golden.json"
FULL = Path("data/benchmark/results/full_runs.json")
REPORT = Path("data/benchmark/results/feedback_compare.md")

# A mix: a fragment, invented-part victims, a case-law answer, answers the examiner
# flagged for wrong data, a case study.
DEFAULT = [
    "forumias_gs1_flt2_q9",     # 38-word fragment
    "forumias_gs3_flt1_q9",     # Operation Sindoor
    "forumias_gs1_flt1_q18",    # Kidfluencers ('to what extent')
    "forumias_gs2_flt1_q2",     # property rights, case laws
    "forumias_gs2_flt2_q16",    # food security; examiner flagged wrong GHI rank
    "forumias_gs3_flt2_q1",     # debt-to-GDP; examiner flagged wrong 29% figure
    "forumias_gs2_flt2_q19",    # BIMSTEC; wrong member list
    "forumias_gs4_flt2_q9",     # case study (Gopal)
]

_STOP = set("""
also add more good fair valid well better write give mention points point answer intro
conclusion content context added with your this that from into have been could should
would like such some them they their there then than only very just each other part parts
""".split())


def words(text):
    return {w[:5] for w in re.findall(r"[a-z0-9][a-z0-9-]{2,}", str(text).lower()) if w not in _STOP}


def examiner_points(comment):
    return [p.strip() for p in re.split(r";|\n", comment or "") if len(p.strip()) > 3]


def our_feedback(res):
    def g(o, k, d=None):
        return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)
    parts = {
        "strengths": list(g(res, "strengths") or []),
        "weaknesses": list(g(res, "weaknesses") or []),
        "suggestions": list(g(res, "improvement_suggestions") or []),
        "dimension notes": [t for t in (str(g(d, "improvement") or "").strip()
                                        for d in g(res, "dimension_scores") or [])
                            if t and t.lower() not in ("none", "null", "n/a", "-")],
        "fact-check": [f"{g(v, 'label')}: {g(v, 'claim')}" for v in g(res, "claim_verifications") or []],
    }
    parts["overall"] = [str(g(res, "overall_feedback") or "")]
    return parts


def reclean(res, case):
    """Re-apply the current post-generation filters to a saved result (no model calls)."""
    from app.evaluator.feedback import (clean_dimension_notes, clean_feedback, score_band,
                                        _is_gs4)
    verifs = res.get("claim_verifications") or []
    contradicted = [v for v in verifs if v.get("label") == "contradicted"]
    ctx = dict(answer=case["answer"], question=case["question"],
               word_count=res.get("word_count") or len(case["answer"].split()),
               word_limit=case.get("word_limit"),
               max_marks=case.get("original_max_marks") or case["max_marks"],
               total_score=float(res.get("total_score") or 0),
               supported_claims=[v.get("claim", "") for v in verifs if v.get("label") == "supported"],
               confirmed_claims=[v.get("claim", "") for v in contradicted],
               gs4=_is_gs4(case.get("subject"), case["question"]),
               extra_numbers=" ".join(str(v.get("quote") or "") for v in contradicted))
    band = score_band(ctx["total_score"], ctx["max_marks"])[0]
    fb, notes = clean_feedback({k: res.get(k) for k in ("strengths", "weaknesses",
                                "improvement_suggestions", "overall_feedback")},
                               band=band, concerns=res.get("factual_concerns"), **ctx)
    out = {**res, **fb, "dimension_scores": clean_dimension_notes(res.get("dimension_scores"), **ctx)}
    for n in notes:
        print(f"  [{case['id']}] {n}")
    return out


def run(ids, golden, saved):
    from app.evaluator.graph import evaluate_submission
    for cid in ids:
        c = golden[cid]
        marks = c.get("original_max_marks") or c["max_marks"]
        payload = {"question": c["question"], "answer": c["answer"], "subject": c["subject"],
                   "max_marks": marks, "word_limit": c["word_limit"]}
        for attempt in range(1, 4):
            t0 = time.time()
            try:
                res = evaluate_submission(payload)
                break
            except Exception as exc:
                print(f"[attempt {attempt}/3] {cid}: {type(exc).__name__}: {str(exc)[:120]}")
                res = None
                time.sleep(60 * attempt)
        if res is None:
            print(f"[failed] {cid}")
            continue
        print(f"[done] {cid}: {res.get('total_score')}/{marks} "
              f"(examiner {c.get('original_marks', c['examiner_marks'])}) {round(time.time() - t0)}s")
        saved.setdefault(cid, []).append({"total": res.get("total_score"), "max_marks": marks,
                                          "result": res})
        FULL.parent.mkdir(parents=True, exist_ok=True)
        FULL.write_text(json.dumps(saved, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="?", default=",".join(DEFAULT))
    ap.add_argument("--reuse", action="store_true", help="no model calls; use saved full runs")
    ap.add_argument("--reclean", action="store_true",
                    help="re-apply the current feedback filters to the saved runs (with --reuse)")
    args = ap.parse_args()
    ids = [i for i in args.ids.split(",") if i]

    golden = {}
    for f in Path(".").glob(GOLDEN_GLOB):
        for c in json.loads(f.read_text(encoding="utf-8")):
            golden[c["id"]] = c
    missing = [i for i in ids if i not in golden]
    if missing:
        raise SystemExit(f"Unknown case id(s): {', '.join(missing)}")
    saved = json.loads(FULL.read_text(encoding="utf-8")) if FULL.exists() else {}
    if not args.reuse:
        run(ids, golden, saved)

    lines = ["# Feedback vs examiner\n"]
    total_pts = total_hit = 0
    print(f"\n{'case':<28} {'marks (ours / examiner)':<24} examiner points we also raised")
    for cid in ids:
        runs = saved.get(cid) or []
        if not runs:
            print(f"{cid:<28} no full run saved")
            continue
        c, res = golden[cid], runs[-1]["result"]
        if args.reclean:
            res = reclean(res, c)
        marks = runs[-1]["max_marks"]
        ours = our_feedback(res)
        ours_words = words(" ".join(t for v in ours.values() for t in v))
        pts = examiner_points(c.get("examiner_comment_not_for_model", ""))
        hits = []
        for p in pts:
            pw = words(p)
            hits.append(bool(pw) and len(pw & ours_words) / len(pw) >= 0.5)
        total_pts += len(pts)
        total_hit += sum(hits)
        print(f"{cid:<28} {str(runs[-1]['total']) + ' / ' + str(c.get('original_marks', c['examiner_marks'])):<24} "
              f"{sum(hits)}/{len(pts)}")

        lines += [f"\n## {cid}\n", f"**Question:** {c['question'][:400]}\n",
                  f"**Marks:** ours {runs[-1]['total']} / {marks}, examiner "
                  f"{c.get('original_marks', c['examiner_marks'])} / {marks}\n",
                  "\n### Examiner's comment (point by point)\n"]
        lines += [f"- {'✅' if h else '❌'} {p}" for p, h in zip(pts, hits)]
        lines.append("\n### Our feedback\n")
        for k, v in ours.items():
            v = [t for t in v if t.strip()]
            if v:
                lines.append(f"**{k}:**")
                lines += [f"- {t}" for t in v]
                lines.append("")
    if total_pts:
        print(f"\nOverall: {total_hit}/{total_pts} examiner points ({round(100 * total_hit / total_pts)}%) "
              f"also appear in our feedback (rough key-word match; read the report).")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()
