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
from framebounty.submissions import (capture_token_hash, coverage, finalize_upload, issue_capture_session,
                                     review, submission_view)
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
    token, _ = issue_capture_session(db, accounts[2], rid)
    item = finalize_upload(db, accounts[2], rid, key, hashlib.sha256(video).hexdigest(), len(video), "video/mp4",
                           capture_hash=capture_token_hash(token))
    assert item.state == "chain_pending" and not item.fixture
    assert db.scalar(select(VerificationJob).where(VerificationJob.submission_id == item.id)) is None
    assert transact(db, rpc, accounts[2], rid, "submit")["reservation_state"] == "submitted"
    return item.id


def ai_image_ready(pg, rpc, accounts, *, reject=False):
    """Real escrow/hash/Pillow path; only external model observations simulated."""
    from framebounty.domain import Plan
    from framebounty.funding import actions
    from framebounty.marketplace import create_job
    from framebounty.automatic_verification import evaluate
    from test_chain import send
    from test_image_posts import image_plan, image_bytes
    with Session(pg) as db:
        job = create_job(db, accounts[1], Plan.model_validate({**image_plan(), "verification_policy": "ai"}))
        rpc.check_contract()
        if rpc.contract_version < 3:
            # Represents a historical job already pinned before the upgrade.
            job.escrow_address = rpc.config.escrow; db.commit()
        for action in actions(rpc, job, accounts[0]): send(db, rpc, action)
        funding_step(db, rpc, accounts[1], job.id, job.plan_hash, accounts[0])
        task = db.scalar(select(Task).where(Task.job_id == job.id))
        jid = job.id
    submissions = []
    for index in range(1 if reject else 2):
        with Session(pg) as db:
            task = db.scalar(select(Task).where(Task.job_id == jid))
            confirmation = prepare_confirmation(db, accounts[2], task.id)
            reservation = reserve(db, accounts[2], confirmation.id, task.id, task.version, task.reward_atomic, "ai-image-" + str(index))
            if db.get(Job, jid).protection_version >= 3:
                from framebounty.chain_rpc import resource_id
                now = int(rpc.rpc("eth_getBlockByNumber", ["latest", False])["timestamp"], 16)
                policy = rpc.read_escrow("protections", [resource_id(jid)])
                assert now < int(reservation.expires_at.timestamp()) <= min(policy[0], now + 2 * policy[1]), (int(reservation.expires_at.timestamp()), now, policy, db.get(Job, jid).protection_version)
            sync_allocation(db, rpc, reservation.id, LocalUnlockedSigner(rpc, accounts[0]))
            data = image_bytes()
            key = secrets.token_hex(16) + ".image"; LocalStorage().path(key).write_bytes(data)
            item = finalize_upload(db, accounts[2], reservation.id, key, hashlib.sha256(data).hexdigest(), len(data), "image/png")
            sid = item.id
            transact(db, rpc, accounts[2], reservation.id, "submit")
        assert run_once(pg)
        with Session(pg) as db:
            item = db.get(Submission, sid)
            assert item.findings["decoded"]
            checks = {key: {**value, "result": "pass", "confidence": 95} for key, value in item.findings["assessment"].items()} if item.findings.get("assessment") else {
                key: {"result": "pass", "confidence": 95, "explanation": "Synthetic observation only", "timestamps_ms": [0]}
                for key in ["task_completion", "visibility", "cat_climbing_tree"]}
            if reject: checks["cat_climbing_tree"].update(result="fail", confidence=80, explanation="No cat or tree visible")
            item.state, item.findings = "needs_review", {**item.findings, "assessment": checks}
            work = db.scalar(select(VerificationJob).where(VerificationJob.submission_id == sid)); work.state = "done"
            db.commit(); assert evaluate(db, sid)
            submissions.append(sid)
    if not reject:
        from framebounty.protected_chain import sync_protected
        with Session(pg) as db:
            if db.get(Job, jid).protection_version >= 3:
                for sid in submissions:
                    sync_protected(db, rpc, db.get(Submission, sid).reservation_id, LocalUnlockedSigner(rpc, accounts[0]))
    return jid, submissions


