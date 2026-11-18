"""Deterministic small-batch allocation under an approved funded plan.

Accepted clips, promises and advertised slots all reduce purchase deficits. This
does not cancel existing commitments when another clip fills a category quota.
"""
import hashlib
import os
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import CoverageItem, Plan, deficits
from .marketplace import audit, new_id
from .models import Audit, Job, Reservation, Submission, Task


def locked_owned_fixture(db: Session, wallet: str, job_id: str) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
    if job is None or job.buyer != wallet:
        raise HTTPException(404, "Job not found")
    if os.getenv("APP_MODE", "fixture") != "fixture":
        raise HTTPException(503, "Simulated funding is available only in explicit fixture mode")
    return job


def create_batch(db: Session, job: Job, count: int, tags: list[str]) -> list[str]:
    if count == 0:
        return []
    equipment = ["phone"]
    if "large_towel" in {r["key"] for r in job.plan["requirements"]}:
        equipment += ["towel"] + (["dark_table"] if "dark_surface" in tags else [])
    task = Task(id=new_id(), job_id=job.id, version=job.plan["version"],
        reward_atomic=job.plan["reward_atomic"], slots=count, claimed=0, tags=tags, equipment=equipment,
        minutes=15, deadline=datetime.now(UTC) + timedelta(hours=24), state="open")
    db.add(task)
    return [task.id]


def publish_fixture(db: Session, wallet: str, job_id: str, plan_hash: str) -> list[str]:
    job = locked_owned_fixture(db, wallet, job_id)
    if job.plan_hash != plan_hash:
        raise HTTPException(409, "Plan version changed; review current terms")
    if job.fixture and job.state == "open":
        return list(db.scalars(select(Task.id).where(Task.job_id == job.id)))
    if job.state != "draft":
        raise HTTPException(409, "Only a draft can initialize fixture funding")
    plan = Plan.model_validate(job.plan)
    job.fixture, job.state, job.deposited_atomic = True, "open", plan.budget_atomic
    tags = [r.key for r in plan.requirements]
    ids = create_batch(db, job, min(2, plan.total), tags)
    audit(db, wallet, "buyer", "simulate_funding_and_publish", job.id,
          {"plan_hash": plan_hash, "simulated_atomic": str(plan.budget_atomic), "task_ids": ids})
    db.commit()
    return ids


def next_collection_batch(db: Session, wallet: str, job_id: str, request_id: str) -> dict:
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
    if job is None or job.buyer != wallet:
        raise HTTPException(404, "Job not found")
    enabled = (job.fixture and os.getenv("APP_MODE", "fixture") == "fixture") or (
        not job.fixture and os.getenv("APP_MODE") == "testnet" and os.getenv("ALLOW_CHAIN_TRANSACTIONS") == "true")
    if not enabled or job.state != "open" or job.deposited_atomic <= 0:
        raise HTTPException(409, "Job must have confirmed funding before replanning")
    audit_id = hashlib.sha256(f"batch:{job_id}:{wallet}:{request_id}".encode()).hexdigest()
    old = db.get(Audit, audit_id)
    if old:
        return old.details
    plan = Plan.model_validate(job.plan)
    tasks = db.scalars(select(Task).where(Task.job_id == job.id)).all()
    by_id = {task.id: task for task in tasks}
    accepted = db.scalars(select(Submission).where(Submission.job_id == job.id, Submission.state.in_(["fixture_accepted", "accepted"]))).all()
    pending = db.scalars(select(Reservation).where(Reservation.job_id == job.id,
        Reservation.state.in_(["fixture_reserved", "fixture_submitted", "reserve_pending", "reserved", "submitted"]))).all()
    accepted_items = [CoverageItem(reservation_id=item.reservation_id, tags=item.reviewed_tags) for item in accepted]
    commitments = [CoverageItem(reservation_id=item.id, tags=by_id[item.task_id].tags) for item in pending]
    # Unclaimed published slots are not financial obligations, but another new
    # advertisement would compete with them and could buy redundant examples.
    for task in tasks:
        if task.state == "open" and task.deadline > datetime.now(UTC):
            commitments.extend(CoverageItem(reservation_id=f"open:{task.id}:{slot}", tags=task.tags)
                               for slot in range(task.slots - task.claimed))
    remaining = deficits(plan, accepted_items, commitments)
    available = job.deposited_atomic - job.committed_atomic - job.paid_atomic - job.refunded_atomic
    slots = min(2, remaining["total"], available // plan.reward_atomic)
    tags = sorted(key for key, count in remaining.items() if key != "total" and count > 0)
    ids = create_batch(db, job, slots, tags)
    result = {"task_ids": ids, "deficits_after_existing_work": remaining, "published_slots": slots,
              "fixture": job.fixture, "explanation": "Existing accepted clips, active promises and advertised slots were counted before allocating available " + ("simulated" if job.fixture else "confirmed testnet") + " funds."}
    db.add(Audit(id=audit_id, wallet=wallet, role="buyer", action="fixture_next_batch" if job.fixture else "next_batch", resource_id=job.id, details=result))
    db.commit()
    return result


def next_fixture_batch(db: Session, wallet: str, job_id: str, request_id: str) -> dict:
    job = locked_owned_fixture(db, wallet, job_id)
    if not job.fixture:
        raise HTTPException(409, "This endpoint requires a fixture job")
    return next_collection_batch(db, wallet, job_id, request_id)
