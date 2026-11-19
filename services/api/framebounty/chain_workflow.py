"""Receipt-gated reservation, submission and human-review ledger projection.

The database holds pending allocations before dispatch, so concurrent contributors
cannot oversubscribe while RPC is slow. Unknown outcomes keep their obligations.
Only the allocator signs automatically; contributor/reviewer actions require their
own wallet. Models have no interface to create review decisions or signatures.
"""
import hashlib
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .chain_rpc import ChainFailure, ChainRPC, address, escrow_call, resource_id
from .marketplace import audit, new_id
from .models import Job, Reservation, Submission, Task, TransactionIntent, VerificationJob
from .transactions import Action, attach_wallet_hash, broadcast, create_intent, reconcile, sign_intent


def records(db, reservation_id, wallet=None):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(404, "Reservation not found")
    job = db.get(Job, reservation.job_id)
    if wallet is not None and wallet not in {reservation.wallet, job.buyer, job.reviewer}:
        raise HTTPException(404, "Reservation not found")
    if job.fixture:
        raise HTTPException(409, "Fixture obligations cannot use chain transactions")
    return job, reservation


def event_fields(reservation):
    return {"jobId": "0x" + resource_id(reservation.job_id).hex(),
            "reservationId": "0x" + resource_id(reservation.id).hex()}


def project(db: Session, rpc: ChainRPC, intent_id: str) -> Reservation:
    intent = db.get(TransactionIntent, intent_id)
    if intent is None or intent.reservation_id is None or intent.chain_id != rpc.config.chain_id:
        raise ChainFailure("Unknown reservation transaction")
    if intent.projected:
        return db.get(Reservation, intent.reservation_id)
    reference = db.get(Reservation, intent.reservation_id)
    job = db.scalar(select(Job).where(Job.id == reference.job_id).with_for_update().execution_options(populate_existing=True))
    reservation = db.scalar(select(Reservation).where(Reservation.id == reference.id).with_for_update().execution_options(populate_existing=True))
    submission = db.scalar(select(Submission).where(Submission.reservation_id == reservation.id).with_for_update())
    before = reservation.state
    if job.fixture or intent.job_id != job.id or intent.destination.lower() != rpc.config.escrow.lower():
        raise ChainFailure("Chain projection belongs to different immutable terms")
    if intent.state not in {"confirmed", "reverted"}:
        return reservation  # Unknown evidence never releases an obligation.
    if intent.state == "reverted" and intent.kind == "reserve" and reservation.state == "reserve_pending":
        reservation.state = "reserve_failed"
        job.committed_atomic -= reservation.reward_atomic
        db.get(Task, reservation.task_id).claimed -= 1
    elif intent.state == "confirmed":
        fields = intent.verified_event or {}
        if any(fields.get(key) != value for key, value in event_fields(reservation).items()):
            raise ChainFailure("Receipt belongs to another reservation")
        if intent.kind == "reserve" and reservation.state == "reserve_pending":
            if fields.get("recipient") != reservation.wallet or fields.get("reward") != reservation.reward_atomic:
                raise ChainFailure("Receipt changed recipient/reward")
            reservation.state = "reserved"
        elif intent.kind == "submit" and reservation.state == "reserved":
            if submission is None or fields.get("submissionHash") != "0x" + submission.sha256:
                raise ChainFailure("Receipt changed the uploaded content hash")
            submission.review_deadline = datetime.fromtimestamp(fields["reviewDeadline"], UTC)
            submission.state, reservation.state = "queued", "submitted"
            db.add(VerificationJob(id=new_id(), submission_id=submission.id, state="queued", attempts=0))
        elif intent.kind == "approve" and reservation.state == "submitted":
            if submission is None or submission.state != "accept_pending" or fields.get("recipient") != reservation.wallet or fields.get("reward") != reservation.reward_atomic:
                raise ChainFailure("Payment lacks its matching human-reviewed decision")
            reservation.state, submission.state = "paid", "accepted"
            job.committed_atomic -= reservation.reward_atomic
            job.paid_atomic += reservation.reward_atomic
        elif intent.kind in {"reject", "verify_reject", "expire", "timeout"}:
            expected = {"reject": ("submitted", 4, "rejected"), "verify_reject": ("submitted", 4, "rejected"), "expire": ("reserved", 5, "expired"), "timeout": ("submitted", 6, "timed_out")}[intent.kind]
            if reservation.state == expected[0]:
                if fields.get("terminalState") != expected[1] or fields.get("reward") != reservation.reward_atomic:
                    raise ChainFailure("Release event changed the obligation")
                if intent.kind == "reject" and (submission is None or submission.state != "reject_pending"):
                    raise ChainFailure("Rejection lacks the human reviewer decision")
                if intent.kind == "verify_reject" and (submission is None or submission.state != "verification_rejected"
                        or submission.findings.get("verification", {}).get("decision") != "reject"):
                    raise ChainFailure("Rejection lacks a deterministic verification failure")
                reservation.state = expected[2]
                if submission:
                    submission.state = expected[2]
                job.committed_atomic -= reservation.reward_atomic
                db.get(Task, reservation.task_id).claimed -= 1
    db.flush()
    if reservation.state != before:
        audit(db, intent.sender, "chain", "verified_" + intent.kind, reservation.id,
            {"transaction_hash": intent.tx_hash, "state": reservation.state})
    intent.projected = True
    db.commit()
    return reservation


