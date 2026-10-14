"""Pass the question's paper (GS1-GS4) to the notes search.
Usage (project root):  python patches\\patch_factcheck.py
Edits app/evaluator/factcheck.py and app/evaluator/graph.py. No corpus rebuild needed.
Extra arguments are only passed when a paper is known, so existing tests/fakes keep working.
"""
import sys
from pathlib import Path


def patch(path, edits):
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    for old, new in edits:
        if s.count(old) != 1:
            raise SystemExit(f"{path}: expected exactly 1 match, found {s.count(old)} for:\n{old[:90]}\nNothing changed.")
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")
    print("patched", path)


root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

FC = [
    ('from app.retrieval.corpus import search_corpus\n',
     'from app.retrieval import corpus as _corpus\n'
     'from app.retrieval.corpus import paper_from_subject, search_corpus\n'),

    ('''def _cache_key(claim: str) -> str:
    return hashlib.sha1(_squash(claim).encode()).hexdigest()
''', '''def _corpus_version() -> str:
    """Changes whenever the notes index or the tag manifest changes, so a verdict cached
    before the corpus grew is not reused."""
    parts = []
    for f in (_corpus.CACHE_FILE, _corpus.MANIFEST_FILE):
        try:
            st = f.stat()
            parts.append(f"{st.st_size}:{int(st.st_mtime)}")
        except OSError:
            parts.append("none")
    return "|".join(parts)


def _cache_key(claim: str, papers: list[str] | None = None) -> str:
    raw = f"{_squash(claim)}||{','.join(papers or [])}||{_corpus_version()}"
    return hashlib.sha1(raw.encode()).hexdigest()
'''),

    ('''def search_evidence(query: str, max_results: int = 4) -> list[dict]:
    sources = [
        {"url": s["url"], "text": s["text"], "tier": "notes"}
        for s in search_corpus(query, k=3)
    ]''', '''def search_evidence(query: str, max_results: int = 4, papers: list[str] | None = None) -> list[dict]:
    extra = {"papers": papers} if papers else {}     # a paper filter falls back to all notes if empty
    sources = [
        {"url": s["url"], "text": s["text"], "tier": "notes"}
        for s in search_corpus(query, k=3, **extra)
    ]'''),

    ('def verify_claim(claim: str, query: str | None = None, use_cache: bool = True) -> dict:',
     'def verify_claim(claim: str, query: str | None = None, use_cache: bool = True,\n'
     '                 papers: list[str] | None = None) -> dict:'),
    ('    key = _cache_key(claim)\n', '    key = _cache_key(claim, papers)\n'),
    ('    sources = search_evidence(query or claim)\n',
     '    sources = search_evidence(query or claim, **({"papers": papers} if papers else {}))\n'),

    ('def fact_check(answer: str) -> tuple[list[dict], list[str]]:',
     'def fact_check(answer: str, subject: str | None = None) -> tuple[list[dict], list[str]]:'),
    ('    verifications, gaps = [], []\n    for c in extract_claims(answer):\n',
     '    verifications, gaps = [], []\n'
     '    paper = paper_from_subject(subject)               # "GS-2" -> "GS2"; None if not recognised\n'
     '    extra = {"papers": [paper]} if paper else {}\n'
     '    for c in extract_claims(answer):\n'),
    ('            v = verify_claim(c["claim"], c["query"])\n',
     '            v = verify_claim(c["claim"], c["query"], **extra)\n'),
]
patch(root / "app/evaluator/factcheck.py", FC)

patch(root / "app/evaluator/graph.py", [
    ('        verifications, gaps = fact_check(state["answer"])\n',
     '        verifications, gaps = fact_check(state["answer"], subject=state.get("subject"))\n'),
])