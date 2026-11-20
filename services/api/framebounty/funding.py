"""Buyer-only fixed-budget funding, with chain evidence before publication.

The server supplies calldata from the saved plan. Wallets retain their keys and
must separately authorize creation, allowance and deposit. This service cannot
reserve work or authorize quality/payment.
"""
from fastapi import HTTPException
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from .chain_rpc import ChainFailure, ChainRPC, address, call_data, escrow_call, resource_id
from .domain import Plan
from .marketplace import audit
from .models import Job, Task, TransactionIntent
from .planning import create_batch
from .transactions import Action, attach_wallet_hash, create_intent, reconcile


def owned_job(db: Session, wallet: str, job_id: str, plan_hash: str) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
    if job is None or job.buyer != address(wallet):
        raise HTTPException(404, "Job not found")
    if job.archived:
        raise HTTPException(409, "This post is archived; create a new post")
    if job.fixture or job.state not in {"draft", "open"}:
        raise HTTPException(409, "Only a real draft or funded job can use chain funding")
    if job.plan_hash != plan_hash:
        raise HTTPException(409, "Plan changed; confirm the saved plan again")
    return job


def actions(rpc: ChainRPC, job: Job, allocator: str) -> list[Action]:
    if address(allocator) in {job.buyer, job.reviewer}:
        raise ChainFailure("Use a dedicated non-reviewer allocator wallet")
    plan = Plan.model_validate(job.plan)
    jid = resource_id(job.id)
    fields = {"jobId": "0x" + jid.hex()}
    rpc.check_contract()
    if plan.verification_policy == "ai" and rpc.contract_version < 3 and job.escrow_address is None:
        raise HTTPException(409, "New automatic posts require the protected V3 escrow; legacy funded posts retain their original contract")
    protected = rpc.contract_version >= 3 and plan.verification_policy == "ai"
    if protected:
        job.protection_version = 3
        if job.expires_at is None:
            job.expires_at = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=plan.posting_hours)
        if job.expires_at <= datetime.now(UTC) and job.state == "draft":
            raise HTTPException(409, "Publication deadline expired; create a new post")
    create_args = [jid, job.reviewer, address(allocator), bytes.fromhex(job.plan_hash), plan.review_hours * 3600]
    if protected: create_args += [int(job.expires_at.timestamp()), plan.expected_minutes * 60]
    return [
        Action("create_protected" if protected else "create_job", job.id, job.buyer, rpc.config.escrow,
            escrow_call("createProtectedJob" if protected else "createJob", create_args),
            {"name": "JobCreated", "fields": {**fields, "buyer": job.buyer, "reviewer": job.reviewer,
                "allocator": address(allocator), "rubric": "0x" + job.plan_hash, "reviewSeconds": plan.review_hours * 3600}}, job_id=job.id),
        Action("token_approve", job.id, job.buyer, rpc.config.token,
            call_data("approve(address,uint256)", ["address", "uint256"], [rpc.config.escrow, plan.budget_atomic]),
            {"name": "Approval", "fields": {"owner": job.buyer, "spender": rpc.config.escrow, "value": plan.budget_atomic}}, job_id=job.id),
        Action("deposit", job.id, job.buyer, rpc.config.escrow, escrow_call("deposit", [jid, plan.budget_atomic]),
            {"name": "Deposited", "fields": {**fields, "amount": plan.budget_atomic}}, job_id=job.id),
    ]


def project_funding(db: Session, rpc: ChainRPC, job_id: str, wallet: str, plan_hash: str, allocator: str) -> Job:
    job = owned_job(db, wallet, job_id, plan_hash)
    expected = actions(rpc, job, allocator)
    for action in expected:
        item = db.scalar(select(TransactionIntent).where(TransactionIntent.chain_id == rpc.config.chain_id,
            TransactionIntent.kind == action.kind, TransactionIntent.resource_id == job.id))
        if item is None or item.state != "confirmed" or item.expected_event != action.expected_event or item.call_data != action.data:
            raise HTTPException(409, "All funding steps require verified successful receipts")
    rpc.check_contract()
    # Do not publish from an old deposit event after an external close/refund or
    # allocation. The allocator must be dedicated to this application's ledger.
    values = rpc.read_escrow("jobs", [resource_id(job.id)])
    plan = Plan.model_validate(job.plan)
    if values[:5] != (job.buyer, job.reviewer, address(allocator), bytes.fromhex(plan_hash), plan.review_hours * 3600) or values[5]:
        raise ChainFailure("Current escrow terms no longer match this open job")
    if values[6:] != (plan.budget_atomic, job.committed_atomic, job.paid_atomic, job.refunded_atomic):
        raise ChainFailure("Current escrow accounting differs from the application ledger")
    if job.protection_version >= 3 and rpc.read_escrow("protections", [resource_id(job.id)]) != (
        int(job.expires_at.timestamp()), plan.expected_minutes * 60, 3600):
        raise ChainFailure("Protected deadline/duration differs from the approved terms")
    if job.state == "draft":
        job.deposited_atomic, job.state = plan.budget_atomic, "open"
        # Reuse the same bounded first-batch policy as explicit fixture funding.
        ids = create_batch(db, job, min(2, plan.total), [item.key for item in plan.requirements])
        audit(db, wallet, "buyer", "verified_chain_funding", job.id,
            {"plan_hash": plan_hash, "deposited_atomic": str(plan.budget_atomic), "task_ids": ids,
             "chain_id": rpc.config.chain_id, "escrow": rpc.config.escrow})
        db.commit()
    return job


def funding_step(db: Session, rpc: ChainRPC, wallet: str, job_id: str, plan_hash: str, allocator: str,
                 intent_id: str | None = None, tx_hash: str | None = None) -> dict:
    job = owned_job(db, wallet, job_id, plan_hash)
    expected = actions(rpc, job, allocator)
    # Release the owner read lock before transaction-intent locks; publication
    # later locks the job again. Every request rechecks immutable plan ownership.
    db.commit()
    for action in expected:
        item = create_intent(db, rpc, action)
        if intent_id == item.id and tx_hash is not None:
            item = attach_wallet_hash(db, rpc, item.id, wallet, tx_hash)
            intent_id, tx_hash = None, None
        elif item.tx_hash:
            item = reconcile(db, rpc, item.id)
        if item.state != "confirmed":
            if intent_id is not None and intent_id != item.id:
                raise HTTPException(409, "Complete the current funding step first")
            return {"funded": False, "step": action.kind, "intent_id": item.id, "state": item.state,
                "tx_hash": item.tx_hash, "chain_id": rpc.config.chain_id,
                "transaction": {"from": wallet, "to": action.destination, "data": action.data, "value": "0x0", "chainId": hex(rpc.config.chain_id)},
                "amount_atomic": str(job.plan["budget_atomic"]), "last_error": item.last_error}
    if intent_id is not None:
        raise HTTPException(409, "Unknown funding transaction intention")
    job = project_funding(db, rpc, job_id, wallet, plan_hash, allocator)
    return {"funded": True, "state": job.state, "deposited_atomic": str(job.deposited_atomic),
        "task_ids": list(db.scalars(select(Task.id).where(Task.job_id == job.id))), "chain_id": rpc.config.chain_id}
