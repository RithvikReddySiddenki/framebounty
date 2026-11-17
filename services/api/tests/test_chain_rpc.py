"""Fail-closed provider/configuration boundaries, alongside real-EVM tests."""
import httpx
import pytest

from framebounty.chain_rpc import ChainConfig, ChainFailure, ChainRPC, InvalidReceipt

ESCROW = "0x" + "1" * 40
TOKEN = "0x" + "2" * 40


@pytest.mark.parametrize("chain,url,local,token", [
    (1, "https://example.invalid", False, TOKEN),
    (31337, "http://127.0.0.1:1", False, TOKEN),
    (31337, "http://example.invalid", True, TOKEN),
    (5042002, "http://example.invalid", False, "0x3600000000000000000000000000000000000000"),
    (5042002, "https://example.invalid", False, TOKEN),
])
def test_config_refuses_mainnet_remote_unlocked_and_wrong_token(chain, url, local, token):
    with pytest.raises(ChainFailure):
        ChainConfig(url, chain, ESCROW, token, allow_local=local)


@pytest.mark.parametrize("result", [None, {}, "bad", "0x1"])
def test_malformed_or_wrong_network_never_passes_preflight(result):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result}))
    rpc = ChainRPC(ChainConfig("http://127.0.0.1:1", 31337, ESCROW, TOKEN, allow_local=True), transport)
    try:
        with pytest.raises(ChainFailure):
            rpc.check_network()
    finally:
        rpc.close()


def test_incomplete_event_expectation_cannot_confirm_a_receipt():
    rpc = ChainRPC(ChainConfig("http://127.0.0.1:1", 31337, ESCROW, TOKEN, allow_local=True))
    try:
        with pytest.raises(InvalidReceipt, match="every field"):
            rpc.match_event({"logs": []}, {"name": "Paid", "fields": {"reward": 1000000}}, 1)
    finally:
        rpc.close()
