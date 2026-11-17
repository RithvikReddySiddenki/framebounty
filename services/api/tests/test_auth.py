from datetime import UTC, datetime, timedelta

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from framebounty.auth import challenge_message, verify_signature, wallet_address


def test_signature_binds_wallet_origin_chain_nonce_and_expiry(monkeypatch):
    account, other = Account.create(), Account.create()
    expires = datetime.now(UTC) + timedelta(minutes=5)
    monkeypatch.setenv("AUTH_ORIGIN", "https://framebounty.example")
    monkeypatch.setenv("ARC_CHAIN_ID", "5042002")
    message = challenge_message(account.address, "nonce-a", expires)
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    assert verify_signature(message, signature, account.address)
    assert not verify_signature(message, signature, other.address)
    for value in [message.replace("nonce-a", "nonce-b"), message.replace("5042002", "1"), message.replace("framebounty.example", "attacker.example"), message.replace(expires.isoformat(), "never")]:
        assert not verify_signature(value, signature, account.address)
    assert not verify_signature(message, "malformed", account.address)


@pytest.mark.parametrize("wallet", ["0x" + "0" * 40, "0x123", "0x" + "g" * 40])
def test_invalid_wallet_rejected(wallet):
    with pytest.raises(ValueError):
        wallet_address(wallet)
