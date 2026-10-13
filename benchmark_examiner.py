# """
# Score the examiner-marked golden set and compare model vs examiner.

# Run from the project root (resumable - safe to Ctrl+C and re-run):
#     python benchmark_examiner.py
#     python benchmark_examiner.py --report-only      # just re-print the table
#     python benchmark_examiner.py --only forumias_gs2_q3,forumias_gs2_q6
#     python benchmark_examiner.py --fresh            # re-run the selected cases (others are kept)

# Needs: data/benchmark/forumias_gs2_examiner_golden.json
# Writes: data/benchmark/results/examiner_gs2.json  (one entry per case, saved after each case)
# """
# import argparse
# import json
# import re
# import time
# from pathlib import Path

# GOLDEN = Path("data/benchmark/forumias_gs2_examiner_golden.json")
# RESULTS = Path("data/benchmark/results/examiner_gs2.json")
# INPUT_KEYS = ("question", "answer", "subject", "max_marks", "word_limit")


# def load_json(path, default):
#     try:
#         return json.loads(path.read_text(encoding="utf-8"))
#     except (FileNotFoundError, json.JSONDecodeError):
#         return default


# def save_json(path, data):
#     path.parent.mkdir(parents=True, exist_ok=True)
#     tmp = path.with_suffix(".tmp")
#     tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
#     tmp.replace(path)


# def run_cases(cases, saved, retries=2):
#     from app.evaluator.graph import evaluate_submission  # imported late so --report-only is instant

#     for case in cases:
#         cid = case["id"]
#         if cid in saved and saved[cid].get("status") == "success":
#             print(f"[skip] {cid} (already done)")
#             continue
#         payload = {k: case[k] for k in INPUT_KEYS}
#         for attempt in range(retries + 1):
#             t0 = time.time()
#             try:
#                 res = evaluate_submission(payload)
#                 break
#             except Exception as exc:  # network drops etc.
#                 print(f"[retry {attempt + 1}] {cid}: {exc!r}")
#                 res = {"status": "error", "errors": [repr(exc)]}
#                 time.sleep(5)
#         dims = res.get("dimension_scores") or []
#         saved[cid] = {
#             "status": res.get("status"),
#             "errors": res.get("errors"),
#             "seconds": round(time.time() - t0, 1),
#             "raw_total": res.get("raw_total_score"),
#             "final_total": res.get("total_score"),
#             "factual_concerns": res.get("factual_concerns"),
#             "claim_verifications": res.get("claim_verifications"),
#             "dims": [
#                 {
#                     "dimension": d.get("dimension"),
#                     "raw_level": d.get("raw_level"),
#                     "final_level": d.get("final_level"),
#                     "cap_note": d.get("cap_note"),
#                     "audit_note": d.get("audit_note"),
#                 }
#                 for d in dims
#             ],
#         }
#         save_json(RESULTS, saved)
#         print(f"[done] {cid}: raw={saved[cid]['raw_total']} final={saved[cid]['final_total']} "
#               f"({saved[cid]['seconds']}s)")


# def ranks(xs):
#     order = sorted(range(len(xs)), key=lambda i: xs[i])
#     r = [0.0] * len(xs)
#     i = 0
#     while i < len(order):
#         j = i
#         while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
#             j += 1
#         for k in range(i, j + 1):
#             r[order[k]] = (i + j) / 2 + 1
#         i = j + 1
#     return r


# def pearson(a, b):
#     n = len(a)
#     ma, mb = sum(a) / n, sum(b) / n
#     num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
#     da = sum((x - ma) ** 2 for x in a) ** 0.5
#     db = sum((y - mb) ** 2 for y in b) ** 0.5
#     return num / (da * db) if da and db else float("nan")


# def report(cases, saved):
#     rows = []
#     for c in cases:
#         r = saved.get(c["id"])
#         if not r or r.get("status") != "success":
#             continue
#         words = len(re.findall(r"\S+", c["answer"]))
#         capped = [d["dimension"] for d in r["dims"] if d["raw_level"] != d["final_level"]]
#         rows.append({
#             "id": c["id"].replace("forumias_gs2_", ""),
#             "exam": c["examiner_marks"],
#             "raw": r["raw_total"],
#             "final": r["final_total"],
#             "words": words,
#             "capped": capped,
#         })
#     if not rows:
#         print("No successful results yet.")
#         return

#     print(f"\n{'case':<6}{'examiner':>9}{'raw':>7}{'final':>7}{'diff':>7}{'words':>7}  levels lowered by caps/audit")
#     for r in rows:
#         print(f"{r['id']:<6}{r['exam']:>9}{r['raw']:>7}{r['final']:>7}{r['final'] - r['exam']:>+7.2f}"
#               f"{r['words']:>7}  {', '.join(r['capped']) or '-'}")

