import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from framebounty.marketplace import create_job, prepare_confirmation, reserve
from framebounty.models import Job, Reservation, Task
from framebounty.planning import next_fixture_batch, publish_fixture
from test_domain import draft
from test_postgres import pg


def test_publish_is_confirmed_owner_scoped_and_idempotent(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    buyer = "0x" + "1" * 40
    with Session(pg) as db:
        job = create_job(db, buyer, draft())
        with pytest.raises(HTTPException):
            publish_fixture(db, "0x" + "2" * 40, job.id, job.plan_hash)
        db.rollback()
        with pytest.raises(HTTPException):
            publish_fixture(db, buyer, job.id, "0" * 64)
        db.rollback()
        first = publish_fixture(db, buyer, job.id, job.plan_hash)
        assert publish_fixture(db, buyer, job.id, job.plan_hash) == first
        assert sum(t.slots for t in db.scalars(select(Task))) == 2
        assert job.deposited_atomic == 20_000_000


def test_replanning_preserves_promises_and_counts_published_slots(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    buyer, contributor = "0x" + "1" * 40, "0x" + "2" * 40
    with Session(pg) as db:
        job = create_job(db, buyer, draft())
        task_id = publish_fixture(db, buyer, job.id, job.plan_hash)[0]
        confirmation = prepare_confirmation(db, contributor, task_id)
        obligation = reserve(db, contributor, confirmation.id, task_id, 1, 1_000_000, "planning-reserve")
        next_batch = next_fixture_batch(db, buyer, job.id, "batch-request-01")
        assert next_batch["deficits_after_existing_work"] == {"total": 18, "large_towel": 3, "dark_surface": 3}
        assert next_batch["published_slots"] == 2
        assert next_fixture_batch(db, buyer, job.id, "batch-request-01") == next_batch
        assert db.get(Reservation, obligation.id).state == "fixture_reserved"
        assert db.get(Job, job.id).committed_atomic == 1_000_000
        for index in range(20):
            next_fixture_batch(db, buyer, job.id, f"more-batch-{index:02d}")
        assert sum(t.slots for t in db.scalars(select(Task))) == 20
        assert next_fixture_batch(db, buyer, job.id, "last-batch-request")["published_slots"] == 0


def test_live_mode_never_silently_simulates_funding(pg, monkeypatch):
    buyer = "0x" + "1" * 40
    with Session(pg) as db:
        job = create_job(db, buyer, draft())
        monkeypatch.setenv("APP_MODE", "live")
        with pytest.raises(HTTPException) as error:
            publish_fixture(db, buyer, job.id, job.plan_hash)
        assert error.value.status_code == 503
        assert job.deposited_atomic == 0
