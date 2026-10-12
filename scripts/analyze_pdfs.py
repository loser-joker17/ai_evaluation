import re
from collections import Counter
from pathlib import Path

from pypdf import PdfReader   # pip install pypdf

SAMPLE_PAGES = 12   # pages sampled per PDF, spread across the document


def sample_indices(n, k):
    if n <= k:
        return list(range(n))
    step = n / k
    return [int(i * step) for i in range(k)]


for p in sorted(Path("data/corpus").glob("*.pdf")):
    print("=" * 78)
    try:
        r = PdfReader(str(p))
    except Exception as e:
        print(f"{p.name}: FAILED to open ({type(e).__name__})")
        continue

    n = len(r.pages)
    idx = sample_indices(n, SAMPLE_PAGES)
    texts = []
    for i in idx:
        try:
            texts.append(r.pages[i].extract_text() or "")
        except Exception:
            texts.append("")

    chars = [len(t) for t in texts]
    empty = sum(1 for c in chars if c < 100)
    words = sum(len(t.split()) for t in texts)
    alpha = sum(ch.isalpha() for t in texts for ch in t)
    total = sum(chars) or 1

    # lines that repeat on many sampled pages = likely headers/footers/watermarks
    line_counts = Counter()
    for t in texts:
        for line in {l.strip() for l in t.splitlines() if l.strip()}:
            line_counts[line] += 1
    repeated = [(l, c) for l, c in line_counts.most_common(6) if c >= max(3, len(texts) // 3)]

    # rough table signal: many short lines with numbers/separators
    short_lines = sum(1 for t in texts for l in t.splitlines() if 0 < len(l.strip()) < 25)
    all_lines = sum(1 for t in texts for l in t.splitlines()) or 1

    print(f"{p.name}")
    print(f"  pages: {n} | sampled: {len(idx)} | pages with <100 chars (likely scanned/image): {empty}")
    print(f"  avg chars/page: {sum(chars)//max(len(chars),1)} | avg words/page: {words//max(len(texts),1)}")
    print(f"  letters share of text: {alpha/total:.0%} (low = lots of symbols/garbage)")
    print(f"  short-line share: {short_lines/all_lines:.0%} (high = tables/bullets/columns)")
    print(f"  repeated lines (headers/footers/watermarks):")
    for l, c in repeated:
        print(f"     [{c}/{len(texts)} pages] {l[:80]}")
    print(f"  sample from page {idx[len(idx)//2] + 1}:")
    mid = texts[len(texts) // 2].strip().replace("\n", " ")
    print(f"     {mid[:350]}")