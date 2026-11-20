"""PostgreSQL session boundary. Connections are lazy, never opened by pure tests."""
import os
import re
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


@lru_cache
def engine():
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://framebounty:framebounty@localhost:5432/framebounty")
    if url.startswith("postgres://"): url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"): url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("PostgreSQL is required; SQLite is not a concurrency substitute")
    schema = os.getenv("DATABASE_SCHEMA")
    connection_options = {}
    if schema:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema): raise RuntimeError("Invalid private database schema")
        connection_options["options"] = "-csearch_path=" + schema
    # Session pooling preserves transaction/advisory-lock semantics. Keep the
    # per-process pool small because API and both workers each own a pool.
    return create_engine(make_url(url), pool_pre_ping=True, pool_size=3, max_overflow=2, connect_args=connection_options)


def session():
    with Session(engine()) as db:
        yield db
