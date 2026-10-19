
import re

from app.llm import llm
from app.schemas import FeedbackResponse, ConsistencyCheckResponse


# Examiners' comments name what was missing ("mention Nolan principles", "add Article
# 21 cases"). Generic advice ("add causal explanations") matched only 31% of their points,
# so well-known names may now be suggested. Figures, years, ranks and percentages may
# not: the model invented "public debt ~90% of GDP". _clean_feedback enforces that.
ALLOW_NAMED_REFERENCES = True

_STOP = set("""the and for that this with from into are was were has have had not but its their
there which what when where while about also than then them they these those such been being
answer candidate claim claims may inaccurate verify should could would india indian""".split())


# ------------------------------------------------------------ helpers

def _level_view(dimension_scores: list[dict]) -> list[dict]:
    """Expose final levels and explanations, not scaled marks."""
    return [
        {
            "dimension": d["dimension"],
            "level": d.get("final_level", 0),
            "reason": d.get("justification", ""),
            "gap": d.get("improvement", ""),
            "limited_by": d.get("cap_note"),
        }
        for d in dimension_scores
    ]


def _relevance_level(dimension_scores: list[dict]) -> int:
    for d in dimension_scores:
        if d["dimension"] == "relevance":
            return d.get("final_level", 5)
    return 5


def _dimension_level(
    dimension_scores: list[dict],
    dimension: str,
) -> int | None:
    for d in dimension_scores:
        if d["dimension"] == dimension:
            return d.get("final_level", 0)
    return None


def _off_topic_feedback() -> dict:
    return {
        "strengths": [],
        "weaknesses": [
            "The answer does not address the question that was asked.",
            "Because the content is largely unrelated to the question, "
            "the other dimensions earned very little credit.",
        ],
        "improvement_suggestions": [
            "Identify the command word and each demand in the question before writing.",
            "Organize the answer around those demands using relevant explanations and evidence.",
        ],
        "overall_feedback": (
            "This answer does not respond to the question, so it cannot be "
            "credited meaningfully. Start by identifying what the question "
            "demands, then build the answer around it."
        ),
    }


def _answer_feature_context(features: dict) -> str:
    """Create a compact, explicit summary of detected answer features."""
    return f"""
- Has introduction: {features.get("has_introduction")}
- Has conclusion: {features.get("has_conclusion")}
- Legal references: {features.get("constitutional_or_legal_refs", [])}
- Schemes and policies: {features.get("schemes_policies_committees", [])}
- Examples or data: {features.get("examples_or_data", [])}
- Causal explanations (how/why) found: {features.get("mechanisms_explained", "unknown")}
- Addresses all question parts: {features.get("addresses_all_question_parts", "unknown")}
- Distinct relevant points: {features.get("relevant_point_count", "unknown")}
"""


# ------------------------------------------------- grounding helpers

def _key_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9-]{2,}", str(text or "").lower())
    return {w[:5] for w in words if w not in _STOP}


def claims_match(a: str, b: str, need: float = 0.6) -> bool:
    """Same claim in other words: most key words of the shorter one appear in the other."""
    ka, kb = _key_words(a), _key_words(b)
    if not ka or not kb:
        return False
    small, big = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    return len(small & big) / len(small) >= need


def drop_supported(concerns: list[dict] | None, verifications: list[dict] | None) -> list[dict]:
    """The judge's 'may be inaccurate' concerns that the fact check found supported."""
    supported = [v.get("claim", "") for v in verifications or [] if v.get("label") == "supported"]
    return [c for c in concerns or []
            if not any(claims_match(c.get("claim", ""), s) for s in supported)]


