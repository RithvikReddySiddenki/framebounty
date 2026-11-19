"""Durable prepared/signed/broadcast/verified chain intentions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"


def upgrade():
    op.create_table("transaction_intents",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("chain_id", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False), sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("reservation_id", sa.String(64), sa.ForeignKey("reservations.id"), nullable=True),
        sa.Column("sender", sa.String(42), nullable=False), sa.Column("destination", sa.String(42), nullable=False),
        sa.Column("call_data", sa.Text, nullable=False), sa.Column("expected_event", JSONB, nullable=False),
        sa.Column("nonce", sa.BigInteger, nullable=True), sa.Column("unsigned", JSONB, nullable=False),
        sa.Column("raw_transaction", sa.Text, nullable=True), sa.Column("tx_hash", sa.String(66), nullable=True),
        sa.Column("state", sa.String(20), nullable=False), sa.Column("start_block", sa.BigInteger, nullable=False),
        sa.Column("confirmed_block", sa.BigInteger, nullable=True), sa.Column("verified_event", JSONB, nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True), sa.Column("broadcast_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("chain_id", "kind", "resource_id", name="transaction_action_unique"),
        sa.UniqueConstraint("chain_id", "sender", "nonce", name="transaction_nonce_unique"),
        sa.CheckConstraint("state IN ('intent', 'signed', 'broadcast', 'confirmed', 'reverted', 'invalid')", name="transaction_state_bounds"))
    for column in ("job_id", "tx_hash"):
        op.create_index(f"ix_transaction_intents_{column}", "transaction_intents", [column])


def downgrade():
    op.drop_table("transaction_intents")
