from app.llm import llm
from app.schemas import QuestionAnalysis


def analyze_question(
    question: str,
    subject: str,
    max_marks: int,
    word_limit: int | None,
) -> dict:
    structured_llm = llm.with_structured_output(QuestionAnalysis)

    prompt = f"""
You are an experienced UPSC GS Mains question analyst.

Your task is to interpret the question and create a concise,
flexible coverage plan for evaluating a student's answer.

Do not write a model answer.
Do not turn the coverage plan into a rigid checklist.

Subject: {subject}
Maximum marks: {max_marks}
Word limit: {word_limit if word_limit is not None else "Not specified"}

Question:
{question}

Return these fields:
- topic: the main topic
- directive: the question's directive
- question_parts: the distinct demands of the question
- expected_coverage:
    - essential_points
    - important_points
    - optional_points
- interpretation: explain what the question asks in plain language

Rules for interpreting the question:

1. Identify the directive carefully.
   Examples:
   - Discuss: explain the topic with relevant arguments and perspectives.
   - Examine: investigate the issue and explain its significance.
   - Analyze: explain relationships, causes, mechanisms, or consequences.
   - Critically examine: assess strengths and limitations, or supporting
     and opposing arguments, where relevant to the specific question.
   - Evaluate: make a reasoned assessment using appropriate criteria.
   - Comment: provide a focused, reasoned observation or judgment.
   These are general guidelines. Interpret each directive in context.

2. Separate explicit demands from possible enrichment.
   Include a demand as essential only when it is explicitly requested
   or strongly implied by the question's wording and directive.

3. Do not automatically add challenges, solutions, recommendations,
   government initiatives, constitutional provisions, case studies,
   or a conclusion as mandatory requirements.
   Include them as essential only when the question explicitly asks
   for them or they are necessary to address its central demand.

4. For questions using "critically examine", "critically analyze",
   or similar wording, normally expect a balanced assessment.
   Identify the relevant sides of the assessment without inventing
   unrelated demands.

5. Keep question_parts focused on the actual distinct demands.
   Do not split one demand into many small subtopics merely to create
   a longer checklist.

6. Keep essential_points concise and limited to the central requirements.
   A short answer should not be expected to cover every relevant angle.
   Scale the expected breadth to the marks and word limit.

7. Use important_points for useful supporting angles that strengthen
   the answer but are not individually compulsory.
   Use optional_points for additional enrichment, not core requirements.

8. Accept alternative valid approaches.
   Do not require a particular example, scheme, judgment, statistic,
   or framework when other relevant evidence or reasoning could
   adequately address the question.

9. Do not invent constitutional articles, amendments, judgments,
   statistics, policies, or factual references.
   If a specific reference is uncertain, describe the relevant concept
   without fabricating the reference.

10. Do not penalize an answer merely because it omits an optional point.
    The coverage plan is an evaluation guide, not an exhaustive answer key.

11. Do not infer demands from the subject alone. Base the plan primarily
    on the actual question and its directive.

12. If the wording is ambiguous, acknowledge the ambiguity rather than
    arbitrarily imposing additional requirements.

Return only the structured QuestionAnalysis response.
"""

    result = structured_llm.invoke(prompt)
    return result.model_dump()