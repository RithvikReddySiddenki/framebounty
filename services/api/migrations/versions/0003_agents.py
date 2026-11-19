"""Separate owned buyer/contributor sessions and durable tool decision intents."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"


def upgrade():
    op.create_table("agent_sessions", sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("wallet", sa.String(42), nullable=False), sa.Column("role", sa.String(20), nullable=False),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("profile", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('buyer', 'contributor')", name="agent_role_bounds"))
    op.create_index("ix_agent_sessions_wallet", "agent_sessions", ["wallet"])
    op.create_table("agent_turns", sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False), sa.Column("message", sa.Text, nullable=True),
        sa.Column("tool", sa.String(64), nullable=True), sa.Column("arguments", JSONB, nullable=False),
        sa.Column("state", sa.String(20), nullable=False), sa.Column("result", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", "request_id", name="agent_turn_retry_unique"),
        sa.CheckConstraint("state IN ('proposing', 'prepared', 'completed', 'failed')", name="agent_turn_state_bounds"))
    op.create_index("ix_agent_turns_session_id", "agent_turns", ["session_id"])


def downgrade():
    op.drop_table("agent_turns")
    op.drop_table("agent_sessions")