#     n = len(rows)
#     ex = [r["exam"] for r in rows]
#     fin = [r["final"] for r in rows]
#     raw = [r["raw"] for r in rows]

#     def mae(a, b):
#         return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

#     def bias(a, b):
#         return sum(x - y for x, y in zip(a, b)) / len(a)

#     print(f"\nCases scored: {n}")
#     print(f"Examiner mean {sum(ex) / n:.2f}   model final mean {sum(fin) / n:.2f}   model raw mean {sum(raw) / n:.2f}")
#     print(f"FINAL  vs examiner: MAE {mae(fin, ex):.2f}  bias {bias(fin, ex):+.2f}  "
#           f"within 0.5: {sum(abs(a - b) <= 0.5 for a, b in zip(fin, ex))}/{n}  within 1: {sum(abs(a - b) <= 1 for a, b in zip(fin, ex))}/{n}")
#     print(f"RAW    vs examiner: MAE {mae(raw, ex):.2f}  bias {bias(raw, ex):+.2f}   (before caps/audit)")
#     if n >= 4:
#         print(f"Rank agreement (Spearman) final: {pearson(ranks(fin), ranks(ex)):.2f}   "
#               f"(examiner range is narrow, treat as rough)")

#     # simple one-parameter scale, fitted on these cases only
#     k = sum(f * e for f, e in zip(fin, ex)) / sum(f * f for f in fin)
#     scaled = [f * k for f in fin]
#     print(f"Best single scale factor k = {k:.2f}  -> MAE after scaling {mae(scaled, ex):.2f}  "
#           f"(in-sample only: not proof, needs held-out cases)")

#     over = [r for r in rows if r["words"] > 150]
#     print(f"\nOver the 150-word limit: {len(over)}/{n} (examiner gave no word-count penalty on these)")
#     n_capped = sum(bool(r["capped"]) for r in rows)
#     print(f"Cases where caps/audit lowered at least one dimension: {n_capped}/{n}")


# def main():
#     ap = argparse.ArgumentParser()
#     ap.add_argument("--report-only", action="store_true")
#     ap.add_argument("--only", default="")
#     ap.add_argument("--fresh", action="store_true")
#     args = ap.parse_args()

#     cases = load_json(GOLDEN, None)
#     if cases is None:
#         raise SystemExit(f"Put the golden file at {GOLDEN}")
#     if args.only:
#         wanted = set(args.only.split(","))
#         cases = [c for c in cases if c["id"] in wanted]
#     saved = load_json(RESULTS, {})
#     if args.fresh:
#         # drop only the selected cases, never the whole results file
#         for c in cases:
#             saved.pop(c["id"], None)

#     if not args.report_only:
#         run_cases(cases, saved)
#     report(cases, saved)


# if __name__ == "__main__":
#     main()
"""
Score the examiner-marked golden set and compare model vs examiner.

Run from the project root (resumable - safe to Ctrl+C and re-run):
    python benchmark_examiner.py
    python benchmark_examiner.py --report-only      # just re-print the table
    python benchmark_examiner.py --only forumias_gs2_q3,forumias_gs2_q6
    python benchmark_examiner.py --fresh            # re-run the selected cases (others are kept)

Needs: one or more data/benchmark/*_examiner_golden.json files
Writes: data/benchmark/results/examiner_gs2.json  (one entry per case, saved after each case)
"""
import argparse
import json
import re
import time
from pathlib import Path

GOLDEN_GLOB = "data/benchmark/*_examiner_golden.json"   # every file ending in _examiner_golden.json is loaded
RESULTS = Path("data/benchmark/results/examiner_gs2.json")
INPUT_KEYS = ("question", "answer", "subject", "max_marks", "word_limit")


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def run_cases(cases, saved, retries=2):
    from app.evaluator.graph import evaluate_submission  # imported late so --report-only is instant

    for case in cases:
        cid = case["id"]
        if cid in saved and saved[cid].get("status") == "success":
            print(f"[skip] {cid} (already done)")
            continue
        payload = {k: case[k] for k in INPUT_KEYS}
        for attempt in range(retries + 1):
            t0 = time.time()
            try:
                res = evaluate_submission(payload)
                break
            except Exception as exc:  # network drops etc.
                print(f"[retry {attempt + 1}] {cid}: {exc!r}")
                res = {"status": "error", "errors": [repr(exc)]}
                time.sleep(5)
        dims = res.get("dimension_scores") or []
        saved[cid] = {
            "status": res.get("status"),
            "errors": res.get("errors"),
            "seconds": round(time.time() - t0, 1),
            "raw_total": res.get("raw_total_score"),
            "final_total": res.get("total_score"),
            "factual_concerns": res.get("factual_concerns"),
            "claim_verifications": res.get("claim_verifications"),
            "dims": [
                {
                    "dimension": d.get("dimension"),
                    "raw_level": d.get("raw_level"),
                    "final_level": d.get("final_level"),
                    "cap_note": d.get("cap_note"),
                    "audit_note": d.get("audit_note"),
                }
                for d in dims
            ],
        }
        save_json(RESULTS, saved)
        print(f"[done] {cid}: raw={saved[cid]['raw_total']} final={saved[cid]['final_total']} "
              f"({saved[cid]['seconds']}s)")


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    return num / (da * db) if da and db else float("nan")


