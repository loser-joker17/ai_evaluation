"""Time one real evaluation, stage by stage.
Run from the project root:
    python time_one.py forumias_gs2_q7            # new graph, prints time after each stage
    python time_one.py forumias_gs2_q7 --twice    # run again to see the question-analysis cache
    python time_one.py forumias_gs2_q7 --old      # old graph (needs graph_old.py next to graph.py), total only
"""
import importlib
import json
import sys
import time
from pathlib import Path

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = {a for a in sys.argv[1:] if a.startswith("--")}
if not args:
    raise SystemExit("usage: python time_one.py <case id> [--twice] [--old]")

case = None
for f in sorted(Path("data/benchmark").glob("*_examiner_golden.json")):
    for c in json.loads(f.read_text(encoding="utf-8")):
        if c["id"] == args[0]:
            case = c
if case is None:
    raise SystemExit(f"case {args[0]} not found in data/benchmark/*_examiner_golden.json")

payload = {k: case[k] for k in ("question", "answer", "subject", "max_marks", "word_limit")}
module_name = "app.evaluator.graph_old" if "--old" in flags else "app.evaluator.graph"
graph = importlib.import_module(module_name)


def run_once(label):
    t0 = time.time()
    if hasattr(graph, "evaluate_submission_stream") and "--old" not in flags:
        result = None
        for node, update in graph.evaluate_submission_stream(payload):
            print(f"  {time.time() - t0:7.1f}s  after {node}")
            if node == "final":
                result = update
    else:
        result = graph.evaluate_submission(payload)
    total = time.time() - t0
    print(f"{label}: total {total:.1f}s | status {result.get('status')} | "
          f"marks {result.get('total_score')} (examiner {case['examiner_marks']})")


print(f"{case['id']} using {module_name}")
run_once("run 1")
if "--twice" in flags:
    run_once("run 2")