"""Internal HTTP service around the evaluator, called by the Spring Boot backend.

Run locally (from the project root):
    uvicorn api.main:app --port 8000

Every endpoint except /health needs the header  X-Internal-Key: <INTERNAL_API_KEY>.
This service is not meant to be reachable from the internet; only the backend calls it.

    GET  /health            liveness + queue size (no key needed)
    POST /jobs              start an evaluation in the background -> 202
    GET  /jobs/{job_id}     poll a job's status and result
    POST /evaluate          run one evaluation and wait for it (manual testing only)
"""
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from api.jobs import JobManager, QueueFullError
from api.models import JobRequest, JobStatus
from app.config import Settings, get_settings
from app.schemas import EvaluationInput

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("evaluator.api")


def _warm_corpus_index() -> None:
    """Build the notes search index at startup instead of during the first evaluation."""
    try:
        from app.retrieval.corpus import search_corpus
        search_corpus("warm up", k=1)
        log.info("notes index ready")
    except Exception:
        log.exception("could not build the notes index; fact-checks will retry on first use")


def create_app(
    evaluate: Callable[[dict], dict] | None = None,
    settings: Settings | None = None,
    warm_index: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    if not settings.internal_api_key:
        raise RuntimeError("INTERNAL_API_KEY is missing. Set it in .env (any long random string).")

    if evaluate is None:
        from app.evaluator.graph import evaluate_submission   # builds the LLM clients
        evaluate = evaluate_submission

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.jobs = JobManager(
            evaluate=evaluate,
            max_workers=settings.max_concurrent_jobs,
            max_queued=settings.max_queued_jobs,
            ttl_s=settings.job_ttl_s,
            callback_url=settings.callback_url,
            internal_key=settings.internal_api_key,
        )
        if warm_index:
            threading.Thread(target=_warm_corpus_index, daemon=True).start()
        yield
        app.state.jobs.shutdown()

    app = FastAPI(title="UPSC Answer Evaluator", version="1.0", lifespan=lifespan)

    def require_key(x_internal_key: str = Header(default="")) -> None:
        if not secrets.compare_digest(x_internal_key.encode(), settings.internal_api_key.encode()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-Internal-Key")

    def jobs() -> JobManager:
        return app.state.jobs

    @app.get("/health")
    def health(manager: JobManager = Depends(jobs)) -> dict:
        return {"status": "ok", **manager.stats()}

    @app.post("/jobs", status_code=status.HTTP_202_ACCEPTED, response_model=JobStatus,
              dependencies=[Depends(require_key)])
    def create_job(req: JobRequest, manager: JobManager = Depends(jobs)):
        try:
            job, created = manager.submit(req.job_id, req.input.model_dump())
        except QueueFullError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                "Too many evaluations waiting. Retry later.",
                                headers={"Retry-After": "60"})
        if not created:
            # Same id sent again (a retried request): return the existing job, don't rerun it.
            return JSONResponse(job.model_dump(mode="json"), status_code=status.HTTP_200_OK)
        return job

    @app.get("/jobs/{job_id}", response_model=JobStatus, dependencies=[Depends(require_key)])
    def get_job(job_id: str, manager: JobManager = Depends(jobs)):
        job = manager.get(job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "Unknown job (never submitted, expired, or the service restarted)")
        return job

    @app.post("/evaluate", dependencies=[Depends(require_key)])
    async def evaluate_now(data: EvaluationInput) -> dict:
        # Blocks for the whole evaluation (minutes). Use /jobs from the backend.
        return await run_in_threadpool(evaluate, data.model_dump())

    return app


app = create_app()
