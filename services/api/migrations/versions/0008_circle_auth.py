"""Circle-owned wallet session bindings and durable public challenge recovery."""
from alembic import op
import sqlalchemy as sa
revision = "0008"
down_revision = "0007"

def upgrade():
    op.add_column("jobs", sa.Column("chain_id", sa.Integer()))
    op.execute("UPDATE jobs SET chain_id=(SELECT min(chain_id) FROM transaction_intents WHERE job_id=jobs.id) WHERE escrow_address IS NOT NULL")
    op.add_column("auth_sessions", sa.Column("chain_id", sa.Integer(), nullable=False, server_default="5042002"))
    op.add_column("auth_sessions", sa.Column("circle_wallet_id", sa.String(36)))
    op.create_table("auth_rate_buckets", sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False))
    op.create_table("circle_challenges", sa.Column("intent_id", sa.String(64), sa.ForeignKey("transaction_intents.id"), primary_key=True),
        sa.Column("challenge_id", sa.String(36), nullable=False, unique=True), sa.Column("wallet_id", sa.String(36), nullable=False))

def downgrade():
    op.drop_table("circle_challenges")
    op.drop_table("auth_rate_buckets")
    op.drop_column("auth_sessions", "circle_wallet_id")
    op.drop_column("auth_sessions", "chain_id")
    op.drop_column("jobs", "chain_id")
