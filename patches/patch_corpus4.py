"""Fourth patch for app/retrieval/corpus.py (search-time only, NO rebuild needed).
The 'rare term' limit was 2% of all chunks (about 12 when the corpus had 579 chunks). With ~19,000 chunks
that became ~390, so ordinary words like 'tribunal' counted as rare and the guard that returns nothing for
claims the notes cannot answer stopped working. The limit is now capped in absolute terms.
"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")


def sub(old, new):
    global s
    if s.count(old) != 1:
        raise SystemExit(f"expected exactly 1 match, found {s.count(old)} for:\n{old[:90]}\nNothing changed.")
    s = s.replace(old, new)


sub('RARE_DF_SHARE = 0.02   # a term in under 2% of chunks counts as rare (about 12 of 579)',
    'RARE_DF_SHARE = 0.02   # a term in under 2% of chunks counts as rare ...\n'
    'RARE_DF_MAX = 12       # ... but never more than this many chunks (keeps the guard strict as the corpus grows)')
sub('        limit = max(3, int(self.n * RARE_DF_SHARE))\n',
    '        limit = max(3, min(int(self.n * RARE_DF_SHARE), RARE_DF_MAX))\n')

p.write_text(s, encoding="utf-8")
print("patched", p)