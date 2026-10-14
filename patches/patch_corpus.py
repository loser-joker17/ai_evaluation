"""One-time patch: tags, filters, kind weight, CLI additions for app/retrieval/corpus.py"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")


def sub(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        raise SystemExit(f"expected {count} match(es), found {n} for:\n{old[:80]}\nNothing changed.")
    s = s.replace(old, new)


# 1. constants + manifest helpers (after FILE_PRIORITY block)
sub('''    "complete_polity": 2,
}
''', '''    "complete_polity": 2,
}

# Tags per PDF live in data/corpus_manifest.json (edit it without rebuilding the cache).
MANIFEST_FILE = Path("data/corpus_manifest.json")
# Textbook prose (NCERT) is dense and not exam-shaped; it backs up the notes instead of outranking them.
KIND_WEIGHT = {"notes": 1.0, "ncert": 0.9}
''')

sub('''# ----------------------------------------------------------- cleaning
''', '''# ----------------------------------------------------------- tags

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}
_manifest: dict | None = None


def _key(stem: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")


def load_manifest(force: bool = False) -> dict:
    global _manifest
    if _manifest is None or force:
        try:
            raw = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            raw = {}
        _manifest = {_key(k): v for k, v in raw.items() if not k.startswith("_")}
    return _manifest


def file_meta(stem: str) -> dict:
    m = load_manifest().get(_key(stem))
    return {
        "tagged": m is not None,
        "papers": [str(x).upper().replace("-", "").replace(" ", "") for x in (m or {}).get("papers", [])],
        "subject": str((m or {}).get("subject", "untagged")).lower(),
        "kind": (m or {}).get("kind", "notes"),
    }


def paper_from_subject(subject) -> str | None:
    """'GS-2', 'GS2', 'General Studies Paper III', 'gs iv' -> 'GS2' / 'GS3' / 'GS4'; None if unknown."""
    s = re.sub(r"[^A-Z0-9]+", " ", str(subject or "").upper())
    m = re.search(r"\\b(?:GS|GENERAL STUDIES)\\s*(?:PAPER\\s*)?(IV|III|II|I|[1-4])\\b", s)
    if not m:
        return None
    v = m.group(1)
    return f"GS{_ROMAN.get(v) or int(v)}"


# ----------------------------------------------------------- cleaning
''')

# 2. priority from manifest
sub('''def _priority(path: Path) -> int:
    return FILE_PRIORITY.get(path.stem.lower(), 5)
''', '''def _priority(path: Path) -> int:
    m = load_manifest().get(_key(path.stem))
    if m and "priority" in m:
        return m["priority"]
    return FILE_PRIORITY.get(path.stem.lower(), 5)
''')

# 3. verbose progress in build_chunks
sub('''def build_chunks() -> tuple[list[dict], dict]:
    from pypdf import PdfReader
''', '''def build_chunks(verbose: bool = False) -> tuple[list[dict], dict]:
    import time
    from pypdf import PdfReader
''')
sub('''    for path in files:
        reader = PdfReader(str(path))
''', '''    for path in files:
        t0 = time.time()
        reader = PdfReader(str(path))
''')
sub('''        stats[path.name] = s
    return kept, stats''', '''        stats[path.name] = s
        if verbose:
            print(f"  {path.name:<44} {s['pages']:>5} pages -> kept {s['kept']:>5} chunks ({time.time() - t0:.0f}s)",
                  flush=True)
    return kept, stats''')

# 4. index metadata + filter + kind weight
sub('''        self.chunks, self.k1, self.b = chunks, k1, b
''', '''        self.chunks, self.k1, self.b = chunks, k1, b
        self.meta = [file_meta(c["file"]) for c in chunks]
''')
sub('''    def _rare_terms(self, q: set[str]) -> set[str]:''', '''    def _allowed(self, papers, subjects) -> set[int] | None:
        """Chunk ids that pass the paper/subject filter (None = no filter)."""
        ps = {str(p).upper().replace("-", "").replace(" ", "") for p in (papers or [])}
        ss = {str(x).lower() for x in (subjects or [])}
        if not ps and not ss:
            return None
        ok = set()
        for i, m in enumerate(self.meta):
            if ps and not (ps & set(m["papers"])):
                continue
            if ss and m["subject"] not in ss:
                continue
            ok.add(i)
        return ok

    def _rare_terms(self, q: set[str]) -> set[str]:''')
sub('''        candidate_k: int = 10,
        deduplicate: bool = True,
    ) -> list[tuple[float, dict]]:''', '''        candidate_k: int = 10,
        deduplicate: bool = True,
        papers=None,
        subjects=None,
    ) -> list[tuple[float, dict]]:''')
sub('''        scored = []

        for i, tf in enumerate(self.tf):
            matched = [t for t in q if t in tf]
''', '''        scored = []
        allowed = self._allowed(papers, subjects)

        for i, tf in enumerate(self.tf):
            if allowed is not None and i not in allowed:
                continue
            matched = [t for t in q if t in tf]
''')
sub('''            scored.append((score, self.chunks[i]))
''', '''            score *= KIND_WEIGHT.get(self.meta[i]["kind"], 1.0)
            scored.append((score, self.chunks[i]))
''')

# 5. search_corpus
sub('''def search_corpus(query: str, k: int = 3, deduplicate: bool = True) -> list[dict]:
    global _index
    if _index is None:
        chunks = load_chunks() if list(CORPUS_DIR.glob("*.pdf")) else []
        _index = BM25Index(chunks)
    return [
        {
            "url": f"{c['file']} p.{c['page']}",
            "file": c["file"], "page": c["page"], "page_end": c.get("page_end", c["page"]),
            "text": c["text"], "tier": "notes", "score": round(s, 2),
        }
        for s, c in _index.search(query, k, deduplicate=deduplicate)
    ]
''', '''def search_corpus(query: str, k: int = 3, deduplicate: bool = True,
                  papers=None, subjects=None, fallback: bool = True) -> list[dict]:
    """papers=['GS3'] / subjects=['economy'] restrict the search. With fallback=True, a filtered
    search that finds nothing is repeated over the whole corpus (results then carry scope='all')."""
    global _index
    if _index is None:
        chunks = load_chunks() if list(CORPUS_DIR.glob("*.pdf")) else []
        _index = BM25Index(chunks)
    scope = "paper" if (papers or subjects) else "all"
    hits = _index.search(query, k, deduplicate=deduplicate, papers=papers, subjects=subjects)
    if not hits and scope == "paper" and fallback:
        hits, scope = _index.search(query, k, deduplicate=deduplicate), "all"
    out = []
    for s, c in hits:
        m = file_meta(c["file"])
        out.append({
            "url": f"{c['file']} p.{c['page']}",
            "file": c["file"], "page": c["page"], "page_end": c.get("page_end", c["page"]),
            "text": c["text"], "tier": "notes", "score": round(s, 2),
            "paper": m["papers"], "subject": m["subject"], "kind": m["kind"], "scope": scope,
        })
    return out
''')

# 6. CLI
sub('''    ap.add_argument("--search", default=None, help="run a test query")
    args = ap.parse_args()
''', '''    ap.add_argument("--search", default=None, help="run a test query")
    ap.add_argument("--paper", default=None, help="restrict --search to GS1/GS2/GS3/GS4")
    ap.add_argument("--file", default=None, help="restrict --sample to one PDF (part of its name)")
    ap.add_argument("--stats", action="store_true", help="chunks per paper/subject/kind, untagged files")
    args = ap.parse_args()
''')
sub('''        chunks, stats = build_chunks()
        CACHE_FILE.parent.mkdir''', '''        chunks, stats = build_chunks(verbose=True)
        CACHE_FILE.parent.mkdir''')
sub('''        chunks = load_chunks()
        random.seed(1)
        for c in random.sample(chunks, min(args.sample, len(chunks))):''', '''        chunks = load_chunks()
        if args.file:
            chunks = [c for c in chunks if args.file.lower() in c["file"].lower()]
        random.seed(1)
        for c in random.sample(chunks, min(args.sample, len(chunks))):''')
sub('''    if args.search:
        for r in search_corpus(args.search, k=3):
            print(f"\\n[{r['score']}] {r['url']}\\n{r['text']}")
''', '''    if args.stats:
        chunks = load_chunks()
        by = Counter()
        untagged = set()
        for c in chunks:
            m = file_meta(c["file"])
            if not m["tagged"]:
                untagged.add(c["file"])
            by[(",".join(m["papers"]) or "-", m["subject"], m["kind"])] += 1
        print(f"{'paper':<10}{'subject':<24}{'kind':<8}chunks")
        for (pp, sj, kd), n in sorted(by.items()):
            print(f"{pp:<10}{sj:<24}{kd:<8}{n}")
        print(f"total chunks: {len(chunks)}")
        if untagged:
            print("UNTAGGED files (not searched when a paper filter is used):", ", ".join(sorted(untagged)))

    if args.search:
        papers = [args.paper] if args.paper else None
        for r in search_corpus(args.search, k=3, papers=papers):
            print(f"\\n[{r['score']}] {r['url']}  ({','.join(r['paper']) or '-'} / {r['subject']} / {r['kind']} / scope={r['scope']})\\n{r['text']}")
''')

p.write_text(s, encoding="utf-8")
print("patched", p)