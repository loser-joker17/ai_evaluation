# UPSC Mains AI Answer Evaluator

An AI evaluator for UPSC Civil Services Mains answers. Give it a question and a candidate's answer, and it returns marks out of the question's maximum, a score for each of five rubric dimensions, fact-checks of named legal claims, and written feedback.

The design goal is an evaluator that does **not** simply trust the LLM. Every score the model gives is audited in code: quotes must really appear in the answer, high scores need real evidence, and a claim is only marked wrong if an official source contradicts it.

> Scores are AI-generated estimates, not official UPSC marks. They should be calibrated against human-marked answers before anyone relies on them.

---

## How it works

The evaluator is a [LangGraph](https://langchain-ai.github.io/langgraph/) pipeline. Each step is a node, and the state passes from node to node:

```
validate_input ─► analyze_input ─► analyze_question ─► extract_features ─► fact_check ─► evaluate_answer
      │                                                                                       │
      └──────────────► return_error ◄────────────── (invalid scores) ◄─────────────────────────┤
                                                                                              ▼
                                       build_result ◄── check_feedback_consistency ◄── generate_feedback
```

| Step | What it does | File |
|---|---|---|
| **validate_input** | Checks the request (question, answer, marks, word limit) with Pydantic. | `app/evaluator/graph.py` |
| **analyze_input** | Counts words and labels the answer under, within or over the word limit. | `app/evaluator/graph.py` |
| **analyze_question** | LLM reads the question's directive ("discuss", "critically examine"…) and builds a coverage plan of essential, important and optional points. | `app/evaluator/question_analysis.py` |
| **extract_features** | LLM extracts facts about the answer: intro and conclusion sentences, named Articles, cases, schemes, examples, cause-effect explanations. Code then checks the intro is really near the start and the conclusion really at the end. | `app/evaluator/features.py` |
| **fact_check** | Picks up to 5 checkable legal or institutional claims and verifies them with RAG (see below). | `app/evaluator/factcheck.py` |
| **evaluate_answer** | LLM scores five dimensions on a 0–5 scale; code then audits and caps those scores (see below). | `app/evaluator/scoring.py` |
| **generate_feedback** | LLM writes strengths, weaknesses and suggestions that match the final scores. | `app/evaluator/feedback.py` |
| **check_feedback_consistency** | Flags feedback that contradicts the scores or the detected features. | `app/evaluator/feedback.py` |
| **build_result** | Assembles the final JSON output. | `app/evaluator/graph.py` |

### Scoring rubric

| Dimension | Weight |
|---|---|
| Relevance | 20% |
| Content and substantiation (accuracy, specifics) | 25% |
| Analysis depth | 25% |
| Coverage and balance | 15% |
| Structure and presentation | 15% |

The LLM gives each dimension a level from 0 to 5. Code then converts levels to marks and applies checks the LLM can't override:

- **Evidence audit:** a level 4 or 5 needs quotes that actually appear in the answer; a level 5 needs at least three substantial quotes.
- **Feature caps:** no conclusion, too few words, or exceeding the word limit caps the relevant dimension.
- **Factual caps:** claims contradicted by an official source, or confidently flagged by the judge, cap content and substantiation.
- **Realistic ceiling:** level 5 is worth 85% of a dimension, and no total exceeds 75% of maximum marks, in line with how strictly UPSC answers are actually marked.
- **Rounding:** the total is rounded to the nearest half mark, the way examiners award marks.

### RAG fact-checking

Fact-checking uses retrieval-augmented generation (RAG): instead of trusting the model's memory, it retrieves source text and asks the model to judge the claim using only that text.

1. **Claim extraction:** the LLM copies up to 5 checkable claims word for word from the answer (named cases, Articles, Acts, amendments, committees, years).
2. **Retrieval** from two tiers of sources:
   - **Notes corpus (local):** your study-notes PDFs in `data/corpus/`, split into overlapping 180-word chunks, de-duplicated, and searched with BM25 keyword ranking (`app/retrieval/corpus.py`).
   - **Official websites:** a [Tavily](https://tavily.com/) web search restricted to trusted government and legal domains such as indiacode.nic.in, sci.gov.in, prsindia.org and pib.gov.in.
3. **Verdict:** the LLM labels each claim *supported*, *contradicted* or *unverifiable*, and must copy a quote from a source as proof.
4. **Safeguards against false accusations:**
   - The quote is checked to really exist in the retrieved text.
   - "Contradicted" must be backed by an **official** source; study notes alone can't mark a student wrong.
   - A contradiction is re-checked a second time with the sources in reverse order before it counts.

Results are cached in `data/cache/factcheck.json` to save API calls.

---

## Tech stack

| Tool | Used for |
|---|---|
| **LangGraph** | The evaluation pipeline (nodes, state, conditional routing) |
| **LangChain OpenAI** (`ChatOpenAI`) | Calling LLMs through NVIDIA's OpenAI-compatible API, with structured (Pydantic) outputs |
| **NVIDIA API** | Hosts the models: `nvidia/nemotron-3-ultra-550b-a55b` (fast model) and `z-ai/glm-5.3` (judge model) by default |
| **Pydantic** | Input validation and structured LLM output schemas (`app/schemas.py`) |
| **Tavily** | Web search limited to official Indian government and legal sites |
| **pypdf** | Extracting text from the notes PDFs |
| **BM25** (implemented in-house) | Keyword search over the notes corpus |
| **pytest** | Unit tests for scoring, caps, auditing and the corpus |

---

## Setup

You need **Python 3.11 or newer** (the code uses `int | None` type syntax).

### 1. Clone the repository

```bash
git clone https://github.com/loser-joker17/ai_evaluation.git
cd ai_evaluation
```

### 2. Create and activate a virtual environment

A virtual environment keeps this project's packages separate from the rest of your system.

**Windows (PowerShell or Command Prompt):**

```bash
python -m venv myenv
myenv\Scripts\activate
```

**macOS / Linux:**

```bash
python3 -m venv myenv
source myenv/bin/activate
```

Your prompt should now start with `(myenv)`. Run the activate command again every time you open a new terminal. To leave the environment, run `deactivate`.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add your API keys

Create a file named `.env` in the project root (it's in `.gitignore`, so it is never committed):

```env
NVIDIA_API_KEY=your_nvidia_api_key
TAVILY_API_KEY=your_tavily_api_key

# Optional: override the default models
# FAST_MODEL=nvidia/nemotron-3-ultra-550b-a55b
# JUDGE_MODEL=z-ai/glm-5.3
```

- NVIDIA API key: [build.nvidia.com](https://build.nvidia.com/)
- Tavily API key: [tavily.com](https://tavily.com/)

### 5. Add your notes PDFs (optional)

Put your study-notes PDFs in `data/corpus/`. They are **not** included in the repository for copyright reasons.

The first run builds a search index from them and caches it in `data/cache/corpus_chunks.json`; it rebuilds automatically when the PDFs change. Without any PDFs the evaluator still works, and fact-checking uses only the official websites.

---

## Usage

### Evaluate an answer

Run from the project root:

```python
from app.evaluator.graph import evaluate_submission

result = evaluate_submission({
    "question": "Critically examine the role of Public Interest Litigation in strengthening access to justice in India.",
    "answer": "Public Interest Litigation (PIL) emerged when courts relaxed the rule of locus standi...",
    "subject": "GS Paper II",
    "max_marks": 10,
    "word_limit": 150,
})

print(result["total_score"], "/", result["max_marks"])
for d in result["dimension_scores"]:
    print(d["dimension"], d["score"], "/", d["max_score"])
print(result["overall_feedback"])
```

The result also includes `strengths`, `weaknesses`, `improvement_suggestions`, `claim_verifications`, `factual_concerns`, `answer_features` and `limitations`.

### Run the tests

```bash
pytest
```

### Benchmark against human marks

Compare the evaluator's marks with human-marked answers:

```bash
# Examiner-marked GS2 answers (resumable; safe to stop and re-run)
python benchmark_examiner.py
python benchmark_examiner.py --report-only     # re-print the saved table
python benchmark_examiner.py --fresh           # ignore saved results

# Original golden set, with run-to-run variance
python -m scripts.benchmark --runs 3 --label my_run
python -m scripts.benchmark --label v2 --compare data/benchmark/results/my_run.json
```

The benchmark reports mean absolute error (MAE) on a 10-mark scale, bias, the share of answers within 0.5 and 1 mark of the human score, rank correlation (Spearman), and how much scores vary between runs.

### Inspect the notes corpus

```bash
python -m app.retrieval.corpus --rebuild              # rebuild the index and print stats
python -m app.retrieval.corpus --search "Article 323A tribunals"
python -m app.retrieval.corpus --sample 3             # show 3 random chunks
```

---

## Project structure

```
app/
  llm.py                      LLM clients (NVIDIA API)
  schemas.py                  Pydantic input, output and LLM response schemas
  evaluator/
    graph.py                  LangGraph pipeline and evaluate_submission()
    state.py                  Shared pipeline state
    question_analysis.py      Directive and coverage-plan analysis
    features.py               Answer feature extraction and verification
    factcheck.py              Claim extraction, retrieval and verdicts
    scoring.py                Rubric scoring, audits, caps and rounding
    feedback.py               Feedback generation and consistency check
  retrieval/
    corpus.py                 PDF cleaning, chunking, de-duplication, BM25 search
data/
  benchmark/                  Golden sets and benchmark results
  cache/                      Fact-check and corpus caches
  corpus/                     Your notes PDFs (not committed)
scripts/                      Benchmarking and debugging scripts
tests/                        Unit tests
benchmark_examiner.py         Benchmark against examiner-marked answers
```