def test_ai_verified_batch_waits_for_final_wallet_and_recovers_projection(pg, chain, live_mode):
    from framebounty.payouts import release_step
    rpc, accounts = chain
    jid, ids = ai_image_ready(pg, rpc, accounts)
    with Session(pg) as db:
        assert all(db.get(Submission, sid).state == "verified" for sid in ids)
        assert token_balance(rpc, accounts[2]) == 0 and db.get(Job, jid).paid_atomic == 0
        with pytest.raises(HTTPException): release_step(db, rpc, accounts[2], jid, "unauthorized-batch")
        db.rollback()
        step = release_step(db, rpc, accounts[1], jid, "final-batch-release")
        rpc.rpc("evm_setAutomine", [False])
        transaction = {k: v for k, v in step["transaction"].items() if k != "chainId"}; transaction["gas"] = hex(1_500_000)
        tx_hash = rpc.rpc("eth_sendTransaction", [transaction])
        assert not release_step(db, rpc, accounts[1], jid, "final-batch-release", step["intent_id"], tx_hash)["confirmed"]
        assert db.get(Job, jid).paid_atomic == 0 and token_balance(rpc, accounts[2]) == 0
    rpc.rpc("evm_mine", []); rpc.rpc("evm_setAutomine", [True])
    with Session(pg) as db:
        intent = reconcile(db, rpc, step["intent_id"])
        assert intent.state == "confirmed" and not intent.projected
    reconcile_once(pg, rpc, LocalUnlockedSigner(rpc, accounts[0]))
    with Session(pg) as db:
        assert release_step(db, rpc, accounts[1], jid, "final-batch-release")["confirmed"]
        assert token_balance(rpc, accounts[2]) == 2_000_000
        assert db.get(Job, jid).paid_atomic == 2_000_000 and db.get(Job, jid).committed_atomic == 0
        assert all(db.get(Submission, sid).state == "accepted" for sid in ids)
        assert db.get(TransactionIntent, step["intent_id"]).projected


def test_confident_ai_failure_rejects_and_frees_budget_without_reviewer_signature(pg, chain, live_mode):
    rpc, accounts = chain
    jid, ids = ai_image_ready(pg, rpc, accounts, reject=True)
    with Session(pg) as db:
        assert db.get(Submission, ids[0]).state == "verification_rejected"
        assert db.get(Job, jid).committed_atomic == 1_000_000
    reconcile_once(pg, rpc, LocalUnlockedSigner(rpc, accounts[0]))
    reconcile_once(pg, rpc, LocalUnlockedSigner(rpc, accounts[0]))
    with Session(pg) as db:
        assert db.get(Submission, ids[0]).state == "rejected"
        assert db.get(Job, jid).committed_atomic == 0 and db.get(Job, jid).paid_atomic == 0
        assert token_balance(rpc, accounts[2]) == 0
        intents = db.scalars(select(TransactionIntent).where(TransactionIntent.kind == "verify_reject")).all()
        assert len(intents) == 1 and intents[0].sender == accounts[0]


def test_protected_worker_automatically_pays_once_at_confirmed_deadline(pg, chain, live_mode):
    from framebounty.payouts import release_step
    rpc, accounts = chain
    jid, ids = ai_image_ready(pg, rpc, accounts)
    with Session(pg) as db:
        due = max(db.get(Submission, sid).payment_due_at.timestamp() for sid in ids)
        first_due = min(db.get(Submission, sid).payment_due_at.timestamp() for sid in ids)
        assert db.get(Job, jid).protection_version == 3
        # Buyer opens the batch prompt but never signs. This cannot veto payment.
        assert not release_step(db, rpc, accounts[1], jid, "unsigned-buyer-batch")["confirmed"]
    rpc.rpc("evm_setNextBlockTimestamp", [int(first_due) - 1]); rpc.rpc("evm_mine", [])
    reconcile_once(pg, rpc, LocalUnlockedSigner(rpc, accounts[0]))
    assert token_balance(rpc, accounts[2]) == 0
    rpc.rpc("evm_setNextBlockTimestamp", [int(due)]); rpc.rpc("evm_mine", [])
    reconcile_once(pg, rpc, LocalUnlockedSigner(rpc, accounts[0]))
    reconcile_once(pg, rpc, LocalUnlockedSigner(rpc, accounts[0]))
    with Session(pg) as db:
        assert all(db.get(Submission, sid).state == "accepted" for sid in ids)
        assert db.get(Job, jid).paid_atomic == 2_000_000 and db.get(Job, jid).committed_atomic == 0
        assert len(export(jid, accounts[1], db)["items"]) == 2
        assert release_step(db, rpc, accounts[1], jid, "unsigned-buyer-batch")["automatically_settled"]
    assert token_balance(rpc, accounts[2]) == 2_000_000