def length_statement(word_count: int, word_limit: int | None) -> str:
    """Exact, model-proof wording of the answer length."""
    if not word_limit:
        return f"{word_count} words (no word limit given)."
    pct = round(100 * (word_count - word_limit) / word_limit)
    if pct > 0:
        rel = f"{pct}% over the limit"
    elif pct < 0:
        rel = f"{-pct}% under the limit"
    else:
        rel = "exactly at the limit"
    if word_count >= 0.8 * word_limit:
        verdict = "This is a full-length answer: do NOT call it brief, short or underdeveloped in length."
    elif word_count >= 0.5 * word_limit:
        verdict = "Somewhat short of the limit; mention length only if it explains missing content."
    else:
        verdict = "Well short of the limit; the answer is incomplete."
    return f"{word_count} words for a {word_limit}-word limit ({rel}). {verdict}"


def score_band(total: float, max_marks: float) -> tuple[str, str]:
    """UPSC-realistic band and the tone it calls for. Toppers average 45-55% in GS."""
    r = (total / max_marks) if max_marks else 0
    if r >= 0.55:
        return ("excellent", "This is a top-scoring answer by UPSC standards. Lead with what makes "
                "it strong; weaknesses are refinements, not failures. Never call it superficial, "
                "weak or poor.")
    if r >= 0.45:
        return ("good", "This is a competitive answer by UPSC standards. Acknowledge that first; "
                "frame weaknesses as what would lift it further. Avoid words such as superficial, "
                "poor or weak for the answer as a whole.")
    if r >= 0.3:
        return ("average", "An average answer. Be balanced: name real strengths, then the "
                "specific gaps holding it back.")
    return ("weak", "A weak or incomplete answer. Be honest and kind: at most one strength, and "
            "only if it is genuinely there; do not praise depth, coverage or analysis it lacks.")


def _is_gs4(subject: str | None, question: str) -> bool:
    s = str(subject or "").lower()
    return bool(re.search(r"\b(?:gs[- ]?(?:paper)?[- ]?(?:iv|4)|ethics?)\b", s)) or \
        bool(re.search(r"\bcase study\b", str(question).lower()) and "ethic" in str(question).lower())


GS4_GUIDE = """GS PAPER IV (ETHICS) GUIDANCE:
- Examiners reward ethical thinkers, quotes, principles and constitutional values (Gandhi's
  talisman, Nolan principles, Kant, Rawls, the Preamble, Article 51A ...) when they are linked
  to the point being made. Never call such a reference irrelevant or unnecessary; at most
  say it should be linked more explicitly to the argument.
- Credit definitions of the ethical terms, real-life or administrative examples, and for
  case studies: stakeholders, the ethical dilemmas, options with merits and demerits, the
  chosen course of action and its justification.
- Suggestions should name the ethical concept, thinker, value or stakeholder to add."""


_ARTICLE_RX = re.compile(
    r"\b(?:articles?|arts?\.|sections?|schedules?|sdgs?|goals?|entry|entries|lists?)\s*"
    r"(?:\d+[a-z]?(?:\(\w+\))*\s*(?:,|and|&|or|-)?\s*)+|"
    r"\b\d+(?:st|nd|rd|th)\s+(?:constitutional\s+)?amendments?\b|"
    r"\b\d+(?:st|nd|rd|th)\s+(?:schedule|five[- ]year plan|finance commission)\b",
    re.I,
)
_NUMBER_RX = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUMBER_RX.findall(str(text or ""))}


def _invented_numbers(item: str, allowed: set[str]) -> set[str]:
    """Figures in a feedback line that come from neither the answer nor the question.
    Article / section / schedule / amendment numbers are references, not figures."""
    return _numbers(_ARTICLE_RX.sub(" ", item)) - allowed


_BRIEF_RX = re.compile(r"\b(?:very |too |rather |quite |overly )?(?:brief|short)\b|\bbrevity\b|"
                       r"\blength (?:is|was) (?:limited|insufficient)\b", re.I)
_DOUBT_RX = re.compile(r"inaccura|incorrect|verify|verif|double[- ]check|unverified|"
                       r"without verification|may be wrong|questionable|dubious", re.I)
