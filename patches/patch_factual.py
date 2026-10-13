"""Judge-only factual concerns no longer lower content_substantiation.
Only claims contradicted by fact-check (confirmed_errors) cap the level.
Unconfirmed concerns are shown to the candidate as "double-check" notes, not scored.
Edits app/evaluator/scoring.py. Run from the project root: python patch_factual.py
Changes NOTHING if an expected line is missing or appears twice."""
from pathlib import Path

SC = Path("app/evaluator/scoring.py")


def read(p):
    raw = p.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), "\r\n" in raw


def write(p, s, crlf):
    p.write_bytes((s.replace("\n", "\r\n") if crlf else s).encode("utf-8"))


def once(s, old, label):
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"[{label}] expected exactly 1 match, found {n}. Nothing was changed.")


s, crlf = read(SC)
if "concern_note" in s:
    raise SystemExit("Already patched. Nothing was changed.")

# 1) a per-dimension variable for the unscored note
old = "        level, cap_note = raw_level, None\n"
once(s, old, "init")
s = s.replace(old, old + "        concern_note = None\n")

# 2) replace the 2b block (from its 'if' line to the cap_note join line)
start_line = '        if dim == "content_substantiation" and (confirmed_errors or factual_concerns):\n'
end_line = '            cap_note = " ".join(n for n in (cap_note, *parts) if n)\n'
once(s, start_line, "2b start")
once(s, end_line, "2b end")
i = s.index(start_line)
j = s.index(end_line) + len(end_line)
if j < i:
    raise SystemExit("[2b] end line comes before start line. Nothing was changed.")

new_block = '''        if dim == "content_substantiation" and (confirmed_errors or factual_concerns):
            n_conf = len(confirmed_errors or [])
            if n_conf:
                # Only errors contradicted by an official source lower the level.
                level = min(level, 3 if n_conf == 1 else 2)
                listed = "; ".join(f'"{c["claim"][:70]}"' for c in confirmed_errors[:3])
                conf_note = f"{n_conf} claim(s) contradicted by official sources: {listed}."
                cap_note = " ".join(n for n in (cap_note, conf_note) if n)
            if factual_concerns:
                # The judge's own concerns are not scored; the candidate is told to check them.
                listed = "; ".join(f'"{c["claim"][:70]}"' for c in factual_concerns[:3])
                concern_note = (f"Double-check (flagged, not confirmed, not scored): {listed}.")
'''
s = s[:i] + new_block + s[j:]

# 3) show the note in the improvement text (search only inside finalize_scores)
fs = s.index("def finalize_scores(")
nxt = s.find("\ndef ", fs + 1)
fs_end = nxt if nxt != -1 else len(s)
hook = '            improvement = item.get("improvement", "")\n'
span = s[fs:fs_end]
if span.count(hook) != 1:
    raise SystemExit(f"[improvement hook] expected exactly 1 match inside finalize_scores, "
                     f"found {span.count(hook)}. Nothing was changed.")
addition = (
    "\n        if concern_note:\n"
    "            improvement = f\"{improvement} {concern_note}\".strip()\n"
)
span = span.replace(hook, hook + addition)
s = s[:fs] + span + s[fs_end:]

# 4) the old comment says unverified concerns count toward the cap; they no longer do
old = "        #     concerns both count toward the cap.\n"
if s.count(old) == 1:
    s = s.replace(old, "        #     concerns are shown as notes only (not scored).\n")

write(SC, s, crlf)
print("patched scoring.py")