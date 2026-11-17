"""Private uploads and durable leased verification work."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table("submissions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("reservation_id", sa.String(64), sa.ForeignKey("reservations.id"), nullable=False, unique=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("wallet", sa.String(42), nullable=False),
        sa.Column("object_key", sa.String(64), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("rights_declaration", sa.Text, nullable=False),
        sa.Column("rubric_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("findings", JSONB, nullable=False),
        sa.Column("reviewed_tags", JSONB, nullable=False),
        sa.Column("review_reason", sa.Text, nullable=True),
        sa.Column("review_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    for column in ["job_id", "wallet", "sha256"]:
        op.create_index(f"ix_submissions_{column}", "submissions", [column])
    op.create_table("verification_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("submission_id", sa.String(64), sa.ForeignKey("submissions.id"), nullable=False, unique=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(64), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 3", name="verification_attempt_bounds"))


def downgrade():
    op.drop_table("verification_jobs")
    op.drop_table("submissions")
