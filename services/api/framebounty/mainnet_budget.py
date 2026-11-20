"""Fail-closed cumulative cap for this operator's mainnet gas spending.

Reserve the full signed maximum before signing; unknown outcomes keep it held.
Only verified receipts release unused fee headroom. This file is private local
operator state, not a buyer budget or proof that customers have been paid.
"""
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .domain import parse_usdc
from .networks import active_network

MAX_AUTHORIZED_NATIVE = 10**18  # User authorized 1 USDC total; gas has 18 decimals.


class BudgetFailure(RuntimeError): pass


def path():
    configured = os.getenv("MAINNET_BUDGET_PATH")
    if configured:
        result = Path(configured).resolve()
        result.parent.mkdir(parents=True, exist_ok=True)
        return result
    root = Path(__file__).resolve().parents[3] / ".local"
    root.mkdir(exist_ok=True)
    return root / "mainnet-budget.json"


@contextmanager
def locked():
    state_path = path()
    with state_path.with_suffix(".lock").open("a+b") as lock:
        if lock.tell() == 0: lock.write(b"0"); lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            limit = parse_usdc(os.getenv("MAINNET_SPEND_LIMIT_USDC", "1.000000")) * 10**12
            if not 0 < limit <= MAX_AUTHORIZED_NATIVE: raise BudgetFailure("Budget exceeds the authorized 1-USDC cap")
            try: state = json.loads(state_path.read_text()) if state_path.exists() else {"limit": limit, "entries": {}}
            except (ValueError, OSError): raise BudgetFailure("Budget file is unavailable; no signature authorized") from None
            if state.get("limit") != limit or not isinstance(state.get("entries"), dict):
                raise BudgetFailure("Existing budget preserved; reconcile before changing its limit")
            yield state
            with tempfile.NamedTemporaryFile(mode="w", dir=state_path.parent, delete=False, encoding="utf-8") as target:
                temporary = Path(target.name)
                json.dump(state, target); target.flush(); os.fsync(target.fileno())
            try: os.replace(temporary, state_path)
            finally: temporary.unlink(missing_ok=True)
        finally:
            lock.seek(0)
            if os.name == "nt": msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(lock, fcntl.LOCK_UN)


def reserve(sender, unsigned):
    if unsigned["chainId"] != 5042: return
    if active_network().chain_id != 5042: raise BudgetFailure("Mainnet consent/configuration is missing")
    if unsigned.get("value", 0) != 0: raise BudgetFailure("Operator cannot transfer native principal")
    cap = unsigned["gas"] * unsigned["maxFeePerGas"]
    key = sender.lower() + ":" + str(unsigned["nonce"])
    commitment = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with locked() as state:
        previous = state["entries"].get(key)
        if previous:
            if previous["cap"] != cap or previous.get("commitment") != commitment:
                raise BudgetFailure("Nonce already has another reserved transaction")
            return
        used = sum(v.get("actual", v["cap"]) for v in state["entries"].values())
        if cap <= 0 or used + cap > state["limit"]: raise BudgetFailure("Mainnet budget exhausted; no new signature authorized")
        state["entries"][key] = {"cap": cap, "commitment": commitment}


def settle(sender, nonce, receipt):
    actual = int(receipt["gasUsed"], 16) * int(receipt["effectiveGasPrice"], 16)
    key = sender.lower() + ":" + str(nonce)
    with locked() as state:
        item = state["entries"].get(key)
        if item is None or actual > item["cap"] or ("actual" in item and item["actual"] != actual):
            raise BudgetFailure("Fee receipt does not match its reserved budget")
        item["actual"] = actual
