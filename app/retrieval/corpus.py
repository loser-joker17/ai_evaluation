"""Local notes corpus: clean, chunk, dedupe and keyword-search the PDFs in data/corpus."""
import argparse
import json
import math
import random
import re
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

CORPUS_DIR = Path("data/corpus")
CACHE_FILE = Path("data/cache/corpus_chunks.json")

CHUNK_WORDS = 180
CHUNK_STEP = 140         # 40-word overlap
REPEAT_SHARE = 0.30       # a line on >30% of pages is a running header/footer
DEDUPE_JACCARD = 0.5
MIN_CHUNK_WORDS = 80
RARE_DF_SHARE = 0.02   # a term in under 2% of chunks counts as rare ...
RARE_DF_MAX = 12       # ... but never more than this many chunks (keeps the guard strict as the corpus grows)

# Lower number = preferred when two chunks are near-duplicates.
FILE_PRIORITY = {
    "indian polity and constitution": 0,
    "governance": 1,
    "complete_polity": 2,
}

# Tags per PDF live in data/corpus_manifest.json (edit it without rebuilding the cache).
MANIFEST_FILE = Path("data/corpus_manifest.json")
# Textbook prose (NCERT) is dense and not exam-shaped; it backs up the notes instead of outranking them.
KIND_WEIGHT = {"notes": 1.0, "ncert": 0.9}

INLINE_JUNK = re.compile(r"INDIAN POLITY BY VYASA IAS|VYASA IAS|/rhombbutton\d*", re.I)
PRIVATE_CHARS = re.compile(r"[\ue000-\uf8ff\ufffd\u200b\u00ad\u00be]")
LINE_BLOCKLIST = {
    "governance",
    "indian polity and constitution",
    "do you know?",
    "do you know?do you know?",
    "knowledge nuggets",
    "key words",
    "previous year questions year",
}
PYQ_START = "previous year questions"

STOP = set(
    "the a an of to in on and or for is are was were be by with as at from "
    "that this it its which their than into under over".split()
)


# ----------------------------------------------------------- tags

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}
_manifest: dict | None = None


