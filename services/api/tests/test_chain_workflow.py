"""Real PostgreSQL/EVM/FFmpeg workflow; synthetic video is not task-quality proof."""
import hashlib
import secrets
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from framebounty.chain_rpc import call_data
from framebounty.chain_workflow import sync_allocation, wallet_step
from framebounty.chain_worker import run_once as reconcile_once
from framebounty.funding import funding_step
from framebounty.marketplace import prepare_confirmation, reserve
from framebounty.media import LocalStorage
from framebounty.models import Job, Reservation, Submission, Task, TransactionIntent, VerificationJob
from framebounty.submissions import coverage, finalize_upload, review, submission_view
from framebounty.planning import next_collection_batch
from framebounty.submission_routes import export
from framebounty.transactions import LocalUnlockedSigner, reconcile
from framebounty.worker import run_once
from framebounty.worker import claim, finish
from test_chain import chain, funded, receipt, token_balance
from test_postgres import pg
from test_submission_flow import video


def prepare(db, rpc, accounts):
    job_id, _ = funded(db, rpc, accounts)
    job = db.get(Job, job_id)
    funding_step(db, rpc, accounts[1], job_id, job.plan_hash, accounts[0])
    task = db.scalar(select(Task).where(Task.job_id == job_id))
    confirmation = prepare_confirmation(db, accounts[2], task.id)
    reservation = reserve(db, accounts[2], confirmation.id, task.id, task.version, task.reward_atomic, "real-chain-reserve")
    return job_id, reservation.id


def transact(db, rpc, wallet, rid, purpose):
    step = wallet_step(db, rpc, wallet, rid, purpose)
    if step["confirmed"]:
        return step
    transaction = {key: value for key, value in step["transaction"].items() if key != "chainId"}
    transaction["gas"] = hex(500000)
    tx_hash = rpc.rpc("eth_sendTransaction", [transaction])
    receipt(rpc, tx_hash)
    return wallet_step(db, rpc, wallet, rid, purpose, step["intent_id"], tx_hash)


@pytest.fixture
def live_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_MODE", "testnet")
    monkeypatch.setenv("ALLOW_CHAIN_TRANSACTIONS", "true")
    monkeypatch.setenv("ALLOW_MODEL_MEDIA", "false")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "private"))


def uploaded(db, rpc, accounts, rid, video):
    storage = LocalStorage()
    key = secrets.token_hex(16) + ".video"
    storage.path(key).write_bytes(video)
    item = finalize_upload(db, accounts[2], rid, key, hashlib.sha256(video).hexdigest(), len(video), "video/mp4")
    assert item.state == "chain_pending" and not item.fixture
    assert db.scalar(select(VerificationJob).where(VerificationJob.submission_id == item.id)) is None
    assert transact(db, rpc, accounts[2], rid, "submit")["reservation_state"] == "submitted"
    return item.id


