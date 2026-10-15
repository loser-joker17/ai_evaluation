import math

from app.llm import llm
from app.llm import judge_llm
from app.schemas import DimensionScoresResponse, EXPECTED_DIMENSIONS
import re

judge_llm.with_structured_output(DimensionScoresResponse)

DIMENSION_WEIGHTS = {
    "relevance": 0.20,
    "content_substantiation": 0.25,
    "analysis_depth": 0.25,
    "coverage_balance": 0.15,
    "structure_presentation": 0.15,
}

# to answers about 70% over the limit and did not penalise length.
OVER_LIMIT_SOFT_RATIO = 1.5   # beyond this, structure is capped at level 4
OVER_LIMIT_HARD_RATIO = 2.0   # beyond this, structure is capped at level 3

# Level 5 needs this many valid quotes, each at least this many words long.
MIN_LEVEL5_QUOTES = 3
MIN_QUOTE_WORDS = 8
MAX_QUOTE_WORDS = 40
MIN_CONCERN_CLAIM_WORDS = 4

# Allocation over question parts (measured in features.py).
# An asked part with less than this fraction of its fair share of the body is
# "brief treatment" (0.4 x 50% = 20% for a two-part question).
MIN_PART_SHARE_FACTOR = 0.4
# Share of the body spent on things the question did not ask for.
MAX_UNASKED_SHARE = 0.30


# Strictness knobs ---------------------------------------------------------
# Level 5 is deliberately not 100%: an AI estimate should not claim perfection.
# LEVEL_TO_FRACTION = {0: 0.0, 1: 0.12, 2: 0.25, 3: 0.45, 4: 0.65, 5: 0.85}
LEVEL_TO_FRACTION = {0: 0.0, 1: 0.12, 2: 0.30, 3: 0.45, 4: 0.55, 5: 0.65}

# No automated total may exceed this share of the maximum marks.
MAX_FRACTION_OF_MARKS = 0.75

# Share of cited evidence that may fail verification before a high level
# (4 or 5) is downgraded.
MAX_BAD_EVIDENCE_SHARE = 1 / 3
# --------------------------------------------------------------------------

LEVEL_MAX = 5

assert set(DIMENSION_WEIGHTS) == EXPECTED_DIMENSIONS, (
    "DIMENSION_WEIGHTS and schemas.EXPECTED_DIMENSIONS are out of sync."
)
assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9, (
    "DIMENSION_WEIGHTS must add up to 1.0."
)


def dimension_max(dimension: str, max_marks: int) -> float:
    return round(DIMENSION_WEIGHTS[dimension] * max_marks, 2)


# ------------------------------------------------ analysis_depth by directive
# "Describe / elaborate / identify" questions ask for specific, well-illustrated
# points. "Critically examine / analyse" questions ask for explained mechanisms.
# Everything else (discuss, comment, examine, explain, ...) sits in between.
_DESCRIPTIVE_DIRECTIVES = (
    "describe", "elaborate", "enumerate", "identify", "outline", "list",
    "state", "mention", "highlight", "illustrate", "trace",
)
_ANALYTICAL_DIRECTIVES = (
    "critically", "analyse", "analyze", "evaluate", "assess", "justify",
    "to what extent", "how far", "do you agree",
)

ANALYSIS_LEVELS = {
    "analytical": """  5 explains causal mechanisms, examines implications or trade-offs,
    and develops a reasoned argument
  4 explains the reasoning behind most major points
  3 explains some points but is mostly descriptive
  2 offers limited explanation
  1 mainly lists assertions without explaining them
  0 provides no meaningful analysis""",
    "balanced": """  5 explains causal mechanisms, examines implications or trade-offs,
    and develops a reasoned argument
  4 gives a reason, mechanism or consequence for most major points
  3 gives a reason, mechanism, consequence or concrete example for some
    points; the rest are specific but unexplained
  2 is mostly bare points, with only occasional reasoning or examples
  1 is only bare, generic labels with no reasons or examples
  0 provides no meaningful analysis
  Short, point-style answers are acceptable when each point carries a reason,
  mechanism, consequence or concrete example.""",
    "descriptive": """  5 nearly every point is specific and linked to the demand, with an example,
    data or brief reason, and the points span diverse dimensions
  4 most points are specific and supported by an example, data or brief reason
  3 points are relevant and fairly specific, with some examples or reasons;
    others are bare labels
  2 is mostly bare labels with few examples or reasons
  1 is only generic assertions with no specifics or reasons
  0 provides no meaningful analysis
  This question asks the candidate to describe, elaborate or identify. Short,
  crisp points that each carry a specific example, fact or reason are good
  analysis here. Do not require long explanation of every point.""",
}


