"""Bind jobs to their escrow and persist immutable final payout batches."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"


def upgrade():
    op.add_column("jobs", sa.Column("escrow_address", sa.String(42)))
    # Existing funded jobs must keep the original deployed escrow, never silently
    # follow a new global deployment address. Fixture jobs have no chain binding.
    op.execute("UPDATE jobs SET escrow_address = LOWER(t.destination) FROM transaction_intents t WHERE t.job_id = jobs.id AND t.kind = 'create_job'")
    op.create_table("payout_batches",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("reviewer", sa.String(42), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("submission_ids", postgresql.JSONB, nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("job_id", "request_id", name="batch_request_unique"))
    op.create_index("ix_payout_batches_job_id", "payout_batches", ["job_id"])


def downgrade():
    op.drop_table("payout_batches")
    op.drop_column("jobs", "escrow_address")
