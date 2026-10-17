"""Stage 2: directive guide + demand check. Run once from the project folder, AFTER
apply_directive_fix.py, with app/evaluator/demands.py already saved:

    python scripts/apply_demand_check.py

Changes (backups *.bak2 are written first):
  app/schemas.py           DemandCheck model; DimensionScoresResponse.demand_check
  app/evaluator/scoring.py - question type now comes from demands.directive_kind (every
                             directive in the question, most demanding one wins)
                           - the judge prompt gets "what the directives demand" and a
                             numbered demand check (Q = asked by the question, D = implied
                             by a directive)
                           - score_answer returns the demand list with the judge output
                           - finalize_scores caps levels when a demand is missing/thin
  app/evaluator/graph.py   passes demands + demand_check to finalize_scores
  tests/test_scoring.py    tests updated for the new question types; new demand tests

Each step prints OK / SKIP / FAIL. A file is written only if all its steps succeed.
"""
import re
import shutil
from pathlib import Path

DEMAND_SCHEMA = '''

class DemandCheck(BaseModel):
    """The judge's status for one numbered demand (Q1, D1 ...)."""

    id: str
    status: Literal["covered", "thin", "missing"]
    evidence: str = ""
'''

NEW_TESTS = '''


def test_directive_kind_uses_every_directive():
    from app.evaluator.demands import directive_kind, find_directives
    assert directive_kind("", "What is floriculture? How is it helpful in boosting exports?") == "descriptive"
    assert directive_kind("", "What are REEs? Discuss the implications.") == "balanced"
    assert directive_kind("Examine", "To what extent can X be seen as Y?") == "judgement"
    assert directive_kind("", "Critically analyse the scheme.") == "judgement"
    assert directive_kind("", "Analyze.") == "analytical"
    keys = [f["key"] for f in find_directives("Critically examine the procedure.")]
    assert keys == ["critically"]                        # not also "examine"
    # "State" as a noun and "What is your opinion" are not directives of their own
    assert "define" not in [f["key"] for f in find_directives("What is your opinion? Give reasons.")]
    assert find_directives("The British Indian State changed.") == []


def test_build_demands_numbers_parts_and_directive_needs():
    from app.evaluator.demands import build_demands
    q = "What are the objectives of IBC? To what extent has it been successful?"
    d = build_demands(q, {"question_parts": ["objectives of IBC", "extent of success"], "directive": ""})
    ids = [x["id"] for x in d]
    assert ids[:2] == ["Q1", "Q2"]
    assert any(x["source"] == "directive" and x["cap"] == "analysis_depth" for x in d)
    # no question_parts: the question itself is Q1
    assert build_demands("Discuss X.", {})[0] == {"id": "Q1", "text": "Discuss X.", "source": "question", "cap": None}


def test_demand_caps():
    from app.evaluator.demands import build_demands, demand_caps
    q = "Explain X. What are its consequences? To what extent has it worked?"
    d = build_demands(q, {"question_parts": ["explain X", "consequences", "extent"]})
    assert demand_caps(d, []) == {}                      # old saved runs: no caps
    caps = demand_caps(d, [{"id": "Q2", "status": "missing"}])
    assert caps["coverage_balance"][0] == 3 and caps["relevance"][0] == 3
    assert "consequences" in caps["coverage_balance"][1]
    caps = demand_caps(d, [{"id": "Q1", "status": "missing"}, {"id": "Q2", "status": "missing"}])
    assert caps["coverage_balance"][0] == 2
    assert demand_caps(d, [{"id": "Q3", "status": "thin"}])["coverage_balance"][0] == 3
    verdict = next(x["id"] for x in d if "verdict" in x["text"])
    assert demand_caps(d, [{"id": verdict, "status": "missing"}])["analysis_depth"][0] == 3
    # feedback-only directive demands never cap; unknown ids are ignored
    assert demand_caps(d, [{"id": "Q1", "status": "covered"}, {"id": "Z9", "status": "missing"}]) == {}


def test_finalize_applies_demand_caps():
    from app.evaluator.demands import build_demands
    items = [{"dimension": dim, "score": 5, "justification": "ok",
              "evidence_from_answer": [], "improvement": "None"}
             for dim in ("relevance", "content_substantiation", "analysis_depth",
                         "coverage_balance", "structure_presentation")]
    d = build_demands("Q?", {"question_parts": ["part one", "part two"]})
    final, issues = finalize_scores(items, {"has_conclusion": True}, 140, 150, 10, "within_limit",
                                    demands=d, demand_check=[{"id": "Q2", "status": "missing"}])
    levels = {x["dimension"]: x["final_level"] for x in final}
    assert levels["coverage_balance"] == 3 and levels["relevance"] == 3
'''