def analysis_expectation(directive) -> str:
    """Return 'analytical', 'descriptive' or 'balanced' for a question directive."""
    d = str(directive or "").lower()
    for kw in _ANALYTICAL_DIRECTIVES:
        if re.search(r"\b" + re.escape(kw) + r"\b", d):
            return "analytical"
    for kw in _DESCRIPTIVE_DIRECTIVES:
        if re.search(r"\b" + re.escape(kw) + r"\b", d):
            return "descriptive"
    return "balanced"


# ------------------------------------------------------------------ LLM call

def score_answer(
    question: str,
    answer: str,
    subject: str,
    max_marks: int,
    word_limit: int | None,
    word_count: int,
    word_limit_status: str,
    question_analysis: dict,
    features: dict,
) -> dict:
    structured_llm = llm.with_structured_output(DimensionScoresResponse)

    directive = question_analysis.get("directive", "") if isinstance(question_analysis, dict) else ""
    analysis_levels = ANALYSIS_LEVELS[analysis_expectation(directive)]

    prompt = f"""
You are an experienced, strict UPSC GS Mains answer evaluator.

QUESTION:
{question}

SUBJECT: {subject}
MAXIMUM MARKS: {max_marks}
WORD LIMIT: {word_limit if word_limit is not None else "Not specified"}
ANSWER WORD COUNT: {word_count} ({word_limit_status})

CANDIDATE ANSWER:
{answer}

QUESTION ANALYSIS (a guide to what is expected, NOT part of the answer):
{question_analysis}

DETECTED FEATURES (facts about the answer, treat as reliable):
{features}

Score each of the five dimensions as an integer LEVEL from 0 to 5.


RUBRIC

GENERAL SCORING PRINCIPLES
- Judge the answer against the actual question, directive, marks and word limit.
- Essential points represent core demands, not an exhaustive checklist.
- Important points improve completeness but are not all mandatory.
- Optional points must never be treated as requirements.
- Accept alternative, factually valid approaches.
- Reward concise answers when they address the core demands effectively.
- Do not penalise the same weakness in multiple dimensions.
- Distinguish missing coverage from irrelevant content.
- Use detected features as supporting evidence, not infallible ground truth.

STANDARD RELATIVE TO LENGTH
- Every level is relative to the marks and word limit. A 15-mark / 250-word
  answer has room for about 1.5 times the content of a 10-mark / 150-word
  answer, so it needs proportionally more specifics, explained points and
  coverage to reach the SAME level.
- Never raise a level because a longer answer contains more points in absolute
  terms. Judge how well the available words are used: how many specifics and
  explained points per 100 words, compared with what the word limit allows.
  DETECTED FEATURES gives specifics_per_100_words and, when available, the
  share of the answer spent on each question part.
- An answer that is only "good for a short answer" is not level 4 or 5 when
  the word limit is 250 words.

DIMENSION BOUNDARIES (each dimension judges ONE thing)
- Something missing from the answer (a fact, event, aspect or example) can
  lower coverage_balance ONLY. Never lower relevance, content_substantiation
  or analysis_depth because something is absent.
- relevance: does what is WRITTEN respond to the directive and the demand?
- content_substantiation: judge the specifics that are PRESENT, not specifics
  that could have been added.
- analysis_depth: judge the reasoning that is PRESENT.
- Do not mark the answer down for facts the question did not ask for. Do not
  compare it with a model answer that would not fit in the word limit.
- Before finalising, check your justifications: if the same missing item is the
  reason for lowering more than one dimension, restore the other dimensions to
  the level the written content deserves and keep the reduction only in
  coverage_balance.

relevance
  5 directly and clearly answers all central demands of the question
  4 answers the central demands with minor omissions or drift
  3 generally on topic but incompletely responds to one demand
  2 only partly responds to the question or misunderstands a demand
  1 has little relevant content
  0 is essentially off topic
  An answer whose points respond to the directive and the demand is at least
  level 3 even if it omits some aspects; omissions belong in coverage_balance.
  Relevance also judges WHERE the words go. Level 4 or 5 requires the answer to
  spend its space on what the question asks, roughly in proportion to its
  demands. If an explicitly asked part gets only brief treatment while a
  section the question did not ask for (or asked only as context, e.g. "need
  for X" or a long background) takes substantial space, relevance is at most 3.

content_substantiation (accuracy and specificity)
  5 uses multiple accurate, relevant specifics that substantiate its arguments
  4 uses several relevant specifics with no major apparent factual issue
  3 includes some relevant specifics, but support is limited
  2 is mostly generic, with little specific support
  1 is vague or contains significant factual concerns
  0 is predominantly factually incorrect or unsupported in a way that
    undermines the answer
  Do not assume a claim is false merely because it cannot be verified here.
  Do not award extra credit for irrelevant references or name-dropping.
  Do not lower this level for specifics the answer could have added; judge
  the specifics it actually gives.

analysis_depth
{analysis_levels}

coverage_balance
  5 covers the central demands comprehensively and balances them well
  4 covers the main demands with only a few meaningful omissions
  3 covers the core of the question but leaves notable gaps
  2 covers only a limited part of the question
  1 addresses only a narrow fragment
  0 provides almost no meaningful coverage
  Judge coverage relative to the word limit and marks.
  Do not count every expected-coverage bullet as a separate requirement.
  For multi-part questions, assess whether each central demand receives
  meaningful attention, not whether every possible example is included.

structure_presentation
  5 has a clear opening, logical progression and effective conclusion
  4 is well organised, even if one structural element is weaker
  3 is understandable but has noticeable organisational weaknesses
  2 has weak framing or poorly connected points
  1 is difficult to follow
  0 is incoherent or unreadable
  Level 4 or 5 requires the body to follow the order of the question's
  demands (e.g. "enumerate bottlenecks, then discuss how legislations help"
  means bottlenecks first). If the sections are out of that order, structure
  is at most 3.

EVIDENCE RULES
- Every evidence_from_answer item must be an exact quote from the candidate's
  answer, not from the question or question analysis.
- Do not claim a point is covered without supporting text from the answer.
- Levels 4 and 5 require at least one valid evidence quote.
- The improvement field should be "None" only if no meaningful improvement
  is needed. If a gap is identified, the level should normally be 4 or below.

CALIBRATION
- Level 5 represents exceptional quality, not merely a good answer.
- A typical adequate UPSC answer is around level 3, depending on the question.
- Do not infer factual errors from missing information.
- Do not invent facts, article numbers, judgments or statistics.
- Do not lower relevance simply because an answer lacks breadth.
- Do not lower coverage simply because an answer lacks detailed analysis.
- Do not penalise a missing conclusion in both analysis depth and relevance.
- Act on what you write. If your own justification for content_substantiation
  names a factual error (a wrong figure, rate, name or attribution), that level
  is at most 3. If the question explicitly asks the answer to name, list or
  highlight something and your coverage_balance justification says it was not
  done, coverage_balance is at most 3.

FACTUAL CONCERNS
- Separately from the levels, list claims in the CANDIDATE ANSWER that you
  believe are factually or legally WRONG or clearly misdescribed.
- claim: copy the sentence or phrase word for word from the candidate answer
  (at least 4 words).
- issue: one sentence saying what is wrong.
- confidence: "high" only if you are sure. Use "medium" or "low" if you are
  unsure. Only "high" affects the score.
- Do NOT list: missing information, vague or incomplete points, opinions,
  value judgements, reform suggestions, claims you merely cannot verify,
  or anything you cannot judge from general knowledge.
- Do NOT list a claim that is partly right but imprecise; that is a weakness
  of precision, not a factual error.
- If you find none, return an empty list. An empty list is the normal case.

Return exactly one entry per dimension. Return only the structured response.
"""

    return structured_llm.invoke(prompt).model_dump()


