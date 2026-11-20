"""Real PostgreSQL + isolated local EVM transaction-layer tests.

Set TEST_CHAIN_RPC_URL only to the dedicated ephemeral Anvil node. No keys, Arc
funds, hosted provider calls or mocked business/chain behaviors are used here.
"""
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

import pytest
from eth_abi import decode, encode
from sqlalchemy import select
from sqlalchemy.orm import Session

from framebounty.chain_rpc import ChainConfig, ChainFailure, ChainRPC, InvalidReceipt, artifact, call_data, escrow_call, resource_id
from framebounty.demo import example_plan
from framebounty.funding import funding_step
from framebounty.marketplace import create_job
from framebounty.models import TransactionIntent
from framebounty.transactions import Action, LocalUnlockedSigner, attach_wallet_hash, broadcast, create_intent, reconcile, sign_intent
from test_postgres import pg


def receipt(rpc, tx_hash):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = rpc.rpc("eth_getTransactionReceipt", [tx_hash])
        if result is not None:
            assert int(result["status"], 16) == 1, "Local chain fixture transaction failed"
            return result
        time.sleep(0.05)
    raise AssertionError("Local chain fixture receipt timed out")


@pytest.fixture
def chain(pg, monkeypatch):
    url = os.getenv("TEST_CHAIN_RPC_URL")
    if not url:
        pytest.skip("Set TEST_CHAIN_RPC_URL for the separately gated real local-chain suite")
    # Domain services must use the same explicit local network as the RPC
    # fixture. Production still permits only the two real Arc chain IDs.
    from dataclasses import replace
    from framebounty import networks
    monkeypatch.setattr(networks, "TESTNET", replace(networks.TESTNET, chain_id=31337))
    monkeypatch.setenv("ARC_CHAIN_ID", "31337")
    dummy = ChainRPC(ChainConfig(url, 31337, "0x" + "1" * 40, "0x" + "2" * 40, allow_local=True))
    dummy.check_network()
    snapshot = dummy.rpc("evm_snapshot", [])
    # Snapshot rollback restores old block time while the Python/server clock
    # keeps advancing. Start each isolated case near wall time like the live
    # continuously mined network; never weaken production deadline checks.
    latest = int(dummy.rpc("eth_getBlockByNumber", ["latest", False])["timestamp"], 16)
    dummy.rpc("evm_setNextBlockTimestamp", [max(int(time.time()), latest + 1)])
    dummy.rpc("evm_mine", [])
    accounts = [value.lower() for value in dummy.rpc("eth_accounts", [])]
    assert len(accounts) >= 3
    dummy.rpc("evm_setAutomine", [True])
    root = Path(__file__).resolve().parents[3]
    token_artifact = json.loads((root / "contracts/out/Escrow.t.sol/TestUSDC.json").read_text())
    token_hash = dummy.rpc("eth_sendTransaction", [{"from": accounts[0], "data": token_artifact["bytecode"]["object"], "gas": hex(5_000_000)}])
    token = receipt(dummy, token_hash)["contractAddress"].lower()
    creation = artifact()["creation_bytecode"] + encode(["address"], [token]).hex()
    escrow_hash = dummy.rpc("eth_sendTransaction", [{"from": accounts[0], "data": creation, "gas": hex(5_000_000)}])
    escrow = receipt(dummy, escrow_hash)["contractAddress"].lower()
    rpc = ChainRPC(ChainConfig(url, 31337, escrow, token, allow_local=True))
    rpc.check_contract()
    minted = rpc.rpc("eth_sendTransaction", [{"from": accounts[0], "to": token,
        "data": call_data("mint(address,uint256)", ["address", "uint256"], [accounts[1], 20_000_000]), "gas": hex(200000)}])
    receipt(rpc, minted)
    try:
        yield rpc, accounts
    finally:
        rpc.rpc("evm_setAutomine", [True])
        rpc.rpc("evm_revert", [snapshot])
        rpc.close()
        dummy.close()


def send(db, rpc, action):
    intent = create_intent(db, rpc, action)
    sign_intent(db, rpc, intent.id, LocalUnlockedSigner(rpc, action.sender))
    broadcast(db, rpc, intent.id)
    result = reconcile(db, rpc, intent.id)
    assert result.state == "confirmed", result.last_error
    return result