def report(cases, saved):
    rows = []
    for c in cases:
        r = saved.get(c["id"])
        if not r or r.get("status") != "success":
            continue
        words = len(re.findall(r"\S+", c["answer"]))
        capped = [d["dimension"] for d in r["dims"] if d["raw_level"] != d["final_level"]]
        rows.append({
            "id": c["id"].replace("forumias_gs2_", ""),
            "exam": c["examiner_marks"],
            "raw": r["raw_total"],
            "final": r["final_total"],
            "words": words,
            "capped": capped,
        })
    if not rows:
        print("No successful results yet.")
        return

    print(f"\n{'case':<6}{'examiner':>9}{'raw':>7}{'final':>7}{'diff':>7}{'words':>7}  levels lowered by caps/audit")
    for r in rows:
        print(f"{r['id']:<6}{r['exam']:>9}{r['raw']:>7}{r['final']:>7}{r['final'] - r['exam']:>+7.2f}"
              f"{r['words']:>7}  {', '.join(r['capped']) or '-'}")

    n = len(rows)
    ex = [r["exam"] for r in rows]
    fin = [r["final"] for r in rows]
    raw = [r["raw"] for r in rows]

    def mae(a, b):
        return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

    def bias(a, b):
        return sum(x - y for x, y in zip(a, b)) / len(a)

    print(f"\nCases scored: {n}")
    print(f"Examiner mean {sum(ex) / n:.2f}   model final mean {sum(fin) / n:.2f}   model raw mean {sum(raw) / n:.2f}")
    print(f"FINAL  vs examiner: MAE {mae(fin, ex):.2f}  bias {bias(fin, ex):+.2f}  "
          f"within 0.5: {sum(abs(a - b) <= 0.5 for a, b in zip(fin, ex))}/{n}  within 1: {sum(abs(a - b) <= 1 for a, b in zip(fin, ex))}/{n}")
    print(f"RAW    vs examiner: MAE {mae(raw, ex):.2f}  bias {bias(raw, ex):+.2f}   (before caps/audit)")
    if n >= 4:
        print(f"Rank agreement (Spearman) final: {pearson(ranks(fin), ranks(ex)):.2f}   "
              f"(examiner range is narrow, treat as rough)")

    # simple one-parameter scale, fitted on these cases only
    k = sum(f * e for f, e in zip(fin, ex)) / sum(f * f for f in fin)
    scaled = [f * k for f in fin]
    print(f"Best single scale factor k = {k:.2f}  -> MAE after scaling {mae(scaled, ex):.2f}  "
          f"(in-sample only: not proof, needs held-out cases)")

    insts = {}
    for c in cases:
        insts.setdefault(c.get("institute", "?"), []).append(c["id"])
    if len(insts) > 1:
        print("\nPer institute:")
        for name, ids in insts.items():
            sub = [r for r, c in zip(rows, [x for x in cases if saved.get(x["id"], {}).get("status") == "success"]) if c["id"] in ids]
            if sub:
                d = [r["final"] - r["exam"] for r in sub]
                print(f"  {name:<14} n={len(sub)}  MAE {sum(abs(x) for x in d)/len(d):.2f}  bias {sum(d)/len(d):+.2f}")

    over = [r for r in rows if r["words"] > 150]
    print(f"\nOver the 150-word limit: {len(over)}/{n} (examiner gave no word-count penalty on these)")
    n_capped = sum(bool(r["capped"]) for r in rows)
    print(f"Cases where caps/audit lowered at least one dimension: {n_capped}/{n}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    cases = []
    for f in sorted(Path(".").glob(GOLDEN_GLOB)):
        cases.extend(load_json(f, []))
    if not cases:
        raise SystemExit(f"No golden files found matching {GOLDEN_GLOB}")
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    saved = load_json(RESULTS, {})
    if args.fresh:
        # drop only the selected cases, never the whole results file
        for c in cases:
            saved.pop(c["id"], None)

    if not args.report_only:
        run_cases(cases, saved)
    report(cases, saved)


if __name__ == "__main__":
    main()