_DISMISS_RX = re.compile(r"\b(?:irrelevant|not relevant|unnecessary|tangential|digress\w*|distract\w*|"
                         r"out of place|adds? little)\b", re.I)
# Stating as fact that a claim is false. Allowed only for a CONFIRMED ERROR: the model
# called the real Property Owners' Association (2024) judgment "fictional".
_OVERCLAIM_RX = re.compile(r"\b(?:fictional|fictitious|fabricated|made[- ]up|non[- ]?existent|"
                           r"does not exist|doesn't exist|not a (?:recogni[sz]ed|real|genuine)|"
                           r"contains? (?:several |some |a few |many )?factual (?:in)?accurac\w*|"
                           r"factual (?:errors?|missteps?|mistakes?)|"
                           r"(?:is|are|was|were) (?:factually )?(?:incorrect|wrong|false|erroneous)\b)", re.I)

# Most weaknesses a band may list: seven weaknesses on a 4/10 answer read as a failure.
MAX_WEAKNESSES = {"excellent": 2, "good": 3, "average": 4, "weak": 5}
_PRIORITY_RX = re.compile(r"inaccura|contradict|official source|verify", re.I)

_ETHICS_REF_RX = re.compile(r"quote|thinker|philosoph|principle|talisman|gandhi|nolan|kant|rawls|"
                            r"value|virtue|preamble|ethic", re.I)


def clean_feedback(feedback: dict, *, answer: str, question: str, word_count: int,
                   word_limit: int | None, max_marks: float, total_score: float,
                   supported_claims: list[str] | None = None, gs4: bool = False,
                   confirmed_claims: list[str] | None = None,
                   extra_numbers: str = "", band: str | None = None,
                   concerns: list[dict] | None = None) -> tuple[dict, list[str]]:
    """Remove lines the evidence contradicts. Returns (feedback, notes on what was removed).
      - doubts about a claim the official-source fact check supported
      - 'brief/short' for an answer at 80%+ of the word limit
      - figures (percentages, years, ranks) not in the answer or the question
        (an '(e.g. ...)' aside is cut first; the whole line goes only if needed)
      - GS4: calling a thinker, principle or value irrelevant
      - calling a claim fictional / wrong when no official source contradicted it
      - weaknesses beyond what the score band allows (factual ones are kept first)"""
    allowed = _numbers(answer) | _numbers(question) | _numbers(extra_numbers) | {
        str(word_count), str(word_limit or ""), str(int(max_marks)), str(max_marks),
        f"{total_score:g}", "1", "2", "3", "4", "5"}
    allowed.discard("")
    full_length = bool(word_limit) and word_count >= 0.8 * word_limit
    notes: list[str] = []

    def fix(item: str) -> str | None:
        text = str(item or "").strip()
        if not text or text.lower() in ("none", "null", "n/a"):
            return None
        if supported_claims and _DOUBT_RX.search(text) and any(
                claims_match(text, c, need=0.5) for c in supported_claims):
            notes.append(f"dropped doubt about a supported claim: {text[:80]}")
            return None
        if full_length and _BRIEF_RX.search(text) and re.search(
                r"answer|length|word|treatment|discussion|brief", text, re.I):
            notes.append(f"dropped 'brief' for a full-length answer: {text[:80]}")
            return None
        if _OVERCLAIM_RX.search(text) and not any(
                claims_match(text, c, need=0.4) for c in confirmed_claims or []):
            notes.append(f"dropped unconfirmed 'this is false' claim: {text[:80]}")
            return None
        if gs4 and _DISMISS_RX.search(text) and _ETHICS_REF_RX.search(text):
            notes.append(f"dropped dismissal of an ethics reference: {text[:80]}")
            return None
        bad = _invented_numbers(text, allowed)
        if bad:
            trimmed = re.sub(r"\s*\((?:e\.g\.|eg|for example|such as|like|~|approx)[^)]*\)", "", text, flags=re.I)
            trimmed = re.sub(r",?\s*(?:e\.g\.|for example|such as)\s*[^.;]*\d[^.;]*", "", trimmed, flags=re.I)
            if not _invented_numbers(trimmed, allowed) and len(trimmed) > 25:
                notes.append(f"cut figures {sorted(bad)} from: {text[:80]}")
                return trimmed.strip()
            notes.append(f"dropped line with figures {sorted(bad)}: {text[:80]}")
            return None
        return text

    out = dict(feedback)
    for key in ("strengths", "weaknesses", "improvement_suggestions"):
        out[key] = [x for x in (fix(i) for i in feedback.get(key) or []) if x]
    # Every unverified concern keeps one neutral "may be inaccurate" line, even if the
    # model's own line was removed above for stating it as false.
    for c in concerns or []:
        claim = str(c.get("claim") or "").strip()
        if claim and not any(claims_match(w, claim, need=0.5) for w in out["weaknesses"]):
            short = claim if len(claim) <= 100 else claim[:97].rstrip() + "..."
            out["weaknesses"].append(f'The claim "{short}" may be inaccurate; verify it against '
                                     f"the original source before using it.")
            notes.append(f"added neutral line for concern: {short[:60]}")
    limit = MAX_WEAKNESSES.get(band or "")
    if limit and len(out["weaknesses"]) > limit:
        ranked = sorted(out["weaknesses"], key=lambda w: not _PRIORITY_RX.search(w))
        keep = set(ranked[:limit])
        notes.append(f"kept {limit} of {len(out['weaknesses'])} weaknesses ({band} band)")
        out["weaknesses"] = [w for w in out["weaknesses"] if w in keep]
    overall = str(feedback.get("overall_feedback") or "")
    sentences = re.split(r"(?<=[.!?])\s+", overall.strip())
    kept = [x for x in (fix(s) for s in sentences) if x]
    out["overall_feedback"] = " ".join(kept) if kept else overall
    return out, notes



