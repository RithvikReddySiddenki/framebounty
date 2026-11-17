"""Snapshot real/fixture provenance on private submission records."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"


def upgrade():
    # All pre-migration submissions were explicitly fixture-only.
    op.add_column("submissions", sa.Column("fixture", sa.Boolean, nullable=False, server_default=sa.true()))
    op.add_column("transaction_intents", sa.Column("projected", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("transaction_intents", "projected")
    op.drop_column("submissions", "fixture")
