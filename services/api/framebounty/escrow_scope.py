"""Keep old funded jobs bound to their verified deployment after upgrades."""
from contextlib import contextmanager
from dataclasses import replace
from .chain_rpc import ChainRPC, ChainFailure
from .models import Job


@contextmanager
def scoped_rpc(db, job_id, rpc):
    job = db.get(Job, job_id)
    if job and job.chain_id is not None and job.chain_id != rpc.config.chain_id:
        raise ChainFailure("Funded collection belongs to another network")
    escrow = job.escrow_address if job and job.escrow_address else rpc.config.escrow
    if escrow.lower() == rpc.config.escrow.lower():
        yield rpc
    else:
        child = ChainRPC(replace(rpc.config, escrow=escrow))
        try: yield child
        finally: child.close()
