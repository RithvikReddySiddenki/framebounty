"""Hide archived demos while retaining their funded obligations for settlement."""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"

def upgrade():
    op.add_column("jobs", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))

def downgrade():
    op.drop_column("jobs", "archived")
