"""Deterministic policy over untrusted model observations. Never sends payouts.

Legacy jobs require buyer release; protected jobs attest then settle after one hour. A definite mandatory failure at reported
confidence >=80 rejects; insufficient evidence/provider failure retries (bounded).
The score is a model estimate, not a calibrated probability of correctness.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .marketplace import audit
from .models import Job, Reservation, Submission, Task, VerificationJob

THRESHOLD = 80


def automatic(job: Job) -> bool:
    return job.plan.get("verification_policy", "ai") == "ai"


def evaluate(db: Session, submission_id: str) -> bool:
    reference = db.get(Submission, submission_id)
    if reference is None: return False
    job = db.scalar(select(Job).where(Job.id == reference.job_id).with_for_update().execution_options(populate_existing=True))
    if not automatic(job):
        db.rollback(); return False
    reservation = db.scalar(select(Reservation).where(Reservation.id == reference.reservation_id).with_for_update().execution_options(populate_existing=True))
    item = db.scalar(select(Submission).where(Submission.id == submission_id).with_for_update().execution_options(populate_existing=True))
    if item.state not in {"needs_review", "invalid"} or reservation.state not in {"fixture_submitted", "submitted"}:
        db.rollback(); return False
    work = db.scalar(select(VerificationJob).where(VerificationJob.submission_id == item.id).with_for_update())
    if work is None or work.state not in {"done", "failed"}:
        db.rollback(); return False
    task = db.get(Task, reservation.task_id)
    checks = item.findings.get("assessment") or {}
    mandatory = {"task_completion", "visibility", *task.tags}
    failed = [(key, checks[key]) for key in sorted(mandatory) if key in checks and checks[key].get("result") == "fail"
              and type(checks[key].get("confidence")) is int and checks[key]["confidence"] >= THRESHOLD]
    invalid = item.state == "invalid"
    passed = bool(item.findings.get("decoded")) and all(
        checks.get(key, {}).get("result") == "pass" and type(checks[key].get("confidence")) is int
        and checks[key]["confidence"] >= THRESHOLD for key in mandatory)
    if invalid or failed:
        decision = "reject"
        reason = item.findings.get("processing_error", "Invalid media") if invalid else "; ".join(
            f"{key}: {check['explanation']} (model-reported confidence {check['confidence']}%)" for key, check in failed)
        item.state, item.review_reason = "verification_rejected", reason[:1000]
        if job.fixture:
            # Fixture release is simulated, atomic and fenced by reservation state.
            job.committed_atomic -= reservation.reward_atomic
            task.claimed -= 1
            reservation.state = "fixture_rejected"
        item.reviewed_tags = []
    elif passed:
        decision, reason = "pass", ("Required checks passed; awaiting on-chain verification and its one-hour payment window."
            if job.protection_version >= 3 else "Required checks passed automated verification; awaiting buyer funds release.")
        item.state, item.review_reason = "verified", reason
        item.reviewed_tags = sorted(key for key in {r["key"] for r in job.plan["requirements"]}
            if checks.get(key, {}).get("result") == "pass" and checks[key].get("confidence", 0) >= THRESHOLD)
    else:
        decision, reason = "retry", item.findings.get("provider_error") or "Evidence is uncertain or below the required confidence; payment is blocked."
        if work.attempts < 3 and item.review_deadline > datetime.now(UTC) + timedelta(seconds=10):
            item.state, work.state = "queued", "queued"
            work.lease_until = datetime.now(UTC) + timedelta(seconds=2 ** work.attempts)
        else:
            item.state = "verification_pending"
            if job.protection_version >= 3:
                work.available_at = datetime.now(UTC) + timedelta(minutes=5)
                reason += " Pending automatic retry in five minutes; reserved funds stay protected."
            else:
                reason += " Automatic retries are exhausted; the obligation will release at its deadline, without payment."
    item.findings = {**item.findings, "verification": {"decision": decision, "threshold": THRESHOLD,
        "score_notice": "Model-reported certainty is not a calibrated probability.", "reason": reason,
        "attempts": work.attempts}}
    audit(db, job.buyer, "verification", "automatic_" + decision, item.id, {"threshold": THRESHOLD, "reason": reason[:1000]})
    db.commit()
    return True
