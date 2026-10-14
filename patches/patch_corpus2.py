"""Second patch for app/retrieval/corpus.py:
 1. manifest loader accepts a UTF-8 BOM and warns loudly when the manifest is missing/invalid
 2. build falls back to PyMuPDF when pypdf output is mostly rejected (or manifest says "extractor")
"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")


def sub(old, new):
    global s
    if s.count(old) != 1:
        raise SystemExit(f"expected exactly 1 match, found {s.count(old)} for:\n{old[:80]}\nNothing changed.")
    s = s.replace(old, new)


# 1. manifest loader
sub('''        try:
            raw = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            raw = {}
''', '''        try:
            raw = json.loads(MANIFEST_FILE.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            print(f"WARNING: {MANIFEST_FILE} not found - no paper/subject tags will be applied.", file=sys.stderr)
            raw = {}
        except json.JSONDecodeError as exc:
            print(f"WARNING: {MANIFEST_FILE} is not valid JSON ({exc}) - no tags applied.", file=sys.stderr)
            raw = {}
''')

# 2. extraction helpers (before _priority)
sub('''def _priority(path: Path) -> int:''', '''def _extract_pypdf(path: Path) -> list[str]:
    from pypdf import PdfReader

    out = []
    for pg in PdfReader(str(path)).pages:
        try:
            out.append(pg.extract_text() or "")
        except Exception:
            out.append("")
    return out


def _extract_pymupdf(path: Path) -> list[str]:
    import pymupdf

    doc = pymupdf.open(str(path))
    try:
        return [pg.get_text() or "" for pg in doc]
    finally:
        doc.close()


def _prepare(raw_pages: list[str]):
    """raw page text -> (all chunks, chunks that pass the quality check)"""
    rep = repeated_lines(raw_pages)
    cleaned = [(i + 1, " ".join(clean_lines(raw, rep))) for i, raw in enumerate(raw_pages)]
    chunks = chunk_pages(cleaned)
    return chunks, [c for c in chunks if good_chunk(c[2])]


def _extract_best(path: Path):
    """pypdf first (keeps the cleaning rules tuned on it). If most of its chunks are rejected
    (e.g. letters spaced apart, broken fonts), try PyMuPDF and keep whichever gives more good chunks.
    Manifest key "extractor": "pypdf" | "pymupdf" | "auto" (default) overrides this."""
    mode = (load_manifest().get(_key(path.stem)) or {}).get("extractor", "auto")
    if mode == "pymupdf":
        raw = _extract_pymupdf(path)
        chunks, good = _prepare(raw)
        return raw, chunks, "pymupdf"
    raw = _extract_pypdf(path)
    chunks, good = _prepare(raw)
    if mode == "auto" and len(good) < 0.6 * max(len(chunks), 1):
        try:
            raw2 = _extract_pymupdf(path)
            chunks2, good2 = _prepare(raw2)
            if len(good2) > len(good):
                return raw2, chunks2, "pymupdf"
        except Exception as exc:
            print(f"  (PyMuPDF fallback failed for {path.name}: {exc!r})", file=sys.stderr)
    return raw, chunks, "pypdf"


def _priority(path: Path) -> int:''')

# 3. use it in build_chunks
sub('''        reader = PdfReader(str(path))
        raw_pages = []
        for pg in reader.pages:
            try:
                raw_pages.append(pg.extract_text() or "")
            except Exception:
                raw_pages.append("")

        rep = repeated_lines(raw_pages)
        cleaned = [(i + 1, " ".join(clean_lines(raw, rep))) for i, raw in enumerate(raw_pages)]
        chunks = chunk_pages(cleaned)

        s = {"pages": len(raw_pages), "chunks": len(chunks), "bad_quality": 0, "duplicate": 0, "kept": 0}''',
    '''        raw_pages, chunks, extractor = _extract_best(path)

        s = {"pages": len(raw_pages), "chunks": len(chunks), "bad_quality": 0, "duplicate": 0, "kept": 0,
             "extractor": extractor}''')
sub('''        t0 = time.time()
        reader''' if False else '''    import time
    from pypdf import PdfReader
''', '''    import time
''')

# 4. show the extractor
sub('''pages -> kept {s['kept']:>5} chunks ({time.time() - t0:.0f}s)",''',
    '''pages -> kept {s['kept']:>5} chunks via {s['extractor']} ({time.time() - t0:.0f}s)",''')
sub('''duplicate={s['duplicate']:<4} kept={s['kept']}")''',
    '''duplicate={s['duplicate']:<4} kept={s['kept']:<5} via={s['extractor']}")''')

p.write_text(s, encoding="utf-8")
print("patched", p)