def _all_feedback_text(feedback: dict) -> str:
    """Flatten student-facing feedback for deterministic checks."""
    values = []

    for key in (
        "strengths",
        "weaknesses",
        "improvement_suggestions",
        "overall_feedback",
    ):
        value = feedback.get(key, [])

        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value:
            values.append(str(value))

    return " ".join(values).lower()



def _feature_consistency_issues(
    feedback: dict,
    features: dict | None,
    dimension_scores: list[dict] | None = None,
) -> list[str]:
    """Catch contradictions between feedback, detected features, and scores."""
    if not features:
        return []

    issues = []
    text = _all_feedback_text(feedback)

    conclusion_patterns = (
        r"\badd\b.{0,35}\bconclusion\b",
        r"\binclude\b.{0,35}\bconclusion\b",
        r"\bmissing\b.{0,35}\bconclusion\b",
        r"\bno\b.{0,20}\bconclusion\b",
        r"\bconclusion\b.{0,35}\bmissing\b",
        r"\blacks?\b.{0,25}\bconclusion\b",
    )

    introduction_patterns = (
        r"\badd\b.{0,35}\bintroduction\b",
        r"\binclude\b.{0,35}\bintroduction\b",
        r"\bmissing\b.{0,35}\bintroduction\b",
        r"\bno\b.{0,20}\bintroduction\b",
        r"\bintroduction\b.{0,35}\bmissing\b",
        r"\blacks?\b.{0,25}\bintroduction\b",
    )

    conclusion_missing = features.get("has_conclusion") is False
    introduction_missing = features.get("has_introduction") is False

    if features.get("has_conclusion") is True:
        if any(re.search(p, text) for p in conclusion_patterns):
            issues.append(
                "Feedback suggests a missing conclusion although one was detected."
            )

    if features.get("has_introduction") is True:
        if any(re.search(p, text) for p in introduction_patterns):
            issues.append(
                "Feedback suggests a missing introduction although one was detected."
            )

    # A missing element can be a valid minor refinement even at level 4.
    # Flag it only if feedback explicitly treats it as a major structural flaw.
    structure_level = None
    if dimension_scores:
        structure_level = _dimension_level(
            dimension_scores, "structure_presentation"
        )

    major_structure_phrases = (
        "major structural flaw",
        "poor structure",
        "structure is poor",
        "seriously undermines the structure",
        "structure is fundamentally weak",
    )

    if (
        structure_level is not None
        and structure_level >= 4
        and (conclusion_missing or introduction_missing)
        and any(phrase in text for phrase in major_structure_phrases)
    ):
        issues.append(
            "Feedback describes a major structural flaw despite a strong structure level."
        )

    return issues


