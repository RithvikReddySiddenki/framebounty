"""Non-paying automatic rejection/expiry. Never authorizes a payout."""
import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from sqlalchemy import select
from .chain_rpc import ChainFailure, escrow_call, resource_id
from .chain_workflow import records, event_fields, wallet_action, project
from .models import Submission
from .transactions import Action, create_intent, sign_intent, broadcast, reconcile


def sync_failure_or_deadline(db, rpc, reservation_id, signer):
    job, reservation = records(db, reservation_id)
    submission = db.scalar(select(Submission).where(Submission.reservation_id == reservation_id))
    rpc.check_contract()
    chain_time = datetime.fromtimestamp(int(rpc.rpc("eth_getBlockByNumber", ["latest", False])["timestamp"], 16), UTC)
    failed = submission and submission.state == "verification_rejected" and submission.findings.get("verification", {}).get("decision") == "reject"
    if failed and reservation.state == "submitted" and rpc.contract_version >= 2 and (job.protection_version >= 3 or submission.review_deadline > chain_time):
        terms = rpc.read_escrow("jobs", [resource_id(job.id)])
        if signer.address != terms[2] or signer.address in {job.buyer, job.reviewer}:
            raise ChainFailure("Only the assigned dedicated verifier can dispatch automatic rejection")
        reason = hashlib.sha256(submission.review_reason.encode()).digest()
        action = Action("verify_reject", reservation.id, signer.address, rpc.config.escrow,
            escrow_call("rejectVerification", [resource_id(reservation.id), reason]),
            {"name": "Released", "fields": {**event_fields(reservation), "terminalState": 4,
                "reasonHash": "0x" + reason.hex(), "reward": reservation.reward_atomic}}, job.id, reservation.id)
    elif ((reservation.state == "reserved" and reservation.expires_at <= chain_time) or
          (reservation.state == "submitted" and submission and job.protection_version < 3 and submission.review_deadline <= chain_time)):
        # These deadline releases are permissionless even in the old deployment.
        action = replace(wallet_action(db, rpc, reservation.wallet, reservation.id, "release"), sender=signer.address)
    else:
        if failed and rpc.contract_version == 1:
            submission.findings = {**submission.findings, "verification": {
                **submission.findings["verification"], "legacy_release_wait": True,
                "budget_release_notice": "Original escrow commitment releases at its on-chain timeout; no reviewer rejection transaction is required."}}
            db.commit()
        else: db.rollback()
        return False
    db.commit()
    item = create_intent(db, rpc, action)
    if item.state == "intent": sign_intent(db, rpc, item.id, signer)
    if item.state in {"signed", "broadcast"}: broadcast(db, rpc, item.id)
    reconcile(db, rpc, item.id)
    project(db, rpc, item.id)
    return True
