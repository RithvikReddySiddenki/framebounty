"""Authorized marketplace services. Fixture commitments are explicitly simulated.

Live requests hold budget while chain reservation reconciliation is pending.
Job-before-task row locking serializes budget changes across different task records.
"""
import hashlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .domain import Plan
from .models import Audit, Confirmation, Job, Reservation, Task


def new_id() -> str:
    return secrets.token_hex(16)


def audit(db: Session, wallet: str, role: str, action: str, resource_id: str, details: dict):
    db.add(Audit(id=new_id(), wallet=wallet, role=role, action=action, resource_id=resource_id, details=details))


def create_job(db: Session, wallet: str, plan: Plan) -> Job:
    payload = plan.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    job = Job(id=new_id(), buyer=wallet, reviewer=wallet, plan=payload, plan_hash=digest, state="draft", fixture=False)
    db.add(job)
    audit(db, wallet, "buyer", "draft_plan", job.id, {"plan_hash": digest})
    db.commit()
    return job


def search_tasks(db: Session, equipment: set[str], minutes: int | None) -> list[dict]:
    now = datetime.now(UTC)
    rows = db.execute(select(Task, Job).join(Job, Task.job_id == Job.id).where(
        Job.state == "open", Task.state == "open", Task.deadline > now,
        Job.fixture == (os.getenv("APP_MODE", "fixture") == "fixture"),
        Task.equipment.contained_by(sorted(equipment)),
        Task.claimed < Task.slots, *([] if minutes is None else [Task.minutes <= minutes]),
        Job.deposited_atomic - Job.committed_atomic - Job.paid_atomic - Job.refunded_atomic >= Task.reward_atomic,
    ).order_by(Task.deadline, Task.id).limit(100)).all()
    # Equipment filtering stays deterministic. Do not infer undeclared tools from prose.
    return [dict(task_id=t.id, job_id=j.id, title=j.plan["title"], version=t.version,
                 media_type=j.plan.get("media_type", "video"), reward_atomic=str(t.reward_atomic), tags=t.tags, equipment=t.equipment,
                 minutes=t.minutes, deadline=t.deadline, fixture=j.fixture,
                 requirements=j.plan["requirements"], min_seconds=j.plan["min_seconds"], max_seconds=j.plan["max_seconds"],
                 rubric_hash=j.plan_hash, rights_declaration=j.plan["rights_declaration"],
                 review_hours=j.plan["review_hours"], reviewer=j.reviewer,
                 explanation=f"Requires {', '.join(t.equipment)}; estimated {t.minutes} minutes" + ("; no time filter requested." if minutes is None else ", within your declared availability."))
            for t, j in rows if set(t.equipment) <= equipment]


def prepare_confirmation(db: Session, wallet: str, task_id: str, confirmation_id: str | None = None) -> Confirmation:
    task = db.get(Task, task_id)
    if task is None or task.state != "open" or task.deadline <= datetime.now(UTC):
        raise HTTPException(409, "Task is no longer available; refresh search")
    job = db.get(Job, task.job_id)
    if job.state != "open" or task.claimed >= task.slots or job.deposited_atomic - job.committed_atomic - job.paid_atomic - job.refunded_atomic < task.reward_atomic:
        raise HTTPException(409, "Task is no longer funded or available")
    item = Confirmation(id=confirmation_id or new_id(), wallet=wallet, task_id=task.id, version=task.version,
                        reward_atomic=task.reward_atomic, expires_at=datetime.now(UTC) + timedelta(minutes=5),
                        # Small clock-skew allowance keeps the advertised window
                        # within the on-chain maximum even if latest block lags.
                        reservation_expires_at=min(task.deadline, datetime.now(UTC).replace(microsecond=0)
                            + timedelta(minutes=2 * task.minutes, seconds=-5 if job.protection_version >= 3 else 0)))
    if confirmation_id:
        db.execute(insert(Confirmation).values(id=item.id, wallet=item.wallet, task_id=item.task_id,
            version=item.version, reward_atomic=item.reward_atomic, expires_at=item.expires_at,
            reservation_expires_at=item.reservation_expires_at).on_conflict_do_nothing(index_elements=["id"]))
        db.commit()
        saved = db.get(Confirmation, item.id)
        if saved.wallet != wallet or saved.task_id != task_id:
            raise HTTPException(409, "Confirmation identity belongs to different terms")
        return saved
    db.add(item)
    db.commit()
    return item


