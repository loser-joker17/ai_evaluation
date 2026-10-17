"""Apply the directive fix to your local files. Run once from the project folder:

    python scripts/apply_directive_fix.py

What it changes (backups are written as *.bak first):
  app/evaluator/scoring.py
    - question types: analytical / judgement / balanced / descriptive. "To what extent /
      do you agree / assess / evaluate / critically examine" are now "judgement": they
      need specific points on the relevant sides and a verdict, NOT a how/why for every point.
    - every analysis rubric says a specific point (named concept, scheme, fact, example,
      table row) is not a "bare" point; level 2 is for vague, generic claims.
    - coverage: judged against what fits the word limit (6-8 points for 150 words,
      10-12 for 250); topics that could not fit are not gaps.
    - the "too few causal explanations" cap only applies to analyse / discuss-type
      questions, not to judgement or describe-type questions.
  app/evaluator/graph.py   passes the directive and question to finalize_scores.
  tests/test_scoring.py    updated / new tests.

Each step prints OK, SKIP (already applied) or FAIL (anchor not found: paste me that part
of the file). Nothing is written unless every step for that file succeeds.
"""
import re
import shutil
from pathlib import Path

NEW_BLOCK = '# ------------------------------------------------ analysis_depth by directive\n# What "analysis" means depends on what the question asks:\n#   analytical  analyse / critically analyse: break the issue into parts and explain\n#               how they connect (causes, effects, trade-offs).\n#   judgement   to what extent / how far / do you agree / in your opinion / justify /\n#               assess / evaluate / critically examine: specific points on the relevant\n#               sides and a reasoned verdict. A how/why for every point is NOT required.\n#   descriptive describe / elaborate / identify / highlight / trace: specific,\n#               well-illustrated points.\n#   balanced    discuss / examine / explain / comment and everything else.\n# Order matters: "critically analyse" is analytical, "critically examine" is judgement.\n_ANALYTICAL_DIRECTIVES = (\n    "critically analyse", "critically analyze", "analyse", "analyze",\n)\n_JUDGEMENT_DIRECTIVES = (\n    "to what extent", "how far", "do you agree", "in your opinion", "do you think",\n    "justify", "assess", "evaluate", "critically",\n)\n_DESCRIPTIVE_DIRECTIVES = (\n    "describe", "elaborate", "enumerate", "identify", "outline", "list",\n    "state", "mention", "highlight", "illustrate", "trace",\n)\n\n# Shared by every level table: what counts as a specific (not "bare") point.\n_SPECIFIC_POINT_NOTE = """  A point that names a specific concept, institution, provision, scheme,\n  fact, figure or example is a specific point even without a why-sentence. A\n  comparison table with specific parameters counts as specific points. Level 2\n  and below are for vague, generic claims, not for crisp specific points."""\n\nANALYSIS_LEVELS = {\n    "analytical": """  5 explains causal mechanisms, examines implications or trade-offs,\n    and develops a reasoned argument\n  4 explains the reasoning behind most major points\n  3 explains some points; the rest are specific but unexplained\n  2 is mostly vague, generic points with little explanation\n  1 mainly lists generic assertions without explaining them\n  0 provides no meaningful analysis\n  This question asks the candidate to analyse, so explaining how and why\n  matters here.\n""" + _SPECIFIC_POINT_NOTE,\n    "judgement": """  5 weighs specific points on the relevant sides (e.g. achievements and\n    shortfalls, for and against) across several dimensions and reaches a clear,\n    reasoned verdict on the extent or view asked\n  4 gives specific points on the relevant sides and a verdict, with minor gaps\n  3 gives specific points but mostly on one side, OR covers the sides without\n    a clear verdict\n  2 is a one-sided list of mostly generic points with no verdict\n  1 is only generic assertions with no specifics\n  0 provides no meaningful analysis\n  This question asks for a judgement ("to what extent", "do you agree",\n  "assess", "evaluate"). It does NOT ask for a how/why explanation of every\n  point: a specific factor, fact, example or institution is enough support for\n  a point. Do not lower this dimension for missing causal mechanisms, and do\n  not ask for them in the feedback.\n""" + _SPECIFIC_POINT_NOTE,\n    "balanced": """  5 explains causal mechanisms, examines implications or trade-offs,\n    and develops a reasoned argument\n  4 gives a reason, mechanism, consequence or concrete example for most major points\n  3 gives a reason, mechanism, consequence or concrete example for some\n    points; the rest are specific but unexplained\n  2 is mostly vague, generic points, with only occasional reasoning or examples\n  1 is only generic labels with no reasons or examples\n  0 provides no meaningful analysis\n  Short, point-style answers are acceptable when each point carries a reason,\n  mechanism, consequence or concrete example.\n""" + _SPECIFIC_POINT_NOTE,\n    "descriptive": """  5 nearly every point is specific and linked to the demand, with an example,\n    data or brief reason, and the points span diverse dimensions\n  4 most points are specific and supported by an example, data or brief reason\n  3 points are relevant and fairly specific, with some examples or reasons;\n    others are bare labels\n  2 is mostly generic labels with few examples or reasons\n  1 is only generic assertions with no specifics or reasons\n  0 provides no meaningful analysis\n  This question asks the candidate to describe, elaborate or identify. Short,\n  crisp points that each carry a specific example, fact or reason are good\n  analysis here. Do not require long explanation of every point, and do not ask\n  for causal mechanisms in the feedback.\n""" + _SPECIFIC_POINT_NOTE,\n}\n\n\ndef analysis_expectation(directive) -> str:\n    """Return \'analytical\', \'judgement\', \'descriptive\' or \'balanced\' for a directive."""\n    d = str(directive or "").lower()\n    for group, name in (\n        (_ANALYTICAL_DIRECTIVES, "analytical"),\n        (_JUDGEMENT_DIRECTIVES, "judgement"),\n        (_DESCRIPTIVE_DIRECTIVES, "descriptive"),\n    ):\n        for kw in group:\n            if re.search(r"\\b" + re.escape(kw) + r"\\b", d):\n                return name\n    return "balanced"\n\n\ndef directive_type(directive, question: str = "") -> str:\n    """Classify by the extracted directive; if that says nothing specific, use the question text.\n    The question-analysis model sometimes returns a generic directive ("Examine") for a\n    "to what extent" question, so the question wording is the tie-breaker."""\n    kind = analysis_expectation(directive)\n    if kind == "balanced" and question:\n        kind = analysis_expectation(question)\n    return kind\n\n\n# Directive types for which the "too few causal explanations" cap applies.\nMECHANISM_CAP_TYPES = ("analytical", "balanced")\n\n\n'

