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
