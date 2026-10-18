"""
Fast scoring loop: re-score examiner-marked answers WITHOUT re-running
fact-check, feedback and consistency nodes.

First run per case: runs validate -> analyze_input -> analyze_question -> extract_features
and caches that state (pickle). Later runs reuse the cache, so only the scoring call is repeated.

    python benchmark_fast.py                     # score each case 3 times, report median
    python benchmark_fast.py --repeats 1
    python benchmark_fast.py --only forumias_gs1_q1,forumias_gs1_q3
    python benchmark_fast.py --rebuild-cache     # re-run the upstream nodes
    python benchmark_fast.py --report-only
    python benchmark_fast.py --split heldout     # only cases with "heldout": true in the golden file
    python benchmark_fast.py --split dev         # only the others
    python benchmark_fast.py --replay            # NO model calls: re-apply the current scoring.py
                                                 # (caps, audit, factual rule, rounding) to the saved
                                                 # raw judge outputs. Takes seconds.

Every run now also saves the judge's raw output ("raw"), which is what --replay needs.
Runs saved by the older version have no raw output and are skipped by --replay.

Writes: data/benchmark/results/fast_scores.json (includes the judge's justification text per dimension)
        data/benchmark/results/fast_replay.json (only for --replay; fast_scores.json is never touched by it)
"""
import argparse
import copy
import json
import os
import pickle
import re
import statistics
import time
from pathlib import Path

# The benchmark repeats runs itself; one judge call per run keeps old results comparable.
os.environ.setdefault("JUDGE_SAMPLES", "1")

GOLDEN_GLOB = "data/benchmark/*_examiner_golden.json"
CACHE_DIR = Path("data/benchmark/results/state_cache")
# BENCH_RESULTS lets a judge experiment write to its own file instead of the main one.
RESULTS = Path(os.getenv("BENCH_RESULTS", "data/benchmark/results/fast_scores.json"))
REPLAY = Path("data/benchmark/results/fast_replay.json")
INPUT_KEYS = ("question", "answer", "subject", "max_marks", "word_limit")
UPSTREAM = ("validate_input_node", "analyze_input_node", "analyze_question_node", "extract_features_node")


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


def get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def build_state(case, graph_mod):
    """Run only the upstream nodes; each node returns a dict of updates."""
    state = dict(case_input(case))
    for name in UPSTREAM:
        node = getattr(graph_mod, name, None)
        if node is None:
            continue
        update = node(state)
        if update:
            state.update(update)
        if state.get("status") == "error" or state.get("errors"):
            raise RuntimeError(f"{name} failed: {state.get('errors')}")
    return state


def case_input(case):
    # same shape evaluate_submission() starts from; adjust here if your initial state differs
    inp = {k: case[k] for k in INPUT_KEYS}
    # 15-mark cases are stored scaled to /10 in the goldens. The evaluator must still see
    # the real question (15 marks, 250 words), so pass the original marks; the report
    # scales the result back to /10 (see to_ten).
    if case.get("original_max_marks"):
        inp["max_marks"] = case["original_max_marks"]
    return inp


def to_ten(case, value):
    """Put an evaluator total on the same /10 scale as examiner_marks."""
    orig = case.get("original_max_marks")
    if value is None or not orig:
        return value
    return round(value * 10 / orig, 2)


def check_case(case):
    """Warn about golden entries the evaluator would misread."""
    orig = case.get("original_max_marks") or case.get("max_marks")
    want = {10: 150, 15: 250, 20: 250}.get(orig)
    if want and case.get("word_limit") != want:
        print(f"[warn] {case['id']}: {orig} marks but word_limit={case.get('word_limit')} (expected {want})")


def get_state(case, graph_mod, rebuild):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / f"{case['id']}.pkl"
    if p.exists() and not rebuild:
        return pickle.loads(p.read_bytes())
    state = build_state(case, graph_mod)
    p.write_bytes(pickle.dumps(state))
    return state


