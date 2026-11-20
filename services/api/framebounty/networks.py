"""Explicit Arc environments. Real USDC must never be a testnet fallback.

Token rewards are six-decimal atoms; native gas is 18-decimal atoms. The active
database must be separate for mainnet. Existing funded jobs retain network pins.
"""
import os
from dataclasses import dataclass

USDC = "0x3600000000000000000000000000000000000000"


@dataclass(frozen=True)
class Network:
    chain_id: int
    name: str
    rpc_url: str
    explorer: str
    circle_chain: str
    real_money: bool


TESTNET = Network(5042002, "Arc Testnet", "https://rpc.testnet.arc.io", "https://explorer.testnet.arc.io", "ARC-TESTNET", False)
MAINNET = Network(5042, "Arc", "https://rpc.mainnet.arc.io", "https://explorer.arc.io", "ARC", True)


def active_network() -> Network:
    raw = os.getenv("ARC_CHAIN_ID", str(TESTNET.chain_id))
    if raw == str(TESTNET.chain_id):
        if os.getenv("APP_MODE") == "mainnet": raise ValueError("Mainnet mode cannot use a testnet chain")
        return TESTNET
    if raw == str(MAINNET.chain_id):
        if os.getenv("APP_MODE") != "mainnet" or os.getenv("ALLOW_MAINNET_TRANSACTIONS") != "true":
            raise ValueError("Real USDC requires explicit mainnet mode and consent")
        return MAINNET
    raise ValueError("Only Arc mainnet and testnet are supported")


def chain_enabled() -> bool:
    try:
        network = active_network()
    except ValueError:
        return False
    return (os.getenv("ALLOW_CHAIN_TRANSACTIONS") == "true"
        and os.getenv("APP_MODE") == ("mainnet" if network.real_money else "testnet"))