NEW_TESTS = 'def test_directive_type_uses_question_when_directive_is_generic():\n    from app.evaluator.scoring import directive_type\n    q = "To what extent can the rise of \'Kidfluencers\' be seen as a reflection of changing family structures?"\n    assert directive_type("Examine", q) == "judgement"\n    assert directive_type("Analyze", q) == "analytical"   # an explicit directive wins\n    assert directive_type("", "Highlight the salient differences.") == "descriptive"\n\n\ndef test_mechanism_cap_only_where_explanation_is_asked():\n    feats = {"has_conclusion": True, "mechanisms_explained": 0}\n    assert "analysis_depth" in compute_caps(feats, 140, 150, "within_limit", "Discuss")\n    assert "analysis_depth" in compute_caps(feats, 140, 150, "within_limit", "Analyze")\n    assert "analysis_depth" not in compute_caps(feats, 140, 150, "within_limit", "To what extent")\n    assert "analysis_depth" not in compute_caps(feats, 140, 150, "within_limit", "Highlight")\n    assert "analysis_depth" not in compute_caps(\n        feats, 140, 150, "within_limit", "Examine", "Do you agree with this view?")\n\n\ndef test_every_rubric_explains_specific_points():\n    from app.evaluator.scoring import ANALYSIS_LEVELS\n    assert set(ANALYSIS_LEVELS) == {"analytical", "judgement", "balanced", "descriptive"}\n    for text in ANALYSIS_LEVELS.values():\n        assert "specific point even without a why-sentence" in text\n    assert "Do not lower this dimension for missing causal mechanisms" in ANALYSIS_LEVELS["judgement"]\n'

COVERAGE_NOTE = """
  What fits: about 6-8 distinct points for a 150-word answer and 10-12 for a
  250-word answer, spread over every demand of the question and its main
  dimensions. A missing demand of the question is a real gap. Topics that
  could not fit in the word limit are not gaps: do not list them as missing,
  and do not lower coverage below 3 for them when every demand is addressed."""