def score_once(state, graph_mod, replay_raw=None):
    """Run the scoring node once. Captures the judge's raw output; with replay_raw the
    saved raw output is returned instead of calling the model."""
    if not hasattr(graph_mod, "score_answer"):
        raise RuntimeError("graph.py has no 'score_answer' name; capture/replay needs it "
                           "(from app.evaluator.scoring import score_answer).")
    s = dict(state)
    s.setdefault("claim_verifications", [])
    s.setdefault("factual_concerns", [])
    captured = {}
    original = graph_mod.score_answer

    def wrapper(*args, **kwargs):
        if replay_raw is not None:
            result = copy.deepcopy(replay_raw)
        else:
            result = original(*args, **kwargs)
        captured["raw"] = copy.deepcopy(result)
        return result

    graph_mod.score_answer = wrapper
    try:
        update = graph_mod.evaluate_answer_node(s)
    finally:
        graph_mod.score_answer = original
    dims = update.get("dimension_scores") or []
    if not update.get("scores_valid") or not dims:
        # The judge returned an incomplete or invalid response. Raise so the caller
        # retries, instead of saving a 0.0 that looks like a real score.
        raise RuntimeError(f"invalid judge output: {update.get('score_errors')}")
    return {
        "raw_total": update.get("raw_total_score"),
        "final_total": update.get("total_score"),
        "raw": captured.get("raw"),
        "dims": [
            {
                "dimension": get(d, "dimension"),
                "raw_level": get(d, "raw_level"),
                "final_level": get(d, "final_level"),
                "justification": get(d, "justification"),
                "improvement": get(d, "improvement"),
                "cap_note": get(d, "cap_note"),
                "audit_note": get(d, "audit_note"),
            }
            for d in dims
        ],
    }


def replay_cases(cases, saved):
    """Re-apply current post-processing to saved raw judge outputs. No model calls."""
    import app.evaluator.graph as graph_mod

    out = {}
    skipped = 0
    for case in cases:
        runs = saved.get(case["id"], {}).get("runs", [])
        usable = [r for r in runs if r.get("raw")]
        if not usable:
            skipped += 1
            continue
        state = get_state(case, graph_mod, False)
        out[case["id"]] = {"runs": [score_once(state, graph_mod, replay_raw=r["raw"]) for r in usable]}
    save_json(REPLAY, out)
    print(f"Replayed {len(out)} cases from saved raw output; skipped {skipped} without raw output.")
    return out


# Free endpoints reject calls when their shared capacity is used up (429 / 503 "busy" /
# "per minute limit"). That is not a judge failure: wait and try again instead of
# losing the case. BENCH_PAUSE (seconds) adds a pause before every judge call.
_BUSY_MARKERS = ("429", "rate limit", "rate_limit", "per minute limit", "are busy", "get_channel_failed")
BUSY_WAITS = (20, 40, 60, 90, 120, 180)
PAUSE = float(os.getenv("BENCH_PAUSE", "0"))


def _is_busy(exc):
    text = repr(exc).lower()
    return any(m in text for m in _BUSY_MARKERS)


def score_with_backoff(state, graph_mod, cid):
    waited = 0
    for wait in BUSY_WAITS + (None,):
        if PAUSE:
            time.sleep(PAUSE)
        try:
            result = score_once(state, graph_mod)
            if waited:
                print(f"       waited {waited}s in total for {cid}")
            return result
        except Exception as exc:
            if wait is None or not _is_busy(exc):
                raise
            if not waited:  # one line per case, however many waits follow
                print(f"[busy] {cid}: provider busy, waiting (up to {sum(BUSY_WAITS)}s)...")
            waited += wait
            time.sleep(wait)


def run_cases(cases, saved, repeats, rebuild):
    import app.evaluator.graph as graph_mod

    for case in cases:
        cid = case["id"]
        # Runs without dimension scores were failed judge calls saved as 0.0; redo them.
        have = [r for r in saved.get(cid, {}).get("runs", []) if r.get("dims")]
        if len(have) >= repeats and not rebuild:
            print(f"[skip] {cid} ({len(have)} runs)")
            continue
        t0 = time.time()
        try:
            state = get_state(case, graph_mod, rebuild)
        except Exception as exc:
            print(f"[error] {cid} upstream: {exc!r}")
            continue
        runs = list(have)
        while len(runs) < repeats:
            try:
                runs.append(score_with_backoff(state, graph_mod, cid))
            except Exception as exc:
                print(f"[retry] {cid}: {exc!r}")
                time.sleep(5)
                try:
                    runs.append(score_with_backoff(state, graph_mod, cid))
                except Exception as exc2:
                    print(f"[error] {cid}: {exc2!r}")
                    break
            saved[cid] = {"runs": runs}
            save_json(RESULTS, saved)
        finals = [r["final_total"] for r in runs if r.get("final_total") is not None]
        print(f"[done] {cid}: finals={finals} ({time.time() - t0:.0f}s)")


def pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    return num / (da * db) if da and db else float("nan")


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


def report(cases, saved, show_text):
    rows = []
    for c in cases:
        runs = [r for r in saved.get(c["id"], {}).get("runs", []) if r.get("dims")]
        finals = [to_ten(c, r["final_total"]) for r in runs if r.get("final_total") is not None]
        if not finals:
            continue
        rows.append({"case": c, "runs": runs, "finals": finals, "med": statistics.median(finals)})
    if not rows:
        print("No results yet.")
        return

    print(f"\n{'case':<18}{'exam':>6}{'median':>8}{'diff':>7}{'spread':>8}  levels (rel/con/ana/cov/str, last run)")
    for r in rows:
        c = r["case"]
        last = r["runs"][-1]["dims"]
        lv = "/".join(str(d["final_level"]) for d in last)
        print(f"{c['id'][-18:]:<18}{c['examiner_marks']:>6}{r['med']:>8}{r['med'] - c['examiner_marks']:>+7.2f}"
              f"{max(r['finals']) - min(r['finals']):>8.1f}  {lv}")

    n = len(rows)
    ex = [r["case"]["examiner_marks"] for r in rows]
    med = [r["med"] for r in rows]
    mae = sum(abs(a - b) for a, b in zip(med, ex)) / n
    bias = sum(a - b for a, b in zip(med, ex)) / n
    spread = sum(max(r["finals"]) - min(r["finals"]) for r in rows) / n
    print(f"\nCases {n} | MAE {mae:.2f} | bias {bias:+.2f} | "
          f"within 0.5: {sum(abs(a - b) <= 0.5 for a, b in zip(med, ex))}/{n} | "
          f"within 1: {sum(abs(a - b) <= 1 for a, b in zip(med, ex))}/{n}")
    print(f"Mean run-to-run spread (max-min): {spread:.2f}  <- differences smaller than this are noise")
    if n >= 4:
        print(f"Spearman: {pearson(ranks(med), ranks(ex)):.2f} (rough)")

    for name in sorted({r['case'].get('institute', '?') for r in rows}):
        sub = [r for r in rows if r["case"].get("institute", "?") == name]
        d = [r["med"] - r["case"]["examiner_marks"] for r in sub]
        print(f"  {name:<14} n={len(sub)} MAE {sum(map(abs, d)) / len(d):.2f} bias {sum(d) / len(d):+.2f}")

    if show_text:
        print("\nJudge reasoning (last run), dimensions at level <= 2 only:")
        for r in rows:
            for d in r["runs"][-1]["dims"]:
                if d["final_level"] is not None and d["final_level"] <= 2:
                    print(f"\n[{r['case']['id']}] {d['dimension']} = {d['final_level']}\n  {d.get('justification')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--only", default="")
    ap.add_argument("--split", choices=["all", "dev", "heldout"], default="all")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="discard saved scores for the selected cases")
    ap.add_argument("--text", action="store_true", help="print judge justification for low dimensions")
    ap.add_argument("--replay", action="store_true",
                    help="re-score saved raw judge outputs with the current scoring.py (no model calls)")
    args = ap.parse_args()

    cases = []
    for f in sorted(Path(".").glob(GOLDEN_GLOB)):
        cases.extend(load_json(f, []))
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if args.split != "all":
        want_held = args.split == "heldout"
        cases = [c for c in cases if bool(c.get("heldout")) == want_held]
    if not cases:
        raise SystemExit("No cases selected.")
    for c in cases:
        check_case(c)

    saved = load_json(RESULTS, {})
    if args.fresh:
        for c in cases:
            saved.pop(c["id"], None)
    if args.replay:
        saved = replay_cases(cases, saved)
    elif not args.report_only:
        run_cases(cases, saved, args.repeats, args.rebuild_cache)
    report(cases, saved, args.text)


if __name__ == "__main__":
    main()