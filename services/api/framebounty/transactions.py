"""Durable signed intentions. Broadcast is never payment recognition.

Controllers must authorize the immutable domain action before creating an Action.
Models are not given this interface. Signed bytes are private authorization data:
persist them for safe restart recovery, never log or return them to agent/UI callers.
"""
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from eth_account import Account
from eth_account.typed_transactions import TypedTransaction
from eth_abi import decode
from eth_utils import keccak
from hexbytes import HexBytes
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .chain_rpc import ChainFailure, ChainRPC, InvalidReceipt, address, artifact, call_data, hex_bytes
from .models import TransactionIntent


KINDS = {"create_job": ("createJob", "JobCreated"), "token_approve": ("tokenApprove", "Approval"),
    "deposit": ("deposit", "Deposited"), "reserve": ("reserve", "Reserved"),
    "submit": ("submit", "Submitted"), "approve": ("approve", "Paid"),
    "reject": ("reject", "Released"), "expire": ("expire", "Released"),
    "timeout": ("timeout", "Released"), "close": ("close", "Closed"), "refund": ("refund", "Refunded"),
    "verify_reject": ("rejectVerification", "Released"), "approve_batch": ("approveBatch", "BatchPaid")}
KINDS.update({"create_protected": ("createProtectedJob", "JobCreated"),
    "verify": ("verify", "Verified"), "settle": ("settle", "Paid"), "rate": ("rate", "Rated")})


@dataclass(frozen=True)
class Action:
    kind: str
    resource_id: str
    sender: str
    destination: str
    data: str
    expected_event: dict
    job_id: str | None = None
    reservation_id: str | None = None


class KeySigner:
    """Dedicated allocator signer; never instantiate with a buyer/reviewer key."""
    def __init__(self, private_key: str):
        try:
            self._account = Account.from_key(private_key)
        except (ValueError, TypeError):
            raise ChainFailure("Allocator signer configuration is invalid") from None
        self.address = self._account.address.lower()

    def sign(self, rpc: ChainRPC, unsigned: dict) -> str:
        if rpc.config.chain_id == 5042:
            from .mainnet_budget import reserve, BudgetFailure
            try: reserve(self.address, unsigned)
            except (BudgetFailure, ValueError, OSError): raise ChainFailure("Mainnet operator budget/configuration prevents signing") from None
        signed = self._account.sign_transaction(unsigned)
        return "0x" + bytes(signed.raw_transaction).hex()


class LocalUnlockedSigner:
    """Test-only node signer: refuses every non-loopback or non-local network."""
    def __init__(self, rpc: ChainRPC, wallet: str):
        parsed = urlparse(rpc.config.rpc_url)
        if rpc.config.chain_id != 31337 or not rpc.config.allow_local or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ChainFailure("Unlocked signing is restricted to the isolated local test chain")
        self.address = address(wallet)

    def sign(self, rpc: ChainRPC, unsigned: dict) -> str:
        transaction = {key: hex(value) if isinstance(value, int) else value for key, value in unsigned.items()}
        transaction["from"] = self.address
        result = rpc.rpc("eth_signTransaction", [transaction])
        return result["raw"] if isinstance(result, dict) else result


def validate_action(rpc: ChainRPC, action: Action):
    if action.kind not in KINDS or not 1 <= len(action.resource_id) <= 64:
        raise ChainFailure("Unknown action identity")
    function, event = KINDS[action.kind]
    if action.expected_event.get("name") != event:
        raise ChainFailure("Action and receipt-event schema disagree")
    if action.kind == "token_approve":
        selector = call_data("approve(address,uint256)", ["address", "uint256"], [rpc.config.escrow, 1])[:10]
        if address(action.destination) != address(rpc.config.token):
            raise ChainFailure("Token approval has an invalid destination")
        if action.expected_event["fields"].get("owner") != address(action.sender) or action.expected_event["fields"].get("spender") != address(rpc.config.escrow):
            raise ChainFailure("Approval must be scoped to this owner and escrow")
        spender, amount = decode(["address", "uint256"], hex_bytes(action.data)[4:])
        if address(spender) != address(rpc.config.escrow) or amount != action.expected_event["fields"].get("value"):
            raise ChainFailure("Approval calldata differs from the committed spender/amount")
    else:
        definitions = [item for item in artifact()["abi"]
                       if item.get("type") == "function" and item["name"] == function]
        types = [item["type"] for item in definitions[0]["inputs"]]
        selector = "0x" + keccak(text=function + "(" + ",".join(types) + ")")[:4].hex()
        if address(action.destination) != address(rpc.config.escrow):
            raise ChainFailure("Escrow action has an invalid destination")
    if action.data[:10].lower() != selector.lower():
        raise ChainFailure("Action calldata does not match its fixed operation")


