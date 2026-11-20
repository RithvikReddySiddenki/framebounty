"""Reconcile durable actions, verification attestations and fixed permissionless payments.

Never signs contributor hashes, refunds or buyer approvals. V3 settlement executes only an attested, fixed reward after its chain deadline. Deterministic policy may authorize rejection. Wallet hashes
must first be attached by authenticated owners. Logs contain public IDs only.
"""
import argparse
import logging
import os
import time
from datetime import UTC, datetime

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from .arc import USDC_ADDRESS
from .networks import active_network, chain_enabled
from .chain_rpc import ChainConfig, ChainFailure, ChainRPC
from .chain_workflow import project, sync_allocation
from .db import engine
from .models import Job, Reservation, TransactionIntent, Submission
from .transactions import KeySigner, reconcile
from .escrow_scope import scoped_rpc
from .verification_chain import sync_failure_or_deadline

log = logging.getLogger("framebounty.chain_worker")


def run_once(db_engine, rpc, signer):
    try:
        chain_time = datetime.fromtimestamp(int(rpc.rpc("eth_getBlockByNumber", ["latest", False])["timestamp"], 16), UTC)
    except (ChainFailure, KeyError, TypeError, ValueError):
        chain_time = None  # Unknown chain time can never authorize a deadline release.
    with Session(db_engine) as db:
        protected = list(db.scalars(select(Reservation.id).join(Job, Job.id == Reservation.job_id).join(Submission, Submission.reservation_id == Reservation.id).where(
            Job.protection_version >= 3, Reservation.state == "submitted", Submission.state.in_(["verified", "release_pending"])).limit(100)))
        pending = list(db.scalars(select(Reservation.id).where(Reservation.state == "reserve_pending").limit(50)))
        transactions = list(db.scalars(select(TransactionIntent.id).where(TransactionIntent.reservation_id.is_not(None),
            TransactionIntent.projected.is_(False),
            TransactionIntent.state.in_(["signed", "broadcast", "confirmed", "reverted"])).limit(100)))
        batches = list(db.scalars(select(TransactionIntent.id).where(TransactionIntent.kind == "approve_batch",
            TransactionIntent.projected.is_(False), TransactionIntent.state.in_(["broadcast", "confirmed", "reverted"])).limit(50)))
        deadlines = list(db.scalars(select(Reservation.id).outerjoin(Submission, Submission.reservation_id == Reservation.id).where(or_(
            (Reservation.state == "reserved") & (Reservation.expires_at <= chain_time),
            (Reservation.state == "submitted") & or_(Submission.review_deadline <= chain_time,
                (Submission.state == "verification_rejected") & or_(
                    Submission.findings["verification"]["legacy_release_wait"].as_boolean().is_(None),
                    Submission.findings["verification"]["legacy_release_wait"].as_boolean() == False)))).limit(100))) if chain_time else []
    for rid in pending:
        with Session(db_engine) as db:
            try:
                reservation = db.get(Reservation, rid)
                with scoped_rpc(db, reservation.job_id, rpc) as active:
                    sync_allocation(db, active, rid, signer)
            except ChainFailure:
                db.rollback()
                log.warning("allocation_pending reservation_id=%s", rid)
    for intent_id in transactions:
        with Session(db_engine) as db:
            try:
                intent = db.get(TransactionIntent, intent_id)
                with scoped_rpc(db, intent.job_id, rpc) as active:
                    reconcile(db, active, intent_id)
                    project(db, active, intent_id)
            except ChainFailure:
                db.rollback()
                log.warning("reconciliation_pending intent_id=%s", intent_id)
    for intent_id in batches:
        with Session(db_engine) as db:
            try:
                from .payouts import project_batch
                intent = db.get(TransactionIntent, intent_id)
                with scoped_rpc(db, intent.job_id, rpc) as active:
                    reconcile(db, active, intent_id); project_batch(db, active, intent_id)
            except ChainFailure:
                db.rollback(); log.warning("batch_release_pending intent_id=%s", intent_id)
    for rid in deadlines:
        with Session(db_engine) as db:
            try:
                reservation = db.get(Reservation, rid)
                with scoped_rpc(db, reservation.job_id, rpc) as active:
                    sync_failure_or_deadline(db, active, rid, signer)
            except ChainFailure:
                db.rollback(); log.warning("automatic_release_pending reservation_id=%s", rid)
    for rid in protected:
        with Session(db_engine) as db:
            try:
                from .protected_chain import sync_protected
                reservation = db.get(Reservation, rid)
                with scoped_rpc(db, reservation.job_id, rpc) as active:
                    sync_protected(db, active, rid, signer)
            except ChainFailure:
                db.rollback(); log.warning("protected_settlement_pending reservation_id=%s", rid)
    return len(pending) + len(transactions) + len(batches) + len(protected)


def main():
    parser = argparse.ArgumentParser(description="Dispatch reservations and reconcile receipts; never approve quality")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not chain_enabled():
        raise SystemExit("Explicit matching network mode and chain transaction consent are required")
    try:
        signer = KeySigner(os.getenv("ARC_ALLOCATOR_PRIVATE_KEY", ""))
        if signer.address != os.getenv("ARC_ALLOCATOR_ADDRESS", "").lower():
            raise ChainFailure("Allocator address/key mismatch")
        rpc = ChainRPC(ChainConfig(os.getenv("ARC_RPC_URL", ""), active_network().chain_id, os.getenv("ARC_ESCROW_ADDRESS", ""), USDC_ADDRESS))
        rpc.check_contract()
    except ChainFailure:
        raise SystemExit("Verify the dedicated allocator and deployed escrow network configuration") from None
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
