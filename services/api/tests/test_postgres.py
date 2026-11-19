"""Real PostgreSQL tests. Each test owns an isolated schema and applies Alembic.

No SQLite stand-in, mock locks or pre-existing user data is used. Explicitly
set TEST_DATABASE_URL to enable; unavailable infrastructure is reported as a skip.
"""
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from framebounty.auth import issue_challenge, sign_in
from framebounty.marketplace import create_job, prepare_confirmation, reserve, search_tasks
from framebounty.models import Job, Reservation, Task
from test_domain import draft


@pytest.fixture
def pg():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for real PostgreSQL integration tests")
    if not url.startswith("postgresql+psycopg://"):
        pytest.fail("Integration tests require PostgreSQL")
    schema = "test_" + secrets.token_hex(12)
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    db_engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    try:
        with db_engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "head")
        yield db_engine
        with db_engine.begin() as conn:
            config.attributes["connection"] = conn
            command.downgrade(config, "base")
    finally:
        db_engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def seeded(db, slots=1, buyer=None):
    buyer = buyer or "0x" + "1" * 40
    job = create_job(db, buyer, draft())
    job.fixture = True
    job.state = "open"
    job.deposited_atomic = 1_000_000
    task = Task(id="towel-task", job_id=job.id, version=1, reward_atomic=1_000_000,
        slots=slots, claimed=0, tags=["large_towel", "dark_surface"], equipment=["phone", "towel"],
        minutes=15, deadline=datetime.now(UTC) + timedelta(hours=1), state="open")
    db.add(task)
    db.commit()
    return job, task


