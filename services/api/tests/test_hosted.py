"""Hosted safety configuration and real private-schema database behavior."""
from pathlib import Path
import pytest
from sqlalchemy import text

from framebounty import hosted
from framebounty.db import engine
from test_postgres import pg


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("AUTH_ORIGIN", "https://demo.vercel.app")
    monkeypatch.setenv("DATABASE_URL", "postgresql://private-placeholder:5432/postgres?sslmode=require")
    monkeypatch.setenv("DATABASE_SCHEMA", "framebounty")
    monkeypatch.setenv("STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("APP_MODE", "fixture")
    monkeypatch.setenv("ARC_CHAIN_ID", "5042002")
    monkeypatch.setenv("ALLOW_CHAIN_TRANSACTIONS", "false")
    monkeypatch.setenv("RUN_CHAIN_WORKER", "false")
    # Only the provider metadata boundary is simulated in this config-only test.
    class Bucket:
        def client(self):
            from contextlib import nullcontext
            return nullcontext(None)
        def check_private(self, client): pass
    monkeypatch.setattr(hosted, "private_storage", Bucket)


@pytest.mark.parametrize("origin", ["http://demo.vercel.app", "https://demo.vercel.app/", "https://demo.vercel.app/path", "https://user:secret@demo.vercel.app"])
def test_hosted_requires_one_exact_https_origin(settings, monkeypatch, origin):
    monkeypatch.setenv("AUTH_ORIGIN", origin)
    with pytest.raises(ValueError): hosted.validate()


def test_fixture_does_not_start_an_operator(settings, monkeypatch):
    assert hosted.validate()["chain_worker"] is False
    monkeypatch.setenv("RUN_CHAIN_WORKER", "true")
    with pytest.raises(ValueError): hosted.validate()


def test_enabled_mainnet_worker_requires_persistent_budget(settings, monkeypatch):
    for name, value in {"APP_MODE": "mainnet", "ARC_CHAIN_ID": "5042", "ALLOW_MAINNET_TRANSACTIONS": "true",
            "ALLOW_CHAIN_TRANSACTIONS": "true", "RUN_CHAIN_WORKER": "true", "MAINNET_BUDGET_PATH": "/tmp/budget.json"}.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValueError): hosted.validate()
    monkeypatch.setenv("MAINNET_BUDGET_PATH", "/data/operator/mainnet-budget.json")
    monkeypatch.setattr(hosted, "data_volume_mounted", lambda: False)
    with pytest.raises(ValueError): hosted.validate()
    monkeypatch.setattr(hosted, "data_volume_mounted", lambda: True)
    assert hosted.validate()["chain_worker"] is True


@pytest.mark.parametrize("url", ["postgresql://host:6543/postgres?sslmode=require", "postgresql://host:5432/postgres"])
def test_hosted_requires_tls_and_session_pooling(settings, monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ValueError): hosted.validate()


def test_hosted_schema_must_not_use_exposed_public_tables(settings, monkeypatch):
    monkeypatch.setenv("DATABASE_SCHEMA", "public")
    with pytest.raises(ValueError): hosted.validate()


def test_database_url_normalization_and_schema_use_real_postgres(pg, monkeypatch):
    # Reuse this case's disposable migrated schema, never a hosted project.
    with pg.connect() as connection:
        schema = connection.scalar(text("select current_schema()"))
    url = pg.url.difference_update_query(["options"]).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", url.replace("postgresql+psycopg://", "postgres://", 1))
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
    engine.cache_clear()
    configured = engine()
    try:
        with configured.connect() as connection:
            assert connection.scalar(text("select current_schema()")) == schema
            assert connection.scalar(text("select version_num from alembic_version")) == "0010"
    finally:
        configured.dispose(); engine.cache_clear()


def test_migration_history_has_one_unambiguous_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    history = ScriptDirectory.from_config(config)
    assert history.get_heads() == ["0010"]
    assert history.get_revision("0009").down_revision == "0008"
    assert history.get_revision("0008").down_revision == "0007"


def test_budget_ledger_can_use_persistent_operator_volume(tmp_path, monkeypatch):
    from framebounty.mainnet_budget import path
    location = tmp_path / "operator" / "budget.json"
    monkeypatch.setenv("MAINNET_BUDGET_PATH", str(location))
    assert path() == location and location.parent.is_dir()
