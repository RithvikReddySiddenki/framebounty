"""Actual local-chain deployment and signed-byte restart/tamper checks."""
from copy import deepcopy
import json

import pytest

from framebounty.chain_rpc import ChainFailure
from framebounty.deployment import broadcast, prepare, reconcile, validate
from framebounty.transactions import LocalUnlockedSigner
from test_chain import chain
from test_postgres import pg


def test_canonical_deployment_reconciles_after_lost_response(chain, tmp_path):
    rpc, accounts = chain
    record = prepare(rpc, LocalUnlockedSigner(rpc, accounts[0]))
    saved = tmp_path / "private-deployment.json"
    saved.write_text(json.dumps(record))
    original = record["tx_hash"], record["nonce"], record["raw_transaction"]
    broadcast(rpc, record)
    recovered = json.loads(saved.read_text())
    broadcast(rpc, recovered)
    assert reconcile(rpc, recovered) and recovered["state"] == "confirmed"
    assert (recovered["tx_hash"], recovered["nonce"], recovered["raw_transaction"]) == original
    assert reconcile(rpc, recovered)
    assert int(recovered["gas_cost_native_atomic"]) > 0


def test_deployment_refuses_mutated_signed_terms(chain):
    rpc, accounts = chain
    record = prepare(rpc, LocalUnlockedSigner(rpc, accounts[0]))
    changed = deepcopy(record)
    changed["unsigned"]["value"] = 1
    with pytest.raises(ChainFailure):
        validate(rpc, changed)
    changed = deepcopy(record)
    changed["address"] = accounts[2]
    with pytest.raises(ChainFailure):
        validate(rpc, changed)
