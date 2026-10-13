"""Time every step of one evaluation separately (run one after another, so each number is clean).
Run from the project root:   python time_steps.py forumias_gs2_q7
Takes about as long as one normal evaluation (a few minutes)."""
import json
import sys
import time
from pathlib import Path

import app.evaluator.graph as g

if len(sys.argv) < 2:
    raise SystemExit("usage: python time_steps.py <case id>")

case = None
for f in sorted(Path("data/benchmark").glob("*_examiner_golden.json")):
    for c in json.loads(f.read_text(encoding="utf-8")):
        if c["id"] == sys.argv[1]:
            case = c
if case is None:
    raise SystemExit("case not found")

state = {k: case[k] for k in ("question", "answer", "subject", "max_marks", "word_limit")}
rows = []


def step(name, fn):
    t = time.time()
    update = fn(state)
    state.update(update or {})
    rows.append((name, time.time() - t))
    print(f"  {name:<28}{rows[-1][1]:7.1f}s", flush=True)


state.update(g.analyze_input_node(state))   # word count and limit status (instant)

# the question analysis may be cached from an earlier call in this process; this is a fresh process
step("analyze_question", g.analyze_question_node)
step("extract_features", g.extract_features_node)
step("fact_check", g.fact_check_node)
step("evaluate_answer (scoring)", g.evaluate_answer_node)
step("generate_feedback", g.generate_feedback_node)
step("check_feedback_consistency", g.check_feedback_consistency_node)

total = sum(t for _, t in rows)
prep_parallel = max(rows[0][1] + rows[1][1], rows[2][1])
print(f"\nsequential total {total:.1f}s")
print(f"with the parallel prepare step: {total - (rows[0][1] + rows[1][1] + rows[2][1]) + prep_parallel:.1f}s")