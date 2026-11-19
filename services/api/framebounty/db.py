"""PostgreSQL session boundary. Connections are lazy, never opened by pure tests."""
import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@lru_cache
def engine():
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://framebounty:framebounty@localhost:5432/framebounty")
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("PostgreSQL is required; SQLite is not a concurrency substitute")
    return create_engine(url, pool_pre_ping=True)


def session():
    with Session(engine()) as db:
        yield db