def _key(stem: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")


def load_manifest(force: bool = False) -> dict:
    global _manifest
    if _manifest is None or force:
        try:
            raw = json.loads(MANIFEST_FILE.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            print(f"WARNING: {MANIFEST_FILE} not found - no paper/subject tags will be applied.", file=sys.stderr)
            raw = {}
        except json.JSONDecodeError as exc:
            print(f"WARNING: {MANIFEST_FILE} is not valid JSON ({exc}) - no tags applied.", file=sys.stderr)
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
    m = re.search(r"\b(?:GS|GENERAL STUDIES)\s*(?:PAPER\s*)?(IV|III|II|I|[1-4])\b", s)
    if not m:
        return None
    v = m.group(1)
    return f"GS{_ROMAN.get(v) or int(v)}"


# ----------------------------------------------------------- cleaning


def _norm_line(line: str) -> str:
    line = re.sub(r"(?<=\d)[\ue00b\ufffd](?=\d)", ".", line)
    line = PRIVATE_CHARS.sub(" ", line)
    line = INLINE_JUNK.sub(" ", line)
    return " ".join(line.split())



# def debug_special_chars():
#     from pypdf import PdfReader

#     for path in CORPUS_DIR.glob("*.pdf"):
#         reader = PdfReader(str(path))

#         for page_no, page in enumerate(reader.pages, start=1):
#             raw = page.extract_text() or ""

#             for i, ch in enumerate(raw):
#                 if ch in "\ue00b\ufffd\u00be\u200b\u00ad" or "\ue000" <= ch <= "\uf8ff":
#                     before = raw[max(0, i - 15):i]
#                     after = raw[i + 1:i + 16]

#                     print(
#                         f"{path.name}, page {page_no}: "
#                         f"U+{ord(ch):04X}, "
#                         f"context={before!r}{ch!r}{after!r}"
#                     )
#                     if ch == "\ue00b":
#                         break

#             else:
#                 continue
#             break



def repeated_lines(pages_raw: list[str]) -> set[str]:
    """Lines that appear on a large share of pages (headers, footers, watermarks)."""
    n = len(pages_raw)
    if n < 20:
        return set()
    counts: Counter = Counter()
    for raw in pages_raw:
        seen = {_norm_line(l) for l in raw.splitlines()}
        for l in seen:
            if 3 <= len(l) <= 80:
                counts[l] += 1
    return {l for l, c in counts.items() if c / n > REPEAT_SHARE}


def clean_lines(raw: str, repeated: set[str]) -> list[str]:
    out = []
    for line in raw.splitlines():
        line = _norm_line(line)
        if not line:
            continue
        low = line.lower()
        if low.startswith(PYQ_START):
            break                      # drop the rest of the page (PYQ block)
        if low in LINE_BLOCKLIST or line in repeated or re.fullmatch(r"\d{1,3}", line):
            continue
        out.append(line)
    return out


# ----------------------------------------------------------- chunking

def chunk_pages(pages: list[tuple[int, str]]):
    """pages = [(page_no, cleaned_text)] -> [(page_start, page_end, text)]"""
    words, page_of = [], []
    for page_no, text in pages:
        for w in text.split():
            words.append(w)
            page_of.append(page_no)
    chunks, i = [], 0
    while i < len(words):
        seg = words[i:i + CHUNK_WORDS]
        chunks.append((page_of[i], page_of[i + len(seg) - 1], " ".join(seg)))
        if i + CHUNK_WORDS >= len(words):
            break
        i += CHUNK_STEP
    return chunks


_YEAR_TAG = re.compile(r"\((?:19|20)\d{2}\)")
_DIRECTIVE = re.compile(r"\b(?:discuss|examine|critically|comment|analy[sz]e|elaborate|illustrate|evaluate|substantiate)\b", re.I)


def is_question_list(text: str) -> bool:
    """A chunk that is mostly past-year exam questions: several '?' plus year tags, or many year
    tags with several directive words. Such text is a question, not a fact."""
    years = len(_YEAR_TAG.findall(text))
    if text.count("?") >= 3 and years >= 2:
        return True
    return years >= 4 and len(_DIRECTIVE.findall(text)) >= 3


def good_chunk(text: str) -> bool:
    """Reject garbled table text, symbol debris and very short chunks."""
    words = text.split()
    if len(words) < MIN_CHUNK_WORDS:
        return False
    if sum(c.isalpha() for c in text) / max(len(text), 1) < 0.60:
        return False
    if sum(1 for w in words if len(w) > 22) / len(words) > 0.015:
        return False                   # run-together words
    if sum(len(w) for w in words) / len(words) > 8.0:
        return False
    return True


# ----------------------------------------------------------- dedupe

def _shingles(text: str) -> set[int]:
    ws = re.findall(r"[a-z0-9]+", text.lower())
    out = set()
    for i in range(max(len(ws) - 5, 0)):
        h = zlib.crc32(" ".join(ws[i:i + 6]).encode())
        if h % 3 == 0:                 # sample to keep it fast
            out.add(h)
    return out


# ----------------------------------------------------------- build

FFFD_LIMIT = 20          # this many U+FFFD characters in a file = broken text layer for pypdf


def _fffd(raw_pages: list[str]) -> int:
    return sum(t.count("\ufffd") for t in raw_pages)


def _extract_pypdf(path: Path) -> list[str]:
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
    broken = _fffd(raw)
    if mode == "auto" and (len(good) < 0.6 * max(len(chunks), 1) or broken >= FFFD_LIMIT):
        try:
            raw2 = _extract_pymupdf(path)
            chunks2, good2 = _prepare(raw2)
            if len(good2) > len(good) or (_fffd(raw2) < broken and len(good2) >= 0.85 * len(good)):
                return raw2, chunks2, "pymupdf"
        except Exception as exc:
            print(f"  (PyMuPDF fallback failed for {path.name}: {exc!r})", file=sys.stderr)
    return raw, chunks, "pypdf"


def _priority(path: Path) -> int:
    m = load_manifest().get(_key(path.stem))
    if m and "priority" in m:
        return m["priority"]
    return FILE_PRIORITY.get(path.stem.lower(), 5)


def build_chunks(verbose: bool = False) -> tuple[list[dict], dict]:
    import time

    files = sorted(CORPUS_DIR.glob("*.pdf"), key=lambda p: (_priority(p), p.name))
    kept: list[dict] = []
    kept_sh: list[set[int]] = []
    inv: dict[int, list[int]] = defaultdict(list)
    stats: dict[str, dict] = {}

    for path in files:
        t0 = time.time()
        raw_pages, chunks, extractor = _extract_best(path)

        s = {"pages": len(raw_pages), "chunks": len(chunks), "bad_quality": 0, "duplicate": 0, "kept": 0,
             "extractor": extractor, "pyq": 0, "fffd": _fffd(raw_pages)}
        for p0, p1, text in chunks:
            if is_question_list(text):
                s["pyq"] += 1
                continue
            if not good_chunk(text):
                s["bad_quality"] += 1
                continue
            sh = _shingles(text)
            cand: Counter = Counter()
            for h in sh:
                for j in inv.get(h, ()):
                    cand[j] += 1
            if any(c / (len(sh) + len(kept_sh[j]) - c) > DEDUPE_JACCARD for j, c in cand.items()):
                s["duplicate"] += 1
                continue
            idx = len(kept)
            kept.append({"file": path.stem, "page": p0, "page_end": p1, "tier": "notes", "text": text})
            kept_sh.append(sh)
            for h in sh:
                inv[h].append(idx)
            s["kept"] += 1
        stats[path.name] = s
        if verbose:
            print(f"  {path.name:<44} {s['pages']:>5} pages -> kept {s['kept']:>5} chunks via {s['extractor']}, pyq {s['pyq']}, fffd {s['fffd']} ({time.time() - t0:.0f}s)",
                  flush=True)
    return kept, stats


def _signature() -> dict:
    sig = {p.name: [p.stat().st_size, int(p.stat().st_mtime)] for p in sorted(CORPUS_DIR.glob("*.pdf"))}
    sig["_params"] = [CHUNK_WORDS, CHUNK_STEP, MIN_CHUNK_WORDS, DEDUPE_JACCARD]
    return sig

def load_chunks(force: bool = False) -> list[dict]:
    sig = _signature()
    if not force and CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if data.get("signature") == sig:
                return data["chunks"]
        except Exception:
            pass
    chunks, _ = build_chunks()
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps({"signature": sig, "chunks": chunks}, ensure_ascii=False), encoding="utf-8"
    )
    return chunks


# ----------------------------------------------------------- search (BM25)


def tokenize(text: str) -> list[str]:
    out = []

    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if len(w) < 2 or w in STOP:
            continue

        # Handle common plural endings without damaging words
        # such as "business" and "process".
        if len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
            w = w[:-1]

        out.append(w)

    return out



def is_near_duplicate(
    text_a: str,
    text_b: str,
    threshold: float = 0.20,
) -> bool:
    """Detect chunks that substantially repeat the same passages."""

    def make_shingles(text: str) -> set[tuple[str, ...]]:
        words = tokenize(text)
        return {
            tuple(words[i:i + 5])
            for i in range(len(words) - 4)
        }

    shingles_a = make_shingles(text_a)
    shingles_b = make_shingles(text_b)

    if not shingles_a or not shingles_b:
        return False

    shared = len(shingles_a & shingles_b)
    similarity = shared / min(len(shingles_a), len(shingles_b))

    return similarity >= threshold



class BM25Index:
    def __init__(self, chunks: list[dict], k1: float = 1.5, b: float = 0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        self.meta = [file_meta(c["file"]) for c in chunks]
        self.tf = [Counter(tokenize(c["text"])) for c in chunks]
        self.dl = [sum(t.values()) for t in self.tf]
        self.n = len(chunks)
        self.avgdl = (sum(self.dl) / self.n) if self.n else 1.0
        self.df: Counter = Counter()
        for t in self.tf:
            self.df.update(t.keys())

    def _idf(self, term: str) -> float:
        d = self.df.get(term, 0)
        return math.log(1 + (self.n - d + 0.5) / (d + 0.5))

    def _allowed(self, papers, subjects) -> set[int] | None:
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

    def _rare_terms(self, q: set[str]) -> set[str]:
        limit = max(3, min(int(self.n * RARE_DF_SHARE), RARE_DF_MAX))
        return {t for t in q if 0 < self.df.get(t, 0) <= limit}

    
    def search(
        self,
        query: str,
        k: int = 3,
        candidate_k: int = 10,
        deduplicate: bool = True,
        papers=None,
        subjects=None,
    ) -> list[tuple[float, dict]]:
        q = set(tokenize(query))

        if not q:
            return []

        rare = self._rare_terms(q)
        # Terms in the query that appear nowhere in the corpus (e.g. "bns").
        unknown = {t for t in q if self.df.get(t, 0) == 0}

        scored = []
        allowed = self._allowed(papers, subjects)

        for i, tf in enumerate(self.tf):
            if allowed is not None and i not in allowed:
                continue
            matched = [t for t in q if t in tf]

            if len(matched) < 2 or len(matched) / len(q) < 0.5:
                continue

            # Require a distinctive term. If the query has rare terms, at least one
            # must be present. If a distinctive term is missing from the whole
            # corpus, the notes cannot address the claim, so skip every chunk.
            if unknown and len(unknown) >= 1 and not (rare & set(matched)):
                continue
            if rare and not (rare & set(matched)):
                continue

            score = 0.0

            for t in matched:
                f = tf[t]
                score += self._idf(t) * f * (self.k1 + 1) / (
                    f + self.k1 * (
                        1 - self.b + self.b * self.dl[i] / self.avgdl
                    )
                )

            score *= KIND_WEIGHT.get(self.meta[i]["kind"], 1.0)
            scored.append((score, self.chunks[i]))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Baseline: return the highest-scoring results directly.
        if not deduplicate:
            return scored[:k]

        # Filtered version: examine more candidates to find diverse results.
        candidates = scored[:candidate_k]
        selected = []

        for score, chunk in candidates:
            duplicate = any(
                is_near_duplicate(
                    chunk["text"], chosen_chunk["text"]
                )
                for _, chosen_chunk in selected
            )

            if duplicate:
                continue

            selected.append((score, chunk))

            if len(selected) >= k:
                break

        return selected

    
_index: BM25Index | None = None


def search_corpus(query: str, k: int = 3, deduplicate: bool = True,
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

# ----------------------------------------------------------- CLI

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="rebuild the chunk cache and print stats")
    ap.add_argument("--sample", type=int, default=0, help="print N random chunks to eyeball")
    ap.add_argument("--search", default=None, help="run a test query")
    ap.add_argument("--paper", default=None, help="restrict --search to GS1/GS2/GS3/GS4")
    ap.add_argument("--file", default=None, help="restrict --sample to one PDF (part of its name)")
    ap.add_argument("--stats", action="store_true", help="chunks per paper/subject/kind, untagged files")
    args = ap.parse_args()

    if args.rebuild:
        chunks, stats = build_chunks(verbose=True)
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps({"signature": _signature(), "chunks": chunks}, ensure_ascii=False),
            encoding="utf-8",
        )
        for name, s in stats.items():
            print(f"{name:<40} pages={s['pages']:<4} chunks={s['chunks']:<4} "
                  f"bad_quality={s['bad_quality']:<4} duplicate={s['duplicate']:<4} kept={s['kept']:<5} pyq={s['pyq']:<4} fffd={s['fffd']:<5} via={s['extractor']}")
        print(f"total kept: {len(chunks)}")

    if args.sample:
        chunks = load_chunks()
        if args.file:
            chunks = [c for c in chunks if args.file.lower() in c["file"].lower()]
        random.seed(1)
        for c in random.sample(chunks, min(args.sample, len(chunks))):
            print(f"\n--- {c['file']} p.{c['page']} ---\n{c['text'][:600]}")

    if args.stats:
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
            print(f"\n[{r['score']}] {r['url']}  ({','.join(r['paper']) or '-'} / {r['subject']} / {r['kind']} / scope={r['scope']})\n{r['text']}")


if __name__ == "__main__":
    main()