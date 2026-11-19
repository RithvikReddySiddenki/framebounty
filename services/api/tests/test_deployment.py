"""Actual local-chain deployment and signed-byte restart/tamper checks."""
from copy import deepcopy
import json

import pytest

from framebounty.chain_rpc import ChainFailure
from framebounty.deployment import broadcast, prepare, reconcile, validate
from framebounty.transactions import LocalUnlockedSigner
from test_chain import chain
from test_postgres import pg


def test_default_escrow_replacement_requires_exact_explicit_previous_address(tmp_path):
    from pathlib import Path
    import runpy
    configure = runpy.run_path(str(Path(__file__).resolve().parents[3] / "scripts/deploy_arc.py"))["configure"]
    old, new = "0x" + "1" * 40, "0x" + "2" * 40
    original = f"ARC_ESCROW_ADDRESS={old}\nALLOW_CHAIN_TRANSACTIONS=false\nGEMINI_API_KEY=TEST-ONLY\n"
    target = tmp_path / ".env"
    target.write_text(original, encoding="utf-8")
    with pytest.raises(ChainFailure): configure(tmp_path, new)
    assert target.read_text(encoding="utf-8") == original
    with pytest.raises(ChainFailure): configure(tmp_path, new, "0x" + "3" * 40)
    configure(tmp_path, new, old)
    updated = target.read_text(encoding="utf-8")
    assert f"ARC_ESCROW_ADDRESS={new}" in updated
    assert "ALLOW_CHAIN_TRANSACTIONS=false" in updated and "GEMINI_API_KEY=TEST-ONLY" in updated


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
