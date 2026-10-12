from pathlib import Path
from pypdf import PdfReader

TERMS = ["Chandra Kumar", "Tenth Schedule", "two-thirds", "91st", "Tribunal",
         "Sevottam", "Citizen Charter", "106th", "334A", "Madras Bar"]

for p in sorted(Path("data/corpus").glob("*.pdf")):
    r = PdfReader(str(p))
    text = " ".join((pg.extract_text() or "") for pg in r.pages).lower()
    hits = {t: text.count(t.lower()) for t in TERMS}
    print(p.name, {k: v for k, v in hits.items() if v})