def step(steps, name, ok, note=""):
    steps.append((name, "OK" if ok else "FAIL", note))


def patch_schemas(s):
    if "class DemandCheck" in s:
        return s, [("schemas", "SKIP", "already applied")]
    steps = []
    anchor = "class DimensionScoresResponse(BaseModel):"
    ok = s.count(anchor) == 1
    if ok:
        s = s.replace(anchor, DEMAND_SCHEMA.strip("\n") + "\n\n\n" + anchor)
    step(steps, "DemandCheck model", ok)
    s, n = re.subn(r"(class DimensionScoresResponse\(BaseModel\):.*?factual_concerns: list\[FactualConcern\] = Field\(default_factory=list\)\n)",
                   r"\1    demand_check: list[DemandCheck] = Field(default_factory=list)\n", s, count=1, flags=re.S)
    step(steps, "demand_check field", n == 1, f"{n} match(es)")
    if not re.search(r"^from typing import .*\bLiteral\b", s, re.M):
        if re.search(r"^from typing import ", s, re.M):
            s = re.sub(r"^from typing import (.*)$", r"from typing import \1, Literal", s, count=1, flags=re.M)
        else:
            s = "from typing import Literal\n" + s
    return s, steps


def patch_scoring(s):
    if "from app.evaluator.demands import" in s:
        return s, [("scoring", "SKIP", "already applied")]
    steps = []
    # import
    s, n = re.subn(r"^(from app\.schemas import[^\n]*\n)",
                   r"\1from app.evaluator.demands import (\n    directive_kind, directive_guide, build_demands, demand_block, demand_caps,\n)\n",
                   s, count=1, flags=re.M)
    step(steps, "import demands", n == 1, f"{n} match(es)")

    # keyword tuples -> replaced by demands.DIRECTIVES
    s, n = re.subn(r"_ANALYTICAL_DIRECTIVES = \(.*?\)\n_JUDGEMENT_DIRECTIVES = \(.*?\)\n_DESCRIPTIVE_DIRECTIVES = \(.*?\)\n",
                   "# Directive words and what they demand live in app/evaluator/demands.py (DIRECTIVES).\n",
                   s, count=1, flags=re.S)
    step(steps, "remove old keyword lists", n == 1, f"{n} match(es)")

    # classification functions
    s, n = re.subn(
        r"def analysis_expectation\(directive\) -> str:.*?\n    return \"balanced\"\n",
        'def analysis_expectation(directive) -> str:\n'
        '    """Return \'analytical\', \'judgement\', \'descriptive\' or \'balanced\' for a directive."""\n'
        '    return directive_kind(directive)\n', s, count=1, flags=re.S)
    step(steps, "analysis_expectation", n == 1, f"{n} match(es)")
    s, n = re.subn(
        r"def directive_type\(directive, question: str = \"\"\) -> str:.*?\n    return kind\n",
        'def directive_type(directive, question: str = "") -> str:\n'
        '    """Every directive in the extracted directive and the question text counts; the most\n'
        '    demanding one decides (judgement > analytical > balanced > descriptive)."""\n'
        '    return directive_kind(directive, question)\n', s, count=1, flags=re.S)
    step(steps, "directive_type", n == 1, f"{n} match(es)")

    # prompt: build demands before the prompt
    s, n = re.subn(
        r"(    analysis_levels = ANALYSIS_LEVELS\[directive_type\(directive, question\)\]\n)",
        r"\1    demands = build_demands(question, question_analysis)\n"
        r"    directive_text = directive_guide(question, directive)\n"
        r"    demand_text = demand_block(demands)\n", s, count=1)
    step(steps, "build demands in score_answer", n == 1, f"{n} match(es)")

    anchor = "Score each of the five dimensions as an integer LEVEL from 0 to 5."
    ok = s.count(anchor) == 1
    if ok:
        s = s.replace(anchor, "{directive_text}\n\n{demand_text}\n\n" + anchor)
    step(steps, "prompt: directives + demand check", ok, f"{s.count(anchor)} match(es)")

    s, n = re.subn(r"    return structured_llm\.invoke\(prompt\)\.model_dump\(\)\n",
                   "    result = structured_llm.invoke(prompt).model_dump()\n"
                   '    result["demands"] = demands      # saved with the raw output, so --replay can re-apply caps\n'
                   "    return result\n", s, count=1)
    step(steps, "score_answer returns demands", n == 1, f"{n} match(es)")

    # finalize_scores: params + caps
    s, n = re.subn(r"(def finalize_scores\([^)]*?    question: str = \"\",\n)(\) -> )",
                   r"\1    demands: list[dict] | None = None,\n    demand_check: list | None = None,\n\2", s, count=1)
    step(steps, "finalize_scores signature", n == 1, f"{n} match(es)")
    s, n = re.subn(
        r"(    caps = compute_caps\(features, word_count, word_limit, word_limit_status, directive, question\)\n)",
        lambda m: m.group(1)
        + "    # The judge's demand check: a missing or thin part of the question caps the levels.\n"
        + "    for dim, cap in demand_caps(demands, demand_check).items():\n"
        + '        caps[dim] = (min(caps[dim][0], cap[0]), f"{caps[dim][1]} {cap[1]}") if dim in caps else cap\n',
        s, count=1)
    step(steps, "finalize applies demand caps", n == 1, f"{n} match(es)")
    return s, steps


