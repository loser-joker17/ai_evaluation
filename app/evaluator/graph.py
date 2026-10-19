import contextvars
import os
import time
import copy
from concurrent.futures import ThreadPoolExecutor

from langgraph.graph import StateGraph, START, END

from app import monitoring
from app.evaluator.factcheck import fact_check
from app.evaluator.scoring import _squash  
from app.schemas import EvaluationInput, EvaluationOutput
from app.evaluator.state import EvaluatorState
from app.evaluator.question_analysis import analyze_question
from app.evaluator.features import extract_features
from app.evaluator.scoring import score_answer, finalize_scores, validate_scores, round_marks,verify_concerns
from app.evaluator.feedback import (
    drop_supported,
    clean_dimension_notes,
    _is_gs4,
    generate_feedback,
    check_feedback_consistency,
)


# ---------------------------------------------------------------- input

def validate_input_node(state: EvaluatorState) -> dict:
    try:
        data = EvaluationInput.model_validate(state)

        return {
            "input_valid": True,
            "input_errors": [],
            "question": data.question,
            "answer": data.answer,
            "subject": data.subject,
            "max_marks": data.max_marks,
            "word_limit": data.word_limit,
        }

    except Exception as exc:
        return {
            "input_valid": False,
            "input_errors": [str(exc)],
        }


def route_after_input(state: EvaluatorState) -> str:
    return "analyze_input" if state.get("input_valid") else "return_error"


def analyze_input_node(state: EvaluatorState) -> dict:
    words = len(state["answer"].split())
    limit = state.get("word_limit")

    if not limit:
        status = "not_specified"
    elif words < 0.6 * limit:
        status = "under_limit"
    elif words > 1.15 * limit:
        status = "over_limit"
    else:
        status = "within_limit"

    return {"word_count": words, "word_limit_status": status}


# ------------------------------------------------------ question analysis

# The same question is often evaluated many times (a test paper, a class), and the
# analysis depends only on the question, so it is computed once per process.
_QA_CACHE: dict = {}
_QA_CACHE_MAX = 256


def analyze_question_node(state: EvaluatorState) -> dict:
    key = (
        state["question"].strip(),
        state["subject"],
        state["max_marks"],
        state.get("word_limit"),
    )

    if key not in _QA_CACHE:
        if len(_QA_CACHE) >= _QA_CACHE_MAX:
            _QA_CACHE.pop(next(iter(_QA_CACHE)))
        _QA_CACHE[key] = analyze_question(
            question=state["question"],
            subject=state["subject"],
            max_marks=state["max_marks"],
            word_limit=state.get("word_limit"),
        )

    return {"question_analysis": copy.deepcopy(_QA_CACHE[key])}


# --------------------------------------------------------------- features

def extract_features_node(state: EvaluatorState) -> dict:
    features = extract_features(
        question=state["question"],
        answer=state["answer"],
        question_analysis=state["question_analysis"],
    )

    return {"answer_features": features}


# ---------------------------------------------------------------- scoring

# Long answers (15/20 marks, case studies) vary more between judge runs: the same
# case study got 7.5, 9.25 and 10.25 out of 20. They are judged JUDGE_SAMPLES times
# (default 3; 1 for short answers) and each dimension takes the median level, with
# that run's justification. The benchmark sets JUDGE_SAMPLES=1 (it repeats runs itself).
def _judge_samples(state) -> int:
    forced = os.getenv("JUDGE_SAMPLES")
    if forced:
        return max(1, int(forced))
    long_answer = state["max_marks"] >= 15 or (state.get("word_limit") or 0) >= 250
    return 3 if long_answer else 1


