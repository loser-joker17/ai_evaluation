
from typing import Any, TypedDict


class EvaluatorState(TypedDict, total=False):
   # Original request
    question: str
    answer: str
    max_marks: int
    word_limit: int | None
    subject: str

    # Input processing
    input_valid: bool
    input_errors: list[str]
    word_count: int
    word_limit_status: str

    # Question understanding
    question_analysis: dict[str, Any]

    # Features and caps
    answer_features: dict[str, Any]
    score_caps: list[str]
    factual_concerns: list[dict[str, Any]]

    # Evidence retrieval and verification (for future RAG)
    retrieved_sources: list[dict[str, Any]]
    claim_verifications: list[dict[str, Any]]
    evidence_gaps: list[str]

    # Evaluation
    scores_valid: bool
    score_errors: list[str]
    dimension_scores: list[dict[str, Any]]
    total_score: float
    raw_total_score: float

    # Feedback
    strengths: list[str]
    weaknesses: list[str]
    improvement_suggestions: list[str]
    overall_feedback: str

    # Consistency check
    feedback_consistent: bool
    consistency_issues: list[str]

    # Workflow control
    retry_count: int
    errors: list[str]
    limitations: list[str]
    final_result: dict[str, Any]