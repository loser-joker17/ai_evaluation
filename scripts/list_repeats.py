from collections import Counter
from pathlib import Path
from pypdf import PdfReader

for p in sorted(Path("data/corpus").glob("*.pdf")):
    r = PdfReader(str(p))
    n = len(r.pages)
    counts = Counter()
    for pg in r.pages:
        lines = {" ".join(l.split()) for l in (pg.extract_text() or "").splitlines()}
        for l in lines:
            if 3 <= len(l) <= 80:
                counts[l] += 1
    print("=" * 70)
    print(p.name, f"({n} pages)")
    for line, c in counts.most_common(15):
        if c >= max(5, n // 20):
            print(f"  {c:>4} pages ({c / n:.0%})  {line}")