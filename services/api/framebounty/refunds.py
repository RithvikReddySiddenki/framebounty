"""Buyer recovery of unused protected budget after expiry; commitments stay locked."""
import hashlib
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .auth import current_wallet
from .db import session
from .models import Job, TransactionIntent
from .chain_rpc import ChainFailure, escrow_call, resource_id
from .funding_routes import configured_rpc
from .payouts import ReleaseRequest
from .transactions import Action, create_intent, attach_wallet_hash, reconcile

router = APIRouter()


def refund_step(db, rpc, wallet, job_id, request_id, intent_id=None, tx_hash=None):
    job = db.get(Job, job_id)
    if not job or job.buyer != wallet: raise HTTPException(404, "Owned post not found")
    if job.fixture or job.protection_version < 3: raise HTTPException(409, "This action requires a protected post")
    now = datetime.fromtimestamp(int(rpc.rpc("eth_getBlockByNumber", ["latest", False])["timestamp"], 16), UTC)
    if not job.expires_at or now < job.expires_at: raise HTTPException(409, "Budget is locked until the published deadline")
    jid = resource_id(job.id)
    close = Action("close", job.id, wallet, rpc.config.escrow, escrow_call("close", [jid]),
        {"name": "Closed", "fields": {"jobId": "0x" + jid.hex()}}, job.id)
    key = hashlib.sha256(f"refund:{job.id}:{request_id}".encode()).hexdigest()
    for closing in [True, False]:
        if closing:
            action = close
        else:
            # A retry keeps the original amount even if later rejected work frees
            # additional budget. Another explicit action may recover that remainder.
            existing = db.get(TransactionIntent, hashlib.sha256(f"tx:{rpc.config.chain_id}:refund:{key}".encode()).hexdigest())
            amount = existing.expected_event["fields"]["amount"] if existing else (
                job.deposited_atomic - job.committed_atomic - job.paid_atomic - job.refunded_atomic)
            if amount <= 0: return {"funded": True, "state": "confirmed", "amount_atomic": "0"}
            action = Action("refund", key, wallet, rpc.config.escrow, escrow_call("refund", [jid, resource_id(key), amount]),
                {"name": "Refunded", "fields": {"jobId": "0x" + jid.hex(), "refundId": "0x" + resource_id(key).hex(),
                    "buyer": wallet, "amount": amount}}, job.id)
        intent = create_intent(db, rpc, action)
        if intent_id == intent.id and tx_hash:
            intent = attach_wallet_hash(db, rpc, intent.id, wallet, tx_hash); intent_id = tx_hash = None
        elif intent.tx_hash: intent = reconcile(db, rpc, intent.id)
        if intent.state != "confirmed":
            if intent_id: raise HTTPException(409, "Reconcile the current refund step first")
            return {"funded": False, "state": intent.state, "intent_id": intent.id, "tx_hash": intent.tx_hash,
                "transaction": {"from": wallet, "to": action.destination, "data": action.data, "value": "0x0", "chainId": hex(rpc.config.chain_id)}}
        if not intent.projected:
            db.refresh(job, with_for_update=True)
            db.refresh(intent)  # A concurrent retry may have projected while we waited.
            if not intent.projected:
                if closing: job.state = "closed"
                else:
                    if amount > job.deposited_atomic - job.committed_atomic - job.paid_atomic - job.refunded_atomic:
                        raise ChainFailure("Refund receipt requires ledger reconciliation")
                    job.refunded_atomic += amount
                intent.projected = True
            db.commit()
    if intent_id: raise HTTPException(409, "Unknown refund transaction identity")
    return {"funded": True, "state": "confirmed", "amount_atomic": str(amount)}


@router.post("/jobs/{job_id}/refund-unused")
def refund_unused(job_id: str, body: ReleaseRequest, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    if not body.confirmed: raise HTTPException(422, "Explicit refund authorization required")
    if (body.intent_id is None) != (body.tx_hash is None): raise HTTPException(422, "Supply the hash and intention together")
    job = db.get(Job, job_id)
    if not job or job.buyer != wallet: raise HTTPException(404, "Owned post not found")
    generator = configured_rpc(db, job_id=job.id)
    try: return refund_step(db, next(generator), wallet, job_id, body.request_id, body.intent_id, body.tx_hash)
    except ChainFailure: raise HTTPException(409, "Refund is unverified; reconcile the saved transaction") from None
    finally: generator.close()
