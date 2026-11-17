"""Reconcile durable chain actions; only reserve dispatch uses the allocator key.

Never signs quality decisions, submit hashes, refunds or payouts. Wallet hashes
must first be attached by authenticated owners. Logs contain public IDs only.
"""
import argparse
import logging
import os
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .arc import CHAIN_ID, USDC_ADDRESS
from .chain_rpc import ChainConfig, ChainFailure, ChainRPC
from .chain_workflow import project, sync_allocation
from .db import engine
from .models import Reservation, TransactionIntent
from .transactions import KeySigner, reconcile

log = logging.getLogger("framebounty.chain_worker")


def run_once(db_engine, rpc, signer):
    with Session(db_engine) as db:
        pending = list(db.scalars(select(Reservation.id).where(Reservation.state == "reserve_pending").limit(50)))
        transactions = list(db.scalars(select(TransactionIntent.id).where(TransactionIntent.reservation_id.is_not(None),
            TransactionIntent.projected.is_(False),
            TransactionIntent.state.in_(["signed", "broadcast", "confirmed", "reverted"])).limit(100)))
    for rid in pending:
        with Session(db_engine) as db:
            try:
                sync_allocation(db, rpc, rid, signer)
            except ChainFailure:
                db.rollback()
                log.warning("allocation_pending reservation_id=%s", rid)
    for intent_id in transactions:
        with Session(db_engine) as db:
            try:
                reconcile(db, rpc, intent_id)
                project(db, rpc, intent_id)
            except ChainFailure:
                db.rollback()
                log.warning("reconciliation_pending intent_id=%s", intent_id)
    return len(pending) + len(transactions)


def main():
    parser = argparse.ArgumentParser(description="Dispatch reservations and reconcile receipts; never approve quality")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if os.getenv("APP_MODE") != "testnet" or os.getenv("ALLOW_CHAIN_TRANSACTIONS") != "true":
        raise SystemExit("Explicit testnet mode and chain transaction consent are required")
    try:
        signer = KeySigner(os.getenv("ARC_ALLOCATOR_PRIVATE_KEY", ""))
        if signer.address != os.getenv("ARC_ALLOCATOR_ADDRESS", "").lower():
            raise ChainFailure("Allocator address/key mismatch")
        rpc = ChainRPC(ChainConfig(os.getenv("ARC_RPC_URL", ""), CHAIN_ID, os.getenv("ARC_ESCROW_ADDRESS", ""), USDC_ADDRESS))
        rpc.check_contract()
    except ChainFailure:
        raise SystemExit("Verify the dedicated allocator and deployed testnet escrow configuration") from None
    try:
        while True:
            run_once(engine(), rpc, signer)
            if args.once:
                return
            time.sleep(2)
    finally:
        rpc.close()


if __name__ == "__main__":
    main()
