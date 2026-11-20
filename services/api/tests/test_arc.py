import httpx
import pytest

from framebounty.arc import ChainUnavailable, preflight


def transport(results):
    def handler(request):
        import json
        body = json.loads(request.content)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": results[body["id"] - 1]})
    return httpx.MockTransport(handler)


def test_native_gas_units_stay_separate_from_token_units():
    with httpx.Client(transport=transport([hex(5042002), hex(6), hex(25_000_000_000)])) as client:
        result = preflight(client)
    assert result.erc20_decimals == 6 and result.native_decimals == 18
    assert result.gas_price_native_atomic_per_gas == "25000000000"


def test_mainnet_preflight_does_not_accept_testnet_as_real_usdc():
    with httpx.Client(transport=transport([hex(5042), hex(6), hex(25_000_000_000)])) as client:
        assert preflight(client, "https://rpc.mainnet.arc.io", 5042).chain_id == 5042
    with httpx.Client(transport=transport([hex(5042002)])) as client:
        with pytest.raises(ChainUnavailable): preflight(client, "https://rpc.mainnet.arc.io", 5042)


@pytest.mark.parametrize("results", [["0x1"], [hex(5042002), "0x12"], [hex(5042002), "malformed"]])
def test_wrong_chain_or_decimals_fail_before_transfers(results):
    with httpx.Client(transport=transport(results)) as client:
        with pytest.raises(ChainUnavailable):
            preflight(client)


def test_rpc_errors_are_not_confirmed_state():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        with pytest.raises(ChainUnavailable):
            preflight(client)
