"""Validate hosted configuration before migrations or background processes start."""
import os
from pathlib import Path
from urllib.parse import urlparse
from sqlalchemy.engine import make_url

from .networks import active_network, chain_enabled
from .object_storage import private_storage

def data_volume_mounted():
    """A writable directory alone is not proof the operator ledger survives deploys."""
    try:
        return any(line.split()[4] == "/data" for line in Path("/proc/self/mountinfo").read_text().splitlines())
    except (OSError, IndexError): return False


def validate():
    origin = urlparse(os.getenv("AUTH_ORIGIN", ""))
    if (origin.scheme != "https" or not origin.hostname or origin.path or origin.query
            or origin.fragment or origin.username or origin.password):
        raise ValueError("AUTH_ORIGIN must be the exact HTTPS frontend origin, without a trailing slash")
    if not os.getenv("DATABASE_URL"): raise ValueError("DATABASE_URL is required")
    database = make_url(os.environ["DATABASE_URL"])
    if database.port == 6543 or database.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("Hosted PostgreSQL requires TLS and a session/direct connection, not transaction pooling")
    if os.getenv("STORAGE_BACKEND") != "supabase":
        raise ValueError("Hosted deployment requires private Supabase storage")
    if os.getenv("DATABASE_SCHEMA") != "framebounty":
        raise ValueError("Hosted application tables must use the private framebounty schema")
    storage = private_storage()
    with storage.client() as client: storage.check_private(client)
    network = active_network()
    worker = os.getenv("RUN_CHAIN_WORKER", "false") == "true"
    if worker != chain_enabled():
        raise ValueError("RUN_CHAIN_WORKER must match the explicitly enabled chain transaction mode")
    if network.real_money and worker:
        budget = os.getenv("MAINNET_BUDGET_PATH", "")
        if not budget or not Path(budget).resolve().is_relative_to(Path("/data").resolve()) or not data_volume_mounted():
            raise ValueError("Mainnet operator budget must live on the persistent /data volume")
    return {"configuration": "valid", "network": network.chain_id, "chain_worker": worker}


if __name__ == "__main__":
    try:
        import json
        print(json.dumps(validate()))
    except Exception:
        # Provider/DB configuration exceptions may contain secret request details.
        raise SystemExit("Hosted configuration failed validation. Check the deployment guide and private service variables.") from None
