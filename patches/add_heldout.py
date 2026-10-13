"""Marks a fixed set of answers as held-out in the golden files.
Run from the project root:   python add_heldout.py
Held-out answers are NOT to be used for tuning prompts or rubrics: look at them
only with   python benchmark_fast.py --split heldout
Safe to re-run."""
import json
from pathlib import Path

HELDOUT = {
    "forumias_gs2_q3", "forumias_gs2_q5", "forumias_gs2_q7", "forumias_gs2_q10",
    "forumias_gs1_q6",
    "understandupsc_gs4_q3",
}

found = set()
for f in sorted(Path("data/benchmark").glob("*_examiner_golden.json")):
    cases = json.loads(f.read_text(encoding="utf-8"))
    for c in cases:
        c["heldout"] = c["id"] in HELDOUT
        if c["heldout"]:
            found.add(c["id"])
    f.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{f.name}: {sum(c['heldout'] for c in cases)} held out of {len(cases)}")

missing = HELDOUT - found
if missing:
    print("Not found in any golden file:", ", ".join(sorted(missing)))