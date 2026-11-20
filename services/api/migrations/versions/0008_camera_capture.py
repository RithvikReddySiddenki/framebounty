"""Require a short-lived reservation-bound grant for browser video capture."""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"


def upgrade():
    op.create_table(
        "capture_sessions",
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        sa.Column("reservation_id", sa.String(length=64), sa.ForeignKey("reservations.id"), nullable=False),
        sa.Column("wallet", sa.String(length=42), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_capture_sessions_reservation_id", "capture_sessions", ["reservation_id"])
    op.create_index("ix_capture_sessions_wallet", "capture_sessions", ["wallet"])


def downgrade():
    op.drop_index("ix_capture_sessions_wallet", table_name="capture_sessions")
    op.drop_index("ix_capture_sessions_reservation_id", table_name="capture_sessions")
    op.drop_table("capture_sessions")