# --------------------------------------------- candidate-facing caps (features)


def compute_caps(
    features: dict,
    word_count: int,
    word_limit: int | None,
    word_limit_status: str = "not_specified",
) -> dict[str, tuple[int, str]]:
    """Apply only conservative, high-confidence caps."""
    caps: dict[str, tuple[int, str]] = {}

    # Structure: far over the limit and/or no conclusion
    structure_cap = 5
    structure_reasons = []
    if word_limit and word_limit_status == "over_limit":
        ratio = word_count / word_limit
        if ratio > OVER_LIMIT_HARD_RATIO:
            structure_cap = 3
            structure_reasons.append(
                f"Answer is more than double the {word_limit}-word limit ({word_count} words)."
            )
        elif ratio > OVER_LIMIT_SOFT_RATIO:
            structure_cap = 4
            structure_reasons.append(
                f"Answer is well over the {word_limit}-word limit ({word_count} words)."
            )
    if not features.get("has_conclusion", True):
        structure_cap = min(structure_cap, 3)
        structure_reasons.append("No concluding sentence.")
    if structure_reasons:
        caps["structure_presentation"] = (structure_cap, " ".join(structure_reasons))

    # Coverage: too short only. Being over the limit is handled under structure.
    if word_limit and word_limit_status == "under_limit":
        pct = round(100 * word_count / word_limit)
        caps["coverage_balance"] = (
            3,
            f"Answer uses {word_count} of the {word_limit} words ({pct}%).",
        )

    # Analysis: too few explained mechanisms for the length means mostly assertions.
    # 2 for a 150-word answer, scaled with the word limit (3 for 250 words).
    needed = required_mechanisms(word_limit)
    found = features.get("mechanisms_explained", needed)
    if found < needed:
        caps["analysis_depth"] = (
            3,
            "Few causal explanations (how or why) are given; most points are assertions."
            if not word_limit or word_limit <= 150 else
            f"Only {found} causal explanation(s) (how or why) for a {word_limit}-word "
            f"answer; at least {needed} are expected. Most points are assertions.",
        )

    # Relevance / structure: how the words are spread over the question's parts.
    alloc = allocation_caps(features)
    for dim, cap in alloc.items():
        if dim in caps:
            caps[dim] = (min(caps[dim][0], cap[0]), f"{caps[dim][1]} {cap[1]}")
        else:
            caps[dim] = cap

    return caps


