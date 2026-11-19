"""Wallet-owned chain actions and explicitly requested allocator reconciliation."""
import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from .auth import current_wallet
from .chain_rpc import ChainFailure, ChainRPC
from .chain_workflow import records, sync_allocation, wallet_step
from .db import session
from .funding_routes import funding_rpc
from .transactions import KeySigner

router = APIRouter()


def allocation_signer():
    key = os.getenv("ARC_ALLOCATOR_PRIVATE_KEY", "")
    if not key:
        return None
    try:
        return KeySigner(key)
    except ChainFailure:
        raise HTTPException(503, "Allocator signing is not configured correctly") from None


@router.post("/reservations/{reservation_id}/sync")
def sync(reservation_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session),
         rpc: ChainRPC = Depends(funding_rpc), signer=Depends(allocation_signer)):
    job, reservation = records(db, reservation_id, wallet)
    if wallet not in {reservation.wallet, job.buyer, job.reviewer}:
        raise HTTPException(404, "Reservation not found")
    try:
        if reservation.state == "reserve_pending":
            if signer is None:
                raise HTTPException(503, "Reservation pending; configure the dedicated allocator before dispatch")
            reservation = sync_allocation(db, rpc, reservation_id, signer)
        return {"id": reservation.id, "state": reservation.state}
    except ChainFailure:
        db.rollback()
        raise HTTPException(503, "Chain outcome remains unverified; the existing obligation is retained") from None


class WalletRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purpose: Literal["submit", "review", "release"]
    confirmed: bool = Field(strict=True)
    intent_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    tx_hash: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{64}$")

    @model_validator(mode="after")
    def paired(self):
        if (self.intent_id is None) != (self.tx_hash is None):
            raise ValueError("Supply the transaction hash and intention together")
        return self


@router.post("/reservations/{reservation_id}/chain")
def chain_action(reservation_id: str, body: WalletRequest, wallet: str = Depends(current_wallet),
                 db: Session = Depends(session), rpc: ChainRPC = Depends(funding_rpc)):
    if not body.confirmed:
        raise HTTPException(422, "Explicit transaction confirmation is required")
    try:
        return wallet_step(db, rpc, wallet, reservation_id, body.purpose, body.intent_id, body.tx_hash)
    except ChainFailure:
        db.rollback()
        raise HTTPException(409, "Could not verify this action; reconcile its existing transaction before retrying") from None