def patch_scoring(s):
    steps = []
    if "def directive_type(" in s:
        return s, [("scoring.py", "SKIP", "already applied")]

    # 1. directive block
    a = s.find("# ------------------------------------------------ analysis_depth by directive")
    b = s.find("# ------------------------------------------------------------------ LLM call")
    if a < 0 or b < 0 or b < a:
        steps.append(("directive block", "FAIL", "markers 'analysis_depth by directive' / 'LLM call' not found"))
    else:
        s = s[:a] + NEW_BLOCK + s[b:]
        steps.append(("directive block", "OK", ""))

    # 2. prompt uses directive_type
    s, n = re.subn(r"ANALYSIS_LEVELS\[analysis_expectation\(directive\)\]",
                   "ANALYSIS_LEVELS[directive_type(directive, question)]", s)
    steps.append(("prompt rubric choice", "OK" if n == 1 else "FAIL", f"{n} match(es)"))

    # 3. coverage note
    anchor = "  Judge coverage relative to the word limit and marks."
    if s.count(anchor) == 1:
        s = s.replace(anchor, anchor + COVERAGE_NOTE)
        steps.append(("coverage note", "OK", ""))
    else:
        steps.append(("coverage note", "FAIL", f"{s.count(anchor)} match(es) for coverage anchor"))

    # 4. compute_caps signature
    s, n = re.subn(
        r"(def compute_caps\([^)]*?word_limit_status: str = \"not_specified\",\n)(\) -> )",
        r'\1    directive: str = "",\n    question: str = "",\n\2', s)
    steps.append(("compute_caps signature", "OK" if n == 1 else "FAIL", f"{n} match(es)"))

    # 5. mechanism cap condition
    s, n = re.subn(r"if found < needed:",
                   "if found < needed and directive_type(directive, question) in MECHANISM_CAP_TYPES:", s)
    steps.append(("mechanism cap condition", "OK" if n == 1 else "FAIL", f"{n} match(es)"))

    # 6. finalize_scores signature
    s, n = re.subn(
        r"(def finalize_scores\([^)]*?)(\) -> tuple\[list\[dict\], list\[str\]\]:)",
        r'\1    directive: str = "",\n    question: str = "",\n\2', s)
    steps.append(("finalize_scores signature", "OK" if n == 1 else "FAIL", f"{n} match(es)"))

    # 7. compute_caps call inside finalize_scores
    s, n = re.subn(r"compute_caps\(features, word_count, word_limit, word_limit_status\)",
                   "compute_caps(features, word_count, word_limit, word_limit_status, directive, question)", s)
    steps.append(("compute_caps call", "OK" if n == 1 else "FAIL", f"{n} match(es)"))
    return s, steps


def patch_graph(s):
    if "question=state[\"question\"]," in s and "directive=(" in s:
        return s, [("graph.py", "SKIP", "already applied")]
    s, n = re.subn(
        r"(finalize_scores\((?:(?!\n    \)).)*?confirmed_errors=confirmed,)[ \t]*\n",
        "\\1\n        directive=(state[\"question_analysis\"].get(\"directive\", \"\")\n"
        "                   if isinstance(state.get(\"question_analysis\"), dict) else \"\"),\n"
        "        question=state[\"question\"],\n", s, flags=re.S)
    return s, [("finalize_scores call", "OK" if n == 1 else "FAIL", f"{n} match(es)")]


def patch_tests(s):
    if "test_directive_type_uses_question_when_directive_is_generic" in s:
        return s, [("tests", "SKIP", "already applied")]
    steps = []
    old = '    assert analysis_expectation("Critically examine") == "analytical"\n'
    if old in s:
        s = s.replace(old, '    assert analysis_expectation("Critically examine") == "judgement"\n'
                           '    assert analysis_expectation("Critically analyse") == "analytical"\n'
                           '    assert analysis_expectation("To what extent has it succeeded?") == "judgement"\n'
                           '    assert analysis_expectation("Do you agree? Discuss.") == "judgement"\n')
        steps.append(("critically-examine test", "OK", ""))
    else:
        steps.append(("critically-examine test", "SKIP", "line not found (fine if you never had it)"))
    s = s.rstrip("\n") + "\n\n\n" + NEW_TESTS
    steps.append(("new tests", "OK", ""))
    return s, steps


def main():
    root = Path(__file__).resolve().parent.parent
    for rel, fn in (("app/evaluator/scoring.py", patch_scoring),
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
            shutil.copy(p, p.with_suffix(p.suffix + ".bak"))
            p.write_text(new, encoding="utf-8")
            print(f"      -> {rel} written (backup: {p.name}.bak)")


if __name__ == "__main__":
    main()