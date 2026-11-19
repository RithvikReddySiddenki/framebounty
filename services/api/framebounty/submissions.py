"""Private upload and human review services; fixture accounting stays explicit.

Upload bytes are staged before locking budget rows. Finalization rechecks owner,
reservation state and expiry atomically. Accepted fixture work is never called paid.
"""
import os
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .marketplace import audit, new_id
from .media import LocalStorage
from .models import Job, Reservation, Submission, Task, VerificationJob


def owned_reservation(db: Session, reservation_id: str, wallet: str) -> Reservation:
    item = db.get(Reservation, reservation_id)
    if item is None or item.wallet != wallet:
        raise HTTPException(404, "Reservation not found")
    return item


def finalize_upload(db: Session, wallet: str, reservation_id: str, key: str, digest: str, size: int, mime: str, model_ack: bool = False) -> Submission:
    reference = owned_reservation(db, reservation_id, wallet)
    job = db.scalar(select(Job).where(Job.id == reference.job_id).with_for_update().execution_options(populate_existing=True))
    reservation = db.scalar(select(Reservation).where(Reservation.id == reservation_id).with_for_update().execution_options(populate_existing=True))
    old = db.scalar(select(Submission).where(Submission.reservation_id == reservation_id))
    if old:
        if old.sha256 != digest:
            raise HTTPException(409, "Different media was already submitted for this reservation")
        return old
    fixture = job.fixture and os.getenv("APP_MODE", "fixture") == "fixture"
    live = not job.fixture and os.getenv("APP_MODE") == "testnet" and os.getenv("ALLOW_CHAIN_TRANSACTIONS") == "true"
    if not (fixture or live):
        raise HTTPException(503, "Uploads are disabled for this mode")
    if reservation.state != ("fixture_reserved" if fixture else "reserved") or reservation.expires_at <= datetime.now(UTC):
        raise HTTPException(409, "Reservation is expired or no longer accepts uploads")
    item = Submission(id=new_id(), reservation_id=reservation.id, job_id=job.id, wallet=wallet, fixture=fixture,
        object_key=key, sha256=digest, size_bytes=size, content_type=mime,
        rights_declaration=job.plan["rights_declaration"], rubric_hash=reservation.rubric_hash,
        state="queued" if fixture else "chain_pending", findings={"model_consent": model_ack}, reviewed_tags=[],
        review_deadline=datetime.now(UTC) + timedelta(hours=job.plan["review_hours"]))
    db.add(item)
    db.flush()  # The durable job FK is written in the same transaction as submission.
    if fixture:
        db.add(VerificationJob(id=new_id(), submission_id=item.id, state="queued", attempts=0))
        reservation.state = "fixture_submitted"
    audit(db, wallet, "contributor", "fixture_submit" if fixture else "upload_awaiting_chain", item.id, {"reservation_id": reservation.id, "sha256": digest})
    db.commit()
    return item


def private_submission(db: Session, submission_id: str, wallet: str) -> Submission:
    item = db.get(Submission, submission_id)
    if item is None:
        raise HTTPException(404, "Submission not found")
    job = db.get(Job, item.job_id)
    if wallet not in (item.wallet, job.buyer, job.reviewer):
        raise HTTPException(404, "Submission not found")
    return item


def submission_view(item: Submission, include_private_pairs: bool = False) -> dict:
    # Keys are private storage internals, never public download URLs.
    pairs = {"exact_duplicate_candidates", "perceptual_duplicate_candidates"}
    findings = {key: value for key, value in item.findings.items() if key != "frames" and (include_private_pairs or key not in pairs)}
    findings["possible_duplicate_flagged"] = any(item.findings.get(key) for key in pairs)
    findings["frames"] = [{k: v for k, v in frame.items() if k != "key"} for frame in item.findings.get("frames", [])]
    return {"id": item.id, "media_type": "image" if (item.content_type or "").startswith("image/") else "video", "reservation_id": item.reservation_id, "job_id": item.job_id,
        "state": item.state, "findings": findings, "reviewed_tags": item.reviewed_tags,
        "review_reason": item.review_reason, "review_deadline": item.review_deadline,
        "rights_declaration": item.rights_declaration, "rubric_hash": item.rubric_hash,
        "fixture": item.fixture, "payment_confirmed": not item.fixture and item.state == "accepted"}