def reserve(db: Session, wallet: str, confirmation_id: str, task_id: str, version: int, reward_atomic: int, idempotency_key: str) -> Reservation:
    # Same confirmation is locked before all other records to serialize repeated requests.
    confirmation = db.scalar(select(Confirmation).where(Confirmation.id == confirmation_id).with_for_update())
    if confirmation is None or confirmation.wallet != wallet:
        raise HTTPException(403, "Confirmation does not belong to this wallet")
    if (confirmation.task_id, confirmation.version, confirmation.reward_atomic) != (task_id, version, reward_atomic):
        raise HTTPException(409, "Displayed terms do not match confirmation")
    old = db.scalar(select(Reservation).where(Reservation.wallet == wallet, Reservation.idempotency_key == idempotency_key))
    if old:
        if old.confirmation_id != confirmation_id:
            raise HTTPException(409, "Idempotency key was used for another confirmation")
        return old
    if db.scalar(select(Reservation.id).where(Reservation.confirmation_id == confirmation_id)):
        raise HTTPException(409, "Confirmation already consumed")
    if confirmation.expires_at <= datetime.now(UTC):
        raise HTTPException(409, "Confirmation expired; review current terms")
    reference = db.get(Task, task_id)
    if reference is None:
        raise HTTPException(404, "Task not found")
    job = db.scalar(select(Job).where(Job.id == reference.job_id).with_for_update().execution_options(populate_existing=True))
    task = db.scalar(select(Task).where(Task.id == task_id).with_for_update().execution_options(populate_existing=True))
    fixture = job.fixture and os.getenv("APP_MODE", "fixture") == "fixture"
    live = not job.fixture and os.getenv("APP_MODE") == "testnet" and os.getenv("ALLOW_CHAIN_TRANSACTIONS") == "true"
    if not (fixture or live):
        raise HTTPException(503, "Reservations are disabled for this mode")
    if task.version != version or task.reward_atomic != reward_atomic or task.state != "open" or task.deadline <= datetime.now(UTC) or task.claimed >= task.slots or job.state != "open":
        raise HTTPException(409, "Task changed or filled; refresh search")
    available = job.deposited_atomic - job.committed_atomic - job.paid_atomic - job.refunded_atomic
    if job.protection_version >= 3 and wallet == job.buyer:
        raise HTTPException(409, "Use a separate contributor account; protected posts cannot self-trade")
    if available < reward_atomic:
        raise HTTPException(409, "Available budget changed; refresh search")
    job.committed_atomic += reward_atomic
    task.claimed += 1
    # A reservation is a short collection window, not the entire listing lifetime.
    # Bound it at creation; pending chain allocation must not extend the deadline.
    expires_at = min(task.deadline, datetime.now(UTC) + timedelta(minutes=2 * task.minutes),
                     datetime.now(UTC) + timedelta(days=7))
    if confirmation.reservation_expires_at is not None:
        expires_at = min(expires_at, confirmation.reservation_expires_at)
    if expires_at <= datetime.now(UTC): raise HTTPException(409, "Displayed reservation deadline expired; confirm current terms")
    reservation = Reservation(id=new_id(), confirmation_id=confirmation_id, task_id=task.id, job_id=job.id,
        wallet=wallet, idempotency_key=idempotency_key, reward_atomic=reward_atomic,
        rubric_hash=job.plan_hash, state="fixture_reserved" if fixture else "reserve_pending", expires_at=expires_at)
    db.add(reservation)
    audit(db, wallet, "contributor", "fixture_reserve" if fixture else "reserve_requested", reservation.id, {"task_id": task.id, "reward_atomic": reward_atomic})
    db.commit()
    return reservation