def test_wallet_signed_counterparty_votes_are_receipt_gated_and_immutable(pg, chain, live_mode, monkeypatch):
    from framebounty import reputation
    from framebounty.reputation import VoteRequest
    from framebounty.payouts import release_step
    rpc, accounts = chain
    jid, ids = ai_image_ready(pg, rpc, accounts)
    def scoped(*args, **kwargs): yield rpc
    monkeypatch.setattr(reputation, "configured_rpc", scoped)
    with Session(pg) as db:
        assert not reputation.rating(ids[0], accounts[2], db)["eligible"]
        step = release_step(db, rpc, accounts[1], jid, "rating-paid-trade")
        tx = {k: v for k, v in step["transaction"].items() if k != "chainId"}; tx["gas"] = hex(1_500_000)
        tx_hash = rpc.rpc("eth_sendTransaction", [tx]); receipt(rpc, tx_hash)
        assert release_step(db, rpc, accounts[1], jid, "rating-paid-trade", step["intent_id"], tx_hash)["confirmed"]
        before = reputation.rating(ids[0], accounts[2], db)
        assert before["eligible"] and before["up"] == before["down"] == 0
        vote = reputation.rate(ids[0], VoteRequest(vote=1), accounts[2], db)
        assert not vote["confirmed"]
        tx = {k: v for k, v in vote["transaction"].items() if k != "chainId"}; tx["gas"] = hex(300000)
        tx_hash = rpc.rpc("eth_sendTransaction", [tx]); receipt(rpc, tx_hash)
        result = reputation.rate(ids[0], VoteRequest(vote=1, intent_id=vote["intent_id"], tx_hash=tx_hash), accounts[2], db)
        assert result["confirmed"]
        assert reputation.rate(ids[0], VoteRequest(vote=1), accounts[2], db)["confirmed"]
        after = reputation.rating(ids[0], accounts[2], db)
        assert after["up"] == 1 and after["vote"] == 1 and not after["eligible"]
        with pytest.raises(HTTPException): reputation.rate(ids[0], VoteRequest(vote=-1), accounts[2], db)
        assert reputation.buyer_reputation(jid, db)["up"] == 1


def test_refund_after_post_expiry_preserves_and_pays_verified_obligations(pg, chain, live_mode):
    from framebounty.refunds import refund_step
    rpc, accounts = chain
    jid, ids = ai_image_ready(pg, rpc, accounts)
    with Session(pg) as db:
        with pytest.raises(HTTPException): refund_step(db, rpc, accounts[1], jid, "unused-budget-refund")
        expiry = int(db.get(Job, jid).expires_at.timestamp())
    rpc.rpc("evm_setNextBlockTimestamp", [expiry + 1]); rpc.rpc("evm_mine", [])
    with Session(pg) as db:
        step = refund_step(db, rpc, accounts[1], jid, "unused-budget-refund")
        for _ in range(2):
            assert not step["funded"]
            tx = {k:v for k,v in step["transaction"].items() if k != "chainId"}; tx["gas"] = hex(300000)
            tx_hash = rpc.rpc("eth_sendTransaction", [tx]); receipt(rpc, tx_hash)
            step = refund_step(db, rpc, accounts[1], jid, "unused-budget-refund", step["intent_id"], tx_hash)
        assert step["funded"]
        job = db.get(Job, jid)
        refunded = job.refunded_atomic
        assert refunded == job.deposited_atomic - 2_000_000 and job.committed_atomic == 2_000_000
        assert refund_step(db, rpc, accounts[1], jid, "unused-budget-refund")["funded"]
        assert job.refunded_atomic == refunded
    reconcile_once(pg, rpc, LocalUnlockedSigner(rpc, accounts[0]))
    with Session(pg) as db:
        job = db.get(Job, jid)
        assert job.committed_atomic == 0 and job.paid_atomic == 2_000_000 and job.refunded_atomic == refunded
    assert token_balance(rpc, accounts[2]) == 2_000_000