def funded(db, rpc, accounts):
    allocator, buyer, _ = accounts[:3]
    # This helper preserves historical human-review compatibility cases. The
    # current default and the dedicated automatic-policy tests use AI plans.
    job = create_job(db, buyer, example_plan().model_copy(update={"verification_policy": "human"}))
    jid = resource_id(job.id)
    jid_hex = "0x" + jid.hex()
    create = Action("create_job", job.id, buyer, rpc.config.escrow,
        escrow_call("createJob", [jid, buyer, allocator, bytes.fromhex(job.plan_hash), 72 * 3600]),
        {"name": "JobCreated", "fields": {"jobId": jid_hex, "buyer": buyer, "reviewer": buyer,
            "allocator": allocator, "rubric": "0x" + job.plan_hash, "reviewSeconds": 72 * 3600}}, job_id=job.id)
    send(db, rpc, create)
    approve = Action("token_approve", job.id, buyer, rpc.config.token,
        call_data("approve(address,uint256)", ["address", "uint256"], [rpc.config.escrow, 20_000_000]),
        {"name": "Approval", "fields": {"owner": buyer, "spender": rpc.config.escrow, "value": 20_000_000}}, job_id=job.id)
    send(db, rpc, approve)
    deposit = Action("deposit", job.id, buyer, rpc.config.escrow,
        escrow_call("deposit", [jid, 20_000_000]), {"name": "Deposited", "fields": {"jobId": jid_hex, "amount": 20_000_000}}, job_id=job.id)
    send(db, rpc, deposit)
    return job.id, jid


def submitted(db, rpc, accounts, job_id, jid):
    allocator, _, contributor = accounts[:3]
    reservation = secrets.token_hex(16)
    rid = resource_id(reservation)
    timestamp = int(rpc.rpc("eth_getBlockByNumber", ["latest", False])["timestamp"], 16)
    reserve_action = Action("reserve", reservation, allocator, rpc.config.escrow,
        escrow_call("reserve", [jid, rid, contributor, 1_000_000, timestamp + 3600]),
        {"name": "Reserved", "fields": {"jobId": "0x" + jid.hex(), "reservationId": "0x" + rid.hex(),
            "recipient": contributor, "reward": 1_000_000, "expiresAt": timestamp + 3600}}, job_id=job_id)
    send(db, rpc, reserve_action)
    content_hash = hashlib.sha256(b"Local transaction-layer fixture; no human task-quality claim").digest()
    submit = Action("submit", reservation, contributor, rpc.config.escrow, escrow_call("submit", [rid, content_hash]),
        {"name": "Submitted", "fields": {"jobId": "0x" + jid.hex(), "reservationId": "0x" + rid.hex(),
            "submissionHash": "0x" + content_hash.hex()}, "deadline_seconds": 72 * 3600}, job_id=job_id)
    send(db, rpc, submit)
    payout = Action("approve", reservation, accounts[1], rpc.config.escrow, escrow_call("approve", [rid]),
        {"name": "Paid", "fields": {"jobId": "0x" + jid.hex(), "reservationId": "0x" + rid.hex(),
            "recipient": contributor, "reward": 1_000_000}}, job_id=job_id)
    return payout


def token_balance(rpc, wallet):
    return int(rpc.rpc("eth_call", [{"to": rpc.config.token,
        "data": call_data("balanceOf(address)", ["address"], [wallet])}, "latest"]), 16)


def test_broadcast_restart_reuses_hash_and_pays_once(pg, chain):
    rpc, accounts = chain
    with Session(pg) as db:
        job_id, jid = funded(db, rpc, accounts)
        payout = submitted(db, rpc, accounts, job_id, jid)
        item = create_intent(db, rpc, payout)
        intent_id = item.id
        signed = sign_intent(db, rpc, intent_id, LocalUnlockedSigner(rpc, payout.sender))
        raw, tx_hash, nonce = signed.raw_transaction, signed.tx_hash, signed.nonce
        broadcast(db, rpc, intent_id)
        # Emulate loss of the RPC response/process after mining but before recognition.
        signed.state, signed.broadcast_at = "signed", None
        db.commit()
    with Session(pg) as db:
        recovered = sign_intent(db, rpc, intent_id, LocalUnlockedSigner(rpc, payout.sender))
        assert (recovered.raw_transaction, recovered.tx_hash, recovered.nonce) == (raw, tx_hash, nonce)
        broadcast(db, rpc, intent_id)  # Same signed bytes, never a new payment nonce.
        result = reconcile(db, rpc, intent_id)
        assert result.state == "confirmed"
        assert result.verified_event["recipient"] == accounts[2]
        assert token_balance(rpc, accounts[2]) == 1_000_000
        assert create_intent(db, rpc, payout).tx_hash == tx_hash
        assert len(db.scalars(select(TransactionIntent).where(TransactionIntent.kind == "approve")).all()) == 1


def test_reverted_payout_remains_unpaid_and_obligation_survives(pg, chain):
    rpc, accounts = chain
    with Session(pg) as db:
        job_id, jid = funded(db, rpc, accounts)
        payout = submitted(db, rpc, accounts, job_id, jid)
        item = create_intent(db, rpc, payout)
        sign_intent(db, rpc, item.id, LocalUnlockedSigner(rpc, payout.sender))
        failure = rpc.rpc("eth_sendTransaction", [{"from": accounts[0], "to": rpc.config.token,
            "data": call_data("setFailure(bool)", ["bool"], [True]), "gas": hex(100000)}])
        receipt(rpc, failure)
        broadcast(db, rpc, item.id)
        reverted = reconcile(db, rpc, item.id)
        assert reverted.state == "reverted" and reverted.verified_event is None
        assert token_balance(rpc, accounts[2]) == 0
        rid = resource_id(payout.resource_id)
        state = rpc.rpc("eth_call", [{"to": rpc.config.escrow, "data": escrow_call("reservations", [rid])}, "latest"])
        assert decode(["bytes32", "address", "uint256", "uint64", "uint64", "bytes32", "uint8"], bytes.fromhex(state[2:]))[-1] == 2


