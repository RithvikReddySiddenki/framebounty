"""Attest verified content, then execute fixed permissionless payments after one hour.

The oracle cannot choose a payment destination/amount. Receipt and chain time,
never the model's prose or a broadcast hash, authorize ledger transitions.
"""
import hashlib
import json
from datetime import UTC, datetime
from sqlalchemy import select
from .chain_rpc import ChainFailure, escrow_call, resource_id
from .chain_workflow import records, event_fields, project
from .models import Submission, TransactionIntent
from dataclasses import replace
from .transactions import Action, create_intent, sign_intent, broadcast, reconcile


def sync_protected(db, rpc, reservation_id, signer):
    job, reservation = records(db, reservation_id)
    if job.protection_version < 3 or reservation.state != "submitted": return False
    item = db.scalar(select(Submission).where(Submission.reservation_id == reservation.id))
    if not item or item.state not in {"verified", "release_pending"}: return False
    rpc.check_contract()
    if rpc.contract_version < 3: raise ChainFailure("Protected job requires V3")
    if item.payment_due_at is None:
        if item.findings.get("verification", {}).get("decision") != "pass":
            raise ChainFailure("Only deterministic passing verification may be attested")
        terms = rpc.read_escrow("jobs", [resource_id(job.id)])
        if terms[2] != signer.address or signer.address in {job.buyer, job.reviewer}:
            raise ChainFailure("Only assigned independent oracle can attest")
        evidence = hashlib.sha256(json.dumps({"sha256": item.sha256, "rubric": item.rubric_hash,
            "assessment": item.findings.get("assessment")}, sort_keys=True).encode()).digest()
        action = Action("verify", reservation.id, signer.address, rpc.config.escrow,
            escrow_call("verify", [resource_id(reservation.id), evidence]),
            {"name": "Verified", "fields": {**event_fields(reservation), "evidenceHash": "0x" + evidence.hex()},
             "deadline_seconds": 3600, "deadline_field": "payAfter"}, job.id, reservation.id)
    else:
        chain_time = datetime.fromtimestamp(int(rpc.rpc("eth_getBlockByNumber", ["latest", False])["timestamp"], 16), UTC)
        if chain_time < item.payment_due_at: return False
        action = Action("settle", reservation.id, signer.address, rpc.config.escrow,
            escrow_call("settle", [resource_id(reservation.id)]),
            {"name": "Paid", "fields": {**event_fields(reservation), "recipient": reservation.wallet,
                "reward": reservation.reward_atomic}}, job.id, reservation.id)
    # A confirmed revert cannot be rebroadcast into success. Retry with a new
    # durable identity only after chain-time backoff; unknown hashes retain theirs.
    previous = db.scalars(select(TransactionIntent).where(TransactionIntent.reservation_id == reservation.id,
        TransactionIntent.kind == action.kind, TransactionIntent.state.in_(["reverted", "invalid"]))
        .order_by(TransactionIntent.created_at)).all()
    if previous:
        last = previous[-1]
        if last.state == "invalid": raise ChainFailure("Mismatched transaction needs reconciliation")
        failed_at = int(rpc.rpc("eth_getBlockByNumber", [hex(last.confirmed_block), False])["timestamp"], 16)
        now = int(rpc.rpc("eth_getBlockByNumber", ["latest", False])["timestamp"], 16)
        if now < failed_at + min(3600, 60 * 2 ** min(len(previous) - 1, 6)): return False
        action = replace(action, resource_id=hashlib.sha256(f"{action.kind}:{reservation.id}:{len(previous)}".encode()).hexdigest())
    db.commit()
    intent = create_intent(db, rpc, action)
    if intent.state == "intent": sign_intent(db, rpc, intent.id, signer)
    if intent.state in {"signed", "broadcast"}: broadcast(db, rpc, intent.id)
    reconcile(db, rpc, intent.id)
    project(db, rpc, intent.id)
    return True
