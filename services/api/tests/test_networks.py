import pytest
from framebounty.networks import active_network, chain_enabled, MAINNET, TESTNET


def test_default_is_testnet_not_real_money(monkeypatch):
    monkeypatch.delenv("ARC_CHAIN_ID", raising=False)
    monkeypatch.setenv("APP_MODE", "fixture")
    assert active_network() == TESTNET and not chain_enabled()


def test_mainnet_requires_explicit_matching_mode_and_both_transaction_flags(monkeypatch):
    monkeypatch.setenv("ARC_CHAIN_ID", "5042")
    monkeypatch.setenv("APP_MODE", "testnet")
    monkeypatch.setenv("ALLOW_MAINNET_TRANSACTIONS", "true")
    with pytest.raises(ValueError): active_network()
    monkeypatch.setenv("APP_MODE", "mainnet")
    monkeypatch.setenv("ALLOW_MAINNET_TRANSACTIONS", "false")
    with pytest.raises(ValueError): active_network()
    monkeypatch.setenv("ALLOW_MAINNET_TRANSACTIONS", "true")
    monkeypatch.setenv("ALLOW_CHAIN_TRANSACTIONS", "false")
    assert active_network() == MAINNET and not chain_enabled()
    monkeypatch.setenv("ALLOW_CHAIN_TRANSACTIONS", "true")
    assert chain_enabled()


def test_mainnet_never_silently_falls_back_to_testnet(monkeypatch):
    monkeypatch.setenv("APP_MODE", "mainnet")
    monkeypatch.setenv("ARC_CHAIN_ID", "5042002")
    with pytest.raises(ValueError): active_network()
