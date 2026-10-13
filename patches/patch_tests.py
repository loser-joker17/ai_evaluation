"""Update the 3 old over-limit tests in tests/test_scoring.py and add 2 new ones.
Run from the project root:  python patch_tests.py
It fails loudly (and changes nothing) if a line it expects is missing."""
from pathlib import Path

p = Path("tests/test_scoring.py")
raw = p.read_bytes().decode("utf-8")
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n")

edits = [
    ('both = compute_caps({"has_conclusion": False}, 200, 150, "over_limit")',
     'both = compute_caps({"has_conclusion": False}, 320, 150, "over_limit")'),
    ('assert "exceeds" in note and "No concluding" in note',
     'assert "double" in note and "No concluding" in note'),
    ('def test_over_limit_caps_structure_only():\n    res = finalize(raw(4), status="over_limit")\n    assert res["structure_presentation"]["final_level"] == 3',
     'def test_moderately_over_limit_does_not_cap_structure():\n    res = finalize(raw(4), status="over_limit")\n    assert res["structure_presentation"]["final_level"] == 4'),
    ('    assert caps["coverage_balance"][0] == 4',
     '    assert "coverage_balance" not in caps\n    assert "structure_presentation" not in caps'),
]
for old, new in edits:
    if s.count(old) != 1:
        raise SystemExit(f"Expected exactly one match, found {s.count(old)} for:\n{old}")
    s = s.replace(old, new)

if "test_well_over_limit_caps_structure_at_4" not in s:
    s = s.rstrip("\n") + '''


def test_well_over_limit_caps_structure_at_4():
    assert compute_caps({"has_conclusion": True}, 255, 150, "over_limit")["structure_presentation"][0] == 4


def test_double_limit_caps_structure_at_3():
    assert compute_caps({"has_conclusion": True}, 320, 150, "over_limit")["structure_presentation"][0] == 3
'''
if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode("utf-8"))
print("patched", p)