def _median_result(results: list[dict]) -> dict:
    """One judge result whose dimension levels are the per-dimension medians."""
    if len(results) == 1:
        return results[0]
    base = copy.deepcopy(results[0])
    by_dim: dict[str, list[dict]] = {}
    for r in results:
        for item in (r or {}).get("dimension_scores") or []:
            if isinstance(item, dict) and isinstance(item.get("score"), int):
                by_dim.setdefault(item.get("dimension"), []).append(item)
    merged = []
    for dim, items in by_dim.items():
        levels = sorted(i["score"] for i in items)
        median = levels[len(levels) // 2]   # middle of 3; the higher of 2 (avoid under-marking)
        merged.append(copy.deepcopy(next(i for i in items if i["score"] == median)))
    base["dimension_scores"] = merged
    return base


def _score_with_samples(state, **kwargs) -> dict:
    n = _judge_samples(state)
    if n == 1:
        return score_answer(**kwargs)
    ctx = [contextvars.copy_context() for _ in range(n)]
    with ThreadPoolExecutor(max_workers=n) as pool:
        futures = [pool.submit(c.run, score_answer, **kwargs) for c in ctx]
    results, errors = [], []
    for f in futures:
        try:
            results.append(f.result())
        except Exception as exc:  # one failed sample is fine; all failed is not
            errors.append(exc)
    if not results:
        raise errors[0]
    # How much the judge's runs disagreed, per dimension (max level - min level).
    spread = {}
    for r in results:
        for item in (r or {}).get("dimension_scores") or []:
            if isinstance(item, dict) and isinstance(item.get("score"), int):
                spread.setdefault(item.get("dimension"), []).append(item["score"])
    monitoring.note("judge_samples", {"asked": n, "ok": len(results),
                                      "spread": {d: max(v) - min(v) for d, v in spread.items()}})
    return _median_result(results)


def evaluate_answer_node(state: EvaluatorState) -> dict:
    result = _score_with_samples(
        state,
        question=state["question"],
        answer=state["answer"],
        subject=state["subject"],
        max_marks=state["max_marks"],
        word_limit=state.get("word_limit"),
        word_count=state["word_count"],
        word_limit_status=state["word_limit_status"],
        question_analysis=state["question_analysis"],
        features=state["answer_features"],
    )

    concerns = verify_concerns(result.get("factual_concerns", []), state["answer"])
    confirmed = [v for v in state.get("claim_verifications", []) if v["label"] == "contradicted"]

    # Drop judge concerns that a confirmed error already covers.
    def _covered(c):
        a = _squash(c["claim"])
        return any(a in _squash(v["claim"]) or _squash(v["claim"]) in a for v in confirmed)

    concerns = [c for c in concerns if not _covered(c)]
    # ... and concerns about claims the fact check found supported by an official source.
    concerns = drop_supported(concerns, state.get("claim_verifications", []))

    scores, build_issues = finalize_scores(
        raw_items=(result or {}).get("dimension_scores") or [],
        features=state["answer_features"],
        word_count=state["word_count"],
        word_limit=state.get("word_limit"),
        max_marks=state["max_marks"],
        word_limit_status=state["word_limit_status"],
        answer=state["answer"],
        factual_concerns=concerns,  
        confirmed_errors=confirmed,
        directive=(state["question_analysis"].get("directive", "")
                   if isinstance(state.get("question_analysis"), dict) else ""),
        question=state["question"],
        demands=result.get("demands"),
        demand_check=result.get("demand_check"),
    )

    if build_issues:
        return {
            "dimension_scores": [],
            "scores_valid": False,
            "score_errors": build_issues,
            "total_score": 0.0,
            "raw_total_score": 0.0,
            "score_caps": [],
            "factual_concerns": [],             # <- was missing
        }

    valid, issues, total = validate_scores(
        {"dimension_scores": scores},
        state["max_marks"],
    )
    raw_total = total if total is not None else 0.0

    return {
        "dimension_scores": scores,
        "scores_valid": valid,
        "score_errors": issues,
        "raw_total_score": raw_total,
        "total_score": round_marks(raw_total, state["max_marks"]),
        "score_caps": [s["cap_note"] for s in scores if s.get("cap_note")],
        "factual_concerns": concerns, 
    }

def fact_check_node(state: EvaluatorState) -> dict:
    """Never let a search failure break the evaluation."""
    try:
        verifications, gaps = fact_check(state["answer"], subject=state.get("subject"))
    except Exception as exc:
        return {
            "claim_verifications": [],
            "evidence_gaps": [f"Fact check skipped ({type(exc).__name__})."],
        }
    return {"claim_verifications": verifications, "evidence_gaps": gaps}

# ------------------------------------------------- prepare (runs in parallel)

def prepare_node(state: EvaluatorState) -> dict:
    """Run two independent jobs at the same time:
         A) question analysis, then feature extraction (features need the analysis)
         B) fact check (needs only the answer)
    Total time is max(A, B) instead of A + B. fact_check_node never raises."""

    def chain() -> dict:
        update = analyze_question_node(state)
        update.update(extract_features_node({**state, **update}))
        return update

    def in_own_context(fn, *args):
        # keeps LangSmith tracing attached to the parent run inside worker threads
        return contextvars.copy_context().run(fn, *args)

    with ThreadPoolExecutor(max_workers=2) as pool:
        job_a = pool.submit(in_own_context, chain)
        job_b = pool.submit(in_own_context, fact_check_node, state)
        merged = {}
        merged.update(job_a.result())   # an error here is raised, as before
        merged.update(job_b.result())
    return merged


def route_after_scoring(state: EvaluatorState) -> str:
    return "generate_feedback" if state.get("scores_valid") else "return_error"


# --------------------------------------------------------------- feedback

def generate_feedback_node(state: EvaluatorState) -> dict:
    result = generate_feedback(
        question=state["question"],
        answer=state["answer"],
        question_analysis=state["question_analysis"],
        dimension_scores=state["dimension_scores"],
        total_score=state["total_score"],
        max_marks=state["max_marks"],
        features=state["answer_features"],
        score_caps=state.get("score_caps", []),
        word_count=state["word_count"],
        word_limit_status=state["word_limit_status"],
        factual_concerns=state.get("factual_concerns", []),
        confirmed_errors=[v for v in state.get("claim_verifications", []) if v["label"] == "contradicted"],
        word_limit=state.get("word_limit"),
        subject=state.get("subject"),
        claim_verifications=state.get("claim_verifications", []),
    )

    notes_ctx = dict(
        answer=state["answer"], question=state["question"], word_count=state["word_count"],
        word_limit=state.get("word_limit"), max_marks=state["max_marks"],
        total_score=state["total_score"],
        supported_claims=[v.get("claim", "") for v in state.get("claim_verifications", [])
                          if v.get("label") == "supported"],
        confirmed_claims=[v.get("claim", "") for v in state.get("claim_verifications", [])
                          if v.get("label") == "contradicted"],
        gs4=_is_gs4(state.get("subject"), state["question"]),
        extra_numbers=" ".join(str(v.get("quote") or "") for v in state.get("claim_verifications", [])
                               if v.get("label") == "contradicted"),
    )
    return {
        "dimension_scores": clean_dimension_notes(state["dimension_scores"], **notes_ctx),
        "strengths": result["strengths"],
        "weaknesses": result["weaknesses"],
        "improvement_suggestions": result["improvement_suggestions"],
        "overall_feedback": result["overall_feedback"],
    }


def check_feedback_consistency_node(state: EvaluatorState) -> dict:
    feedback = {
        "strengths": state.get("strengths", []),
        "weaknesses": state.get("weaknesses", []),
        "improvement_suggestions": state.get("improvement_suggestions", []),
        "overall_feedback": state.get("overall_feedback", ""),
    }

    result = check_feedback_consistency(
        dimension_scores=state["dimension_scores"],
        total_score=state["total_score"],
        max_marks=state["max_marks"],
        feedback=feedback,
        features=state["answer_features"],
    )

    return {
        "feedback_consistent": result["is_consistent"],
        "consistency_issues": result["issues"],
    }


# ----------------------------------------------------------------- output

def build_result_node(state: EvaluatorState) -> dict:
    limitations = [
        "Scores are AI-generated estimates, not official UPSC marks.",
        "Only a few named legal claims per answer are checked, against selected official websites. "
        "Unchecked claims may still be inaccurate.",
        "Scores and feedback should be calibrated against human-reviewed answers.",
    ]

    if state.get("feedback_consistent") is False:
        limitations.append(
            "The automated consistency check flagged possible feedback contradictions."
        )

    output = EvaluationOutput(
        status="success",
        question=state["question"],
        subject=state["subject"],
        max_marks=state["max_marks"],
        question_analysis=state["question_analysis"],
        answer_features=state.get("answer_features"),
        dimension_scores=state["dimension_scores"],
        total_score=state["total_score"],
        raw_total_score=state["raw_total_score"],
        word_count=state.get("word_count", 0),
        word_limit_status=state.get("word_limit_status", "not_specified"),
        strengths=state.get("strengths", []),
        weaknesses=state.get("weaknesses", []),
        improvement_suggestions=state.get("improvement_suggestions", []),
        overall_feedback=state.get("overall_feedback", ""),
        feedback_consistent=state.get("feedback_consistent"),
        consistency_issues=state.get("consistency_issues", []),
        factual_concerns=state.get("factual_concerns", []),
        claim_verifications=state.get("claim_verifications", []),
        evidence_gaps=state.get("evidence_gaps", []),
        limitations=limitations,
    )

    return {"final_result": output.model_dump()}


def return_error_node(state: EvaluatorState) -> dict:
    errors = state.get("input_errors", []) + state.get("score_errors", [])

    if not errors:
        errors = ["Evaluation could not be completed."]

    # The input may be exactly what failed validation, so never echo it back unchecked.
    max_marks = state.get("max_marks")
    if not isinstance(max_marks, int) or isinstance(max_marks, bool):
        max_marks = 10

    output = EvaluationOutput(
        status="error",
        question=str(state.get("question", "")),
        subject=str(state.get("subject", "")),
        max_marks=max_marks,
        errors=errors,
        limitations=["No successful evaluation result was produced."],
    )

    return {"final_result": output.model_dump()}


# ------------------------------------------------------------------ graph

def build_evaluator_graph():
    builder = StateGraph(EvaluatorState)

    builder.add_node("validate_input", validate_input_node)
    builder.add_node("analyze_input", analyze_input_node)
    builder.add_node("prepare", prepare_node)
    builder.add_node("evaluate_answer", evaluate_answer_node)
    builder.add_node("generate_feedback", generate_feedback_node)
    builder.add_node("check_feedback_consistency",check_feedback_consistency_node)
    builder.add_node("build_result", build_result_node)
    builder.add_node("return_error", return_error_node)

    builder.add_edge(START, "validate_input")

    builder.add_conditional_edges(
        "validate_input",
        route_after_input,
        {
            "analyze_input": "analyze_input",
            "return_error": "return_error",
        },
    )

    builder.add_edge("analyze_input", "prepare")
    builder.add_edge("prepare", "evaluate_answer")

    builder.add_conditional_edges(
        "evaluate_answer",
        route_after_scoring,
        {
            "generate_feedback": "generate_feedback",
            "return_error": "return_error",
        },
    )

    builder.add_edge("generate_feedback", "check_feedback_consistency")
    builder.add_edge("check_feedback_consistency", "build_result")
    builder.add_edge("build_result", END)
    builder.add_edge("return_error", END)

    return builder.compile()


chatbot = build_evaluator_graph()


def evaluate_submission(data: dict | EvaluationInput) -> dict:
    if isinstance(data, EvaluationInput):
        data = data.model_dump()

    run = monitoring.start_run()
    final, last = None, time.time()
    try:
        # stream (not invoke) so each step's duration can be recorded
        for chunk in chatbot.stream(data, stream_mode="updates"):
            now = time.time()
            for node, update in chunk.items():
                monitoring.step_done(node, now - last)
                if update and "final_result" in update:
                    final = update["final_result"]
            last = now
    except Exception as exc:
        monitoring.log_summary(monitoring.summary(run, None, data, "failed",
                                                  f"{type(exc).__name__}: {exc}"[:300]))
        raise
    status = "success" if (final or {}).get("status") == "success" else "rejected"
    info = monitoring.summary(run, final, data, status)
    monitoring.log_summary(info)
    final = dict(final or {})
    final["run_info"] = info
    return final


def evaluate_submission_stream(data: dict | EvaluationInput):
    """Yield (node_name, update) as each step finishes, so a UI can show progress
    (for example the marks as soon as scoring is done, before the feedback text).
    The last event is ("final", <the same dict evaluate_submission returns>)."""
    if isinstance(data, EvaluationInput):
        data = data.model_dump()

    for chunk in chatbot.stream(data, stream_mode="updates"):
        for node, update in chunk.items():
            if not update:
                continue
            if "final_result" in update:
                yield "final", update["final_result"]
            else:
                yield node, update