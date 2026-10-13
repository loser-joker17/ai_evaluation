"""Directive-aware analysis_depth rubric + prompt fixes for app/evaluator/scoring.py.
Run from the project root:   python patch_scoring.py
Fails loudly and changes NOTHING if a line it expects is missing or appears twice."""
from pathlib import Path

SC = Path("app/evaluator/scoring.py")
TS = Path("tests/test_scoring.py")


def read(p):
    raw = p.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), "\r\n" in raw


def write(p, s, crlf):
    p.write_bytes((s.replace("\n", "\r\n") if crlf else s).encode("utf-8"))


def replace_once(s, old, new, label):
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"[{label}] expected exactly 1 match, found {n}. Nothing was changed.")
    return s.replace(old, new)


s, crlf = read(SC)

# 1) helper code, inserted just before the LLM-call section
helper = '''# ------------------------------------------------ analysis_depth by directive
# "Describe / elaborate / identify" questions ask for specific, well-illustrated
# points. "Critically examine / analyse" questions ask for explained mechanisms.
# Everything else (discuss, comment, examine, explain, ...) sits in between.
_DESCRIPTIVE_DIRECTIVES = (
    "describe", "elaborate", "enumerate", "identify", "outline", "list",
    "state", "mention", "highlight", "illustrate", "trace",
)
_ANALYTICAL_DIRECTIVES = (
    "critically", "analyse", "analyze", "evaluate", "assess", "justify",
    "to what extent", "how far", "do you agree",
)

ANALYSIS_LEVELS = {
    "analytical": """  5 explains causal mechanisms, examines implications or trade-offs,
    and develops a reasoned argument
  4 explains the reasoning behind most major points
  3 explains some points but is mostly descriptive
  2 offers limited explanation
  1 mainly lists assertions without explaining them
  0 provides no meaningful analysis""",
    "balanced": """  5 explains causal mechanisms, examines implications or trade-offs,
    and develops a reasoned argument
  4 gives a reason, mechanism or consequence for most major points
  3 gives a reason, mechanism, consequence or concrete example for some
    points; the rest are specific but unexplained
  2 is mostly bare points, with only occasional reasoning or examples
  1 is only bare, generic labels with no reasons or examples
  0 provides no meaningful analysis
  Short, point-style answers are acceptable when each point carries a reason,
  mechanism, consequence or concrete example.""",
    "descriptive": """  5 nearly every point is specific and linked to the demand, with an example,
    data or brief reason, and the points span diverse dimensions
  4 most points are specific and supported by an example, data or brief reason
  3 points are relevant and fairly specific, with some examples or reasons;
    others are bare labels
  2 is mostly bare labels with few examples or reasons
  1 is only generic assertions with no specifics or reasons
  0 provides no meaningful analysis
  This question asks the candidate to describe, elaborate or identify. Short,
  crisp points that each carry a specific example, fact or reason are good
  analysis here. Do not require long explanation of every point.""",
}


def analysis_expectation(directive) -> str:
    """Return 'analytical', 'descriptive' or 'balanced' for a question directive."""
    d = str(directive or "").lower()
    for kw in _ANALYTICAL_DIRECTIVES:
        if re.search(r"\\b" + re.escape(kw) + r"\\b", d):
            return "analytical"
    for kw in _DESCRIPTIVE_DIRECTIVES:
        if re.search(r"\\b" + re.escape(kw) + r"\\b", d):
            return "descriptive"
    return "balanced"


'''
marker = "# ------------------------------------------------------------------ LLM call\n"
s = replace_once(s, marker, helper + marker, "helper insert")

# 2) compute the tier inside score_answer
old = "    structured_llm = llm.with_structured_output(DimensionScoresResponse)\n\n    prompt = f\"\"\""
new = ('    structured_llm = llm.with_structured_output(DimensionScoresResponse)\n\n'
       '    directive = question_analysis.get("directive", "") if isinstance(question_analysis, dict) else ""\n'
       '    analysis_levels = ANALYSIS_LEVELS[analysis_expectation(directive)]\n\n'
       '    prompt = f"""')
s = replace_once(s, old, new, "tier in score_answer")

# 3) use it in the prompt
old = """analysis_depth
  5 explains causal mechanisms, examines implications or trade-offs,
    and develops a reasoned argument
  4 explains the reasoning behind most major points
  3 explains some points but is mostly descriptive
  2 offers limited explanation
  1 mainly lists assertions without explaining them
  0 provides no meaningful analysis
"""
s = replace_once(s, old, "analysis_depth\n{analysis_levels}\n", "analysis block")

# 4) truncated 'Do NOT list' bullet in FACTUAL CONCERNS
old = "- Do NOT list: missing information, vague or incomplete points, opinions,\n"
new = ("- Do NOT list: missing information, vague or incomplete points, opinions,\n"
       "  value judgements, or anything you cannot judge from general knowledge.\n")
s = replace_once(s, old, new, "factual concerns bullet")

write(SC, s, crlf)

# tests
t, tcrlf = read(TS)
if "test_analysis_expectation" not in t:
    t = t.rstrip("\n") + '''


def test_analysis_expectation():
    from app.evaluator.scoring import analysis_expectation
    assert analysis_expectation("Elaborate on the significance") == "descriptive"
    assert analysis_expectation("Describe") == "descriptive"
    assert analysis_expectation("Identify and discuss") == "descriptive"
    assert analysis_expectation("Critically examine") == "analytical"
    assert analysis_expectation("Analyze") == "analytical"
    assert analysis_expectation("Discuss") == "balanced"
    assert analysis_expectation("") == "balanced"
    assert analysis_expectation(None) == "balanced"
'''
    write(TS, t, tcrlf)
print("patched scoring.py and tests/test_scoring.py")