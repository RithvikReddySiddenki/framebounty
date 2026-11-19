"""Final human funds release only. Batch membership and money are immutable.

V2 pays atomically in one wallet transaction. Existing V1 escrows retain their
funds/address and are guided through individual wallet approvals; never migrate
or claim those funds are in the new deployment.
"""
import hashlib
import os
from datetime import UTC, datetime

from eth_abi import encode
from eth_utils import keccak
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_wallet
from .chain_rpc import ChainFailure, address, escrow_call, resource_id
from .chain_workflow import project, wallet_step
from .db import session
from .funding_routes import configured_rpc
from .marketplace import audit, new_id
from .models import Job, PayoutBatch, Reservation, Submission, TransactionIntent
from .transactions import Action, attach_wallet_hash, create_intent, reconcile

router = APIRouter()


def allocate_remaining(db, job_id, batch_id):
    from .planning import next_collection_batch
    job = db.get(Job, job_id)
    if job.state == "open":
        next_collection_batch(db, job.buyer, job.id, "release-" + batch_id)


def prepare(db, wallet, job_id, request_id):
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
    if job is None or job.reviewer != wallet: raise HTTPException(404, "Owned collection not found")
    existing = db.scalar(select(PayoutBatch).where(PayoutBatch.job_id == job_id, PayoutBatch.request_id == request_id))
    if existing: return existing
    active = db.scalar(select(PayoutBatch).where(PayoutBatch.job_id == job_id, PayoutBatch.state == "prepared"))
    if active: return active
    items = db.scalars(select(Submission).where(Submission.job_id == job_id, Submission.state == "verified",
        Submission.review_deadline > datetime.now(UTC)).order_by(Submission.id).with_for_update()).all()
    if not items: raise HTTPException(409, "No AI-verified submissions are ready for funds release")
    if len(items) > 20: raise HTTPException(409, "Payout batch exceeds the approved collection bound")
    for item in items:
        reservation = db.get(Reservation, item.reservation_id)
        if reservation.state != ("fixture_submitted" if job.fixture else "submitted"):
            raise HTTPException(409, "A verified submission no longer has a payable reservation")
        if item.findings.get("verification", {}).get("decision") != "pass":
            raise HTTPException(409, "A submission lacks successful automatic verification")
        item.state = "release_pending"
    batch = PayoutBatch(id=new_id(), job_id=job.id, reviewer=wallet, request_id=request_id,
        submission_ids=[item.id for item in items], state="prepared")
    db.add(batch)
    audit(db, wallet, "buyer", "authorize_final_release", batch.id, {"submission_ids": batch.submission_ids})
    db.commit()
    return batch


def project_batch(db, rpc, intent_id):
    intent = db.get(TransactionIntent, intent_id)
    if intent is None or intent.kind != "approve_batch": raise ChainFailure("Unknown payout batch transaction")
    batch = db.get(PayoutBatch, intent.resource_id)
    job = db.scalar(select(Job).where(Job.id == batch.job_id).with_for_update().execution_options(populate_existing=True))
    batch = db.scalar(select(PayoutBatch).where(PayoutBatch.id == batch.id).with_for_update().execution_options(populate_existing=True))
    if intent.projected: return batch
    if intent.state not in {"confirmed", "reverted"}: return batch
    if intent.state == "reverted":
        # Keep membership fixed for audit/recovery; a reverted receipt pays none.
        batch.state = "reverted"
        for sid in batch.submission_ids:
            item = db.get(Submission, sid)
            if item.state == "release_pending": item.state = "verified"
    else:
        items = [db.get(Submission, sid) for sid in batch.submission_ids]
        reservations = [db.get(Reservation, item.reservation_id) for item in items]
        fields = {"jobId": "0x" + resource_id(job.id).hex(), "batchId": "0x" + resource_id(batch.id).hex(),
            "reviewer": batch.reviewer, "idsHash": "0x" + keccak(encode(["bytes32[]"], [[resource_id(r.id) for r in reservations]])).hex(),
            "total": sum(r.reward_atomic for r in reservations), "count": len(reservations)}
        if intent.destination.lower() != rpc.config.escrow.lower() or intent.verified_event != fields:
            raise ChainFailure("Batch receipt does not match every committed recipient/reward")
        if batch.state != "prepared" or any(item.state != "release_pending" or r.state != "submitted" for item, r in zip(items, reservations)):
            raise ChainFailure("Batch ledger state cannot recognize this payment")
        for item, reservation in zip(items, reservations):
            item.state, reservation.state = "accepted", "paid"
            job.committed_atomic -= reservation.reward_atomic
            job.paid_atomic += reservation.reward_atomic
        batch.state = "confirmed"
    intent.projected = True
    audit(db, batch.reviewer, "chain", "final_batch_" + batch.state, batch.id, {"transaction_hash": intent.tx_hash})
    db.commit()
    if batch.state == "confirmed": allocate_remaining(db, batch.job_id, batch.id)
    return batch