def create_intent(db: Session, rpc: ChainRPC, action: Action) -> TransactionIntent:
    validate_action(rpc, action)
    rpc.check_contract()
    if action.job_id:
        from .models import Job
        job = db.get(Job, action.job_id)
        if job and job.chain_id is None: job.chain_id = rpc.config.chain_id
        elif job and job.chain_id != rpc.config.chain_id: raise ChainFailure("Job belongs to another network")
        if job and job.escrow_address is None:
            job.escrow_address = address(rpc.config.escrow)
        elif job and job.escrow_address != address(rpc.config.escrow):
            raise ChainFailure("This job is bound to another deployed escrow")
    key = hashlib.sha256(f"tx:{rpc.config.chain_id}:{action.kind}:{action.resource_id}".encode()).hexdigest()
    values = dict(id=key, chain_id=rpc.config.chain_id, kind=action.kind, resource_id=action.resource_id,
        job_id=action.job_id, reservation_id=action.reservation_id, sender=address(action.sender),
        destination=address(action.destination), call_data=action.data.lower(), expected_event=action.expected_event,
        unsigned={}, state="intent", start_block=int(rpc.rpc("eth_blockNumber", []), 16))
    db.execute(insert(TransactionIntent).values(**values).on_conflict_do_nothing(index_elements=["id"]))
    db.commit()
    item = db.get(TransactionIntent, key)
    if (item.sender, item.destination, item.call_data, item.expected_event) != (values["sender"], values["destination"], values["call_data"], values["expected_event"]):
        raise ChainFailure("Transaction identity was reused for different immutable terms")
    return item


