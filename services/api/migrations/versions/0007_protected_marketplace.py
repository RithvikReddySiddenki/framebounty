"""Add protected policy/deadlines without rewriting legacy funded terms."""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"

def upgrade():
    op.add_column("jobs", sa.Column("protection_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column("submissions", sa.Column("payment_due_at", sa.DateTime(timezone=True)))
    op.add_column("confirmations", sa.Column("reservation_expires_at", sa.DateTime(timezone=True)))

def downgrade():
    op.drop_column("confirmations", "reservation_expires_at")
    op.drop_column("submissions", "payment_due_at")
    op.drop_column("jobs", "expires_at")
    op.drop_column("jobs", "protection_version")
