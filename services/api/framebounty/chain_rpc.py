"""Strict Arc/local JSON-RPC and canonical ABI boundary; no model tools or keys.

All contract amounts use six-decimal ERC-20 atoms. Gas/fee quantities use native
eighteen-decimal units. The local network is an explicit test exception, not Arc
evidence. Receipt recognition checks the actual transaction and escrow event.
"""
import json
import re
from dataclasses import dataclass
from importlib.resources import files
from urllib.parse import urlparse

import httpx
from eth_abi import decode, encode
from eth_abi.exceptions import DecodingError
from eth_utils import keccak, to_checksum_address

from .arc import CHAIN_ID, USDC_ADDRESS


class ChainFailure(RuntimeError):
    pass


class InvalidReceipt(ChainFailure):
    pass


def address(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value) or int(value[2:], 16) == 0:
        raise ChainFailure("Invalid chain address")
    return value.lower()


def hex_bytes(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", value):
        raise ChainFailure("Malformed RPC byte string")
    return bytes.fromhex(value[2:])


def resource_id(value: str) -> bytes:
    """Application IDs are 16-byte hex; left-pad to the contract's bytes32."""
    if not re.fullmatch(r"[0-9a-fA-F]{32}(?:[0-9a-fA-F]{32})?", value):
        raise ChainFailure("Invalid application/contract identifier")
    return bytes.fromhex(value).rjust(32, b"\x00")


def artifact(version: int = 2) -> dict:
    name = "escrow_v1.json" if version == 1 else "escrow.json"
    return json.loads(files("framebounty").joinpath("contract_abi/" + name).read_text(encoding="utf-8"))


def call_data(signature: str, types: list[str], arguments: list) -> str:
    return "0x" + (keccak(text=signature)[:4] + encode(types, arguments)).hex()


def escrow_call(name: str, arguments: list) -> str:
    matches = [item for item in artifact()["abi"] if item.get("type") == "function" and item["name"] == name]
    if len(matches) != 1:
        raise ChainFailure("Unknown or ambiguous escrow operation")
    types = [item["type"] for item in matches[0]["inputs"]]
    return call_data(name + "(" + ",".join(types) + ")", types, arguments)


def expected_runtime(token: str, version: int = 2) -> bytes:
    compiled = artifact(version)
    result = bytearray(hex_bytes(compiled["runtime_bytecode"]))
    replacement = bytes.fromhex(address(token)[2:]).rjust(32, b"\x00")
    for references in compiled["immutable_references"].values():
        for item in references:
            if item["length"] != 32:
                raise ChainFailure("Unsupported canonical immutable layout")
            result[item["start"]:item["start"] + 32] = replacement
    return bytes(result)


@dataclass(frozen=True)
class ChainConfig:
    rpc_url: str
    chain_id: int
    escrow: str
    token: str
    allow_local: bool = False

    def __post_init__(self):
        address(self.escrow)
        address(self.token)
        parsed = urlparse(self.rpc_url)
        local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if self.chain_id == 31337:
            if not self.allow_local or not local or parsed.scheme not in {"http", "https"}:
                raise ChainFailure("Local chain access requires an explicit loopback test configuration")
        elif self.chain_id == CHAIN_ID:
            if parsed.scheme != "https" or self.token.lower() != USDC_ADDRESS:
                raise ChainFailure("Arc testnet requires HTTPS and the canonical USDC interface")
        else:
            raise ChainFailure("Only Arc testnet or the explicit local test chain is supported")
        if parsed.username or parsed.password:
            raise ChainFailure("Do not embed credentials in RPC URLs")


class ChainRPC:
    def __init__(self, config: ChainConfig, transport: httpx.BaseTransport | None = None):
        self.config, self.transport = config, transport
        self._client = httpx.Client(timeout=httpx.Timeout(15, connect=5), transport=transport)

    def close(self):
        self._client.close()

    def rpc(self, method: str, params: list):
        try:
            with self._client.stream("POST", self.config.rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}) as response:
                response.raise_for_status()
                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload) > 2 * 1024 * 1024:
                        raise ChainFailure("RPC response exceeded its limit")
            result = json.loads(payload)
            if result.get("id") != 1 or "error" in result or "result" not in result:
                raise ChainFailure("RPC returned an error or mismatched response")
            return result["result"]
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            # Provider URLs can contain API tokens; do not chain them into logs.
            raise ChainFailure("Chain provider unavailable or returned malformed data") from None

    def check_network(self):
        try:
            actual = int(self.rpc("eth_chainId", []), 16)
        except (ValueError, TypeError):
            raise ChainFailure("Malformed network identity response") from None
        if actual != self.config.chain_id:
            raise ChainFailure("RPC chain ID does not match the intended network")

    def check_contract(self):
        self.check_network()
        decimals = self.rpc("eth_call", [{"to": self.config.token, "data": call_data("decimals()", [], [])}, "latest"])
        try:
            decimals = int(decimals, 16)
        except (ValueError, TypeError):
            raise ChainFailure("Malformed token decimals response") from None
        if decimals != 6:
            raise ChainFailure("Unsupported token decimals")
        actual = hex_bytes(self.rpc("eth_getCode", [self.config.escrow, "latest"]))
        if actual == expected_runtime(self.config.token):
            self.contract_version = 2
        elif actual == expected_runtime(self.config.token, 1):
            self.contract_version = 1
        else:
            raise ChainFailure("Escrow bytecode does not match the canonical compiled contract")

    def read_escrow(self, name: str, arguments: list) -> tuple:
        definitions = [item for item in artifact()["abi"] if item.get("type") == "function" and item["name"] == name
                       and item.get("stateMutability") in {"view", "pure"}]
        if len(definitions) != 1:
            raise ChainFailure("Unknown escrow read operation")
        self.check_contract()
        raw = self.rpc("eth_call", [{"to": self.config.escrow, "data": escrow_call(name, arguments)}, "latest"])
        try:
            return decode([field["type"] for field in definitions[0]["outputs"]], hex_bytes(raw))
        except (DecodingError, TypeError, ValueError):
            raise ChainFailure("Provider returned malformed escrow state") from None

    def build_unsigned(self, sender: str, destination: str, data: str, nonce: int) -> dict:
        self.check_contract()
        if address(destination) not in {self.config.escrow.lower(), self.config.token.lower()}:
            raise ChainFailure("Transaction destination is outside the escrow/token boundary")
        hex_bytes(data)
        estimate = int(self.rpc("eth_estimateGas", [{"from": address(sender), "to": address(destination), "data": data, "value": "0x0"}, "pending"]), 16)
        gas = estimate * 12 // 10 + 10000
        if not 21000 <= gas <= 2_000_000:
            raise ChainFailure("Gas estimate is outside the allowed transaction limit")
        price = int(self.rpc("eth_gasPrice", []), 16)
        if not 0 < price <= 10**15:
            raise ChainFailure("Native gas quote is outside the configured safety bound")
        return {"chainId": self.config.chain_id, "nonce": nonce, "to": to_checksum_address(destination),
                "data": data, "value": 0, "gas": gas, "type": 2,
                "maxFeePerGas": max(price * 2, 20_000_000_000 if self.config.chain_id == CHAIN_ID else 1),
                "maxPriorityFeePerGas": min(price // 10, 1_000_000_000)}

    def verify_transaction(self, tx_hash: str, sender: str, destination: str, data: str, nonce: int | None = None) -> dict | None:
        self.check_contract()
        if len(hex_bytes(tx_hash)) != 32:
            raise InvalidReceipt("Invalid transaction hash")
        transaction = self.rpc("eth_getTransactionByHash", [tx_hash])
        if transaction is None:
            return None
        if not isinstance(transaction, dict):
            raise ChainFailure("Malformed transaction response")
        try:
            mismatch = (transaction["hash"].lower() != tx_hash.lower()
            or address(transaction["from"]) != address(sender) or address(transaction["to"]) != address(destination)
            or transaction.get("input", transaction.get("data", "")).lower() != data.lower()
            or int(transaction.get("value", "0x0"), 16) != 0
            or int(transaction.get("chainId", hex(self.config.chain_id)), 16) != self.config.chain_id
            or (nonce is not None and int(transaction["nonce"], 16) != nonce))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ChainFailure("Malformed transaction response") from None
        if mismatch:
            raise InvalidReceipt("Transaction does not match the committed action")
        return transaction

    def verified_receipt(self, tx_hash: str, sender: str, destination: str, data: str, event: dict, nonce: int | None = None) -> dict | None:
        try:
            return self._verified_receipt(tx_hash, sender, destination, data, event, nonce)
        except (KeyError, TypeError, ValueError, AttributeError, DecodingError):
            raise ChainFailure("Provider returned malformed receipt/event data") from None

    def _verified_receipt(self, tx_hash: str, sender: str, destination: str, data: str, event: dict, nonce: int | None = None) -> dict | None:
        if self.verify_transaction(tx_hash, sender, destination, data, nonce) is None:
            return None
        receipt = self.rpc("eth_getTransactionReceipt", [tx_hash])
        if receipt is None:
            return None
        if receipt["transactionHash"].lower() != tx_hash.lower():
            raise InvalidReceipt("Receipt hash mismatch")
        status = int(receipt["status"], 16)
        if status not in {0, 1}:
            raise ChainFailure("Malformed receipt status")
        block = self.rpc("eth_getBlockByNumber", [receipt["blockNumber"], False])
        if block is None or block["hash"].lower() != receipt["blockHash"].lower():
            return None  # A noncanonical or unavailable block is not settlement.
        if status == 0:
            return {"status": "reverted", "receipt": receipt}
        matched = self.match_event(receipt, event, int(block["timestamp"], 16))
        return {"status": "confirmed", "receipt": receipt, "event": matched}

    def match_event(self, receipt: dict, expected: dict, block_time: int) -> dict:
        definitions = [item for item in artifact()["abi"] if item.get("type") == "event" and item["name"] == expected["name"]]
        emitter = self.config.escrow
        if expected["name"] == "Approval":
            emitter = self.config.token
            definitions = [{"name": "Approval", "inputs": [
                {"name": "owner", "type": "address", "indexed": True},
                {"name": "spender", "type": "address", "indexed": True},
                {"name": "value", "type": "uint256", "indexed": False}]}]
        if len(definitions) != 1:
            raise InvalidReceipt("Unknown expected escrow event")
        definition = definitions[0]
        required = {field["name"] for field in definition["inputs"]}
        supplied = set(expected["fields"])
        if "deadline_seconds" in expected:
            supplied.add("reviewDeadline")
        if supplied != required:
            raise InvalidReceipt("Expected event must bind every field")
        topic = "0x" + keccak(text=definition["name"] + "(" + ",".join(field["type"] for field in definition["inputs"]) + ")").hex()
        for log in receipt.get("logs", []):
            if log.get("removed") or log.get("address", "").lower() != emitter.lower() or not log.get("topics") or log["topics"][0].lower() != topic:
                continue
            indexed = [field for field in definition["inputs"] if field["indexed"]]
            remaining = [field for field in definition["inputs"] if not field["indexed"]]
            if len(log["topics"]) != len(indexed) + 1:
                continue
            values = [decode([field["type"]], hex_bytes(raw))[0] for field, raw in zip(indexed, log["topics"][1:])]
            values += list(decode([field["type"] for field in remaining], hex_bytes(log["data"])))
            fields = indexed + remaining
            decoded = {field["name"]: ("0x" + value.hex() if isinstance(value, bytes) else value.lower() if isinstance(value, str) else value)
                       for field, value in zip(fields, values)}
            if not all(decoded.get(key) == value for key, value in expected["fields"].items()):
                continue
            if "deadline_seconds" in expected and decoded.get("reviewDeadline") != block_time + expected["deadline_seconds"]:
                continue
            return decoded
        raise InvalidReceipt("Successful receipt lacks the exact committed escrow event")
