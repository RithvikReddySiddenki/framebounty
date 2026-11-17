from fastapi.testclient import TestClient
from framebounty.main import app


def test_health_does_not_claim_payments():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["payments_enabled"] is False


def test_invalid_plan_is_rejected_at_boundary():
    assert TestClient(app).post("/plans/validate", json={"budget_atomic": -1}).status_code == 422


def test_no_duplicate_route_can_shadow_authorization_or_response_policy():
    from fastapi.routing import APIRoute
    seen = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                key = (method, route.path)
                assert key not in seen, f"Shadowed route: {key}"
                seen.add(key)


def test_real_funding_is_disabled_in_fixture_mode(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from framebounty.funding_routes import funding_rpc
    monkeypatch.setenv("APP_MODE", "fixture")
    monkeypatch.setenv("ALLOW_CHAIN_TRANSACTIONS", "true")
    with pytest.raises(HTTPException) as denied:
        next(funding_rpc())
    assert denied.value.status_code == 503


def test_funding_hash_requires_its_intention_identity():
    import pytest
    from pydantic import ValidationError
    from framebounty.funding_routes import FundingRequest
    with pytest.raises(ValidationError):
        FundingRequest(plan_hash="a" * 64, confirmed=True, tx_hash="0x" + "b" * 64)
