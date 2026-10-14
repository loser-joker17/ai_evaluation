"""Third patch for app/retrieval/corpus.py (changes how chunks are built -> needs a rebuild):
 1. strip the '/rhombbutton2' bullet-glyph junk
 2. pypdf puts U+FFFD where a decimal point should be ("13.6" -> "13 6"): prefer PyMuPDF when pypdf
    produces many of them, and turn any that remain between two digits into "."
 3. drop chunks that are lists of past-year questions (counted per file as pyq=)
 4. the rebuild table now also prints pyq= and fffd= (leftover replacement characters) per file
"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")


def sub(old, new):
    global s
    if s.count(old) != 1:
        raise SystemExit(f"expected exactly 1 match, found {s.count(old)} for:\n{old[:90]}\nNothing changed.")
    s = s.replace(old, new)


# 1. junk glyph text
sub('INLINE_JUNK = re.compile(r"INDIAN POLITY BY VYASA IAS|VYASA IAS", re.I)',
    'INLINE_JUNK = re.compile(r"INDIAN POLITY BY VYASA IAS|VYASA IAS|/rhombbutton\\d*", re.I)')

# 2a. decimal point
sub('''    line = re.sub(r"(?<=\\d)\\ue00b(?=\\d)", ".", line)\n''',
    '''    line = re.sub(r"(?<=\\d)[\\ue00b\\ufffd](?=\\d)", ".", line)\n''')

# 2b. prefer PyMuPDF when pypdf output is full of replacement characters
sub('def _extract_pypdf(path: Path) -> list[str]:',
    '''FFFD_LIMIT = 20          # this many U+FFFD characters in a file = broken text layer for pypdf


def _fffd(raw_pages: list[str]) -> int:
    return sum(t.count("\\ufffd") for t in raw_pages)


def _extract_pypdf(path: Path) -> list[str]:''')
sub('''    raw = _extract_pypdf(path)
    chunks, good = _prepare(raw)
''', '''    raw = _extract_pypdf(path)
    chunks, good = _prepare(raw)
    broken = _fffd(raw)
''')
sub('    if mode == "auto" and len(good) < 0.6 * max(len(chunks), 1):\n',
    '    if mode == "auto" and (len(good) < 0.6 * max(len(chunks), 1) or broken >= FFFD_LIMIT):\n')
sub('            if len(good2) > len(good):\n',
    '            if len(good2) > len(good) or (_fffd(raw2) < broken and len(good2) >= 0.85 * len(good)):\n')

# 3. past-year-question lists
sub('def good_chunk(text: str) -> bool:', '''_YEAR_TAG = re.compile(r"\\((?:19|20)\\d{2}\\)")
_DIRECTIVE = re.compile(r"\\b(?:discuss|examine|critically|comment|analy[sz]e|elaborate|illustrate|evaluate|substantiate)\\b", re.I)


def is_question_list(text: str) -> bool:
    """A chunk that is mostly past-year exam questions: several '?' plus year tags, or many year
    tags with several directive words. Such text is a question, not a fact."""
    years = len(_YEAR_TAG.findall(text))
    if text.count("?") >= 3 and years >= 2:
        return True
    return years >= 4 and len(_DIRECTIVE.findall(text)) >= 3


def good_chunk(text: str) -> bool:''')
sub('''        for p0, p1, text in chunks:
            if not good_chunk(text):''', '''        for p0, p1, text in chunks:
            if is_question_list(text):
                s["pyq"] += 1
                continue
            if not good_chunk(text):''')
sub('''             "extractor": extractor}''', '''             "extractor": extractor, "pyq": 0, "fffd": _fffd(raw_pages)}''')

# 4. report
sub('''chunks via {s['extractor']} ({time.time() - t0:.0f}s)",''',
    '''chunks via {s['extractor']}, pyq {s['pyq']}, fffd {s['fffd']} ({time.time() - t0:.0f}s)",''')
sub('''kept={s['kept']:<5} via={s['extractor']}")''',
    '''kept={s['kept']:<5} pyq={s['pyq']:<4} fffd={s['fffd']:<5} via={s['extractor']}")''')

p.write_text(s, encoding="utf-8")
print("patched", p)