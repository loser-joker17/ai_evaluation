
import os
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict, model_validator
from langchain_openai import ChatOpenAI

load_dotenv()


# 1. Define the structured evaluation
class AnswerEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance: int = Field(ge=0, le=3)
    relevance_reason: str

    knowledge_accuracy: int = Field(ge=0, le=3)
    knowledge_accuracy_reason: str

    analysis_depth: int = Field(ge=0, le=2)
    analysis_depth_reason: str

    presentation_structure: int = Field(ge=0, le=2)
    presentation_structure_reason: str

    strengths: List[str]
    weaknesses: List[str]
    missing_points: List[str]
    improvement_suggestions: List[str]
    overall_feedback: str

    @model_validator(mode="after")
    def validate_scores(self):
        # Each dimension has a fixed maximum.
        assert 0 <= self.relevance <= 3
        assert 0 <= self.knowledge_accuracy <= 3
        assert 0 <= self.analysis_depth <= 2
        assert 0 <= self.presentation_structure <= 2
        return self

    @property
    def score(self) -> int:
        # Python, not the LLM, calculates the final score.
        return (
            self.relevance
            + self.knowledge_accuracy
            + self.analysis_depth
            + self.presentation_structure
        )


# 2. Connect to NVIDIA
llm = ChatOpenAI(
    model="openai/gpt-oss-20b",
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv("NVIDIA_API_KEY"),
    temperature=0,
)

structured_llm = llm.with_structured_output(AnswerEvaluation)


# 3. Evaluate an answer
def evaluate_answer(
    question: str,
    answer: str,
    word_limit: int = 150,
) -> AnswerEvaluation:

    word_count = len(answer.split())

    prompt = f"""
You are an experienced UPSC Civil Services Mains answer evaluator.

Evaluate the student's answer using this fixed 10-mark rubric.

RUBRIC:
1. Relevance and demand of question: 0-3
   - Does the answer address the question's directive and core demand?

2. Knowledge and factual accuracy: 0-3
   - Are the facts, constitutional provisions, examples and concepts correct?
   - Do not assume a claim is false merely because it is unfamiliar.
   - Do not invent errors or unsupported facts.

3. Analysis and depth: 0-2
   - Does the answer explain, analyze and critically examine the topic
     where appropriate?

4. Presentation and structure: 0-2
   - Assess logical flow, clarity and organization.
   - A single paragraph is not automatically poorly structured.
   - Consider the introduction and conclusion in context.

IMPORTANT RULES:
- The four dimension scores must stay within their stated ranges.
- Give a short, specific justification for every dimension score.
- Evaluate content quality, not length alone.
- The suggested word limit is a guideline. Penalize brevity only
  when it causes insufficient coverage, explanation or analysis.
- Separate confirmed factual errors from claims that need verification.
- Missing points must be relevant to the actual question.
- Do not invent constitutional articles, statutes, amendments,
  examples, or historical facts.
- Give constructive, actionable feedback.
- Do not output an overall numeric score; Python calculates it.

QUESTION:
{question}

EXPECTED WORD LIMIT:
{word_limit}

STUDENT ANSWER:
{answer}

ACTUAL WORD COUNT:
{word_count}

Return the evaluation using the required schema.
"""

    return structured_llm.invoke(prompt)


# 4. Test the evaluator
if __name__ == "__main__":
    question = (
        "Discuss the role of the Indian Constitution in promoting "
        "social justice. (150 words)"
    )

    answer = """
    The Indian Constitution promotes social justice through
    equality before law under Article 14, prohibition of
    discrimination under Article 15, and abolition of
    untouchability under Article 17. Directive Principles
    guide the state toward reducing inequality. Reservations
    and welfare policies also support disadvantaged groups.
    However, implementation gaps and social discrimination
    remain challenges. Effective enforcement, education,
    and inclusive governance are necessary to achieve
    constitutional ideals.
    """

    result = evaluate_answer(question, answer)

    print("\n========== UPSC ANSWER EVALUATION ==========\n")
    print(f"Final Score: {result.score}/10")
    print(f"Word Count: {len(answer.split())}")
    print("\n--- Dimension Scores ---")
    print(f"Relevance: {result.relevance}/3")
    print(f"Reason: {result.relevance_reason}")
    print(f"\nKnowledge & Accuracy: {result.knowledge_accuracy}/3")
    print(f"Reason: {result.knowledge_accuracy_reason}")
    print(f"\nAnalysis & Depth: {result.analysis_depth}/2")
    print(f"Reason: {result.analysis_depth_reason}")
    print(f"\nPresentation & Structure: {result.presentation_structure}/2")
    print(f"Reason: {result.presentation_structure_reason}")

    print("\n--- Strengths ---")
    for item in result.strengths:
        print(f"- {item}")

    print("\n--- Weaknesses ---")
    for item in result.weaknesses:
        print(f"- {item}")

    print("\n--- Missing Points ---")
    for item in result.missing_points:
        print(f"- {item}")

    print("\n--- Improvement Suggestions ---")
    for item in result.improvement_suggestions:
        print(f"- {item}")

    print("\n--- Overall Feedback ---")
    print(result.overall_feedback)

    print("\n============================================\n")