from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas import EvaluationInput


class JobRequest(BaseModel):
    # Chosen by the backend (for example the submission's UUID), so the same id links
    # the submission row in Postgres to this job and to the callback.
    job_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    input: EvaluationInput


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    # The evaluator's full output (same shape as EvaluationOutput) when status is "done".
    # Note: result["status"] can itself be "error" if the evaluator rejected the answer.
    result: dict[str, Any] | None = None
    # Short technical message when status is "failed" (LLM timeout, provider error...).
    error: str | None = None
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