def required_mechanisms(word_limit: int | None) -> int:
    if not word_limit:
        return 2
    return max(2, round(2 * word_limit / 150))


def allocation_caps(features: dict) -> dict[str, tuple[int, str]]:
    """Caps from the measured share of the answer body spent on each question part.

    Only applies when the feature step produced a valid allocation for a question
    with two or more parts. Intro, conclusion and way-forward text are excluded
    from the body."""
    caps: dict[str, tuple[int, str]] = {}
    shares = features.get("part_word_share") or []
    if len(shares) < 2:
        return caps

    fair = 1 / len(shares)
    reasons = []
    for p in shares:
        if p["share"] < MIN_PART_SHARE_FACTOR * fair:
            reasons.append(
                f"The asked part \"{p['part'][:60]}\" gets only {round(100 * p['share'])}% "
                f"of the answer's body."
            )
    unasked = features.get("unasked_share") or 0.0
    if unasked > MAX_UNASKED_SHARE:
        reasons.append(
            f"About {round(100 * unasked)}% of the answer's body answers something the "
            f"question did not ask (background, need, general context)."
        )
    if reasons:
        caps["relevance"] = (3, " ".join(reasons))

    if features.get("parts_in_order") is False:
        caps["structure_presentation"] = (
            3, "The answer does not take up the question's parts in the order they are asked."
        )
    return caps
# ------------------------------------------------- judge audit (LLM mistakes)

