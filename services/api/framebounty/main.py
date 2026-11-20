"""Authenticated marketplace API; testnet actions are explicitly gated."""
import os
from .networks import chain_enabled
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .auth import bearer, current_wallet, issue_challenge, require_service_auth, revoke_session, sign_in, wallet_address
from .db import session
from .domain import Plan, ReservationIntent as ReserveRequest
from .marketplace import create_job, prepare_confirmation, reserve, search_tasks
from .models import Job, Reservation, Submission, Task, TransactionIntent
from .submission_routes import router as submissions_router
from .agent_routes import router as agents_router
from .funding_routes import router as funding_router
from .chain_routes import router as chain_router
from .chat import router as chat_router
from .payouts import router as payouts_router
from .reputation import router as reputation_router
from .refunds import router as refunds_router
from .circle_wallets import router as circle_router
from .media import MediaUnavailable

app = FastAPI(title="FrameBounty", version="0.1.0", dependencies=[Depends(require_service_auth)],
              docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(submissions_router)
app.include_router(agents_router)
app.include_router(funding_router)
app.include_router(chain_router)
app.include_router(chat_router)
app.include_router(payouts_router)
app.include_router(reputation_router)
app.include_router(refunds_router)
app.include_router(circle_router)
app.add_middleware(CORSMiddleware, allow_origins=[os.getenv("AUTH_ORIGIN", "http://localhost:3000")],
                   allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type", "X-Capture-Token"],
                   expose_headers=["X-Data-Bytes"])


@app.exception_handler(OperationalError)
def database_unavailable(_request, _exc):
    # Never disclose DSNs, SQL statements or credentials in a client-facing error.
    return JSONResponse(status_code=503, content={"detail": "Database unavailable. Start PostgreSQL and apply the documented migrations, then retry."})


@app.exception_handler(MediaUnavailable)
def storage_unavailable(_request, _exc):
    return JSONResponse(status_code=503, content={"detail": "Private media storage is unavailable. Retry the same action; no submission or payment is assumed."})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me/status")
def service_status():
    enabled = (chain_enabled()
               and bool(os.getenv("ARC_RPC_URL")) and bool(os.getenv("ARC_ESCROW_ADDRESS")))
    return {"status": "ok", "mode": os.getenv("APP_MODE", "fixture"), "payments_enabled": enabled,
            "settlement_requires_verified_receipt": True}


@app.post("/plans/validate", response_model=Plan)
def validate_plan(plan: Plan):
    """Validate an untrusted draft; this endpoint cannot publish or spend funds."""
    return plan


class ChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wallet: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nonce: str = Field(min_length=48, max_length=48)
    signature: str = Field(min_length=128, max_length=132)


@app.post("/auth/challenge")
def challenge(body: ChallengeRequest, db: Session = Depends(session)):
    try:
        address = wallet_address(body.wallet)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    item = issue_challenge(db, address)
    return {"nonce": item.id, "message": item.message, "expires_at": item.expires_at}


@app.post("/auth/login")
def login(body: LoginRequest, db: Session = Depends(session)):
    return {"token": sign_in(db, body.nonce, body.signature), "expires_in_seconds": 28800}


@app.post("/auth/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(session)):
    revoke_session(credentials, db)
    return {"signed_out": True}


@app.get("/me/overview")
def overview(wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    fixture = os.getenv("APP_MODE", "fixture") == "fixture"
    owned = (Job.buyer == wallet) & ((Job.fixture == fixture) | (Job.state == "draft"))
    count = lambda condition: db.scalar(select(func.count()).select_from(Job).where(condition))
    reviews = db.scalar(select(func.count()).select_from(Submission).join(Job, Submission.job_id == Job.id).where(
        Job.reviewer == wallet, Job.fixture == fixture, Submission.state.in_(["needs_review", "invalid", "verified", "release_pending"])))
    claimable = select(Task.id).where(Task.job_id == Job.id, Task.state == "open", Task.deadline > datetime.now(UTC),
        Task.claimed < Task.slots, Task.reward_atomic <= Job.deposited_atomic - Job.committed_atomic - Job.paid_atomic - Job.refunded_atomic).exists()
    return {"collections": count(owned), "open_collections": count(owned & (Job.state == "open") & claimable),
            "awaiting_review": reviews, "fixture": fixture}


@app.post("/jobs")
def post_job(plan: Plan, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    item = create_job(db, wallet, plan)
    return {"id": item.id, "state": item.state, "plan_hash": item.plan_hash}


@app.get("/jobs/{job_id}")
def get_job(job_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    item = db.get(Job, job_id)
    if item is None or wallet not in (item.buyer, item.reviewer):
        raise HTTPException(404, "Job not found")
    return {"id": item.id, "state": item.state, "plan": item.plan, "plan_hash": item.plan_hash, "fixture": item.fixture,
            "deposited_atomic": str(item.deposited_atomic), "committed_atomic": str(item.committed_atomic),
            "paid_atomic": str(item.paid_atomic), "refunded_atomic": str(item.refunded_atomic),
            "available_atomic": str(item.deposited_atomic - item.committed_atomic - item.paid_atomic - item.refunded_atomic)}


@app.get("/tasks")
def tasks(equipment: str = "", minutes: int = 20, db: Session = Depends(session)):
    if len(equipment) > 500 or not 1 <= minutes <= 1440:
        raise HTTPException(422, "Invalid equipment or time filter")
    return {"tasks": search_tasks(db, set(equipment.lower().split(",")), minutes)}


@app.post("/tasks/{task_id}/confirmation")
def confirmation(task_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    item = prepare_confirmation(db, wallet, task_id)
    return {"confirmation_id": item.id, "task_id": item.task_id, "version": item.version,
            "reward_atomic": str(item.reward_atomic), "expires_at": item.expires_at,
            "reservation_expires_at": item.reservation_expires_at}


@app.post("/reservations")
def post_reservation(body: ReserveRequest, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    if not body.confirmed:
        raise HTTPException(422, "Explicit task confirmation is required")
    try:
        item = reserve(db, wallet, body.confirmation_id, body.task_id, body.version, int(body.reward_atomic), body.idempotency_key)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Concurrent request changed this reservation; retry the same request") from exc
    return {"id": item.id, "state": item.state, "reward_atomic": str(item.reward_atomic), "expires_at": item.expires_at}


@app.get("/me/reservations")
def my_reservations(wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    items = db.scalars(select(Reservation).where(Reservation.wallet == wallet).order_by(Reservation.id).limit(100)).all()
    return {"reservations": [{"id": r.id, "task_id": r.task_id, "state": r.state, "reward_atomic": str(r.reward_atomic),
        "title": db.get(Job, r.job_id).plan["title"],
        "fixture": db.get(Job, r.job_id).fixture, "media_type": db.get(Job, r.job_id).plan.get("media_type", "video"),
        "expires_at": r.expires_at, "rights_declaration": db.get(Job, r.job_id).plan["rights_declaration"],
        "submission_id": db.scalar(select(Submission.id).where(Submission.reservation_id == r.id))} for r in items]}


@app.get("/me/jobs")
def my_jobs(wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    items = db.scalars(select(Job).where((Job.buyer == wallet) | (Job.reviewer == wallet)).order_by(Job.created_at.desc()).limit(100)).all()
    rows = []
    for item in items:
        available = item.deposited_atomic - item.committed_atomic - item.paid_atomic - item.refunded_atomic
        slots = sum(max(0, task.slots - task.claimed) for task in db.scalars(select(Task).where(
            Task.job_id == item.id, Task.state == "open", Task.deadline > datetime.now(UTC), Task.reward_atomic <= available)))
        pending = db.scalar(select(TransactionIntent.id).where(TransactionIntent.job_id == item.id,
            TransactionIntent.kind.in_(["create_job", "create_protected", "token_approve", "deposit"]),
            TransactionIntent.state.in_(["intent", "signed", "broadcast"])).limit(1))
        status = ("awaiting_funding" if pending else "draft") if item.state == "draft" else (
            "open" if item.state == "open" and slots else "no_available_tasks" if item.state == "open" else item.state)
        if item.state == "open" and item.expires_at and item.expires_at <= datetime.now(UTC): status = "expired"
        rows.append({"id": item.id, "title": item.plan["title"], "state": item.state, "fixture": item.fixture,
            "protection_version": item.protection_version, "expires_at": item.expires_at,
            "publication_status": status, "open_slots": slots, "media_type": item.plan.get("media_type", "video"),
            "plan": item.plan, "plan_hash": item.plan_hash, "available_atomic": str(available),
            "deposited_atomic": str(item.deposited_atomic), "paid_atomic": str(item.paid_atomic)})
    return {"jobs": rows}