# ----------------------------------------------------------- feedback

def generate_feedback(
    question: str,
    answer: str,
    question_analysis: dict,
    dimension_scores: list[dict],
    total_score: float,
    max_marks: int,
    features: dict,
    score_caps: list[str],
    word_count: int,
    word_limit_status: str,
    factual_concerns: list[dict] | None = None,
    confirmed_errors: list[dict] | None = None,
    word_limit: int | None = None,
    subject: str | None = None,
    claim_verifications: list[dict] | None = None,
) -> dict:
    # Avoid unsupported praise for clearly off-topic answers.
    if _relevance_level(dimension_scores) <= 1:
        return _off_topic_feedback()

    supported = [v.get("claim", "") for v in claim_verifications or []
                 if v.get("label") == "supported"]
    factual_concerns = drop_supported(factual_concerns, claim_verifications)
    gs4 = _is_gs4(subject, question)
    band, tone = score_band(total_score, max_marks)

    view = _level_view(dimension_scores)
    strong = [d for d in view if d["level"] >= 4]
    weak = [d for d in view if d["level"] <= 3]

    essential = (
        question_analysis.get("expected_coverage", {}).get(
            "essential_points", []
        )
    )

    if ALLOW_NAMED_REFERENCES:
        reference_rule = (
            "You may name a well-known scheme, Act, Article, landmark case, committee, report, "
            "thinker or concept to add, but only when you are certain it exists and is "
            "relevant to this question. Never give a figure, percentage, rank, amount or year "
            "that is not in the candidate's answer or the question."
        )
    else:
        reference_rule = (
            "Do not introduce any specific case, judgment, article number, "
            "scheme, committee, statistic, or year absent from the candidate's "
            "answer. Describe possible additions generically instead."
        )

    structured_llm = llm.with_structured_output(FeedbackResponse)

    prompt = f"""
You are a constructive UPSC GS Mains answer coach.

QUESTION:
{question}

CANDIDATE ANSWER:
{answer}

SUBJECT: {subject or "not given"}
OVERALL SCORE: {total_score}/{max_marks}
SCORE BAND: {band}. {tone}
LENGTH: {length_statement(word_count, word_limit)}

DIMENSION LEVELS (0-5):
Strong dimensions, level 4-5:
{strong}

Dimensions with room for improvement, level 0-3:
{weak}

ISSUES THAT LIMITED THE SCORE:
{score_caps}

POSSIBLE FACTUAL CONCERNS (unverified, from an automated check):
{factual_concerns or "None"}

CONFIRMED ERRORS (contradicted by an official source):
{[{"claim": c["claim"], "source_says": c.get("quote"), "url": (c.get("sources") or [""])[0]} for c in (confirmed_errors or [])] or "None"}

DETECTED ANSWER FEATURES:
{_answer_feature_context(features)}

CLAIMS CONFIRMED BY AN OFFICIAL SOURCE (never question these):
{supported or "None"}

ESSENTIAL POINTS FROM QUESTION ANALYSIS:
{essential}
{GS4_GUIDE if gs4 else ""}

Produce:
- strengths
- weaknesses
- improvement_suggestions
- overall_feedback

RULES:

1. Ground every claim in the candidate's answer, detected features, or
   dimension-level justifications. Do not invent content.

2. Strengths should primarily reflect strong dimensions. Weaknesses should
   primarily reflect dimensions with room for improvement.

3. A level 4 can have a specific minor refinement, but do not describe it
   as a major deficiency. Do not criticise a level 5 dimension.

4. If there are no weak dimensions, provide at most one minor refinement
   and at most two optional-polish suggestions.

5. Every item in ISSUES THAT LIMITED THE SCORE must be represented in
   weaknesses in clear, student-friendly language. Do not expose internal
   variable names or technical implementation details.

6. Never suggest adding an introduction when the detected feature says an
   introduction is present. Never suggest adding a conclusion when the
   detected feature says a conclusion is present.

7. If an introduction or conclusion is absent, do not automatically treat
   that absence as a major flaw. Consider the structure level, answer length,
   question type, and word limit before suggesting a change.

8. Do not claim that the answer contains a feature, example, reference, or
   argument unless it is actually present. Feature detectors can be imperfect;
   do not make overly specific claims from uncertain detection results.

9. Use essential points only to identify genuinely missing central demands.
   Do not treat important or optional points as mandatory. Accept alternative
   valid approaches.

10. Do not automatically demand challenges, solutions, examples, data,
    legal provisions, or named schemes unless they are relevant to the
    question and proportionate to the word limit.

11. Each list item must be one sentence. Give 2 to 4 improvement suggestions,
    ordered by impact and sized to fit the word limit.

12. {reference_rule}

13. Describe the length only as stated under LENGTH. Do not call a short answer
    poor merely because it is short.

14. Never claim that this is an official UPSC score or official feedback.

15. Match the tone to the SCORE BAND. Be respectful, direct and specific.

16. For each possible factual concern, include ONE weakness saying the claim
    "may be inaccurate" and telling the candidate to verify it against the
    source (the Constitution text, the Act or the judgment). Do NOT state what
    the correct fact is. If the same concern already appears under ISSUES THAT
    LIMITED THE SCORE, do not repeat it. Never doubt a claim listed under
    CLAIMS CONFIRMED BY AN OFFICIAL SOURCE, and do not add doubts of your own
    about claims that are not listed as concerns, except as in rule 22.

17. Never describe a possible factual concern as a confirmed error.
18. Never mention quotes, evidence checks, audits or scoring mechanics.
    Feedback must only describe the answer's content and presentation.
19. For each CONFIRMED ERROR, include ONE weakness that states the claim is
    inaccurate, says what the source states (using "source_says"), and names the
    source website. Use only the quoted text. Do not add facts of your own.
20. Never present a POSSIBLE FACTUAL CONCERN as confirmed.

21. Be specific to THIS question, the way an examiner's margin note is. At least
    two improvement suggestions must each name a concrete piece of content to add:
    a missing dimension or stakeholder, a named scheme, Act, Article, case,
    committee, report, thinker, example type or keyword relevant to this topic.
    "Add more examples", "add causal explanations" or "deepen the analysis" alone
    is not acceptable: say which point needs it and what to add.

22. If the answer lists members of a group, signatories, office-holders or similar
    names and you are certain one of them is wrong, add one weakness saying the
    list "may contain an inaccuracy" and should be checked. Do not state the
    correct list.

23. A requirement such as "with the help of examples / constitutional provisions /
    case laws" runs through the whole answer: judge whether the points are backed
    by them, not whether a separate section exists. Do not ask the candidate to
    describe a phenomenon the question takes as given (for example "the rise of X"
    in "To what extent can the rise of X be seen as ...").

24. Never call a claim fictional, fabricated, non-existent, wrong or a factual error
    unless it is listed under CONFIRMED ERRORS. For other doubts use rule 16 wording.

25. List at most {MAX_WEAKNESSES[band]} weaknesses, the most important first.

Return only the structured FeedbackResponse.
"""

    result = structured_llm.invoke(prompt)
    feedback, notes = clean_feedback(
        result.model_dump(), answer=answer, question=question, word_count=word_count,
        word_limit=word_limit, max_marks=max_marks, total_score=total_score,
        supported_claims=supported, gs4=gs4, band=band, concerns=factual_concerns,
        confirmed_claims=[c.get("claim", "") for c in confirmed_errors or []],
        # a confirmed error's weakness quotes the official source, figures included
        extra_numbers=" ".join(str(c.get("quote") or "") for c in confirmed_errors or []),
    )
    from app import monitoring
    monitoring.note("feedback_lines_removed", len([n for n in notes if not n.startswith("added")]))
    monitoring.note("score_band", band)
    return feedback