def test_real_reserve_upload_review_pending_receipt_and_restart_payment(pg, chain, live_mode, video):
    rpc, accounts = chain
    with Session(pg) as db:
        jid, rid = prepare(db, rpc, accounts)
        assert db.get(Reservation, rid).state == "reserve_pending"
        assert db.get(Job, jid).committed_atomic == 1_000_000
        with pytest.raises(HTTPException):
            finalize_upload(db, accounts[2], rid, "a" * 32 + ".video", hashlib.sha256(video).hexdigest(), len(video), "video/mp4")
        db.rollback()
        assert sync_allocation(db, rpc, rid, LocalUnlockedSigner(rpc, accounts[0])).state == "reserved"
        assert sync_allocation(db, rpc, rid, LocalUnlockedSigner(rpc, accounts[0])).state == "reserved"
        sid = uploaded(db, rpc, accounts, rid, video)
    assert run_once(pg)
    with Session(pg) as db:
        item = db.get(Submission, sid)
        assert item.state == "needs_review" and item.findings["decoded"]
        assert "provider_error" in item.findings  # No private media sent to a model.
        with pytest.raises(HTTPException) as denied:
            wallet_step(db, rpc, accounts[2], rid, "review")
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException):
            review(db, accounts[1], sid, "accept", False, True, ["large_towel", "dark_surface"], "Synthetic orchestration attestation")
        db.rollback()
        accepted = review(db, accounts[1], sid, "accept", True, True, ["large_towel", "dark_surface"], "Synthetic orchestration attestation")
        assert accepted.state == "accept_pending" and not submission_view(accepted)["payment_confirmed"]
        assert coverage(db, db.get(Job, jid))["accepted_total"] == 0
        step = wallet_step(db, rpc, accounts[1], rid, "review")
        rpc.rpc("evm_setAutomine", [False])
        transaction = {key: value for key, value in step["transaction"].items() if key != "chainId"}
        transaction["gas"] = hex(500000)
        tx_hash = rpc.rpc("eth_sendTransaction", [transaction])
        pending = wallet_step(db, rpc, accounts[1], rid, "review", step["intent_id"], tx_hash)
        assert pending["state"] == "broadcast" and db.get(Job, jid).paid_atomic == 0
        assert token_balance(rpc, accounts[2]) == 0
    rpc.rpc("evm_mine", [])
    rpc.rpc("evm_setAutomine", [True])
    with Session(pg) as db:
        intent = reconcile(db, rpc, step["intent_id"])
        assert intent.state == "confirmed" and not intent.projected
        assert db.get(Job, jid).paid_atomic == 0
    # Receipt recognition committed, then the process died before ledger update.
    # The durable worker must find confirmed-but-unprojected work after restart.
    reconcile_once(pg, rpc, LocalUnlockedSigner(rpc, accounts[0]))
    with Session(pg) as db:
        assert wallet_step(db, rpc, accounts[1], rid, "review")["confirmed"]
        assert wallet_step(db, rpc, accounts[1], rid, "review")["confirmed"]
        assert submission_view(db.get(Submission, sid))["payment_confirmed"]
        assert db.get(Job, jid).paid_atomic == 1_000_000
        assert db.get(Job, jid).committed_atomic == 0
        assert token_balance(rpc, accounts[2]) == 1_000_000
        assert coverage(db, db.get(Job, jid))["accepted_categories"] == {"large_towel": 1, "dark_surface": 1}
        assert db.get(TransactionIntent, step["intent_id"]).projected
        assert review(db, accounts[1], sid, "accept", True, True, ["large_towel", "dark_surface"], "Synthetic orchestration attestation").state == "accepted"
        manifest = export(jid, accounts[1], db)
        assert not manifest["fixture"] and len(manifest["items"]) == 1
        assert manifest["items"][0]["sha256"] == hashlib.sha256(video).hexdigest()
        batch = next_collection_batch(db, accounts[1], jid, "chain-next-batch")
        assert not batch["fixture"] and batch["published_slots"] == 2
        assert next_collection_batch(db, accounts[1], jid, "chain-next-batch") == batch
        task = db.scalar(select(Task).where(Task.job_id == jid, Task.claimed < Task.slots))
        confirmation = prepare_confirmation(db, accounts[2], task.id)
        second = reserve(db, accounts[2], confirmation.id, task.id, task.version, task.reward_atomic, "second-live-clip")
        sync_allocation(db, rpc, second.id, LocalUnlockedSigner(rpc, accounts[0]))
        second_id = uploaded(db, rpc, accounts, second.id, video)
    assert run_once(pg)
    with Session(pg) as db:
        assert sid in db.get(Submission, second_id).findings["perceptual_duplicate_candidates"]


def test_expiry_receipt_releases_exactly_once_and_prevents_upload(pg, chain, live_mode):
    rpc, accounts = chain
    with Session(pg) as db:
        jid, rid = prepare(db, rpc, accounts)
        sync_allocation(db, rpc, rid, LocalUnlockedSigner(rpc, accounts[0]))
        expiry = int(db.get(Reservation, rid).expires_at.timestamp())
        rpc.rpc("evm_setNextBlockTimestamp", [expiry])
        rpc.rpc("evm_mine", [])
        assert transact(db, rpc, accounts[2], rid, "release")["reservation_state"] == "expired"
        assert wallet_step(db, rpc, accounts[2], rid, "release")["confirmed"]
        assert db.get(Job, jid).committed_atomic == 0
        assert db.scalar(select(Task).where(Task.job_id == jid)).claimed == 0
        with pytest.raises(HTTPException):
            finalize_upload(db, accounts[2], rid, "a" * 32 + ".video", "a" * 64, 10, "video/mp4")


