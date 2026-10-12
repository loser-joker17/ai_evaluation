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
RARE_DF_SHARE = 0.02   # a term in under 2% of chunks counts as rare (about 12 of 579)

# Lower number = preferred when two chunks are near-duplicates.
FILE_PRIORITY = {
    "indian polity and constitution": 0,
    "governance": 1,
    "complete_polity": 2,
}

INLINE_JUNK = re.compile(r"INDIAN POLITY BY VYASA IAS|VYASA IAS", re.I)
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


# ----------------------------------------------------------- cleaning


def _norm_line(line: str) -> str:
    line = re.sub(r"(?<=\d)\ue00b(?=\d)", ".", line)
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

def _priority(path: Path) -> int:
    return FILE_PRIORITY.get(path.stem.lower(), 5)


def build_chunks() -> tuple[list[dict], dict]:
    from pypdf import PdfReader

    files = sorted(CORPUS_DIR.glob("*.pdf"), key=lambda p: (_priority(p), p.name))
    kept: list[dict] = []
    kept_sh: list[set[int]] = []
    inv: dict[int, list[int]] = defaultdict(list)
    stats: dict[str, dict] = {}

    for path in files:
        reader = PdfReader(str(path))
        raw_pages = []
        for pg in reader.pages:
            try:
                raw_pages.append(pg.extract_text() or "")
            except Exception:
                raw_pages.append("")

        rep = repeated_lines(raw_pages)
        cleaned = [(i + 1, " ".join(clean_lines(raw, rep))) for i, raw in enumerate(raw_pages)]
        chunks = chunk_pages(cleaned)

        s = {"pages": len(raw_pages), "chunks": len(chunks), "bad_quality": 0, "duplicate": 0, "kept": 0}
        for p0, p1, text in chunks:
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

    def _rare_terms(self, q: set[str]) -> set[str]:
        limit = max(3, int(self.n * RARE_DF_SHARE))
        return {t for t in q if 0 < self.df.get(t, 0) <= limit}

    
    def search(
        self,
        query: str,
        k: int = 3,
        candidate_k: int = 10,
        deduplicate: bool = True,
    ) -> list[tuple[float, dict]]:
        q = set(tokenize(query))

        if not q:
            return []

        rare = self._rare_terms(q)
        # Terms in the query that appear nowhere in the corpus (e.g. "bns").
        unknown = {t for t in q if self.df.get(t, 0) == 0}

        scored = []

        for i, tf in enumerate(self.tf):
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


def search_corpus(query: str, k: int = 3, deduplicate: bool = True) -> list[dict]:
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
    args = ap.parse_args()

    if args.rebuild:
        chunks, stats = build_chunks()
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps({"signature": _signature(), "chunks": chunks}, ensure_ascii=False),
            encoding="utf-8",
        )
        for name, s in stats.items():
            print(f"{name:<40} pages={s['pages']:<4} chunks={s['chunks']:<4} "
                  f"bad_quality={s['bad_quality']:<4} duplicate={s['duplicate']:<4} kept={s['kept']}")
        print(f"total kept: {len(chunks)}")

    if args.sample:
        chunks = load_chunks()
        random.seed(1)
        for c in random.sample(chunks, min(args.sample, len(chunks))):
            print(f"\n--- {c['file']} p.{c['page']} ---\n{c['text'][:600]}")

    if args.search:
        for r in search_corpus(args.search, k=3):
            print(f"\n[{r['score']}] {r['url']}\n{r['text']}")


if __name__ == "__main__":
    main()