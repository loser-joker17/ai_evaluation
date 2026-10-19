"""Log format for the service: one JSON object per line (easy for Render / Railway /
Grafana / any log tool to search), or plain text for local runs (LOG_JSON=false).

What is logged: job ids, timings, models, backup use, marks, levels, caps, errors.
What is never logged: the question or answer text, API keys.
"""
import json
import logging
import time

from app import monitoring


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        job = monitoring.job_id_var.get()
        if job:
            out["job_id"] = job
        data = getattr(record, "data", None)
        if isinstance(data, dict):
            out.update(data)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)[-2000:]
        return json.dumps(out, ensure_ascii=False, default=str)


class _JobIdFilter(logging.Filter):
    def filter(self, record):
        record.job_id = monitoring.job_id_var.get() or "-"
        return True


def setup_logging(level: str = "INFO", json_lines: bool = True) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_JobIdFilter())
    if json_lines:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(job_id)s]: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # The HTTP client libraries log every request at INFO; that is noise here.
    for noisy in ("httpx", "httpcore", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
