"""Prepare/reconcile one canonical Arc testnet deployment; --broadcast opts in.

Load .env with scripts/load-env.ps1 first. Signed authorization data stays in
ignored .local; only public identifiers and native gas bounds reach stdout.
"""
import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from framebounty.arc import CHAIN_ID, USDC_ADDRESS
from framebounty.chain_rpc import ChainConfig, ChainFailure, ChainRPC
from framebounty.deployment import broadcast, exclusive_state, prepare, reconcile, validate
from framebounty.transactions import KeySigner


def save(path, record):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix="deployment-", delete=False) as output:
            temporary = Path(output.name)
            json.dump(record, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def configure(root, contract, replace_existing=None):
    path = root / ".env"
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    entries = [line for line in lines if line.startswith("ARC_ESCROW_ADDRESS=")]
    allowed = {"", contract.lower()}
    if replace_existing: allowed.add(replace_existing.lower())
    if len(entries) != 1 or entries[0].split("=", 1)[1].strip().lower() not in allowed:
        raise ChainFailure("Existing escrow configuration preserved; inspect it before replacing")
    # The key-bearing file never enters output or source control. Preserve every
    # other setting, particularly the disabled transaction/model flags.
    updated = "\n".join("ARC_ESCROW_ADDRESS=" + contract if line.startswith("ARC_ESCROW_ADDRESS=") else line for line in lines) + "\n"
    temporary = root / ".env.deployment.tmp"
    created = False
    try:
        with temporary.open("x", encoding="utf-8") as target:
            created = True
            target.write(updated)
            target.flush()
            os.fsync(target.fileno())
        if path.read_text(encoding="utf-8") != original:
            raise ChainFailure("Environment changed during deployment; configuration preserved")
        os.replace(temporary, path)
    finally:
        if created:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Bounded Arc TESTNET escrow deployment, never mainnet")
    parser.add_argument("--broadcast", action="store_true")
    parser.add_argument("--state-file", default=".local/arc-deployment.json", help="Workspace .local file; retain a separate signed state for each escrow version")
    parser.add_argument("--replace-existing", help="Explicit previous default address; existing jobs must already be pinned by migration 0006")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    (root / ".local").mkdir(exist_ok=True)
    with exclusive_state(root / ".local/arc-deployment.lock"):
        execute(root, args)


def execute(root, args):
    path = (root / getattr(args, "state_file", ".local/arc-deployment.json")).resolve()
    if path.parent != (root / ".local").resolve() or path.suffix != ".json":
        raise SystemExit("Deployment state must remain a JSON file in this workspace's .local directory")
    path.parent.mkdir(exist_ok=True)
    if os.getenv("ARC_CHAIN_ID") != str(CHAIN_ID):
        raise SystemExit("Only explicitly configured Arc testnet 5042002 is allowed")
    if os.getenv("ALLOW_CHAIN_TRANSACTIONS") != "false":
        raise SystemExit("Keep application chain actions disabled during deployment setup")
    signer = KeySigner(os.getenv("ARC_ALLOCATOR_PRIVATE_KEY", ""))
    if signer.address != os.getenv("ARC_ALLOCATOR_ADDRESS", "").lower():
        raise SystemExit("Allocator key/address mismatch")
    rpc = ChainRPC(ChainConfig(os.getenv("ARC_RPC_URL", ""), CHAIN_ID, "0x" + "1" * 40, USDC_ADDRESS))
    try:
        record = json.loads(path.read_text()) if path.exists() else prepare(rpc, signer)
        validate(rpc, record)
        if record["sender"] != signer.address:
            raise ChainFailure("Saved deployment belongs to another allocator")
        save(path, record)  # Durable raw/hash BEFORE any network broadcast.
        settled = reconcile(rpc, record)
        if args.broadcast and not settled:
            broadcast(rpc, record)
            save(path, record)
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline and not reconcile(rpc, record):
                time.sleep(1)
        save(path, record)
        if record["state"] == "confirmed":
            configure(root, record["address"], getattr(args, "replace_existing", None))
        print(json.dumps({"state": record["state"], "contract": record["address"], "transaction": record["tx_hash"],
            "chain_id": record["chain_id"], "maximum_fee_native_atomic": str(record["unsigned"]["gas"] * record["unsigned"]["maxFeePerGas"]),
            "gas_cost_native_atomic": record.get("gas_cost_native_atomic")}, indent=2))
    except ChainFailure:
        raise SystemExit("Deployment not verified. Preserve the existing state/hash and reconcile before any new attempt") from None
    finally:
        rpc.close()


if __name__ == "__main__":
    main()