@pytest.mark.parametrize("version", [1, 2])
def test_original_escrow_funds_remain_bound_and_release_through_legacy_path(pg, chain, live_mode, version):
    from dataclasses import replace
    from eth_abi import encode
    from framebounty.chain_rpc import artifact, ChainRPC
    from framebounty.escrow_scope import scoped_rpc
    from framebounty.payouts import release_step
    rpc, accounts = chain
    creation = artifact(version)["creation_bytecode"] + encode(["address"], [rpc.config.token]).hex()
    legacy_hash = rpc.rpc("eth_sendTransaction", [{"from": accounts[0], "data": creation, "gas": hex(5_000_000)}])
    legacy = receipt(rpc, legacy_hash)["contractAddress"].lower()
    old_rpc = ChainRPC(replace(rpc.config, escrow=legacy))
    try:
        old_rpc.check_contract(); assert old_rpc.contract_version == version
        jid, ids = ai_image_ready(pg, old_rpc, accounts, reject=False)
        with Session(pg) as db:
            assert db.get(Job, jid).escrow_address == legacy
            with scoped_rpc(db, jid, rpc) as bound:
                assert bound.config.escrow == legacy
                step = release_step(db, bound, accounts[1], jid, "legacy-final-batch")
                for _ in range(2 if version == 1 else 1):
                    assert not step["confirmed"]
                    if version == 1: assert step["legacy"]
                    transaction = {k: v for k, v in step["transaction"].items() if k != "chainId"}; transaction["gas"] = hex(1_500_000)
                    tx = bound.rpc("eth_sendTransaction", [transaction]); receipt(bound, tx)
                    step = release_step(db, bound, accounts[1], jid, "legacy-final-batch", step["intent_id"], tx)
                assert step["confirmed"]
            assert db.get(Job, jid).escrow_address == legacy and db.get(Job, jid).paid_atomic == 2_000_000
            assert token_balance(rpc, accounts[2]) == 2_000_000
    finally: old_rpc.close()


def test_worker_expires_short_reservation_without_a_human_wallet_action(pg, chain, live_mode):
    rpc, accounts = chain
    with Session(pg) as db:
        jid, rid = prepare(db, rpc, accounts)
        sync_allocation(db, rpc, rid, LocalUnlockedSigner(rpc, accounts[0]))
        expiry = int(db.get(Reservation, rid).expires_at.timestamp())
    rpc.rpc("evm_setNextBlockTimestamp", [expiry + 1]); rpc.rpc("evm_mine", [])
    reconcile_once(pg, rpc, LocalUnlockedSigner(rpc, accounts[0]))
    with Session(pg) as db:
        assert db.get(Reservation, rid).state == "expired"
        assert db.get(Job, jid).committed_atomic == 0 and db.get(Job, jid).paid_atomic == 0
        assert token_balance(rpc, accounts[2]) == 0