def sync_allocation(db: Session, rpc: ChainRPC, reservation_id: str, signer) -> Reservation:
    job, reservation = records(db, reservation_id)
    if reservation.state != "reserve_pending":
        return reservation
    if signer.address in {job.buyer, job.reviewer}:
        raise ChainFailure("Allocator signing must use a dedicated non-reviewer wallet")
    terms = rpc.read_escrow("jobs", [resource_id(job.id)])
    if terms[0] != job.buyer or terms[1] != job.reviewer or terms[2] != signer.address or terms[3] != bytes.fromhex(job.plan_hash):
        raise ChainFailure("Allocator does not own this funded job's immutable terms")
    action = Action("reserve", reservation.id, signer.address, rpc.config.escrow,
        escrow_call("reserve", [resource_id(job.id), resource_id(reservation.id), reservation.wallet,
            reservation.reward_atomic, int(reservation.expires_at.timestamp())]),
        {"name": "Reserved", "fields": {**event_fields(reservation), "recipient": reservation.wallet,
            "reward": reservation.reward_atomic, "expiresAt": int(reservation.expires_at.timestamp())}}, job_id=job.id, reservation_id=reservation.id)
    item = create_intent(db, rpc, action)
    if item.state == "intent":
        sign_intent(db, rpc, item.id, signer)
    if item.state in {"signed", "broadcast"}:
        broadcast(db, rpc, item.id)
    reconcile(db, rpc, item.id)
    return project(db, rpc, item.id)


def wallet_action(db, rpc, wallet, reservation_id, purpose):
    job, reservation = records(db, reservation_id, wallet)
    if wallet not in {reservation.wallet, job.buyer, job.reviewer}:
        raise HTTPException(404, "Reservation not found")
    submission = db.scalar(select(Submission).where(Submission.reservation_id == reservation.id))
    fields = event_fields(reservation)
    rid = resource_id(reservation.id)
    if purpose == "submit":
        if wallet != reservation.wallet:
            raise HTTPException(403, "Only the contributor confirms uploaded content")
        if submission is None:
            raise HTTPException(409, "Upload your video first")
        return Action("submit", reservation.id, wallet, rpc.config.escrow,
            escrow_call("submit", [rid, bytes.fromhex(submission.sha256)]),
            {"name": "Submitted", "fields": {**fields, "submissionHash": "0x" + submission.sha256},
             "deadline_seconds": job.plan["review_hours"] * 3600}, job.id, reservation.id)
    if purpose == "review":
        if wallet != job.reviewer:
            raise HTTPException(403, "Only the designated human reviewer authorizes this decision")
        if submission is None or submission.state not in {"accept_pending", "reject_pending", "accepted", "rejected"}:
            raise HTTPException(409, "Record the human review decision first")
        accept = submission.state in {"accept_pending", "accepted"}
        kind = "approve" if accept else "reject"
        reason = hashlib.sha256(submission.review_reason.encode()).digest()
        arguments = [rid] if accept else [rid, reason]
        expected = {**fields, "recipient": reservation.wallet, "reward": reservation.reward_atomic} if accept else {
            **fields, "terminalState": 4, "reasonHash": "0x" + reason.hex(), "reward": reservation.reward_atomic}
        return Action(kind, reservation.id, wallet, rpc.config.escrow, escrow_call(kind, arguments),
            {"name": "Paid" if accept else "Released", "fields": expected}, job.id, reservation.id)
    if purpose == "release":
        if reservation.state not in {"reserved", "submitted", "expired", "timed_out"}:
            raise HTTPException(409, "No expirable chain obligation exists")
        timeout = reservation.state in {"submitted", "timed_out"}
        kind = "timeout" if timeout else "expire"
        return Action(kind, reservation.id, wallet, rpc.config.escrow, escrow_call(kind, [rid]),
            {"name": "Released", "fields": {**fields, "terminalState": 6 if timeout else 5,
                "reasonHash": "0x" + "00" * 32, "reward": reservation.reward_atomic}}, job.id, reservation.id)
    raise HTTPException(422, "Unknown wallet action")


def wallet_step(db, rpc, wallet, reservation_id, purpose, intent_id=None, tx_hash=None):
    action = wallet_action(db, rpc, address(wallet), reservation_id, purpose)
    item = create_intent(db, rpc, action)
    if intent_id is not None:
        if intent_id != item.id or tx_hash is None:
            raise HTTPException(409, "Transaction identity does not match this action")
        item = attach_wallet_hash(db, rpc, item.id, wallet, tx_hash)
    elif item.tx_hash:
        item = reconcile(db, rpc, item.id)
    reservation = project(db, rpc, item.id)
    return {"intent_id": item.id, "state": item.state, "reservation_state": reservation.state,
        "tx_hash": item.tx_hash, "confirmed": item.state == "confirmed", "step": action.kind,
        "transaction": {"from": action.sender, "to": action.destination, "data": action.data,
            "value": "0x0", "chainId": hex(rpc.config.chain_id)}}