def _norm(text: str) -> str:
    text = (
        text.lower()
        .replace("\u2026", "")     # ellipsis
        .replace("\u2011", "-")    # non-breaking hyphen
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    return " ".join(text.split())


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def evidence_ok(item: str, answer: str) -> bool:
    """True if every fragment of the quoted item appears in the answer."""
    haystack = _squash(answer)
    checked = 0
    for fragment in re.split(r"\.\.\.|…", item):
        needle = _squash(fragment)
        if not needle:
            continue
        checked += 1
        if needle not in haystack:
            return False
    return checked > 0


def _is_none(text: str | None) -> bool:
    t = (text or "").strip().lower().rstrip(".")
    return t in {"", "n/a", "na", "nil", "no improvement needed"} or t.startswith("none")


def audit_item(item: dict, answer: str) -> tuple[int, str | None]:
    """Return (max_level, audit_note) based on the judge's own output."""
    level = item["score"]
    notes: list[str] = []
    max_level = LEVEL_MAX

    evidence = item.get("evidence_from_answer", []) or []

    if level >= 4:
        if not evidence:
            max_level = min(max_level, 3)
            notes.append("Level 4-5 given without quoted evidence.")
        else:
            bad = [e for e in evidence if not evidence_ok(e, answer)]
            if len(bad) / len(evidence) > MAX_BAD_EVIDENCE_SHARE:
                max_level = min(max_level, 3)
                notes.append(
                    f"{len(bad)} of {len(evidence)} cited evidence items "
                    "do not appear in the answer."
                )

    if level == 5:
        # A listed gap means it is not a 5.
        if not _is_none(item.get("improvement")):
            max_level = min(max_level, 4)
            notes.append("Level 5 given while an improvement was listed.")

        # A 5 needs substantial, real quotes, not section labels.
        sentences = set()
        for e in evidence:
            for frag in re.split(r"\.\.\.|…", e):
                for s in re.split(r"(?<=[.!?])\s+|\n+", frag):
                    if len(s.split()) >= MIN_QUOTE_WORDS and evidence_ok(s, answer):
                        sentences.add(_squash(s))
        substantial = list(sentences)
        if len(substantial) < MIN_LEVEL5_QUOTES:
            max_level = min(max_level, 4)
            notes.append(
                f"Level 5 needs at least {MIN_LEVEL5_QUOTES} quotes of "
                f"{MIN_QUOTE_WORDS}+ words; found {len(substantial)}."
            )

    return max_level, (" ".join(notes) if notes else None)


def verify_concerns(concerns: list[dict] | None, answer: str) -> list[dict]:
    """Keep only high-confidence concerns whose quoted claim really is in the answer."""
    verified: list[dict] = []
    seen: set[str] = set()
    for c in concerns or []:
        claim = (c.get("claim") or "").strip()
        issue = (c.get("issue") or "").strip()
        if c.get("confidence") != "high" or not issue:
            continue
        if len(claim.split()) < MIN_CONCERN_CLAIM_WORDS:
            continue
        if not evidence_ok(claim, answer):
            continue
        key = _squash(claim)
        if key in seen:
            continue
        seen.add(key)
        verified.append({"claim": claim, "issue": issue, "confidence": "high"})
    return verified


# ------------------------------------------------------------------ finalize

def finalize_scores(
    raw_items: list[dict],
    features: dict,
    word_count: int,
    word_limit: int | None,
    max_marks: int,
    word_limit_status: str = "not_specified",
    answer: str = "",
    factual_concerns: list[dict] | None = None,
    confirmed_errors: list[dict] | None = None,
) -> tuple[list[dict], list[str]]:
    """Apply caps, audit and factual concerns, convert levels to marks, apply the ceiling."""
    names = [i.get("dimension") for i in raw_items]
    if len(raw_items) != 5 or len(set(names)) != 5 or set(names) != EXPECTED_DIMENSIONS:
        return [], ["The returned dimensions do not match the five required dimensions."]

    caps = compute_caps(features, word_count, word_limit, word_limit_status)
    final = []

    for item in raw_items:
        dim = item["dimension"]
        raw_level = item["score"]
        level, cap_note = raw_level, None
        concern_note = None

        # 1. Candidate-facing caps. Note is kept even if the LLM was already low.
        if dim in caps:
            level = min(level, caps[dim][0])
            cap_note = caps[dim][1]

        # 2. Judge audit. Only runs if there is an answer to verify against.
        audit_note = None
        if answer:
            audit_max, audit_note = audit_item(item, answer)
            level = min(level, audit_max)

                # 2b. Factual problems limit content_substantiation. Confirmed errors
        #     (contradicted by an official source) and the judge's unverified
        #     concerns are shown as notes only (not scored).
        if dim == "content_substantiation" and (confirmed_errors or factual_concerns):
            n_conf = len(confirmed_errors or [])
            if n_conf:
                # Only errors contradicted by an official source lower the level.
                level = min(level, 3 if n_conf == 1 else 2)
                listed = "; ".join(f'"{c["claim"][:70]}"' for c in confirmed_errors[:3])
                conf_note = f"{n_conf} claim(s) contradicted by official sources: {listed}."
                cap_note = " ".join(n for n in (cap_note, conf_note) if n)
            if factual_concerns:
                # The judge's own concerns are not scored; the candidate is told to check them.
                listed = "; ".join(f'"{c["claim"][:70]}"' for c in factual_concerns[:3])
                concern_note = (f"Double-check (flagged, not confirmed, not scored): {listed}.")

        # 3. If a cap applies, use its wording instead of the judge's text,
        #    which may contradict the verified facts (e.g. "has a conclusion").
        if cap_note and level < raw_level:
            justification = f"Level lowered from {raw_level} to {level}: {cap_note}"
            improvement = cap_note
        elif cap_note:
            # The judge was already at or below the cap: keep its specific reasoning
            # and add the cap note, instead of replacing the feedback with a generic line.
            justification = f"{item.get('justification', '')} (Also: {cap_note})".strip()
            improvement = item.get("improvement", "") or cap_note
        else:
            justification = item.get("justification", "")
            improvement = item.get("improvement", "")

        if concern_note:
            improvement = f"{improvement} {concern_note}".strip()

        dmax = dimension_max(dim, max_marks)
        final.append({
            "dimension": dim,
            "score": round(LEVEL_TO_FRACTION[level] * dmax, 2),
            "max_score": dmax,
            "raw_level": raw_level,
            "final_level": level,
            "cap_note": cap_note,
            "audit_note": audit_note,
            "justification": justification,
            "evidence_from_answer": item.get("evidence_from_answer", []),
            "improvement": improvement,
        })

    # 4. Global ceiling: scale all dimensions proportionally.
    total = sum(d["score"] for d in final)
    ceiling = MAX_FRACTION_OF_MARKS * max_marks
    if total > ceiling:
        factor = ceiling / total
        for d in final:
            d["score"] = round(d["score"] * factor, 2)

    return final, []

# ------------------------------------------------------------------ validate

def validate_scores(
    scores: dict,
    max_marks: int,
) -> tuple[bool, list[str], float | None]:
    issues = []
    items = scores.get("dimension_scores", [])
    names = [i.get("dimension") for i in items]

    if len(items) != 5:
        issues.append("Exactly five dimension scores are required.")
    if len(names) != len(set(names)):
        issues.append("Duplicate scoring dimensions were returned.")
    if set(names) != EXPECTED_DIMENSIONS:
        issues.append("The returned dimensions do not match the five required dimensions.")

    total = 0.0
    for item in items:
        dim, score = item.get("dimension"), item.get("score")
        if dim not in EXPECTED_DIMENSIONS:
            continue
        dmax = dimension_max(dim, max_marks)
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            issues.append(f"{dim}: score must be a number.")
            continue
        if not 0 <= score <= dmax + 1e-6:
            issues.append(f"{dim}: score must be between 0 and {dmax}.")
        if abs(item.get("max_score", -1) - dmax) > 1e-6:
            issues.append(f"{dim}: max_score must be {dmax}.")
        total += score

    if total > max_marks + 1e-6:
        issues.append("The sum of dimension scores exceeds the question's maximum marks.")

    if issues:
        return False, issues, None
    return True, [], round(total, 2)


# ------------------------------------------------------------------ rounding

def round_marks(total: float, max_marks: int, step: float = 0.25) -> float:
    """Round to the nearest quarter mark (step=0.25) or half mark (step=0.5)."""
    total = round(total, 2)
    result = math.floor(total / step + 0.5) * step
    return min(result, float(max_marks))