"""Initial wallet and marketplace application view.

Schema is explicitly frozen here: later model edits must not change old migrations.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None


def upgrade():
    op.create_table("auth_nonces", sa.Column("id", sa.String(64), primary_key=True), sa.Column("wallet", sa.String(42), nullable=False), sa.Column("message", sa.Text, nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("used", sa.Boolean, nullable=False))
    op.create_index("ix_auth_nonces_wallet", "auth_nonces", ["wallet"])
    op.create_table("auth_sessions", sa.Column("token_hash", sa.String(64), primary_key=True), sa.Column("wallet", sa.String(42), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_auth_sessions_wallet", "auth_sessions", ["wallet"])
    op.create_table("jobs", sa.Column("id", sa.String(64), primary_key=True), sa.Column("buyer", sa.String(42), nullable=False), sa.Column("reviewer", sa.String(42), nullable=False), sa.Column("plan", JSONB, nullable=False), sa.Column("plan_hash", sa.String(64), nullable=False), sa.Column("state", sa.String(20), nullable=False), sa.Column("fixture", sa.Boolean, nullable=False), *[sa.Column(n, sa.BigInteger, nullable=False) for n in ["deposited_atomic", "committed_atomic", "paid_atomic", "refunded_atomic"]], sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.CheckConstraint("deposited_atomic >= 0 AND committed_atomic >= 0 AND paid_atomic >= 0 AND refunded_atomic >= 0", name="job_nonnegative"), sa.CheckConstraint("committed_atomic + paid_atomic + refunded_atomic <= deposited_atomic", name="job_solvent"))
    op.create_index("ix_jobs_buyer", "jobs", ["buyer"])
    op.create_table("tasks", sa.Column("id", sa.String(64), primary_key=True), sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=False), sa.Column("version", sa.Integer, nullable=False), sa.Column("reward_atomic", sa.BigInteger, nullable=False), sa.Column("slots", sa.Integer, nullable=False), sa.Column("claimed", sa.Integer, nullable=False), sa.Column("tags", JSONB, nullable=False), sa.Column("equipment", JSONB, nullable=False), sa.Column("minutes", sa.Integer, nullable=False), sa.Column("deadline", sa.DateTime(timezone=True), nullable=False), sa.Column("state", sa.String(20), nullable=False), sa.CheckConstraint("slots > 0 AND claimed >= 0 AND claimed <= slots AND reward_atomic > 0", name="task_bounds"))
    op.create_index("ix_tasks_job_id", "tasks", ["job_id"])
    op.create_table("confirmations", sa.Column("id", sa.String(64), primary_key=True), sa.Column("wallet", sa.String(42), nullable=False), sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False), sa.Column("version", sa.Integer, nullable=False), sa.Column("reward_atomic", sa.BigInteger, nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("reservations", sa.Column("id", sa.String(64), primary_key=True), sa.Column("confirmation_id", sa.String(64), sa.ForeignKey("confirmations.id"), nullable=False, unique=True), sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False), sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=False), sa.Column("wallet", sa.String(42), nullable=False), sa.Column("idempotency_key", sa.String(64), nullable=False), sa.Column("reward_atomic", sa.BigInteger, nullable=False), sa.Column("rubric_hash", sa.String(64), nullable=False), sa.Column("state", sa.String(24), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("wallet", "idempotency_key", name="reservation_retry_unique"))
    for column in ["task_id", "job_id", "wallet"]:
        op.create_index(f"ix_reservations_{column}", "reservations", [column])
    op.create_table("audit_events", sa.Column("id", sa.String(64), primary_key=True), sa.Column("wallet", sa.String(42), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("action", sa.String(80), nullable=False), sa.Column("resource_id", sa.String(64), nullable=False), sa.Column("details", JSONB, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_audit_events_wallet", "audit_events", ["wallet"])


def downgrade():
    for name in ["audit_events", "reservations", "confirmations", "tasks", "jobs", "auth_sessions", "auth_nonces"]:
        op.drop_table(name)
