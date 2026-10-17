"""Stage 3: stop penalising "parts" the question never asked. Run once from the project
folder, AFTER apply_directive_fix.py and apply_demand_check.py, with the new
app/evaluator/demands.py saved:

    python scripts/apply_meta_fix.py

Changes (backups *.bak3 first):
  app/evaluator/scoring.py
    - allocation_caps skips parts that only restate the directive ("State whether you
      agree", "Make a reasoned assessment of the extent", "Analyse the relationship" when
      the question never says analyse) or add a side the question never mentions
      ("Identify limitations" for "assess the potential of X"). Before, such a part got
      "0% of the answer's body" and capped relevance at 3.
    - judgement rubric: an implied stance and a short "however / other factors" part
      count; specific, example-backed points with an implied stance are level 3, not lower.
  app/evaluator/question_analysis.py
    - new rule: do not list the directive itself, or sides/elements the question does not
      mention, as question_parts. (Affects new analyses; cached ones are covered by the
      code filter above. Use --rebuild-cache later to refresh them.)
  tests/test_scoring.py
    - tests for the filter.
"""
import re
import shutil
from pathlib import Path

QA_RULE = """5b. question_parts are ONLY what the question text itself asks. Do not add
   the directive restated as a task (for example "state whether you agree",
   "make a reasoned assessment of the extent", "give a verdict"), and do not
   add sides or elements the question does not mention (limitations,
   challenges, definitions, examples, data, way forward) unless the question
   asks for them. The directive is handled separately.
"""

JUDGE_NOTE = """  A stance may be implied by the conclusion (a summing-up or a solution), and a
  short "however / other factors" paragraph counts as the other side. Specific,
  example-backed points on the asked side with an implied stance are level 3,
  not lower. Never lower relevance because an explicit verdict sentence is missing.
"""

NEW_TESTS = '''


def test_meta_parts_are_not_question_parts():
    from app.evaluator.demands import is_meta_part, build_demands
    k = ("To what extent can the rise of 'Kidfluencers' be seen as a reflection of changing "
         "family structures and parental aspirations in Indian society?")
    assert is_meta_part("Make a reasoned assessment of the extent to which this rise reflects", k)
    assert is_meta_part("Analyse the relationship between the rise and the changes", k)
    assert is_meta_part("State whether you agree or disagree with the statement.", "Do you agree?")
    assert not is_meta_part("Identify changes in family structures", k)
    e = "Under what conditions can Emergency be proclaimed? What are the consequences?"
    assert not is_meta_part("Consequences while in force", e)
    assert is_meta_part("Challenges faced by associations", "In what ways do associations contribute?")
    assert not is_meta_part("Provide suitable examples", "Explain with suitable examples.")
    ids = [d["text"] for d in build_demands(k, {"question_parts": [
        "Identify changes in family structures", "Make a reasoned assessment of the extent"]})]
    assert "Make a reasoned assessment of the extent" not in ids


def test_allocation_ignores_meta_parts():
    feats = {"part_word_share": [
        {"part": "Identify changes in family structures", "share": 0.5},
        {"part": "Identify parental aspirations", "share": 0.5},
        {"part": "Make a reasoned assessment of the extent", "share": 0.0},
    ]}
    assert "relevance" not in allocation_caps(feats, "To what extent can X be seen as Y?")


def test_demand_caps_replay_uses_current_rules():
    from app.evaluator.demands import demand_caps
    q = "To what extent can X be seen as Y?"
    saved = [  # as saved by an earlier run: an invented part and an old verdict cap
        {"id": "Q1", "text": "Identify Y", "source": "question", "cap": None},
        {"id": "Q2", "text": "Make a reasoned assessment of the extent", "source": "question", "cap": None},
        {"id": "D1", "text": "a clear, reasoned verdict on the extent or view asked",
         "source": "directive", "cap": "analysis_depth"},
    ]
    check = [{"id": "Q1", "status": "covered"}, {"id": "Q2", "status": "missing"},
             {"id": "D1", "status": "missing"}]
    assert demand_caps(saved, check, q) == {}
'''


