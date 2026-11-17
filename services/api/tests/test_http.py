from fastapi.testclient import TestClient
from framebounty.main import app


def test_health_does_not_claim_payments():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["payments_enabled"] is False


def test_invalid_plan_is_rejected_at_boundary():
    assert TestClient(app).post("/plans/validate", json={"budget_atomic": -1}).status_code == 422