def test_reservation_window_is_twice_expected_minutes_and_capped_by_listing(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    actor = "0x" + "2" * 40
    with Session(pg) as db:
        _, task = seeded(db, slots=2)
        confirmation = prepare_confirmation(db, actor, task.id)
        before = datetime.now(UTC)
        item = reserve(db, actor, confirmation.id, task.id, task.version, task.reward_atomic, "bounded-reserve-window")
        assert before + timedelta(minutes=30) <= item.expires_at <= datetime.now(UTC) + timedelta(minutes=30)
        original = item.expires_at
        assert reserve(db, actor, confirmation.id, task.id, task.version, task.reward_atomic, "bounded-reserve-window").expires_at == original
        # Give the second reservation its own available budget so the assertion
        # tests the listing cap rather than the solvency check.
        job = db.get(Job, task.job_id)
        job.deposited_atomic = 2_000_000
        task.deadline = datetime.now(UTC) + timedelta(minutes=5)
        db.commit()
        confirmation = prepare_confirmation(db, actor, task.id)
        short = reserve(db, actor, confirmation.id, task.id, task.version, task.reward_atomic, "listing-bounded-window")
        assert short.expires_at == task.deadline


def test_nonce_replay_expiry_wrong_wallet_and_concurrent_login(pg, monkeypatch):
    monkeypatch.setenv("ARC_CHAIN_ID", "5042002")
    account = Account.create()
    with Session(pg) as db:
        nonce = issue_challenge(db, account.address)
        nonce_id = nonce.id
        signature = Account.sign_message(encode_defunct(text=nonce.message), account.key).signature.hex()
        wrong = Account.sign_message(encode_defunct(text=nonce.message), Account.create().key).signature.hex()
        with pytest.raises(HTTPException) as err:
            sign_in(db, nonce_id, wrong)
        assert err.value.status_code == 401
        db.rollback()
    def attempt():
        with Session(pg) as db:
            try:
                return sign_in(db, nonce_id, signature)
            except HTTPException:
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        tokens = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(t is not None for t in tokens) == 1
    with Session(pg) as db:
        expired = issue_challenge(db, account.address)
        expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        with pytest.raises(HTTPException):
            sign_in(db, expired.id, signature)


def test_actual_search_confirmation_and_idempotent_reservation(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    wallet = "0x" + "2" * 40
    with Session(pg) as db:
        job, task = seeded(db)
        assert search_tasks(db, {"phone"}, 20) == []
        assert search_tasks(db, {"phone", "towel"}, 10) == []
        results = search_tasks(db, {"phone", "towel"}, 20)
        assert len(results) == 1 and results[0]["task_id"] == task.id
        confirmation = prepare_confirmation(db, wallet, task.id)
        with pytest.raises(HTTPException):
            reserve(db, wallet, confirmation.id, task.id, 1, 2_000_000, "retry-key")
        db.rollback()
        reservation = reserve(db, wallet, confirmation.id, task.id, 1, 1_000_000, "retry-key")
        repeated = reserve(db, wallet, confirmation.id, task.id, 1, 1_000_000, "retry-key")
        assert repeated.id == reservation.id
        assert db.get(Job, job.id).committed_atomic == 1_000_000
        assert search_tasks(db, {"phone", "towel"}, 20) == []


def test_simultaneous_claims_preserve_budget_and_stale_result(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    with Session(pg) as db:
        job, task = seeded(db, slots=2)  # Budget, rather than slots, limits acceptance.
        job_id = job.id
        confirmations = [(wallet, prepare_confirmation(db, wallet, task.id).id)
                         for wallet in ["0x" + "2" * 40, "0x" + "3" * 40]]
    def attempt(pair):
        wallet, confirmation_id = pair
        with Session(pg) as db:
            try:
                return reserve(db, wallet, confirmation_id, "towel-task", 1, 1_000_000, "concurrent-key").id
            except HTTPException as exc:
                assert exc.status_code == 409
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, confirmations))
    assert sum(r is not None for r in results) == 1
    with Session(pg) as db:
        job = db.get(Job, job_id)
        assert job.committed_atomic == job.deposited_atomic == 1_000_000
        assert len(db.scalars(select(Reservation)).all()) == 1


def test_confirmation_cannot_be_used_by_another_wallet_or_in_live_mode(pg, monkeypatch):
    with Session(pg) as db:
        _, task = seeded(db)
        wallet = "0x" + "2" * 40
        confirmation = prepare_confirmation(db, wallet, task.id)
        with pytest.raises(HTTPException) as err:
            reserve(db, "0x" + "3" * 40, confirmation.id, task.id, 1, 1_000_000, "retry-key")
        assert err.value.status_code == 403
        db.rollback()
        monkeypatch.setenv("APP_MODE", "live")
        with pytest.raises(HTTPException) as err:
            reserve(db, wallet, confirmation.id, task.id, 1, 1_000_000, "retry-key")
        assert err.value.status_code == 503


def test_closed_unfunded_expired_and_changed_tasks_cannot_reserve(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    wallet = "0x" + "2" * 40
    with Session(pg) as db:
        job, task = seeded(db)
        confirmation = prepare_confirmation(db, wallet, task.id)
        task.version += 1
        db.commit()
        with pytest.raises(HTTPException) as err:
            reserve(db, wallet, confirmation.id, task.id, 1, 1_000_000, "changed-key")
        assert err.value.status_code == 409
        db.rollback()
        task.version = 1
        job.state = "closed"
        db.commit()
        assert search_tasks(db, {"phone", "towel"}, 20) == []
        with pytest.raises(HTTPException):
            reserve(db, wallet, confirmation.id, task.id, 1, 1_000_000, "changed-key")
        db.rollback()
        job.state = "open"
        job.deposited_atomic = 0
        db.commit()
        assert search_tasks(db, {"phone", "towel"}, 20) == []
        job.deposited_atomic = 1_000_000
        task.deadline = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        with pytest.raises(HTTPException):
            reserve(db, wallet, confirmation.id, task.id, 1, 1_000_000, "changed-key")


def test_http_wallet_isolation_and_explicit_confirmation(pg, monkeypatch):
    from fastapi.testclient import TestClient
    from framebounty.db import session
    from framebounty.main import app

    monkeypatch.setenv("APP_MODE", "fixture")
    def request_session():
        with Session(pg) as db:
            yield db
    app.dependency_overrides[session] = request_session
    try:
        client = TestClient(app)
        def login(account):
            challenge = client.post("/auth/challenge", json={"wallet": account.address}).json()
            signature = Account.sign_message(encode_defunct(text=challenge["message"]), account.key).signature.hex()
            response = client.post("/auth/login", json={"nonce": challenge["nonce"], "signature": signature})
            assert response.status_code == 200
            return {"Authorization": "Bearer " + response.json()["token"]}
        owner = login(Account.create())
        stranger = login(Account.create())
        result = client.post("/jobs", json=draft().model_dump(mode="json"), headers=owner)
        assert result.status_code == 200
        path = "/jobs/" + result.json()["id"]
        assert client.get(path, headers=owner).status_code == 200
        assert client.get(path, headers=stranger).status_code == 404
        assert client.get(path).status_code == 401
        response = client.post("/reservations", headers=owner, json={"confirmation_id": "a" * 32,
            "task_id": "task", "version": 1, "reward_atomic": "1000000", "idempotency_key": "confirm-key", "confirmed": False})
        assert response.status_code == 422
        assert client.get("/me/reservations", headers=stranger).json() == {"reservations": []}
    finally:
        app.dependency_overrides.clear()