def test_reverted_batch_pays_none_and_new_explicit_release_can_retry(pg, chain, live_mode):
    from framebounty.payouts import release_step
    rpc, accounts = chain
    jid, ids = ai_image_ready(pg, rpc, accounts)
    with Session(pg) as db:
        step = release_step(db, rpc, accounts[1], jid, "batch-that-reverts")
        failure = rpc.rpc("eth_sendTransaction", [{"from": accounts[0], "to": rpc.config.token,
            "data": call_data("setFailure(bool)", ["bool"], [True]), "gas": hex(200000)}]); receipt(rpc, failure)
        transaction = {k: v for k, v in step["transaction"].items() if k != "chainId"}; transaction["gas"] = hex(1_500_000)
        failed_hash = rpc.rpc("eth_sendTransaction", [transaction])
        failed_receipt = rpc.rpc("eth_getTransactionReceipt", [failed_hash])
        assert int(failed_receipt["status"], 16) == 0
        failed = release_step(db, rpc, accounts[1], jid, "batch-that-reverts", step["intent_id"], failed_hash)
        assert failed["state"] == "reverted" and not failed["confirmed"]
        assert all(db.get(Submission, sid).state == "verified" for sid in ids)
        assert db.get(Job, jid).paid_atomic == 0 and token_balance(rpc, accounts[2]) == 0
        restored = rpc.rpc("eth_sendTransaction", [{"from": accounts[0], "to": rpc.config.token,
            "data": call_data("setFailure(bool)", ["bool"], [False]), "gas": hex(200000)}]); receipt(rpc, restored)
        retry = release_step(db, rpc, accounts[1], jid, "new-explicit-release")
        transaction = {k: v for k, v in retry["transaction"].items() if k != "chainId"}; transaction["gas"] = hex(1_500_000)
        successful = rpc.rpc("eth_sendTransaction", [transaction]); receipt(rpc, successful)
        assert release_step(db, rpc, accounts[1], jid, "new-explicit-release", retry["intent_id"], successful)["confirmed"]
        assert db.get(Job, jid).paid_atomic == 2_000_000 and token_balance(rpc, accounts[2]) == 2_000_000


def test_image_post_receipt_gated_funding_hash_lock_and_single_payout(pg, chain, live_mode):
    from framebounty.domain import Plan
    from framebounty.funding import actions
    from framebounty.marketplace import create_job
    from test_chain import send
    from test_image_posts import image_plan, image_bytes

    rpc, accounts = chain
    data = image_bytes()
    with Session(pg) as db:
        job = create_job(db, accounts[1], Plan.model_validate(image_plan()))
        jid = job.id
        for action in actions(rpc, job, accounts[0]):
            send(db, rpc, action)
        assert funding_step(db, rpc, accounts[1], jid, job.plan_hash, accounts[0])["funded"]
        task = db.scalar(select(Task).where(Task.job_id == jid))
        assert task.equipment == ["phone"] and task.tags == ["cat_climbing_tree"]
        confirmation = prepare_confirmation(db, accounts[2], task.id)
        reservation = reserve(db, accounts[2], confirmation.id, task.id, task.version, task.reward_atomic, "image-chain-reserve")
        rid = reservation.id
        assert sync_allocation(db, rpc, rid, LocalUnlockedSigner(rpc, accounts[0])).state == "reserved"
        key = secrets.token_hex(16) + ".image"
        LocalStorage().path(key).write_bytes(data)
        item = finalize_upload(db, accounts[2], rid, key, hashlib.sha256(data).hexdigest(), len(data), "image/png")
        sid = item.id
        assert item.state == "chain_pending"
        assert transact(db, rpc, accounts[2], rid, "submit")["confirmed"]
    assert run_once(pg)
    with Session(pg) as db:
        assert db.get(Submission, sid).findings["metadata"]["media_type"] == "image"
        assert db.get(Submission, sid).state == "needs_review"
        review(db, accounts[1], sid, "accept", True, True, ["cat_climbing_tree"], "Synthetic image settlement test only")
        assert token_balance(rpc, accounts[2]) == 0
        assert transact(db, rpc, accounts[1], rid, "review")["confirmed"]
        assert transact(db, rpc, accounts[1], rid, "review")["confirmed"]
        assert token_balance(rpc, accounts[2]) == 1_000_000
        assert db.get(Job, jid).paid_atomic == 1_000_000
        assert submission_view(db.get(Submission, sid))["payment_confirmed"]
        assert export(jid, accounts[1], db)["items"][0]["media_type"] == "image"


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