def review(db: Session, wallet: str, submission_id: str, decision: str, task_completed: bool,
           watched_full_video: bool, tags: list[str], reason: str) -> Submission:
    reference = private_submission(db, submission_id, wallet)
    job = db.scalar(select(Job).where(Job.id == reference.job_id).with_for_update().execution_options(populate_existing=True))
    if wallet != job.reviewer:
        raise HTTPException(403, "Only the job's designated reviewer can decide quality")
    if job.plan.get("verification_policy", "ai") == "ai":
        raise HTTPException(409, "Verification is automatic. Release funds only after the submission is AI-verified.")
    reservation = db.scalar(select(Reservation).where(Reservation.id == reference.reservation_id).with_for_update().execution_options(populate_existing=True))
    item = db.scalar(select(Submission).where(Submission.id == submission_id).with_for_update().execution_options(populate_existing=True))
    allowed_tags = {r["key"] for r in job.plan["requirements"]}
    normalized_tags = sorted(set(tags))
    if not set(tags) <= allowed_tags or len(tags) != len(set(tags)):
        raise HTTPException(422, "Review tags must match this immutable plan")
    if decision not in ("accept", "reject") or not reason.strip():
        raise HTTPException(422, "A decision and reason are required")
    target = ("fixture_accepted" if decision == "accept" else "rejected") if job.fixture else ("accept_pending" if decision == "accept" else "reject_pending")
    if decision == "accept" and (not task_completed or not watched_full_video):
        raise HTTPException(422, "Acceptance requires explicit full-video/task-completion review")
    replay_states = {target} | ({"accepted" if decision == "accept" else "rejected"} if not job.fixture else set())
    if item.state in replay_states and item.review_reason == reason and item.reviewed_tags == normalized_tags:
        return item
    if item.state not in ("needs_review", "invalid") or reservation.state != ("fixture_submitted" if job.fixture else "submitted"):
        raise HTTPException(409, "Submission is not awaiting review")
    if item.review_deadline <= datetime.now(UTC):
        raise HTTPException(409, "Review window expired; use the timeout release path")
    fixture = job.fixture and os.getenv("APP_MODE", "fixture") == "fixture"
    live = not job.fixture and os.getenv("APP_MODE") == "testnet" and os.getenv("ALLOW_CHAIN_TRANSACTIONS") == "true"
    if not (fixture or live):
        raise HTTPException(503, "Review is disabled for this mode")
    if decision == "accept" and (not task_completed or not watched_full_video or not item.findings.get("decoded") or item.state == "invalid"):
        raise HTTPException(422, "Acceptance requires decoded media and explicit full-media/task-completion review")
    task = db.scalar(select(Task).where(Task.id == reservation.task_id).with_for_update())
    if decision == "accept" and not set(task.tags) <= set(tags):
        raise HTTPException(422, "Accepted work must satisfy this reserved task's required categories")
    if live:
        item.state, item.review_reason, item.reviewed_tags = target, reason, normalized_tags
        audit(db, wallet, "reviewer", "human_" + decision + "_awaiting_chain", item.id,
              {"task_completed": task_completed, "watched_full_video": watched_full_video, "tags": normalized_tags, "reason": reason})
        db.commit()
        return item
    job.committed_atomic -= reservation.reward_atomic
    if decision == "accept":
        # Simulation only. This ledger can never recognize a live chain payment.
        job.paid_atomic += reservation.reward_atomic
        reservation.state = "fixture_accepted"
    else:
        reservation.state = "fixture_rejected"
        task.claimed -= 1
    item.state, item.review_reason, item.reviewed_tags = target, reason, normalized_tags
    audit(db, wallet, "reviewer", "fixture_" + decision, item.id,
          {"task_completed": task_completed, "watched_full_video": watched_full_video, "tags": normalized_tags, "reason": reason})
    db.commit()
    return item


def coverage(db: Session, job: Job) -> dict:
    accepted = db.scalars(select(Submission).where(Submission.job_id == job.id, Submission.state.in_(["fixture_accepted", "accepted"]))).all()
    pending = db.scalars(select(Reservation).where(Reservation.job_id == job.id,
        Reservation.state.in_(["fixture_reserved", "fixture_submitted", "reserve_pending", "reserved", "submitted"]))).all()
    return {"accepted_total": len(accepted), "pending_total": len(pending),
        "accepted_categories": {r["key"]: sum(r["key"] in s.reviewed_tags for s in accepted) for r in job.plan["requirements"]},
        "fixture": job.fixture}


def release_expired(db: Session, reservation_id: str, wallet: str) -> Reservation:
    reference = db.get(Reservation, reservation_id)
    if reference is None:
        raise HTTPException(404, "Reservation not found")
    job = db.scalar(select(Job).where(Job.id == reference.job_id).with_for_update().execution_options(populate_existing=True))
    if wallet not in (reference.wallet, job.buyer, job.reviewer):
        raise HTTPException(404, "Reservation not found")
    item = db.scalar(select(Reservation).where(Reservation.id == reservation_id).with_for_update().execution_options(populate_existing=True))
    if item.state in ("fixture_expired", "fixture_timed_out"):
        return item
    if not job.fixture or os.getenv("APP_MODE", "fixture") != "fixture":
        raise HTTPException(503, "Live expiry reconciliation is not connected")
    submission = db.scalar(select(Submission).where(Submission.reservation_id == item.id).with_for_update())
    now = datetime.now(UTC)
    if item.state == "fixture_reserved" and item.expires_at <= now:
        item.state = "fixture_expired"
    elif item.state == "fixture_submitted" and submission and submission.review_deadline <= now:
        item.state, submission.state = "fixture_timed_out", "timed_out"
    else:
        raise HTTPException(409, "A valid reservation or review obligation cannot be released")
    task = db.scalar(select(Task).where(Task.id == item.task_id).with_for_update())
    task.claimed -= 1
    job.committed_atomic -= item.reward_atomic
    audit(db, wallet, "contributor" if wallet == item.wallet else "buyer", item.state, item.id, {})
    db.commit()
    return item
