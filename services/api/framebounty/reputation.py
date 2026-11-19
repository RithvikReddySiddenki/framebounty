"""Counterparty ratings are wallet-signed and read from the job's exact escrow.

No API/operator can create votes. Immutable paid-trade votes and role-specific
counts are contract state. Public addresses/votes are permanently linkable.
"""
import hashlib
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import current_wallet
from .db import session
from .models import Job, Reservation, Submission
from .submissions import private_submission
from .funding_routes import configured_rpc
from .chain_rpc import ChainFailure, escrow_call, resource_id
from .chain_workflow import event_fields
from .transactions import Action, create_intent, attach_wallet_hash, reconcile

router = APIRouter()


@router.get("/jobs/{job_id}/reputation")
def buyer_reputation(job_id: str, db: Session = Depends(session)):
    job = db.get(Job, job_id)
    if job is None: raise HTTPException(404, "Post not found")
    if job.fixture: return {"supported": False, "notice": "Simulated post; no blockchain reputation"}
    generator = configured_rpc(db, job_id=job.id)
    try:
        rpc = next(generator); rpc.check_contract()
        if rpc.contract_version < 3: return {"supported": False, "notice": "Legacy escrow; no blockchain reputation"}
        up, down = rpc.read_escrow("buyerScores", [job.buyer])
        return {"supported": True, "wallet": job.buyer, "up": up, "down": down, "escrow": rpc.config.escrow}
    except ChainFailure: raise HTTPException(503, "Buyer reputation is unavailable") from None
    finally: generator.close()


def terms(db, wallet, sid):
    item = private_submission(db, sid, wallet)
    job = db.get(Job, item.job_id)
    reservation = db.get(Reservation, item.reservation_id)
    if wallet not in {job.buyer, reservation.wallet} or wallet == job.buyer == reservation.wallet:
        raise HTTPException(403, "Only distinct trade participants can rate each other")
    return item, job, reservation


def view(rpc, wallet, job, reservation):
    rpc.check_contract()
    if rpc.contract_version < 3: return {"supported": False, "notice": "This older escrow has no on-chain ratings"}
    buyer_role = wallet == reservation.wallet
    target = job.buyer if buyer_role else reservation.wallet
    up, down = rpc.read_escrow("buyerScores" if buyer_role else "contributorScores", [target])
    vote = rpc.read_escrow("votes", [resource_id(reservation.id), wallet])[0]
    paid = rpc.read_escrow("reservations", [resource_id(reservation.id)])[-1] == 3
    return {"supported": True, "target": target, "role": "buyer" if buyer_role else "contributor",
        "up": up, "down": down, "vote": vote, "eligible": paid and vote == 0,
        "escrow": rpc.config.escrow, "notice": "One permanent public vote per paid submission. Ratings are specific to this escrow."}


@router.get("/submissions/{submission_id}/reputation")
def rating(submission_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    item, job, reservation = terms(db, wallet, submission_id)
    if job.fixture: return {"supported": False, "notice": "Simulated trades do not create blockchain reputation"}
    generator = configured_rpc(db, job_id=job.id)
    try: return view(next(generator), wallet, job, reservation)
    except ChainFailure: raise HTTPException(503, "Reputation unavailable; no vote recorded") from None
    finally: generator.close()


class VoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vote: int = Field(strict=True, ge=-1, le=1)
    intent_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    tx_hash: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{64}$")


@router.post("/submissions/{submission_id}/reputation")
def rate(submission_id: str, body: VoteRequest, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    if body.vote not in {-1, 1}: raise HTTPException(422, "Vote must be up or down")
    if (body.intent_id is None) != (body.tx_hash is None): raise HTTPException(422, "Hash and intention must be supplied together")
    item, job, reservation = terms(db, wallet, submission_id)
    if job.fixture: raise HTTPException(409, "Fixture trades cannot generate reputation")
    generator = configured_rpc(db, job_id=job.id)
    try:
        rpc = next(generator)
        status = view(rpc, wallet, job, reservation)
        if not status["supported"]: raise HTTPException(409, status["notice"])
        if not status["eligible"] and status["vote"] != body.vote:
            raise HTTPException(409, "Only paid trades can be rated once")
        if status["vote"] == body.vote and body.intent_id is None:
            return {**status, "confirmed": True, "state": "confirmed"}
        key = hashlib.sha256(f"rating:{reservation.id}:{wallet}".encode()).hexdigest()
        action = Action("rate", key, wallet, rpc.config.escrow, escrow_call("rate", [resource_id(reservation.id), body.vote]),
            {"name": "Rated", "fields": {**event_fields(reservation), "voter": wallet, "target": status["target"],
                "buyerRole": status["role"] == "buyer", "vote": body.vote}}, job.id)
        intent = create_intent(db, rpc, action)
        if body.intent_id:
            if body.intent_id != intent.id: raise HTTPException(409, "Rating transaction identity changed")
            intent = attach_wallet_hash(db, rpc, intent.id, wallet, body.tx_hash)
        elif intent.tx_hash: intent = reconcile(db, rpc, intent.id)
        return {**status, "confirmed": intent.state == "confirmed", "state": intent.state, "intent_id": intent.id,
            "tx_hash": intent.tx_hash, "transaction": {"from": wallet, "to": rpc.config.escrow, "data": action.data,
                "value": "0x0", "chainId": hex(rpc.config.chain_id)}}
    except ChainFailure: raise HTTPException(409, "Rating remains unverified; reconcile the saved transaction") from None
    finally: generator.close()
