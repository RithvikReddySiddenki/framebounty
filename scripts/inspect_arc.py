"""Explicit live, read-only preflight; not the funded Arc smoke test."""
import json
import argparse
from dataclasses import asdict

import httpx

from framebounty.arc import preflight
from framebounty.networks import MAINNET, TESTNET

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read-only Arc network/token/fee check; never signs or sends")
    parser.add_argument("--network", choices=["testnet", "mainnet"], default="testnet")
    network = MAINNET if parser.parse_args().network == "mainnet" else TESTNET
    with httpx.Client(timeout=15) as client:
        print(json.dumps(asdict(preflight(client, network.rpc_url, network.chain_id)), indent=2))
