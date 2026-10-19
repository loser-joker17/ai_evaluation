"""What happened during one evaluation, for logs and the /stats endpoint.

Each evaluation gets a small "run record": which models ran, whether a backup model had
to step in, how long each step took, how much the judge's samples disagreed, which
rules capped the marks, and how many feedback lines the filters removed.

The record never holds the question or answer text, so it is safe to log and to keep.
It is attached to the result as result["run_info"] and logged as one JSON line.
"""
from __future__ import annotations

import contextvars
import logging
import os
import threading
import time
from typing import Any

# Change when the scoring rules, prompts or models change, so results and logs can be
# grouped by the evaluator that produced them.
EVALUATOR_VERSION = os.getenv("EVALUATOR_VERSION", "2026.10.19")

_run: contextvars.ContextVar[dict | None] = contextvars.ContextVar("evaluation_run", default=None)
job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_id", default=None)
_lock = threading.Lock()


def start_run() -> dict:
    run = {"job_id": job_id_var.get(), "started": time.time(), "steps": {}, "backups": [],
           "notes": {}}
    _run.set(run)
    return run


def current() -> dict | None:
    return _run.get()


def note(key: str, value: Any) -> None:
    """Set a value on the current run (does nothing outside an evaluation)."""
    run = _run.get()
    if run is not None:
        with _lock:
            run["notes"][key] = value


def add_backup(model: str, reason: str) -> None:
    run = _run.get()
    if run is not None:
        with _lock:
            run["backups"].append({"model": model, "reason": reason})


def step_done(name: str, seconds: float) -> None:
    run = _run.get()
    if run is not None:
        with _lock:
            run["steps"][name] = round(run["steps"].get(name, 0) + seconds, 2)


def model_info() -> dict:
    def pick(role):
        return {"model": os.getenv(f"{role}_MODEL", ""),
                "provider": os.getenv(f"{role}_PROVIDER") or os.getenv("LLM_PROVIDER", "nvidia")}
    return {"fast": pick("FAST"), "light": pick("LIGHT"), "judge": pick("JUDGE"),
            "judge_backup": os.getenv("JUDGE_BACKUP_MODEL") or None,
            "llm_backup": os.getenv("LLM_BACKUP_MODEL") or None}


def summary(run: dict, result: dict | None, payload: dict, status: str,
            error: str | None = None) -> dict:
    """The run record as one flat-ish dict. No question or answer text."""
    result = result or {}
    dims = result.get("dimension_scores") or []
    verifs = result.get("claim_verifications") or []
    labels: dict[str, int] = {}
    for v in verifs:
        labels[v.get("label", "?")] = labels.get(v.get("label", "?"), 0) + 1
    caps = [d.get("dimension") for d in dims if d.get("cap_note")]
    return {
        "event": "evaluation",
        "evaluator_version": EVALUATOR_VERSION,
        "job_id": run.get("job_id"),
        "status": status,                              # success | rejected | failed
        "error": error,
        "seconds": round(time.time() - run["started"], 1),
        "steps_s": run["steps"],
        "models": model_info(),
        "backups_used": run["backups"],
        "subject": payload.get("subject"),
        "max_marks": payload.get("max_marks"),
        "word_limit": payload.get("word_limit"),
        "word_count": result.get("word_count"),
        "total_score": result.get("total_score"),
        "levels": {d.get("dimension"): d.get("final_level") for d in dims},
        "capped_dimensions": caps,
        "incomplete_answer": any("Incomplete answer" in str(d.get("cap_note") or "") for d in dims),
        "fact_check": labels,
        "factual_concerns": len(result.get("factual_concerns") or []),
        "feedback_consistent": result.get("feedback_consistent"),
        **run["notes"],
    }


_log = logging.getLogger("evaluator.runs")


def log_summary(info: dict) -> None:
    """One log line per evaluation. With the API's JSON logging this is one JSON object."""
    level = logging.WARNING if info.get("status") == "failed" or info.get("backups_used") else logging.INFO
    _log.log(level, "evaluation %s in %ss (%s)", info.get("status"), info.get("seconds"),
             info.get("job_id") or "no job id", extra={"data": info})