def test_reverted_review_keeps_commitment_until_confirmed_timeout(pg, chain, live_mode, video):
    rpc, accounts = chain
    with Session(pg) as db:
        jid, rid = prepare(db, rpc, accounts)
        sync_allocation(db, rpc, rid, LocalUnlockedSigner(rpc, accounts[0]))
        sid = uploaded(db, rpc, accounts, rid, video)
    assert run_once(pg)
    with Session(pg) as db:
        review(db, accounts[1], sid, "accept", True, True, ["large_towel", "dark_surface"], "Synthetic flow only")
        step = wallet_step(db, rpc, accounts[1], rid, "review")
        failure = rpc.rpc("eth_sendTransaction", [{"from": accounts[0], "to": rpc.config.token,
            "data": call_data("setFailure(bool)", ["bool"], [True]), "gas": hex(100000)}])
        receipt(rpc, failure)
        tx = {key: value for key, value in step["transaction"].items() if key != "chainId"}
        tx["gas"] = hex(500000)
        tx_hash = rpc.rpc("eth_sendTransaction", [tx])
        assert int(rpc.rpc("eth_getTransactionReceipt", [tx_hash])["status"], 16) == 0
        assert wallet_step(db, rpc, accounts[1], rid, "review", step["intent_id"], tx_hash)["state"] == "reverted"
        assert db.get(Job, jid).paid_atomic == 0 and db.get(Job, jid).committed_atomic == 1_000_000
        assert not submission_view(db.get(Submission, sid))["payment_confirmed"]
        deadline = int(db.get(Submission, sid).review_deadline.timestamp())
        rpc.rpc("evm_setNextBlockTimestamp", [deadline])
        rpc.rpc("evm_mine", [])
        assert transact(db, rpc, accounts[2], rid, "release")["reservation_state"] == "timed_out"
        assert db.get(Job, jid).committed_atomic == 0 and token_balance(rpc, accounts[2]) == 0


def test_rejection_is_reviewed_and_receipt_gated(pg, chain, live_mode, video):
    rpc, accounts = chain
    with Session(pg) as db:
        jid, rid = prepare(db, rpc, accounts)
        sync_allocation(db, rpc, rid, LocalUnlockedSigner(rpc, accounts[0]))
        sid = uploaded(db, rpc, accounts, rid, video)
    assert run_once(pg)
    with Session(pg) as db:
        review(db, accounts[1], sid, "reject", False, True, [], "Synthetic clip is not a towel demonstration")
        assert db.get(Job, jid).committed_atomic == 1_000_000
        assert transact(db, rpc, accounts[1], rid, "review")["reservation_state"] == "rejected"
        assert wallet_step(db, rpc, accounts[1], rid, "review")["confirmed"]
        assert db.get(Job, jid).committed_atomic == 0
        assert db.scalar(select(Task).where(Task.job_id == jid)).claimed == 0
        assert token_balance(rpc, accounts[2]) == 0


def test_concurrent_live_claims_count_pending_allocations_before_broadcast(pg, chain, live_mode):
    rpc, accounts = chain
    with Session(pg) as db:
        jid, first = prepare(db, rpc, accounts)
        task = db.scalar(select(Task).where(Task.job_id == jid))
        task_id = task.id
        confirmations = [prepare_confirmation(db, wallet, task_id).id for wallet in accounts[2:4]]
    def attempt(index):
        with Session(pg) as db:
            try:
                return reserve(db, accounts[index + 2], confirmations[index], task_id, 1, 1_000_000, f"concurrent-live-{index}").id
            except HTTPException as error:
                assert error.status_code == 409
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(item is not None for item in results) == 1
    reconcile_once(pg, rpc, LocalUnlockedSigner(rpc, accounts[0]))
    with Session(pg) as db:
        assert db.get(Job, jid).committed_atomic == 2_000_000
        assert db.get(Task, task_id).claimed == 2
        reservations = db.scalars(select(Reservation).where(Reservation.job_id == jid)).all()
        assert len(reservations) == 2 and all(item.state == "reserved" for item in reservations)


def test_chain_timeout_fences_a_late_media_worker(pg, chain, live_mode, video):
    rpc, accounts = chain
    with Session(pg) as db:
        jid, rid = prepare(db, rpc, accounts)
        sync_allocation(db, rpc, rid, LocalUnlockedSigner(rpc, accounts[0]))
        sid = uploaded(db, rpc, accounts, rid, video)
        work_id, lease = claim(db)
        deadline = int(db.get(Submission, sid).review_deadline.timestamp())
        rpc.rpc("evm_setNextBlockTimestamp", [deadline])
        rpc.rpc("evm_mine", [])
        transact(db, rpc, accounts[2], rid, "release")
        assert not finish(db, work_id, lease, {"decoded": True})
        assert db.get(Submission, sid).state == "timed_out"
        assert db.get(Job, jid).committed_atomic == 0
