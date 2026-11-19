"""Keep old funded jobs bound to their verified deployment after upgrades."""
from contextlib import contextmanager
from dataclasses import replace
from .chain_rpc import ChainRPC
from .models import Job


@contextmanager
def scoped_rpc(db, job_id, rpc):
    job = db.get(Job, job_id)
    escrow = job.escrow_address if job and job.escrow_address else rpc.config.escrow
    if escrow.lower() == rpc.config.escrow.lower():
        yield rpc
    else:
        child = ChainRPC(replace(rpc.config, escrow=escrow))
        try: yield child
        finally: child.close()
