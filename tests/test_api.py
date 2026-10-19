"""The HTTP service with a fake evaluator: no model calls, no keys needed."""
import time

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from app.config import Settings

KEY = {"X-Internal-Key": "test-key"}
INPUT = {"question": "Discuss the role of SHGs.", "answer": "SHGs empower women.",
         "max_marks": 10, "word_limit": 150, "subject": "GS Paper II"}


def fake_evaluate(payload):
    if "boom" in payload["answer"]:
        raise RuntimeError("provider down")
    return {"status": "success", "total_score": 4.5,
            "run_info": {"event": "evaluation", "status": "success", "seconds": 1.2,
                         "total_score": 4.5, "max_marks": 10, "backups_used": [],
                         "feedback_consistent": True}}


@pytest.fixture
def client():
    settings = Settings(internal_api_key="test-key", log_json=False, max_concurrent_jobs=1)
    with TestClient(create_app(evaluate=fake_evaluate, settings=settings, warm_index=False)) as c:
        yield c


def wait(client, job_id):
    for _ in range(100):
        r = client.get(f"/jobs/{job_id}", headers=KEY).json()
        if r["status"] in ("done", "failed"):
            return r
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_health_needs_no_key_and_shows_version(client):
    r = client.get("/health").json()
    assert r["status"] == "ok" and r["evaluator_version"]


def test_key_required(client):
    assert client.post("/jobs", json={"job_id": "a1", "input": INPUT}).status_code == 401
    assert client.get("/stats").status_code == 401


def test_job_runs_and_stats_record_it(client):
    assert client.post("/jobs", json={"job_id": "a1", "input": INPUT}, headers=KEY).status_code == 202
    assert wait(client, "a1")["result"]["total_score"] == 4.5
    # same id again: returns the existing job, does not rerun
    assert client.post("/jobs", json={"job_id": "a1", "input": INPUT}, headers=KEY).status_code == 200
    client.post("/jobs", json={"job_id": "b2", "input": {**INPUT, "answer": "boom"}}, headers=KEY)
    assert wait(client, "b2")["status"] == "failed"
    s = client.get("/stats", headers=KEY).json()
    assert s["totals"]["done"] == 1 and s["totals"]["failed"] == 1
    assert s["recent"]["count"] == 2 and s["recent"]["failed_share"] == 0.5
    assert all("answer" not in r for r in s["runs"])


def test_sync_evaluate_disabled_by_default(client):
    assert client.post("/evaluate", json=INPUT, headers=KEY).status_code == 404


def test_input_limits(client):
    long_answer = {**INPUT, "answer": "word " * 4000}
    assert client.post("/jobs", json={"job_id": "c3", "input": long_answer}, headers=KEY).status_code == 422


def test_run_info_and_json_log_have_no_answer_text(monkeypatch, caplog):
    import json
    import logging
    from api.logging_setup import JsonFormatter
    from app import monitoring
    from app.evaluator import graph

    class FakeGraph:
        def stream(self, data, stream_mode):
            monitoring.add_backup("unorouter/gpt-oss-20b:free", "OpenAITimeoutError")
            monitoring.note("judge_samples", {"asked": 3, "ok": 3, "spread": {"relevance": 1}})
            yield {"prepare": {"question_analysis": {}}}
            yield {"build_result": {"final_result": {
                "status": "success", "total_score": 4.5, "word_count": 3,
                "dimension_scores": [{"dimension": "relevance", "final_level": 3,
                                      "cap_note": "Incomplete answer: 3 words."}],
                "claim_verifications": [{"label": "supported"}], "feedback_consistent": True}}}

    monkeypatch.setattr(graph, "chatbot", FakeGraph())
    with caplog.at_level(logging.INFO, logger="evaluator.runs"):
        out = graph.evaluate_submission(INPUT)
    info = out["run_info"]
    assert info["status"] == "success" and info["incomplete_answer"] is True
    assert info["backups_used"][0]["reason"] == "OpenAITimeoutError"
    assert info["judge_samples"]["spread"] == {"relevance": 1}
    assert set(info["steps_s"]) == {"prepare", "build_result"}
    line = JsonFormatter().format(caplog.records[-1])
    assert json.loads(line)["total_score"] == 4.5
    assert INPUT["answer"] not in line and INPUT["question"] not in line