def release_step(db, rpc, wallet, job_id, request_id, intent_id=None, tx_hash=None):
    batch = prepare(db, wallet, job_id, request_id)
    job = db.get(Job, job_id)
    if batch.state == "confirmed":
        allocate_remaining(db, batch.job_id, batch.id)
        return {"confirmed": True, "fixture": job.fixture, "batch_id": batch.id, "state": "confirmed"}
    if job.fixture:
        if os.getenv("APP_MODE", "fixture") != "fixture": raise HTTPException(503, "Fixture release is disabled")
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
        batch = db.scalar(select(PayoutBatch).where(PayoutBatch.id == batch.id).with_for_update().execution_options(populate_existing=True))
        if batch.state != "confirmed":
            for sid in batch.submission_ids:
                item = db.get(Submission, sid)
                reservation = db.get(Reservation, item.reservation_id)
                if item.state != "release_pending" or reservation.state != "fixture_submitted":
                    raise HTTPException(409, "Fixture release state changed")
                item.state, reservation.state = "fixture_accepted", "fixture_accepted"
                job.committed_atomic -= reservation.reward_atomic
                job.paid_atomic += reservation.reward_atomic
            batch.state = "confirmed"
            db.commit()
            allocate_remaining(db, job_id, batch.id)
        return {"confirmed": True, "fixture": True, "batch_id": batch.id, "state": "confirmed"}
    rpc.check_contract()
    if rpc.contract_version == 1:
        # Legacy funds cannot be moved into V2 by a server configuration change.
        for sid in batch.submission_ids:
            item = db.get(Submission, sid)
            if item.state == "release_pending":
                item.state, item.review_reason = "accept_pending", "Final buyer release after automatic verification"
                db.commit()
            if item.state == "accepted": continue
            current = wallet_step(db, rpc, wallet, item.reservation_id, "review", intent_id, tx_hash)
            if not current["confirmed"]:
                return {**current, "confirmed": False, "batch_id": batch.id, "legacy": True}
            intent_id = tx_hash = None
        batch.state = "confirmed"; db.commit(); allocate_remaining(db, job_id, batch.id)
        return {"confirmed": True, "batch_id": batch.id, "legacy": True, "state": "confirmed"}
    items = [db.get(Submission, sid) for sid in batch.submission_ids]
    reservations = [db.get(Reservation, item.reservation_id) for item in items]
    ids = [resource_id(r.id) for r in reservations]
    fields = {"jobId": "0x" + resource_id(job.id).hex(), "batchId": "0x" + resource_id(batch.id).hex(), "reviewer": wallet,
        "idsHash": "0x" + keccak(encode(["bytes32[]"], [ids])).hex(), "total": sum(r.reward_atomic for r in reservations), "count": len(ids)}
    action = Action("approve_batch", batch.id, wallet, rpc.config.escrow, escrow_call("approveBatch", [resource_id(batch.id), ids]),
        {"name": "BatchPaid", "fields": fields}, job.id)
    transaction = create_intent(db, rpc, action)
    if intent_id:
        if intent_id != transaction.id or not tx_hash: raise HTTPException(409, "Payout transaction identity does not match this batch")
        transaction = attach_wallet_hash(db, rpc, transaction.id, wallet, tx_hash)
    elif transaction.tx_hash:
        transaction = reconcile(db, rpc, transaction.id)
    batch = project_batch(db, rpc, transaction.id)
    return {"confirmed": batch.state == "confirmed", "batch_id": batch.id, "intent_id": transaction.id,
        "state": transaction.state, "tx_hash": transaction.tx_hash, "amount_atomic": str(fields["total"]),
        "transaction": {"from": wallet, "to": action.destination, "data": action.data, "value": "0x0", "chainId": hex(rpc.config.chain_id)}}


class ReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = Field(strict=True)
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,64}$")
    intent_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    tx_hash: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{64}$")


@router.post("/jobs/{job_id}/release-funds")
def release_funds(job_id: str, body: ReleaseRequest, wallet: str = Depends(current_wallet),
                  db: Session = Depends(session)):
    if not body.confirmed: raise HTTPException(422, "Final funds release requires explicit buyer approval")
    job = db.get(Job, job_id)
    if job is None or job.reviewer != wallet: raise HTTPException(404, "Owned collection not found")
    if (body.intent_id is None) != (body.tx_hash is None): raise HTTPException(422, "Supply the transaction hash and intention together")
    if job.fixture: return release_step(db, None, wallet, job_id, body.request_id, body.intent_id, body.tx_hash)
    generator = configured_rpc(db, job_id=job_id)
    try:
        rpc = next(generator)
        return release_step(db, rpc, wallet, job_id, body.request_id, body.intent_id, body.tx_hash)
    except ChainFailure:
        db.rollback(); raise HTTPException(409, "Release remains unverified; reconcile the saved transaction before retrying") from None
    finally: generator.close()
