from pathlib import Path
from pypdf import PdfReader

TERMS = ["Chandra Kumar", "two-thirds", "Sevottam", "106th", "Madras Bar"]
WIDTH = 350

out = []
for p in sorted(Path("data/corpus").glob("*.pdf")):
    r = PdfReader(str(p))
    for i, pg in enumerate(r.pages):
        t = " ".join((pg.extract_text() or "").split())
        for term in TERMS:
            k = t.lower().find(term.lower())
            if k != -1:
                snippet = t[max(0, k - WIDTH // 2): k + WIDTH // 2]
                out.append(f"[{p.name} p{i+1}] {term}: ...{snippet}...\n")

Path("context.txt").write_text("\n".join(out), encoding="utf-8", errors="replace")
print(f"Wrote {len(out)} passages to context.txt")