def clean_dimension_notes(dimension_scores: list[dict], **ctx) -> list[dict]:
    """The same checks, sentence by sentence, on each dimension's justification and
    improvement text (the judge wrote "~70% as of 2023" and "remove the fictional case"
    there). Figures in the code's own cap notes are allowed."""
    out = []
    base_extra = str(ctx.pop("extra_numbers", "") or "")
    for d in dimension_scores or []:
        d = dict(d)
        extra = f'{base_extra} {d.get("cap_note") or ""}'
        for key in ("improvement", "justification"):
            text = str(d.get(key) or "").strip()
            if not text or text.lower() in ("none", "null", "n/a"):
                d[key] = ""
                continue
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", text)
            cleaned, _ = clean_feedback(
                {"strengths": sentences, "weaknesses": [], "improvement_suggestions": [],
                 "overall_feedback": ""}, extra_numbers=extra, **ctx)
            d[key] = " ".join(cleaned["strengths"])
        out.append(d)
    return out


# -------------------------------------------------------- consistency

def check_feedback_consistency(
    dimension_scores: list[dict],
    total_score: float,
    max_marks: int,
    feedback: dict,
    features: dict | None = None,
) -> dict:
    issues: list[str] = []

    # Deterministic check for clearly off-topic answers.
    if _relevance_level(dimension_scores) <= 1:
        if feedback.get("strengths"):
            issues.append(
                "The answer has relevance level 0-1, but feedback lists strengths."
            )

    # Deterministic feature checks catch contradictions without another LLM.
    issues.extend(_feature_consistency_issues(feedback, features, dimension_scores))

    # Let the LLM check semantic contradictions that simple rules may miss.
    structured_llm = llm.with_structured_output(ConsistencyCheckResponse)

    prompt = f"""
Check whether the feedback is consistent with the final dimension levels.

TOTAL SCORE: {total_score}/{max_marks}

FINAL DIMENSION LEVELS (0-5):
{_level_view(dimension_scores)}

DETECTED ANSWER FEATURES:
{_answer_feature_context(features or {})}

FEEDBACK:
{feedback}

Level guidance:
- Levels 4-5 indicate strong performance, although level 4 may allow a
  specific minor refinement.
- Level 3 indicates average performance.
- Levels 0-2 indicate weak performance.
- Scaled marks are not the same as dimension levels.

Flag meaningful contradictions only:
- Feedback praises a dimension at level 0-2.
- Feedback criticises a level 4-5 dimension as having a major deficiency.
- Feedback claims a detected feature is missing.
- Feedback claims strong overall performance when most dimensions are weak,
  or the reverse.
- Feedback makes a claim that directly contradicts the detected features.

Do not flag reasonable nuance, minor wording differences, or a specific
improvement suggestion that is compatible with a level 4.

Do not recalculate or change any score.
Return is_consistent=true and an empty issues list if broadly consistent.

Return only the structured ConsistencyCheckResponse.
"""

    result = structured_llm.invoke(prompt).model_dump()
    issues.extend(result.get("issues", []))

    # Deduplicate issues while preserving their order.
    unique_issues = list(dict.fromkeys(issues))

    return {
        "is_consistent": not unique_issues,
        "issues": unique_issues,
    }
