
import re

from app.llm import llm
from app.schemas import FeedbackResponse, ConsistencyCheckResponse


# Until RAG can verify references, avoid suggesting unverified named sources.
ALLOW_NAMED_REFERENCES = False


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
- Mechanism count: {features.get("mechanism_count", "unknown")}
- Addresses all question parts: {features.get("addresses_all_parts", "unknown")}
"""


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
) -> dict:
    # Avoid unsupported praise for clearly off-topic answers.
    if _relevance_level(dimension_scores) <= 1:
        return _off_topic_feedback()

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
            "You may suggest specific references only when you are confident "
            "they are accurate and relevant."
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

OVERALL SCORE: {total_score}/{max_marks}
WORD COUNT: {word_count} ({word_limit_status})

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

ESSENTIAL POINTS FROM QUESTION ANALYSIS:
{essential}

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

11. Each list item must be one sentence. Provide at most three improvement
    suggestions, ordered by impact and sized to fit the word limit.

12. {reference_rule}

13. Do not call a short answer poor merely because it is short. Discuss
    length only when it affects the answer's adequacy or violates the limit.

14. Never claim that this is an official UPSC score or official feedback.

15. Keep the tone respectful, direct, specific, and useful.

16. For each possible factual concern, include ONE weakness saying the claim
    "may be inaccurate" and telling the candidate to verify it against the
    source (the Constitution text, the Act or the judgment). Do NOT state what
    the correct fact is. If the same concern already appears under ISSUES THAT
    LIMITED THE SCORE, do not repeat it.

17. Never describe a possible factual concern as a confirmed error.
18. Never mention quotes, evidence checks, audits or scoring mechanics.
    Feedback must only describe the answer's content and presentation.
19. For each CONFIRMED ERROR, include ONE weakness that states the claim is
    inaccurate, says what the source states (using "source_says"), and names the
    source website. Use only the quoted text. Do not add facts of your own.
20. Never present a POSSIBLE FACTUAL CONCERN as confirmed.

Return only the structured FeedbackResponse.
"""

    result = structured_llm.invoke(prompt)
    return result.model_dump()


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
