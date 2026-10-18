import re

from app.llm import light_llm as llm  # LIGHT_MODEL; same model as before unless you set it
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


# --------------------------------------------------- allocation (parts)

BLOCK_LABELS_FIXED = ("intro", "conclusion", "wayforward", "other")


def split_blocks(answer: str) -> list[str]:
    """Lines of the answer; one block per non-empty line. A single-paragraph
    answer falls back to sentences so the labels still mean something."""
    lines = [l.strip() for l in answer.splitlines() if l.strip()]
    if len(lines) >= 3:
        return lines
    return split_sentences(answer)


def _word_count(text: str) -> int:
    return len(text.split())


def compute_allocation(blocks: list[str], labels: list[str], parts: list[str]) -> dict:
    """Share of the answer body spent on each question part, the share spent on
    things not asked, and whether the parts come in the asked order.

    Body = everything except intro, conclusion and way-forward text. Returns
    empty values (and a note) when the labels cannot be trusted."""
    empty = {"part_word_share": [], "unasked_share": None, "parts_in_order": None}
    n = len(parts)
    if n == 0 or not labels:
        return {**empty, "note": None}
    if len(labels) != len(blocks):
        return {**empty, "note": (f"Allocation not measured: {len(labels)} labels for "
                                  f"{len(blocks)} blocks.")}

    valid = {f"P{i}" for i in range(1, n + 1)} | set(BLOCK_LABELS_FIXED)
    labels = [l.strip() for l in labels]
    if any(l not in valid for l in labels):
        return {**empty, "note": "Allocation not measured: unexpected block labels."}

    words: dict[str, int] = {}
    for block, label in zip(blocks, labels):
        words[label] = words.get(label, 0) + _word_count(block)
    body = sum(w for l, w in words.items() if l.startswith("P") or l == "other")
    if body == 0:
        return {**empty, "note": "Allocation not measured: no body text labelled."}

    shares = [{"part": parts[i - 1], "share": round(words.get(f"P{i}", 0) / body, 3)}
              for i in range(1, n + 1)]

    first_seen: list[int] = []
    for l in labels:
        if l.startswith("P") and int(l[1:]) not in first_seen:
            first_seen.append(int(l[1:]))
    in_order = first_seen == sorted(first_seen) if n >= 2 else None

    return {
        "part_word_share": shares if n >= 2 else [],
        "unasked_share": round(words.get("other", 0) / body, 3),
        "parts_in_order": in_order,
        "note": None,
    }


# ------------------------------------------------------------- main

def extract_features(question: str, answer: str, question_analysis: dict) -> dict:
    structured_llm = llm.with_structured_output(RawAnswerFeatures)
    parts = list(question_analysis.get("question_parts", []) or [])
    blocks = split_blocks(answer)
    numbered_parts = "\n".join(f"P{i}: {p}" for i, p in enumerate(parts, 1)) or "(none)"
    numbered_blocks = "\n".join(f"[B{i}] {b}" for i, b in enumerate(blocks, 1))

    prompt = f"""
You are a fact extractor for UPSC answers. You do NOT score or judge quality.

QUESTION:
{question}

QUESTION PARTS:
{numbered_parts}

ANSWER:
{answer}

THE SAME ANSWER SPLIT INTO NUMBERED BLOCKS:
{numbered_blocks}

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
- block_labels: exactly one label per numbered block, in order ({len(blocks)}
  labels in total). Use:
    "P1", "P2", ... the question part the block mainly answers. A heading
      gets the label of the section it introduces.
    "intro"       opening framing (definition, context, data hook).
    "conclusion"  closing summary or judgement.
    "wayforward"  suggestions or way forward, when the question did not ask
                  for them as a part.
    "other"       anything that answers none of the question parts, e.g. a
                  long background, a "need for X" section the question did
                  not ask for, or points about a different topic.
  If a question part asks for suggestions or measures, label those blocks
  with that part, not "wayforward".
- relevant_points: every distinct point the answer makes that helps answer
  the QUESTION. Copy each one WORD FOR WORD from the answer (a short exact
  phrase or sentence, at least 4 words). One entry per point; a point with its
  example is one entry. Do NOT include the introduction, the conclusion, a
  restatement of the question, general background, or anything off-topic.
  A heading alone ("Challenges:") is not a point.

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
    }

    n_specifics = (len(features["constitutional_or_legal_refs"])
                   + len(features["schemes_policies_committees"])
                   + len(features["examples_or_data"]))
    n_words = _word_count(answer)
    features["specifics_per_100_words"] = round(100 * n_specifics / n_words, 1) if n_words else None

    # Relevant points: keep only quotes that really occur in the answer, once each.
    answer_sq = _squash(answer)
    kept, seen = [], set()
    for q in raw.get("relevant_points") or []:
        sq = _squash(str(q))
        if len(sq) >= 12 and sq in answer_sq and sq not in seen:
            seen.add(sq)
            kept.append(str(q).strip())
    if raw.get("relevant_points") and len(kept) < len(raw["relevant_points"]):
        notes.append(f"Relevant points: {len(raw['relevant_points']) - len(kept)} quote(s) "
                     f"not found in the answer or repeated, dropped.")
    features["relevant_points"] = kept
    features["relevant_point_count"] = len(kept)

    alloc = compute_allocation(blocks, raw.get("block_labels", []), parts)
    alloc_note = alloc.pop("note")
    if alloc_note:
        notes.append(alloc_note)
    features.update(alloc)
    features["feature_notes"] = notes

    # Validate the final shape.
    return AnswerFeatures(**features).model_dump()