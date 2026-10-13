"""Does the light model give the same question analysis and features as the cached ones?
No scoring, no overwriting of the cache. Run from the project root:
    python compare_light.py
    python compare_light.py --only forumias_gs2_q7,forumias_gs1_q1
Set LIGHT_MODEL in .env first (after python patch_light_llm.py)."""
import argparse
import json
import pickle
import time
from collections import defaultdict
from pathlib import Path

import app.evaluator.graph as g

CACHE_DIR = Path("data/benchmark/results/state_cache")

ap = argparse.ArgumentParser()
ap.add_argument("--only", default="")
args = ap.parse_args()


def plain(x):
    return x.model_dump() if hasattr(x, "model_dump") else x


def same(a, b):
    """Scalars must be equal; lists only need the same length."""
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b)
    return a == b


agree = defaultdict(lambda: [0, 0])      # field -> [same, total]
disagree = []                            # (case, field, old, new)
cases = []
for f in sorted(Path("data/benchmark").glob("*_examiner_golden.json")):
    cases.extend(json.loads(f.read_text(encoding="utf-8")))
if args.only:
    wanted = set(args.only.split(","))
    cases = [c for c in cases if c["id"] in wanted]

done = 0
for c in cases:
    p = CACHE_DIR / f"{c['id']}.pkl"
    if not p.exists():
        print(f"[skip] {c['id']} (no cached state)")
        continue
    old = pickle.loads(p.read_bytes())
    t0 = time.time()
    try:
        state = {k: c[k] for k in ("question", "answer", "subject", "max_marks", "word_limit")}
        state.update(g.analyze_input_node(state))
        state.update(g.analyze_question_node(state))
        state.update(g.extract_features_node(state))
    except Exception as exc:
        print(f"[error] {c['id']}: {exc!r}")
        continue
    for part, key in (("question", "question_analysis"), ("features", "answer_features")):
        a, b = plain(old.get(key)) or {}, plain(state.get(key)) or {}
        for field in sorted(set(a) | set(b)):
            ok = same(a.get(field), b.get(field))
            agree[f"{part}.{field}"][0] += ok
            agree[f"{part}.{field}"][1] += 1
            if not ok:
                disagree.append((c["id"], f"{part}.{field}", a.get(field), b.get(field)))
    done += 1
    print(f"[done] {c['id']} ({time.time() - t0:.0f}s)", flush=True)

print(f"\nCompared {done} answers. Agreement per field (same value, or same list length):")
for field, (s, t) in sorted(agree.items(), key=lambda kv: kv[1][0] / kv[1][1]):
    print(f"  {field:<42}{s:>3}/{t:<3} {100 * s / t:5.0f}%")

KEY = ("directive", "has_introduction", "has_conclusion", "mechanisms_explained")
print("\nDisagreements on the fields that drive scoring:")
shown = 0
for cid, field, o, n in disagree:
    if field.split(".")[-1] in KEY:
        print(f"  {cid:<22}{field:<34}cached={str(o)[:40]!r}  light={str(n)[:40]!r}")
        shown += 1
if not shown:
    print("  none")