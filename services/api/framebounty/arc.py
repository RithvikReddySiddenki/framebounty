"""Read-only Arc testnet preflight. No signing, transfers or funding recognition.

Constants were checked against official Arc docs and the live RPC. Native gas
price remains 18-decimal native units per gas; token balances use 6 decimals.
"""
from dataclasses import dataclass

import httpx

CHAIN_ID = 5042002
RPC_URL = "https://rpc.testnet.arc.io"
USDC_ADDRESS = "0x3600000000000000000000000000000000000000"
EXPLORER_URL = "https://explorer.testnet.arc.io"


class ChainUnavailable(RuntimeError):
    pass


def rpc(client: httpx.Client, url: str, method: str, params: list, request_id: int):
    try:
        response = client.post(url, json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        response.raise_for_status()
        result = response.json()
        if result.get("id") != request_id or "error" in result or "result" not in result:
            raise ChainUnavailable("Invalid or failed Arc RPC response")
        return result["result"]
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        raise ChainUnavailable("Arc RPC unavailable; no transaction state may be inferred") from exc


@dataclass(frozen=True)
class NetworkSnapshot:
    chain_id: int
    usdc_address: str
    erc20_decimals: int
    native_decimals: int
    gas_price_native_atomic_per_gas: str


def preflight(client: httpx.Client, url: str = RPC_URL) -> NetworkSnapshot:
    try:
        chain = int(rpc(client, url, "eth_chainId", [], 1), 16)
        if chain != CHAIN_ID:
            raise ChainUnavailable("Wrong chain: Arc testnet is required")
        decimals = int(rpc(client, url, "eth_call", [{"to": USDC_ADDRESS, "data": "0x313ce567"}, "latest"], 2), 16)
        if decimals != 6:
            raise ChainUnavailable("Unexpected USDC token decimals")
        gas = int(rpc(client, url, "eth_gasPrice", [], 3), 16)
        if gas <= 0:
            raise ChainUnavailable("Invalid native gas price")
        return NetworkSnapshot(chain, USDC_ADDRESS, decimals, 18, str(gas))
    except (TypeError, ValueError) as exc:
        raise ChainUnavailable("Malformed chain preflight data") from exc
