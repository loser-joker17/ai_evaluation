"""Read-only: how often did the factual-concern cap actually change a content_substantiation level?
Run from the project root (safe while a benchmark is running):  python analyze_caps.py"""
import json
from pathlib import Path

saved = json.loads(Path("data/benchmark/results/fast_scores.json").read_text(encoding="utf-8"))
exam = {}
for f in Path("data/benchmark").glob("*_examiner_golden.json"):
    for c in json.loads(f.read_text(encoding="utf-8")):
        exam[c["id"]] = c["examiner_marks"]

runs = lowered = flagged = 0
print(f"{'case':<24}{'exam':>6}  content raw->final per run")
for cid, v in saved.items():
    row = []
    for r in v.get("runs", []):
        for d in r.get("dims", []):
            if d.get("dimension") != "content_substantiation":
                continue
            runs += 1
            note = d.get("cap_note") or ""
            has = "possible factual" in note or "contradicted" in note
            flagged += has
            if has and d["final_level"] < d["raw_level"]:
                lowered += 1
            row.append(f"{d['raw_level']}->{d['final_level']}{'*' if has else ''}")
    print(f"{cid:<24}{exam.get(cid, '?'):>6}  {'  '.join(row)}")
print(f"\n* = a factual note was attached. Runs: {runs}, with a factual note: {flagged}, "
      f"where the note actually LOWERED the level: {lowered}")