def patch_scoring(s):
    if "is_meta_part" in s:
        return s, [("scoring", "SKIP", "already applied")]
    steps = []
    s, n = re.subn(r"(from app\.evaluator\.demands import \(\n    directive_kind, directive_guide, build_demands, demand_block, demand_caps,)\n\)",
                   lambda m: m.group(1) + "\n    is_meta_part,\n)", s, count=1)
    steps.append(("import is_meta_part", "OK" if n == 1 else "FAIL", f"{n} match(es)"))
    s, n = re.subn(r"def allocation_caps\(features: dict\) -> ",
                   'def allocation_caps(features: dict, question: str = "") -> ', s, count=1)
    steps.append(("allocation_caps signature", "OK" if n == 1 else "FAIL", f"{n} match(es)"))
    s, n = re.subn(r"(    shares = features\.get\(\"part_word_share\"\) or \[\]\n)",
                   lambda m: m.group(1) + "    # Parts that only restate the directive or add a side the question never asks.\n"
                   "    shares = [p for p in shares if not is_meta_part(p.get(\"part\", \"\"), question)]\n",
                   s, count=1)
    steps.append(("allocation filter", "OK" if n == 1 else "FAIL", f"{n} match(es)"))
    s, n = re.subn(r"alloc = allocation_caps\(features\)", "alloc = allocation_caps(features, question)", s, count=1)
    steps.append(("allocation_caps call", "OK" if n == 1 else "FAIL", f"{n} match(es)"))
    s, n = re.subn(r"demand_caps\(demands, demand_check\)", "demand_caps(demands, demand_check, question)", s, count=1)
    steps.append(("demand_caps call", "OK" if n == 1 else "FAIL", f"{n} match(es)"))
    # judgement rubric note, right after its "Do not ask for them in the feedback." line
    s, n = re.subn(r"(  a point\. Do not lower this dimension for missing causal mechanisms, and do\n"
                   r"  not ask for them in the feedback\.\n)",
                   lambda m: m.group(1) + JUDGE_NOTE, s, count=1)
    steps.append(("judgement rubric note", "OK" if n == 1 else "FAIL", f"{n} match(es)"))
    return s, steps


def patch_qa(s):
    if "5b. question_parts are ONLY" in s:
        return s, [("question_analysis", "SKIP", "already applied")]
    s, n = re.subn(r"(5\. Keep question_parts focused on the actual distinct demands\.\n(?:   .*\n)*?   a longer checklist\.\n)",
                   lambda m: m.group(1) + "\n" + QA_RULE, s, count=1)
    return s, [("question_parts rule", "OK" if n == 1 else "FAIL", f"{n} match(es)")]


def patch_tests(s):
    if "test_meta_parts_are_not_question_parts" in s:
        return s, [("tests", "SKIP", "already applied")]
    # Stage-2 tests expected a missing verdict to cap analysis; now it is feedback only,
    # and only "critically ..." keeps a cap (both merits and demerits).
    s = s.replace(
        '    assert any(x["source"] == "directive" and x["cap"] == "analysis_depth" for x in d)\n',
        '    assert any(x["source"] == "directive" for x in d)\n'
        '    assert all(x["cap"] is None for x in d if x["source"] == "directive")   # feedback only\n')
    s = s.replace(
        '    assert demand_caps(d, [{"id": verdict, "status": "missing"}])["analysis_depth"][0] == 3\n',
        '    assert demand_caps(d, [{"id": verdict, "status": "missing"}]) == {}    # feedback only\n'
        '    c = build_demands("Critically examine the scheme.", {"question_parts": ["the scheme"]})\n'
        '    both = next(x["id"] for x in c if "merits" in x["text"])\n'
        '    assert demand_caps(c, [{"id": both, "status": "missing"}])["analysis_depth"][0] == 3\n')
    if not re.search(r"^from app\.evaluator\.scoring import allocation_caps", s, re.M):
        s = "from app.evaluator.scoring import allocation_caps\n" + s
    return s.rstrip("\n") + NEW_TESTS, [("new tests", "OK", "")]


def main():
    root = Path(__file__).resolve().parent.parent
    demands = (root / "app/evaluator/demands.py").read_text(encoding="utf-8")
    if "def is_meta_part" not in demands:
        raise SystemExit("Save the new app/evaluator/demands.py first (it has is_meta_part).")
    for rel, fn in (("app/evaluator/scoring.py", patch_scoring),
                    ("app/evaluator/question_analysis.py", patch_qa),
                    ("tests/test_scoring.py", patch_tests)):
        p = root / rel
        new, steps = fn(p.read_text(encoding="utf-8"))
        for name, status, note in steps:
            print(f"{status:<5} {rel}: {name} {('- ' + note) if note and status != 'OK' else ''}")
        if any(st == "FAIL" for _, st, _ in steps):
            print(f"      -> {rel} NOT changed")
            continue
        if any(st == "OK" for _, st, _ in steps):
            shutil.copy(p, p.with_suffix(p.suffix + ".bak3"))
            p.write_text(new, encoding="utf-8")
            print(f"      -> {rel} written (backup: {p.name}.bak3)")


if __name__ == "__main__":
    main()