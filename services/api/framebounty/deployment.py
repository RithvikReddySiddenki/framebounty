"""Bounded canonical escrow deployment with exact signed-byte retry recovery.

Amounts here are native gas atoms (18 decimals). No job budget or contributor
payment is created. CLI state contains signed authorization bytes and stays private.
"""
import hashlib
import os
from contextlib import contextmanager

import rlp
from eth_abi import encode
from eth_account import Account
from eth_account.typed_transactions import TypedTransaction
from eth_utils import keccak
from hexbytes import HexBytes

from .chain_rpc import ChainFailure, ChainRPC, address, artifact, call_data, expected_runtime, hex_bytes

MAX_GAS = 3_000_000
MAX_FEE = 100_000_000_000  # 100 Gwei; at most 0.3 test USDC at MAX_GAS.


@contextmanager
def exclusive_state(path):
    """OS lock releases on crash; a stale lock-file never blocks reconciliation."""
    handle = path.open("a+b")
    locked = False
    try:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            raise ChainFailure("Another deployment process owns the saved state") from None
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def creation(token):
    return artifact()["creation_bytecode"] + encode(["address"], [address(token)]).hex()


def contract_address(wallet, nonce):
    return "0x" + keccak(rlp.encode([hex_bytes(address(wallet)), nonce]))[-20:].hex()


def prepare(rpc: ChainRPC, signer):
    rpc.check_network()
    decimals = rpc.rpc("eth_call", [{"to": rpc.config.token, "data": call_data("decimals()", [], [])}, "latest"])
    if int(decimals, 16) != 6:
        raise ChainFailure("Deployment requires the six-decimal USDC interface")
    data = creation(rpc.config.token)
    nonce = int(rpc.rpc("eth_getTransactionCount", [signer.address, "pending"]), 16)
    estimate = int(rpc.rpc("eth_estimateGas", [{"from": signer.address, "data": data, "value": "0x0"}]), 16)
    gas = estimate * 12 // 10 + 10000
    quote = int(rpc.rpc("eth_gasPrice", []), 16)
    fee = max(quote * 2, 20_000_000_000 if rpc.config.chain_id == 5042002 else 1)
    if not 21000 <= gas <= MAX_GAS or not 0 < fee <= MAX_FEE:
        raise ChainFailure("Deployment gas/fee exceeds the fixed safety limits")
    if int(rpc.rpc("eth_getBalance", [signer.address, "pending"]), 16) < gas * fee:
        raise ChainFailure("Allocator lacks the bounded native deployment fee")
    unsigned = {"chainId": rpc.config.chain_id, "nonce": nonce, "data": data, "value": 0,
        "gas": gas, "type": 2, "maxFeePerGas": fee, "maxPriorityFeePerGas": min(quote // 10, 1_000_000_000)}
    raw = signer.sign(rpc, unsigned)
    record = {"chain_id": rpc.config.chain_id, "sender": signer.address, "token": address(rpc.config.token),
        "address": contract_address(signer.address, nonce), "nonce": nonce, "unsigned": unsigned,
        "raw_transaction": raw, "tx_hash": "0x" + keccak(hex_bytes(raw)).hex(), "state": "signed",
        "creation_sha256": hashlib.sha256(hex_bytes(data)).hexdigest()}
    validate(rpc, record)
    return record


def validate(rpc, record):
    rpc.check_network()
    if record["chain_id"] != rpc.config.chain_id or record["token"] != address(rpc.config.token):
        raise ChainFailure("Saved deployment belongs to another network/token")
    unsigned = record["unsigned"]
    if unsigned["data"] != creation(rpc.config.token) or unsigned["value"] != 0 or unsigned["chainId"] != rpc.config.chain_id:
        raise ChainFailure("Saved deployment differs from canonical creation")
    if not 21000 <= unsigned["gas"] <= MAX_GAS or not 0 < unsigned["maxFeePerGas"] <= MAX_FEE:
        raise ChainFailure("Saved deployment exceeds gas safety limits")
    raw = record["raw_transaction"]
    signed = TypedTransaction.from_bytes(HexBytes(raw)).as_dict()
    if signed.get("to") not in {b"", None}:
        raise ChainFailure("Deployment must not transfer to another destination")
    for key, value in unsigned.items():
        actual = signed.get(key)
        if key == "data":
            actual, value = bytes(actual), hex_bytes(value)
        if actual != value:
            raise ChainFailure("Saved signature changed deployment terms")
    if (Account.recover_transaction(raw).lower() != address(record["sender"])
        or record["tx_hash"] != "0x" + keccak(hex_bytes(raw)).hex()
        or unsigned["nonce"] != record["nonce"]
        or record["address"] != contract_address(record["sender"], record["nonce"])):
        raise ChainFailure("Saved deployment signature/identity mismatch")


def reconcile(rpc, record):
    validate(rpc, record)
    receipt = rpc.rpc("eth_getTransactionReceipt", [record["tx_hash"]])
    if receipt is None:
        return False
    tx = rpc.rpc("eth_getTransactionByHash", [record["tx_hash"]])
    if (tx is None or tx["hash"].lower() != record["tx_hash"] or tx["from"].lower() != record["sender"] or tx["to"] is not None
        or tx["input"].lower() != record["unsigned"]["data"].lower()
        or int(tx["value"], 16) != 0 or int(tx["nonce"], 16) != record["nonce"]
        or receipt["transactionHash"].lower() != record["tx_hash"]):
        raise ChainFailure("Deployment receipt does not match its saved transaction")
    block = rpc.rpc("eth_getBlockByNumber", [receipt["blockNumber"], False])
    if block is None or block["hash"].lower() != receipt["blockHash"].lower():
        return False
    if int(receipt["status"], 16) == 0:
        record["state"] = "reverted"
        return True
    if int(receipt["status"], 16) != 1 or address(receipt["contractAddress"]) != record["address"]:
        raise ChainFailure("Successful deployment has an unexpected contract address")
    runtime = hex_bytes(rpc.rpc("eth_getCode", [record["address"], "latest"]))
    if runtime != expected_runtime(rpc.config.token):
        raise ChainFailure("Deployed escrow runtime does not match the canonical artifact")
    record.update(state="confirmed", block_number=int(receipt["blockNumber"], 16),
        gas_used=int(receipt["gasUsed"], 16), gas_cost_native_atomic=str(int(receipt["gasUsed"], 16) * int(receipt["effectiveGasPrice"], 16)))
    return True


def broadcast(rpc, record):
    validate(rpc, record)
    if reconcile(rpc, record):
        return
    try:
        returned = rpc.rpc("eth_sendRawTransaction", [record["raw_transaction"]])
        if returned.lower() != record["tx_hash"]:
            raise ChainFailure("Provider returned another deployment hash")
        record["state"] = "broadcast"
    except ChainFailure:
        # Lost response may follow successful inclusion. Never make another nonce.
        record["state"] = "unknown"
