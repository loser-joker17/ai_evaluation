from app.retrieval.corpus import (
    BM25Index, chunk_pages, clean_lines, good_chunk, repeated_lines, tokenize,
)


def test_clean_removes_headers_pages_and_symbols():
    raw = "INDIAN POLITY BY VYASA IAS\n79\n\uf0b7 Tribunals review matters\nGovernance\nKey Words\nreal text here"
    out = clean_lines(raw, set())
    assert out == ["Tribunals review matters", "real text here"]


def test_pyq_block_dropped():
    raw = "Useful fact one.\nPrevious Year Questions Year\n2019 What is X?"
    assert clean_lines(raw, set()) == ["Useful fact one."]


def test_repeated_line_stripped_but_rare_heading_kept():
    pages = [f"Header Line\nbody {i}\n" + ("Way Forward\n" if i == 0 else "") for i in range(30)]
    rep = repeated_lines(pages)
    assert "Header Line" in rep and "Way Forward" not in rep


def test_garbled_chunk_rejected():
    clean = " ".join(["court held tribunal review"] * 30)
    garbled = " ".join(["reservingone-thirdofseatsforwomeninthelokSabha"] * 30)
    assert good_chunk(clean) and not good_chunk(garbled)


def test_chunking_keeps_page_numbers():
    pages = [(1, "word " * 400), (2, "word " * 400)]
    chunks = chunk_pages(pages)
    assert chunks[0][0] == 1 and chunks[-1][1] == 2


def test_bm25_finds_relevant_chunk_and_needs_overlap():
    chunks = [
        {"file": "a", "page": 1, "tier": "notes",
         "text": "Chandra Kumar case 1997 held tribunals are subject to High Court judicial review"},
        {"file": "a", "page": 2, "tier": "notes", "text": "Monsoon rainfall affects kharif crops sowing"},
    ]
    idx = BM25Index(chunks)
    hits = idx.search("Chandra Kumar tribunals judicial review", k=2)
    assert hits and hits[0][1]["page"] == 1
    assert idx.search("kharif", k=2) == []        # one stray word is not enough
    assert "chandra" in tokenize("Chandra Kumar")

def test_rare_term_required():
    chunks = [
        {"file": "a", "page": 1, "tier": "notes",
         "text": "tribunals follow procedures and are bound by natural justice principles " * 3},
        {"file": "a", "page": 2, "tier": "notes",
         "text": "bns and bnss are criminal law codes replacing the penal code " * 3},
    ] + [
        {"file": "a", "page": 3 + i, "tier": "notes",
         "text": f"tribunals procedures bound filler passage number {i} about courts " * 3}
        for i in range(60)
    ]
    idx = BM25Index(chunks)
    hits = idx.search("tribunals procedures bound bns bnss", k=3)
    assert all("bns" in h[1]["text"] for h in hits)    # common-word-only chunks are rejected
    assert idx.search("tribunals procedures bound zzqx", k=3) == []   # unknown rare term