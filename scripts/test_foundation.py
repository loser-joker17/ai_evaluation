
from app.schemas import EvaluationInput, DimensionScore
from app.llm import llm

# 1. Test input validation
request = EvaluationInput(
    question="Discuss the role of the Indian Constitution in promoting social justice.",
    answer="The Constitution promotes equality through Fundamental Rights.",
    max_marks=10,
    word_limit=150,
)

print("Input validation: PASS")
print("Maximum marks:", request.max_marks)

# 2. Test score validation
score = DimensionScore(
    dimension="relevance",
    score=2,
    max_score=2,
    justification="The answer addresses the question.",
    evidence_from_answer=["Mentions the Constitution and equality."],
    improvement="Add more specific constitutional provisions.",
)

print("Dimension validation: PASS")
print("Configured model:", llm.model_name)