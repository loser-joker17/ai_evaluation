"""Settings for the HTTP service (api/), read from environment variables or .env.

The evaluator itself (models, providers, keys) still reads its own variables in
app/llm.py; this file only holds what the service needs.

    INTERNAL_API_KEY       required. Shared secret with the backend (X-Internal-Key header).
                           Any long random string, e.g. python -c "import secrets; print(secrets.token_urlsafe(32))"
    CALLBACK_URL           optional. Where finished jobs are POSTed: {CALLBACK_URL}/{job_id}
    MAX_CONCURRENT_JOBS    evaluations running at the same time (default 2). Each long answer
                           already makes 3 parallel judge calls, so keep this small on free tiers.
    MAX_QUEUED_JOBS        waiting jobs before POST /jobs answers 503 (default 20)
    JOB_TTL_S              how long a finished job stays readable (default 3600 s)
    ENABLE_SYNC_EVALUATE   true to allow POST /evaluate (blocks for minutes; default false)
    LOG_LEVEL              INFO (default), WARNING, DEBUG
    LOG_JSON               true (default): one JSON object per log line, for log tools
    RECENT_RUNS            how many run summaries GET /stats keeps (default 200)
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    internal_api_key: str = ""
    callback_url: str = ""
    max_concurrent_jobs: int = 2
    max_queued_jobs: int = 20
    job_ttl_s: int = 3600
    enable_sync_evaluate: bool = False
    log_level: str = "INFO"
    log_json: bool = True
    recent_runs: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
