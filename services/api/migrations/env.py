"""Migrations use the same PostgreSQL-only engine as the API."""
from alembic import context
from framebounty.db import engine
from framebounty.models import Base

def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


provided = context.config.attributes.get("connection")
if provided is not None:
    migrate(provided)
else:
    with engine().connect() as connection:
        migrate(connection)
