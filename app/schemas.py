from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DimensionName = Literal[
    "relevance",
    "content_substantiation",
    "analysis_depth",
    "coverage_balance",
    "structure_presentation",
]

EXPECTED_DIMENSIONS = {
    "relevance",
    "content_substantiation",
    "analysis_depth",
    "coverage_balance",
    "structure_presentation",
}


class EvaluationInput(BaseModel):
    """The question and student answer submitted for evaluation."""

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=5, description="UPSC GS Mains question")
    answer: str = Field(min_length=1, description="Student's written answer")
    max_marks: Literal[10, 15, 20] = Field(
        description="Maximum marks available: 10 or 15"
    )
    word_limit: int | None = Field(
        default=None,
        gt=0,
        description="Expected word limit, if specified by the question",
    )
    subject: str = Field(default="GS", description="Subject or GS paper")


class ExpectedCoverage(BaseModel):
    """Flexible checklist of points relevant to the question."""

    essential_points: list[str] = Field(default_factory=list)
    important_points: list[str] = Field(default_factory=list)
    optional_points: list[str] = Field(default_factory=list)


class QuestionAnalysis(BaseModel):
    """Interpretation of what the question is asking."""

    topic: str
    directive: str
    question_parts: list[str] = Field(default_factory=list)
    expected_coverage: ExpectedCoverage
    interpretation: str


class RawAnswerFeatures(BaseModel):
    """What the LLM extracts. It does not decide has_introduction / has_conclusion."""

    introduction_sentence: str | None = None
    conclusion_sentence: str | None = None
    constitutional_or_legal_refs: list[str] = Field(default_factory=list)
    schemes_policies_committees: list[str] = Field(default_factory=list)
    examples_or_data: list[str] = Field(default_factory=list)
    mechanisms_explained: int = Field(ge=0)
    dimensions_covered: list[str] = Field(default_factory=list)
    addresses_all_question_parts: bool
    # One label per numbered block of the answer: "P1", "P2", ... (the question
    # part it answers), "intro", "conclusion", "wayforward" or "other".
    block_labels: list[str] = Field(default_factory=list)


class AnswerFeatures(BaseModel):
    """Final features. The has_* flags are verified in code."""

    has_introduction: bool
    has_conclusion: bool
    introduction_sentence: str | None = None
    conclusion_sentence: str | None = None
    constitutional_or_legal_refs: list[str] = Field(default_factory=list)
    schemes_policies_committees: list[str] = Field(default_factory=list)
    examples_or_data: list[str] = Field(default_factory=list)
    mechanisms_explained: int = Field(ge=0)
    dimensions_covered: list[str] = Field(default_factory=list)
    addresses_all_question_parts: bool
    # Measured in code from block_labels (None when not measurable).
    specifics_per_100_words: float | None = None
    part_word_share: list[dict] = Field(default_factory=list)   # [{"part": str, "share": float}]
    unasked_share: float | None = None
    parts_in_order: bool | None = None
    feature_notes: list[str] = Field(default_factory=list)


class FactualConcern(BaseModel):
    """A claim in the answer that may be wrong. Unverified until RAG exists."""

    claim: str          # exact quote from the candidate's answer
    issue: str          # why it may be inaccurate
    confidence: Literal["high", "medium", "low"]


class RawDimensionScore(BaseModel):
    """What the LLM returns: a level from 0 to 5."""

    dimension: DimensionName
    score: int = Field(ge=0, le=5)
    justification: str
    evidence_from_answer: list[str] = Field(default_factory=list)
    improvement: str


class DemandCheck(BaseModel):
    """The judge's status for one numbered demand (Q1, D1 ...)."""

    id: str
    status: Literal["covered", "thin", "missing"]
    evidence: str = ""


class DimensionScoresResponse(BaseModel):
    """The five raw dimension levels proposed by the LLM."""

    dimension_scores: list[RawDimensionScore]
    factual_concerns: list[FactualConcern] = Field(default_factory=list)
    demand_check: list[DemandCheck] = Field(default_factory=list)


class DimensionScore(BaseModel):
    """Final score in marks, computed by code."""

    dimension: DimensionName
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    raw_level: int = Field(ge=0, le=5)
    final_level: int = Field(ge=0, le=5)
    cap_note: str | None = None
    audit_note: str | None = None
    justification: str
    evidence_from_answer: list[str] = Field(default_factory=list)
    improvement: str

    @model_validator(mode="after")
    def validate_score_range(self):
        if self.score > self.max_score + 1e-6:
            raise ValueError("Dimension score cannot exceed its maximum.")
        return self

class ClaimVerification(BaseModel):
    """Result of checking one claim against official web sources."""

    claim: str
    query: str | None = None
    label: Literal["supported", "contradicted", "unverifiable"]
    quote: str | None = None
    explanation: str = ""
    sources: list[str] = Field(default_factory=list)

class EvaluationOutput(BaseModel):
    """Structured result produced by the evaluator."""

    status: Literal["success", "error"] = "success"
    question: str = ""
    subject: str = "GS"
    question_analysis: QuestionAnalysis | None = None
    answer_features: AnswerFeatures | None = None
    factual_concerns: list[FactualConcern] = Field(default_factory=list)
    claim_verifications: list[ClaimVerification] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    total_score: float | None = Field(default=None, ge=0)
    raw_total_score: float | None = Field(default=None, ge=0)
    max_marks: Literal[10, 15, 20]
    word_count: int = Field(default=0, ge=0)
    word_limit_status: str = "not_specified"

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    overall_feedback: str = ""

    feedback_consistent: bool | None = None
    consistency_issues: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_total_score(self):
        if self.status == "error":
            return self

        if self.question_analysis is None:
            raise ValueError("A successful evaluation requires question analysis.")

        actual = [item.dimension for item in self.dimension_scores]

        if len(actual) != 5 or set(actual) != EXPECTED_DIMENSIONS:
            raise ValueError(
                "Evaluation must contain each of the five dimensions exactly once."
            )

        if abs(sum(i.max_score for i in self.dimension_scores) - self.max_marks) > 0.05:
            raise ValueError(
                "Dimension maximums must add up to the question's maximum marks."
            )

        calculated_total = round(sum(i.score for i in self.dimension_scores), 2)

        if self.raw_total_score is None or abs(self.raw_total_score - calculated_total) > 0.05:
            raise ValueError(
                f"Raw total must equal the sum of dimension scores ({calculated_total})."
            )

        if self.total_score is None or abs(self.total_score - self.raw_total_score) >= 1.0:
            raise ValueError("Rounded total is too far from the raw total.")

        if self.total_score > self.max_marks + 1e-6:
            raise ValueError("Total score cannot exceed maximum marks.")

        return self


class FeedbackResponse(BaseModel):
    """Detailed feedback generated after scoring."""

    strengths: list[str]
    weaknesses: list[str]
    improvement_suggestions: list[str]
    overall_feedback: str


class ConsistencyCheckResponse(BaseModel):
    """Checks whether written feedback agrees with numerical scores."""

    is_consistent: bool
    issues: list[str] = Field(default_factory=list)