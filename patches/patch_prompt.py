"""Prompt fix: keep each dimension on its own job, so one missing fact is not
punished in four dimensions. Edits app/evaluator/scoring.py only.
Run from the project root:   python patch_prompt.py
Changes NOTHING if an expected line is missing or appears twice."""
from pathlib import Path

SC = Path("app/evaluator/scoring.py")


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

if "DIMENSION BOUNDARIES" in s:
    raise SystemExit("Already patched. Nothing was changed.")

# 1) dimension boundaries, placed after the general principles
old = "- Use detected features as supporting evidence, not infallible ground truth.\n"
new = old + """
DIMENSION BOUNDARIES (each dimension judges ONE thing)
- Something missing from the answer (a fact, event, aspect or example) can
  lower coverage_balance ONLY. Never lower relevance, content_substantiation
  or analysis_depth because something is absent.
- relevance: does what is WRITTEN respond to the directive and the demand?
- content_substantiation: judge the specifics that are PRESENT, not specifics
  that could have been added.
- analysis_depth: judge the reasoning that is PRESENT.
- Do not mark the answer down for facts the question did not ask for. Do not
  compare it with a model answer that would not fit in the word limit.
- Before finalising, check your justifications: if the same missing item is the
  reason for lowering more than one dimension, restore the other dimensions to
  the level the written content deserves and keep the reduction only in
  coverage_balance.
"""
s = replace_once(s, old, new, "dimension boundaries")

# 2) relevance anchor
old = "  0 is essentially off topic\n"
new = old + ("  An answer whose points respond to the directive and the demand is at least\n"
             "  level 3 even if it omits some aspects; omissions belong in coverage_balance.\n")
s = replace_once(s, old, new, "relevance anchor")

# 3) content anchor
old = "  Do not award extra credit for irrelevant references or name-dropping.\n"
new = old + ("  Do not lower this level for specifics the answer could have added; judge\n"
             "  the specifics it actually gives.\n")
s = replace_once(s, old, new, "content anchor")

# 4) garbled bullet left by the earlier patch
old = ("  value judgements, or anything you cannot judge from general knowledge.\n"
       "  reform suggestions, or claims you merely cannot verify.\n")
new = ("  value judgements, reform suggestions, claims you merely cannot verify,\n"
       "  or anything you cannot judge from general knowledge.\n")
s = replace_once(s, old, new, "factual concerns bullet")

write(SC, s, crlf)
print("patched scoring.py")