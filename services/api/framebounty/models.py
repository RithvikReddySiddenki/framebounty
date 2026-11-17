"""Persistent application view. Amounts are ERC-20 atomic integers, never gas units.

Constraints are defense in depth; chain projections and authorized domain services
must validate transitions. A database funding value alone is not receipt evidence.
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Nonce(Base):
    __tablename__ = "auth_nonces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    wallet: Mapped[str] = mapped_column(String(42), index=True)
    message: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    wallet: Mapped[str] = mapped_column(String(42), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("deposited_atomic >= 0 AND committed_atomic >= 0 AND paid_atomic >= 0 AND refunded_atomic >= 0", name="job_nonnegative"),
        CheckConstraint("committed_atomic + paid_atomic + refunded_atomic <= deposited_atomic", name="job_solvent"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    buyer: Mapped[str] = mapped_column(String(42), index=True)
    reviewer: Mapped[str] = mapped_column(String(42))
    plan: Mapped[dict] = mapped_column(JSONB)
    plan_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), default="draft")
    fixture: Mapped[bool] = mapped_column(Boolean, default=False)
    deposited_atomic: Mapped[int] = mapped_column(BigInteger, default=0)
    committed_atomic: Mapped[int] = mapped_column(BigInteger, default=0)
    paid_atomic: Mapped[int] = mapped_column(BigInteger, default=0)
    refunded_atomic: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (CheckConstraint("slots > 0 AND claimed >= 0 AND claimed <= slots AND reward_atomic > 0", name="task_bounds"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    reward_atomic: Mapped[int] = mapped_column(BigInteger)
    slots: Mapped[int] = mapped_column(Integer)
    claimed: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list] = mapped_column(JSONB)
    equipment: Mapped[list] = mapped_column(JSONB)
    minutes: Mapped[int] = mapped_column(Integer)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(20), default="open")


class Confirmation(Base):
    __tablename__ = "confirmations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    wallet: Mapped[str] = mapped_column(String(42))
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    version: Mapped[int] = mapped_column(Integer)
    reward_atomic: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (UniqueConstraint("wallet", "idempotency_key", name="reservation_retry_unique"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    confirmation_id: Mapped[str] = mapped_column(ForeignKey("confirmations.id"), unique=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    wallet: Mapped[str] = mapped_column(String(42), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    reward_atomic: Mapped[int] = mapped_column(BigInteger)
    rubric_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(24))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    wallet: Mapped[str] = mapped_column(String(42), index=True)
    role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reservation_id: Mapped[str] = mapped_column(ForeignKey("reservations.id"), unique=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    wallet: Mapped[str] = mapped_column(String(42), index=True)
    object_key: Mapped[str] = mapped_column(String(64), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(80))
    rights_declaration: Mapped[str] = mapped_column(Text)
    rubric_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32), default="queued")
    findings: Mapped[dict] = mapped_column(JSONB, default=dict)
    reviewed_tags: Mapped[list] = mapped_column(JSONB, default=list)
    review_reason: Mapped[str | None] = mapped_column(Text)
    review_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VerificationJob(Base):
    __tablename__ = "verification_jobs"
    __table_args__ = (CheckConstraint("attempts >= 0 AND attempts <= 3", name="verification_attempt_bounds"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), unique=True)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(String(300))


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (CheckConstraint("role IN ('buyer', 'contributor')", name="agent_role_bounds"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    wallet: Mapped[str] = mapped_column(String(42), index=True)
    role: Mapped[str] = mapped_column(String(20))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    profile: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentTurn(Base):
    __tablename__ = "agent_turns"
    __table_args__ = (UniqueConstraint("session_id", "request_id", name="agent_turn_retry_unique"),
                      CheckConstraint("state IN ('proposing', 'prepared', 'completed', 'failed')", name="agent_turn_state_bounds"))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("agent_sessions.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(Text)
    tool: Mapped[str | None] = mapped_column(String(64))
    arguments: Mapped[dict] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