def sign_intent(db: Session, rpc: ChainRPC, intent_id: str, signer: KeySigner | LocalUnlockedSigner) -> TransactionIntent:
    item = db.scalar(select(TransactionIntent).where(TransactionIntent.id == intent_id).with_for_update().execution_options(populate_existing=True))
    if item is None or item.sender != signer.address or item.chain_id != rpc.config.chain_id:
        raise ChainFailure("Signer does not own this network/action intention")
    if item.state != "intent":
        return item
    # Per-signer cross-process lock; max persisted nonce also counts signed intents
    # that have not yet reached the node's pending pool after a worker restart.
    lock_key = int.from_bytes(hashlib.sha256(f"nonce:{item.chain_id}:{item.sender}".encode()).digest()[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    network_nonce = int(rpc.rpc("eth_getTransactionCount", [item.sender, "pending"]), 16)
    previous = db.scalar(select(func.max(TransactionIntent.nonce)).where(TransactionIntent.chain_id == item.chain_id,
                                                                        TransactionIntent.sender == item.sender))
    nonce = max(network_nonce, previous + 1 if previous is not None else 0)
    if not 0 <= nonce < 2**63:
        raise ChainFailure("Signer nonce is outside application limits")
    unsigned = rpc.build_unsigned(item.sender, item.destination, item.call_data, nonce)
    raw = signer.sign(rpc, unsigned)
    raw_bytes = hex_bytes(raw)
    if Account.recover_transaction(raw).lower() != item.sender:
        raise ChainFailure("Signed transaction does not belong to the committed signer")
    decoded = TypedTransaction.from_bytes(HexBytes(raw)).as_dict()
    for field, value in unsigned.items():
        actual = decoded.get(field)
        if field in {"to", "data"}:
            if bytes(actual) != hex_bytes(value):
                raise ChainFailure("Signer changed the committed transaction")
        elif actual != value:
            raise ChainFailure("Signer changed the committed transaction")
    item.nonce, item.unsigned, item.raw_transaction = nonce, unsigned, raw
    item.tx_hash, item.state = "0x" + keccak(raw_bytes).hex(), "signed"
    db.commit()  # Signed bytes/hash are durable BEFORE any broadcast happens.
    return item


def broadcast(db: Session, rpc: ChainRPC, intent_id: str) -> TransactionIntent:
    item = db.get(TransactionIntent, intent_id)
    if item is None or not item.raw_transaction or item.state not in {"signed", "broadcast"}:
        raise ChainFailure("No prepared signed transaction is available")
    check_intent_config(item, rpc)
    rpc.check_contract()
    try:
        returned = rpc.rpc("eth_sendRawTransaction", [item.raw_transaction])
        if returned.lower() != item.tx_hash:
            raise InvalidReceipt("Broadcast hash differs from the persisted signed transaction")
        item.state, item.broadcast_at, item.last_error = "broadcast", datetime.now(UTC), None
    except ChainFailure:
        # The network may have accepted the bytes before losing its response.
        # Keep the SAME signature/nonce/hash for receipt reconciliation or retry.
        item.last_error = "Broadcast outcome uncertain; reconcile the existing hash before retrying"
    db.commit()
    return item


def reconcile(db: Session, rpc: ChainRPC, intent_id: str) -> TransactionIntent:
    item = db.scalar(select(TransactionIntent).where(TransactionIntent.id == intent_id).with_for_update().execution_options(populate_existing=True))
    if item is None:
        raise ChainFailure("Unknown transaction intention")
    check_intent_config(item, rpc)
    if item.state in {"confirmed", "reverted", "invalid"}:
        return item
    if not item.tx_hash:
        return item
    try:
        result = rpc.verified_receipt(item.tx_hash, item.sender, item.destination, item.call_data, item.expected_event, item.nonce)
        if result is None:
            return item
        if item.chain_id == 5042 and item.raw_transaction is not None:
            from .mainnet_budget import settle, BudgetFailure
            try: settle(item.sender, item.nonce, result["receipt"])
            except (BudgetFailure, ValueError, OSError): raise ChainFailure("Mainnet fee budget requires reconciliation") from None
        item.state = result["status"]
        item.confirmed_block = int(result["receipt"]["blockNumber"], 16)
        item.verified_event = result.get("event")
        item.last_error = None if item.state == "confirmed" else "Transaction reverted; no funding/payment recognized"
    except InvalidReceipt:
        item.state, item.last_error = "invalid", "Receipt/transaction does not match the committed action"
    except ChainFailure:
        item.last_error = "Provider unavailable; transaction outcome remains pending"
    db.commit()
    return item


def attach_wallet_hash(db: Session, rpc: ChainRPC, intent_id: str, wallet: str, tx_hash: str) -> TransactionIntent:
    item = db.scalar(select(TransactionIntent).where(TransactionIntent.id == intent_id).with_for_update().execution_options(populate_existing=True))
    if item is None or item.sender != address(wallet) or item.raw_transaction is not None:
        raise ChainFailure("Wallet does not own this external-wallet intention")
    check_intent_config(item, rpc)
    if item.tx_hash is not None and item.tx_hash != tx_hash.lower():
        raise ChainFailure("Intention already tracks another transaction; reconcile its hash")
    if item.state in {"confirmed", "reverted", "invalid"}:
        if item.tx_hash != tx_hash.lower():
            raise ChainFailure("Intention already has a terminal chain result")
        return item
    transaction = rpc.verify_transaction(tx_hash, item.sender, item.destination, item.call_data)
    if transaction is None:
        raise ChainFailure("Transaction is not yet visible; retry the same hash")
    item.tx_hash, item.nonce, item.state = tx_hash.lower(), int(transaction["nonce"], 16), "broadcast"
    item.broadcast_at = datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ChainFailure("Wallet transaction nonce already belongs to another intention") from None
    return reconcile(db, rpc, intent_id)


def check_intent_config(item: TransactionIntent, rpc: ChainRPC):
    if item.chain_id != rpc.config.chain_id or item.destination.lower() not in {rpc.config.escrow.lower(), rpc.config.token.lower()}:
        raise ChainFailure("Intention belongs to a different network or contract configuration")
