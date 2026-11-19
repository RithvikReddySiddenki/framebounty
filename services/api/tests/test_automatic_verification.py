"""Real PostgreSQL/Pillow and deterministic policy over synthetic observations."""
from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from framebounty.automatic_verification import evaluate
from framebounty.models import Job, Submission, Task, VerificationJob
from framebounty.worker import run_once
from test_image_posts import image_plan, image_bytes
from test_postgres import pg
from test_submission_flow import flow


def uploaded_ai(client, buyer, actor, key="auto-reserve-01"):
    job = client.post("/jobs", headers=buyer, json={**image_plan(), "verification_policy": "ai"}).json()
    assert client.post(f"/jobs/{job['id']}/fixture-publish", headers=buyer,
        json={"plan_hash": job["plan_hash"], "confirmed": True}).status_code == 200
    task = next(t for t in client.get("/tasks?equipment=phone", headers=actor).json()["tasks"] if t["job_id"] == job["id"])
    confirmation = client.post(f"/tasks/{task['task_id']}/confirmation", headers=actor).json()
    reserved = client.post("/reservations", headers=actor, json={"confirmation_id": confirmation["confirmation_id"],
        "task_id": task["task_id"], "version": task["version"], "reward_atomic": task["reward_atomic"],
        "confirmed": True, "idempotency_key": key})
    assert reserved.status_code == 200, reserved.text
    uploaded = client.post(f"/reservations/{reserved.json()['id']}/image?rights_ack=true&model_ack=true",
        headers={**actor, "Content-Type": "image/png"}, content=image_bytes())
    assert uploaded.status_code == 200, uploaded.text
    return job["id"], uploaded.json()["id"]


def test_verified_image_needs_only_final_buyer_funds_release(pg, flow, monkeypatch):
    client, buyer, actor, _, _, _ = flow
    monkeypatch.setenv("FIXTURE_VERIFICATION_RESULT", "pass")
    job, sid = uploaded_ai(client, buyer, actor)
    assert run_once(pg)
    item = client.get(f"/submissions/{sid}", headers=actor).json()
    assert item["state"] == "verified" and not item["payment_confirmed"]
    with Session(pg) as db:
        assert db.get(Job, job).paid_atomic == 0 and db.get(Job, job).committed_atomic == 1_000_000
    body = {"confirmed": True, "request_id": "final-release-request"}
    assert client.post(f"/jobs/{job}/release-funds", headers=actor, json=body).status_code == 404
    assert client.post(f"/jobs/{job}/release-funds", headers=buyer, json={**body, "confirmed": False}).status_code == 422
    result = client.post(f"/jobs/{job}/release-funds", headers=buyer, json=body)
    assert result.status_code == 200 and result.json()["confirmed"], result.text
    assert client.post(f"/jobs/{job}/release-funds", headers=buyer, json=body).json() == result.json()
    with Session(pg) as db:
        assert db.get(Job, job).paid_atomic == 1_000_000 and db.get(Job, job).committed_atomic == 0
    assert client.get(f"/submissions/{sid}", headers=actor).json()["state"] == "fixture_accepted"


@pytest.mark.parametrize("confidence,rejected", [(79, False), (80, True), (100, True)])
def test_rejection_threshold_and_contributor_visible_reason(pg, flow, monkeypatch, confidence, rejected):
    client, buyer, actor, _, _, _ = flow
    monkeypatch.setenv("FIXTURE_VERIFICATION_RESULT", "uncertain")
    job, sid = uploaded_ai(client, buyer, actor)
    assert run_once(pg)  # Actually decode the PNG; only model observations are synthetic.
    with Session(pg) as db:
        item = db.get(Submission, sid)
        checks = {key: {**value, "result": "pass", "confidence": 95} for key, value in item.findings["assessment"].items()}
        checks["cat_climbing_tree"] = {"result": "fail", "confidence": confidence, "explanation": "No cat or tree is visible", "timestamps_ms": [0]}
        item.state, item.findings = "needs_review", {**item.findings, "assessment": checks}
        work = db.scalar(select(VerificationJob).where(VerificationJob.submission_id == sid))
        work.state = "done"; db.commit()
        assert evaluate(db, sid)
    item = client.get(f"/submissions/{sid}", headers=actor).json()
    assert item["findings"]["verification"]["decision"] == ("reject" if rejected else "retry")
    assert item["state"] == ("verification_rejected" if rejected else "queued")
    if rejected: assert "No cat or tree" in item["review_reason"]
    assert client.post(f"/jobs/{job}/release-funds", headers=buyer,
        json={"confirmed": True, "request_id": "cannot-release-failed"}).status_code == 409
    with Session(pg) as db:
        ledger = db.get(Job, job)
        assert ledger.paid_atomic == 0
        assert ledger.committed_atomic == (0 if rejected else 1_000_000)
        if rejected: assert db.scalar(select(Task).where(Task.job_id == job)).claimed == 0


def test_uncertain_results_retry_boundedly_without_manual_acceptance(pg, flow, monkeypatch):
    client, buyer, actor, _, _, _ = flow
    monkeypatch.setenv("FIXTURE_VERIFICATION_RESULT", "uncertain")
    job, sid = uploaded_ai(client, buyer, actor)
    for _ in range(3):
        with Session(pg) as db:
            work = db.scalar(select(VerificationJob).where(VerificationJob.submission_id == sid))
            work.lease_until = datetime.now(UTC) - timedelta(seconds=1); db.commit()
        assert run_once(pg)
    item = client.get(f"/submissions/{sid}", headers=actor).json()
    assert item["state"] == "verification_pending" and not item["payment_confirmed"]
    assert item["findings"]["verification"]["decision"] == "retry"
    assert client.post(f"/submissions/{sid}/review", headers=buyer, json={"decision": "accept", "task_completed": True,
        "watched_full_video": True, "tags": ["cat_climbing_tree"], "reason": "Try to bypass automatic checks"}).status_code == 409
