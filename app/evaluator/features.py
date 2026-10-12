import re

from app.llm import llm
from app.schemas import AnswerFeatures, RawAnswerFeatures

INTRO_WINDOW = 2        # intro must be within the first N sentences
CONCLUSION_WINDOW = 2   # conclusion must be within the last N sentences

# "Measures:", "Way forward:", "Challenges:" ... a section label, not framing.
LABEL_RE = re.compile(r"^\s*[A-Za-z][A-Za-z /&-]{0,30}:\s")

CONCLUDING_MARKERS = re.compile(
    r"\b(thus|therefore|hence|in conclusion|to conclude|in sum|to sum up|"
    r"overall|ultimately|in short|all in all)\b",
    re.IGNORECASE,
)

# Split on . ! ? or newlines, but not after "S.P.", "v.", "vs.", "No.", "Art.", "Dr."
_SENTENCE_SPLIT = re.compile(
    r"(?<=[.!?])(?<!\b[A-Z]\.)(?<!\bv\.)(?<!\bvs\.)(?<!\bNo\.)(?<!\bArt\.)(?<!\bDr\.)\s+|\n+"
)


# ------------------------------------------------------------ helpers

def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def split_sentences(answer: str) -> list[str]:
    parts = _SENTENCE_SPLIT.split(answer.strip())
    return [p.strip() for p in parts if p and p.strip()]


def _matching_indices(quote: str, sentences: list[str]) -> list[int]:
    """Indices of sentences that the quote matches (either contains the other)."""
    q = _squash(quote)
    if len(q) < 10:
        return []
    hits = []
    for i, s in enumerate(sentences):
        sq = _squash(s)
        if len(sq) >= 10 and (q in sq or sq in q):
            hits.append(i)
    return hits


# ------------------------------------------------------- verification

def verify_introduction(quote, sentences):
    """Return (ok, matched_indices, note)."""
    if not quote:
        return False, [], None

    hits = [i for i in _matching_indices(quote, sentences) if i < INTRO_WINDOW]
    if not hits:
        return False, [], (
            "Introduction rejected: the quoted sentence is not among the "
            f"first {INTRO_WINDOW} sentences of the answer."
        )

    if all(LABEL_RE.match(sentences[i]) for i in hits):
        return False, [], (
            "Introduction rejected: the opening line is a section label, "
            "not a framing sentence."
        )

    return True, hits, None


def verify_conclusion(quote, sentences):
    """Return (ok, matched_indices, note)."""
    if not quote:
        return False, [], None

    last = len(sentences) - 1
    hits = [
        i for i in _matching_indices(quote, sentences)
        if i >= len(sentences) - CONCLUSION_WINDOW
    ]
    if not hits:
        return False, [], (
            "Conclusion rejected: the quoted sentence is not among the "
            f"last {CONCLUSION_WINDOW} sentences of the answer."
        )

    body = [i for i in hits if not LABEL_RE.match(sentences[i])]
    if not body:
        return False, [], (
            "Conclusion rejected: the closing line is a section label "
            "(for example a list of measures), not a summing-up sentence."
        )

    ok = [i for i in body if i == last or CONCLUDING_MARKERS.search(sentences[i])]
    if not ok:
        return False, [], (
            "Conclusion rejected: the quoted sentence is not the final "
            "sentence and has no concluding marker."
        )

    return True, ok, None


# ------------------------------------------------------------- main

def extract_features(question: str, answer: str, question_analysis: dict) -> dict:
    structured_llm = llm.with_structured_output(RawAnswerFeatures)

    prompt = f"""
You are a fact extractor for UPSC answers. You do NOT score or judge quality.

QUESTION:
{question}

QUESTION PARTS:
{question_analysis.get("question_parts", [])}

ANSWER:
{answer}

Extract the following from the ANSWER only:

- introduction_sentence: copy WORD FOR WORD the first sentence of the answer
  if it frames the topic (a definition, context or thesis). Otherwise null.
  A line that starts a section (for example "Challenges:") is not an
  introduction. Only the first two sentences are eligible.
- conclusion_sentence: copy WORD FOR WORD the last sentence of the answer
  if it sums up the whole answer or gives a closing judgement. Otherwise
  null. A list of measures, recommendations or a "way forward" is NOT a
  conclusion unless a separate closing sentence follows it. If the answer
  simply ends with its last point, return null.
- constitutional_or_legal_refs: Articles, Preamble, DPSP, Acts, judgments
  that are literally named in the answer.
- schemes_policies_committees: named schemes, policies, missions, committees.
- examples_or_data: concrete examples, case studies, statistics, years.
- mechanisms_explained: count of sentences that explain HOW or WHY something
  leads to an outcome (cause -> effect), not merely state it.
- dimensions_covered: social, economic, political, legal, ethical, etc.,
  that the answer actually touches.
- addresses_all_question_parts: true only if every question part is touched.

RULES:
1. List only items that literally appear in the answer. Do not infer.
2. Generic phrases such as "government initiatives" are NOT named schemes.
3. If unsure, leave the list empty, answer false, or return null.
4. mechanisms_explained: count a sentence only if it states BOTH a cause and
   its effect with a link such as "which", "through", "by", "leads to",
   "enables". A statement that merely mentions an outcome is not a
   mechanism. Maximum 5. When unsure, count fewer.
5. Do not list the same item in more than one field. Cases and Articles go
   in constitutional_or_legal_refs only.
6. Each Article is listed as "Article 32", never "Articles 32".

Return only the structured RawAnswerFeatures response.
"""

    raw = structured_llm.invoke(prompt).model_dump()

    sentences = split_sentences(answer)
    notes: list[str] = []

    intro_ok, intro_hits, note = verify_introduction(
        raw.get("introduction_sentence"), sentences
    )
    if note:
        notes.append(note)

    concl_ok, concl_hits, note = verify_conclusion(
        raw.get("conclusion_sentence"), sentences
    )
    if note:
        notes.append(note)

    if intro_ok and concl_ok and set(intro_hits) & set(concl_hits):
        concl_ok = False
        notes.append("Conclusion rejected: it is the same sentence as the introduction.")

    features = {
        "has_introduction": intro_ok,
        "has_conclusion": concl_ok,
        "introduction_sentence": raw.get("introduction_sentence") if intro_ok else None,
        "conclusion_sentence": raw.get("conclusion_sentence") if concl_ok else None,
        "constitutional_or_legal_refs": raw.get("constitutional_or_legal_refs", []),
        "schemes_policies_committees": raw.get("schemes_policies_committees", []),
        "examples_or_data": raw.get("examples_or_data", []),
        "mechanisms_explained": raw.get("mechanisms_explained", 0),
        "dimensions_covered": raw.get("dimensions_covered", []),
        "addresses_all_question_parts": raw.get("addresses_all_question_parts", False),
        "feature_notes": notes,
    }

    # Validate the final shape.
    return AnswerFeatures(**features).model_dump()