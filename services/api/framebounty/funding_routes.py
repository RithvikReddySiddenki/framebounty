"""Explicitly gated wallet funding routes. No signing keys enter HTTP handlers."""
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from .arc import CHAIN_ID, USDC_ADDRESS
from .auth import current_wallet
from .chain_rpc import ChainConfig, ChainFailure, ChainRPC, address
from .db import session
from .funding import funding_step

router = APIRouter()


def funding_rpc():
    if os.getenv("APP_MODE") != "testnet" or os.getenv("ALLOW_CHAIN_TRANSACTIONS") != "true":
        raise HTTPException(503, "Chain funding is disabled; no transaction was requested")
    try:
        rpc = ChainRPC(ChainConfig(os.getenv("ARC_RPC_URL", ""), CHAIN_ID,
            os.getenv("ARC_ESCROW_ADDRESS", ""), USDC_ADDRESS))
    except ChainFailure:
        raise HTTPException(503, "Configure and verify the deployed Arc testnet escrow first") from None
    try:
        yield rpc
    finally:
        rpc.close()


class FundingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: bool = Field(strict=True)
    intent_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    tx_hash: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{64}$")

    @model_validator(mode="after")
    def paired_transaction(self):
        if (self.intent_id is None) != (self.tx_hash is None):
            raise ValueError("Transaction hash and intention identity must be supplied together")
        return self


@router.post("/jobs/{job_id}/funding")
def post_funding(job_id: str, body: FundingRequest, wallet: str = Depends(current_wallet),
                 db: Session = Depends(session), rpc: ChainRPC = Depends(funding_rpc)):
    if not body.confirmed:
        raise HTTPException(422, "Explicit saved-plan funding confirmation is required")
    try:
        allocator = address(os.getenv("ARC_ALLOCATOR_ADDRESS", ""))
        return funding_step(db, rpc, wallet, job_id, body.plan_hash, allocator, body.intent_id, body.tx_hash)
    except ChainFailure:
        db.rollback()
        raise HTTPException(409, "Chain funding could not be verified; reconcile the existing transaction before retrying") from None