def patch_graph(s):
    if "demand_check=result.get(" in s:
        return s, [("graph", "SKIP", "already applied")]
    s, n = re.subn(r"(        question=state\[\"question\"\],\n)(    \))",
                   lambda m: m.group(1) + '        demands=result.get("demands"),\n'
                   '        demand_check=result.get("demand_check"),\n' + m.group(2),
                   s, count=1)
    return s, [("finalize_scores call", "OK" if n == 1 else "FAIL", f"{n} match(es)")]


def patch_tests(s):
    if "test_directive_kind_uses_every_directive" in s:
        return s, [("tests", "SKIP", "already applied")]
    steps = []
    for old, new in (
        ('    assert analysis_expectation("Identify and discuss") == "descriptive"\n',
         '    assert analysis_expectation("Identify and discuss") == "balanced"   # discuss outranks identify\n'),
        ('    assert analysis_expectation("Critically analyse") == "analytical"\n',
         '    assert analysis_expectation("Critically analyse") == "judgement"   # weigh both sides, then a verdict\n'),
        ('    assert directive_type("Analyze", q) == "analytical"   # an explicit directive wins\n',
         '    assert directive_type("Analyze", q) == "judgement"    # "to what extent" in the question outranks it\n'),
    ):
        if old in s:
            s = s.replace(old, new)
            steps.append(("update old assertion", "OK", ""))
        else:
            steps.append(("update old assertion", "SKIP", "line not found"))
    if "finalize_scores" not in s.split("def ", 1)[0]:
        s = "from app.evaluator.scoring import finalize_scores\n" + s
    s = s.rstrip("\n") + NEW_TESTS
    steps.append(("new tests", "OK", ""))
    return s, steps


def main():
    root = Path(__file__).resolve().parent.parent
    if not (root / "app/evaluator/demands.py").exists():
        raise SystemExit("Save app/evaluator/demands.py first.")
    for rel, fn in (("app/schemas.py", patch_schemas),
                    ("app/evaluator/scoring.py", patch_scoring),
                    ("app/evaluator/graph.py", patch_graph),
                    ("tests/test_scoring.py", patch_tests)):
        p = root / rel
        new, steps = fn(p.read_text(encoding="utf-8"))
        for name, status, note in steps:
            print(f"{status:<5} {rel}: {name} {('- ' + note) if note and status != 'OK' else ''}")
        if any(st == "FAIL" for _, st, _ in steps):
            print(f"      -> {rel} NOT changed")
            continue
        if any(st == "OK" for _, st, _ in steps):
            shutil.copy(p, p.with_suffix(p.suffix + ".bak2"))
            p.write_text(new, encoding="utf-8")
            print(f"      -> {rel} written (backup: {p.name}.bak2)")


if __name__ == "__main__":
    main()