def test_pending_transaction_never_recognizes_payment(pg, chain):
    rpc, accounts = chain
    with Session(pg) as db:
        job_id, jid = funded(db, rpc, accounts)
        payout = submitted(db, rpc, accounts, job_id, jid)
        item = create_intent(db, rpc, payout)
        sign_intent(db, rpc, item.id, LocalUnlockedSigner(rpc, payout.sender))
        rpc.rpc("evm_setAutomine", [False])
        broadcast(db, rpc, item.id)
        assert reconcile(db, rpc, item.id).state == "broadcast"
        assert token_balance(rpc, accounts[2]) == 0
        rpc.rpc("evm_mine", [])
        assert reconcile(db, rpc, item.id).state == "confirmed"
        assert token_balance(rpc, accounts[2]) == 1_000_000


def test_wallet_cannot_attach_an_unrelated_transaction_or_change_terms(pg, chain):
    rpc, accounts = chain
    with Session(pg) as db:
        job_id, jid = funded(db, rpc, accounts)
        payout = submitted(db, rpc, accounts, job_id, jid)
        item = create_intent(db, rpc, payout)
        unrelated = rpc.rpc("eth_sendTransaction", [{"from": accounts[1], "to": accounts[2], "value": "0x0", "gas": hex(21000)}])
        receipt(rpc, unrelated)
        with pytest.raises(InvalidReceipt):
            attach_wallet_hash(db, rpc, item.id, accounts[1], unrelated)
        assert item.tx_hash is None and item.state == "intent"
        with pytest.raises(ChainFailure, match="does not own"):
            attach_wallet_hash(db, rpc, item.id, accounts[2], unrelated)
        approval = db.scalar(select(TransactionIntent).where(TransactionIntent.kind == "token_approve"))
        second = create_intent(db, rpc, Action("token_approve", secrets.token_hex(16), accounts[1], rpc.config.token,
            approval.call_data, approval.expected_event, job_id=job_id))
        with pytest.raises(ChainFailure, match="nonce already belongs"):
            attach_wallet_hash(db, rpc, second.id, accounts[1], approval.tx_hash)
        assert db.get(TransactionIntent, second.id).state == "intent"
        altered = Action(payout.kind, payout.resource_id, payout.sender, payout.destination,
            payout.data, {"name": "Paid", "fields": {**payout.expected_event["fields"], "reward": 2_000_000}}, job_id=job_id)
        with pytest.raises(ChainFailure, match="different immutable terms"):
            create_intent(db, rpc, altered)
        sign_intent(db, rpc, item.id, LocalUnlockedSigner(rpc, payout.sender))
        broadcast(db, rpc, item.id)
        assert reconcile(db, rpc, item.id).state == "confirmed"
        assert token_balance(rpc, accounts[2]) == 1_000_000


def test_wallet_funding_requires_receipts_and_publishes_only_once(pg, chain):
    from fastapi import HTTPException
    from framebounty.models import Job, Task
    rpc, accounts = chain
    with Session(pg) as db:
        job = create_job(db, accounts[1], example_plan())
        job_id, plan_hash = job.id, job.plan_hash
        with pytest.raises(HTTPException) as denied:
            funding_step(db, rpc, accounts[2], job_id, plan_hash, accounts[0])
        assert denied.value.status_code == 404
        db.rollback()
        step = funding_step(db, rpc, accounts[1], job_id, plan_hash, accounts[0])
        for expected_step in ["create_protected", "token_approve", "deposit"]:
            assert step["step"] == expected_step and not step["funded"]
            assert db.get(Job, job_id).deposited_atomic == 0
            assert db.scalars(select(Task).where(Task.job_id == job_id)).all() == []
            transaction = {key: value for key, value in step["transaction"].items() if key != "chainId"}
            transaction["gas"] = hex(500000)
            tx_hash = rpc.rpc("eth_sendTransaction", [transaction])
            receipt(rpc, tx_hash)
            step = funding_step(db, rpc, accounts[1], job_id, plan_hash, accounts[0], step["intent_id"], tx_hash)
        assert step["funded"] and step["deposited_atomic"] == "20000000"
        assert len(step["task_ids"]) == 1
        repeated = funding_step(db, rpc, accounts[1], job_id, plan_hash, accounts[0])
        assert repeated == step
        assert token_balance(rpc, accounts[1]) == 0
        assert token_balance(rpc, rpc.config.escrow) == 20_000_000
