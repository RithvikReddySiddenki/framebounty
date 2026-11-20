import pytest
from framebounty import mainnet_budget as budget


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(budget, "path", lambda: tmp_path / "budget.json")
    monkeypatch.setenv("MAINNET_SPEND_LIMIT_USDC", "1.000000")
    monkeypatch.setenv("APP_MODE", "mainnet")
    monkeypatch.setenv("ARC_CHAIN_ID", "5042")
    monkeypatch.setenv("ALLOW_MAINNET_TRANSACTIONS", "true")


def transaction(nonce, amount):
    return {"chainId": 5042, "nonce": nonce, "gas": amount, "maxFeePerGas": 1, "value": 0}


def test_unknown_outcomes_keep_maximum_reserved_across_restarts(ledger):
    budget.reserve("wallet", transaction(1, 8 * 10**17))
    budget.reserve("wallet", transaction(1, 8 * 10**17))
    with pytest.raises(budget.BudgetFailure): budget.reserve("wallet", transaction(2, 3 * 10**17))
    budget.settle("wallet", 1, {"gasUsed": hex(2 * 10**17), "effectiveGasPrice": "0x1"})
    budget.reserve("wallet", transaction(2, 8 * 10**17))
    with pytest.raises(budget.BudgetFailure): budget.reserve("wallet", transaction(3, 1))


def test_cannot_raise_cap_change_reserved_nonce_or_move_principal(ledger, monkeypatch):
    budget.reserve("wallet", transaction(1, 10))
    with pytest.raises(budget.BudgetFailure): budget.reserve("wallet", transaction(1, 11))
    with pytest.raises(budget.BudgetFailure): budget.reserve("wallet", {**transaction(1, 10), "data": "0x1234"})
    with pytest.raises(budget.BudgetFailure): budget.reserve("wallet", {**transaction(2, 10), "value": 1})
    monkeypatch.setenv("MAINNET_SPEND_LIMIT_USDC", "2")
    with pytest.raises(budget.BudgetFailure): budget.reserve("wallet", transaction(2, 1))


def test_corrupt_budget_never_resets_to_fresh_allowance(ledger):
    budget.path().write_text("invalid")
    with pytest.raises(budget.BudgetFailure): budget.reserve("wallet", transaction(1, 1))
