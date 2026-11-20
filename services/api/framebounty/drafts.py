"""Remove unpublished drafts without deleting chain evidence or hiding funds."""
from contextlib import contextmanager
from fastapi import HTTPException
from sqlalchemy import select
from .models import Job, Reservation, TransactionIntent
from .marketplace import audit
from .chain_rpc import ChainFailure, resource_id

def check_chain_unfunded(db, job):
    if job.fixture or not job.escrow_address: return
    from .funding_routes import configured_rpc
    try:
        with contextmanager(configured_rpc)(db, job.id) as rpc:
            rpc.check_contract()
            terms = rpc.read_escrow("jobs", [resource_id(job.id)])
            if any(terms[6:]):
                raise HTTPException(409, "This escrow holds funding history. Use its refund process instead.")
    except ChainFailure:
        raise HTTPException(503, "Could not verify escrow funding. Retry removal after the network recovers.") from None

def remove_draft(db, wallet, job_id):
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
    if job is None or job.buyer != wallet: raise HTTPException(404, "Owned post not found")
    if job.archived: return {"removed": True}
    if job.state != "draft" or any((job.deposited_atomic, job.committed_atomic, job.paid_atomic, job.refunded_atomic)):
        raise HTTPException(409, "Only unpublished, unfunded drafts can be removed. Funded posts use their refund process.")
    if db.scalar(select(Reservation.id).where(Reservation.job_id == job.id).limit(1)):
        raise HTTPException(409, "This post has contributor obligations and cannot be removed as a draft.")
    # A Circle deposit may have been approved even if its hash has not reached
    # this API yet. An unconfirmed deposit must never be treated as zero funds.
    if db.scalar(select(TransactionIntent.id).where(TransactionIntent.job_id == job.id,
            TransactionIntent.kind == "deposit", TransactionIntent.state != "reverted").limit(1)):
        raise HTTPException(409, "A deposit was prepared or is awaiting confirmation. Reconcile funding before removing this post.")
    check_chain_unfunded(db, job)
    job.archived = True
    audit(db, wallet, "buyer", "remove_unfunded_draft", job.id, {"financial_records_preserved": True})
    db.commit()
    return {"removed": True}
