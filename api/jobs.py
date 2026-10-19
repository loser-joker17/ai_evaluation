"""Background evaluation jobs.

An evaluation takes minutes, so the API never runs one inside an HTTP request.
POST /jobs puts it here; a small thread pool runs it; when it finishes the result is
kept in memory for GET /jobs/{id} and, if CALLBACK_URL is set, POSTed to the backend.

Jobs live in memory only. If this service restarts, unfinished jobs are lost: the
backend should treat a job that has been PENDING too long as failed and resubmit it.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import httpx

from api.models import JobStatus

log = logging.getLogger("evaluator.jobs")

CALLBACK_RETRY_DELAYS_S = (2, 5, 15)   # wait before the 2nd, 3rd and 4th attempt


class QueueFullError(Exception):
    pass


class JobManager:
    def __init__(
        self,
        evaluate: Callable[[dict], dict],
        max_workers: int,
        max_queued: int,
        ttl_s: int,
        callback_url: str = "",
        internal_key: str = "",
        http_client: httpx.Client | None = None,
    ):
        self._evaluate = evaluate
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="eval")
        # Callbacks get their own threads, so a slow or down backend never holds up
        # an evaluation worker while it retries.
        self._callback_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="callback")
        self._max_workers = max_workers
        self._max_queued = max_queued
        self._ttl_s = ttl_s
        self._callback_url = callback_url.rstrip("/")
        self._internal_key = internal_key
        self._http = http_client or httpx.Client(timeout=30)
        self._jobs: dict[str, JobStatus] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ public

    def submit(self, job_id: str, payload: dict[str, Any]) -> tuple[JobStatus, bool]:
        """Queue a job. Returns (status, created). Submitting an id that already exists
        returns the existing job instead of running it twice, so the backend can safely
        retry a POST that timed out."""
        with self._lock:
            self._expire_old()
            existing = self._jobs.get(job_id)
            if existing is not None:
                return existing.model_copy(), False
            if self._count("queued") >= self._max_queued:
                raise QueueFullError()
            job = JobStatus(job_id=job_id, status="queued", created_at=time.time())
            self._jobs[job_id] = job
        self._pool.submit(self._run, job_id, payload)
        return job.model_copy(), True

    def get(self, job_id: str) -> JobStatus | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy() if job else None

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "queued": self._count("queued"),
                "running": self._count("running"),
                "workers": self._max_workers,
            }

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._callback_pool.shutdown(wait=False)
        self._http.close()

    # ------------------------------------------------------------ internals

    def _count(self, status: str) -> int:
        return sum(1 for j in self._jobs.values() if j.status == status)

    def _expire_old(self) -> None:
        cutoff = time.time() - self._ttl_s
        for jid in [jid for jid, j in self._jobs.items()
                    if j.finished_at is not None and j.finished_at < cutoff]:
            del self._jobs[jid]

    def _update(self, job_id: str, **changes) -> JobStatus:
        with self._lock:
            job = self._jobs[job_id].model_copy(update=changes)
            self._jobs[job_id] = job
            return job.model_copy()

    def _run(self, job_id: str, payload: dict[str, Any]) -> None:
        self._update(job_id, status="running", started_at=time.time())
        try:
            result = self._evaluate(payload)
            job = self._update(job_id, status="done", result=result, finished_at=time.time())
            log.info("job %s done in %.0fs", job_id, job.finished_at - job.started_at)
        except Exception as exc:  # the job must always end in a final state
            log.exception("job %s failed", job_id)
            job = self._update(job_id, status="failed",
                               error=f"{type(exc).__name__}: {exc}"[:500],
                               finished_at=time.time())
        if self._callback_url:
            self._callback_pool.submit(self._send_callback, job)

    def _send_callback(self, job: JobStatus) -> None:
        url = f"{self._callback_url}/{job.job_id}"
        body = job.model_dump(mode="json")
        headers = {"X-Internal-Key": self._internal_key}
        for attempt in range(len(CALLBACK_RETRY_DELAYS_S) + 1):
            if attempt:
                time.sleep(CALLBACK_RETRY_DELAYS_S[attempt - 1])
            try:
                r = self._http.post(url, json=body, headers=headers)
                if r.status_code < 300:
                    return
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    # The backend rejected it (wrong key, unknown job): retrying won't help.
                    log.error("callback for %s rejected: HTTP %s", job.job_id, r.status_code)
                    return
                log.warning("callback for %s got HTTP %s", job.job_id, r.status_code)
            except httpx.HTTPError as exc:
                log.warning("callback for %s failed: %s", job.job_id, exc)
        log.error("callback for %s gave up; result is still available at GET /jobs/%s",
                  job.job_id, job.job_id)
